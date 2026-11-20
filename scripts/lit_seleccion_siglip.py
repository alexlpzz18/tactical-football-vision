#!/usr/bin/env python
"""Premisa del intento 2 de SigLIP: ¿la consistencia física elige bien entre HS y SigLIP?

docs/plan_siglip_por_partido.md.

Para una pata, con las identidades de una pasada de producción (configs de `main`):
- ventanas de 1,5 s de tramos AISLADOS de cada identidad y parejas separadas ≤ 6 s con un cambio de
  profundidad ≥ 6 m (la misma construcción que `seleccion_feature.py`);
- etiqueta de cada ventana con HS (K-means de 2 sobre las medias HS) y con SigLIP (mayoría de las
  etiquetas de UMAP + K-means de sus detecciones);
- kappa de Cohen de las parejas para cada método, y en 5 submuestras del 50 % de las identidades.

Uso:
    python scripts/lit_seleccion_siglip.py --pata villa \\
        --siglip outputs/literatura/siglip/villa.npz \\
        --configs-de /ruta/worktree_main
"""

import argparse
import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

EJE = {"benja": 0, "villa": 1, "alevinb": 1}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pata", required=True, choices=list(EJE))
    ap.add_argument(
        "--siglip", type=Path, required=True, help=".npz con claves y etiqueta"
    )
    ap.add_argument("--configs-de", type=Path, default=None)
    ap.add_argument("--salida", type=Path, default=None)
    a = ap.parse_args()
    import logging

    import yaml
    from sklearn.cluster import KMeans

    import banco_mision as bm
    from src.team_classification.color_classifier import (
        ParametrosClasificadorColor,
        _feature_trabajo,
    )
    from src.team_classification.seleccion_feature import (
        _kappa,
        parejas,
        ventanas_aisladas,
    )

    logging.basicConfig(level=logging.ERROR)
    bm.BASE_CONFIGS = a.configs_de
    bm.SALIDA = R / "outputs/literatura/seleccion_siglip"
    d = bm.PATAS[a.pata]
    _csv, ids_f, cache_f = bm.correr_capturando(a.pata, "captura", {}, {})
    cfg = yaml.safe_load(open(R / d["config"]))
    crudo_l = pickle.load(open(R / d.get("cache", cfg["rutas"]["cache"]), "rb"))[
        "cache"
    ]
    colores = pickle.load(
        open(R / d.get("cache_colores", cfg["rutas"]["cache_colores"]), "rb")
    )
    crudo = {e["frame_idx"]: e for e in crudo_l}
    tiempo = {e["frame_idx"]: e["t"] for e in crudo_l}
    # (frame, j filtrado) → (frame, j crudo), por igualdad de caja
    a_crudo = {}
    for f, dets in cache_f.items():
        cajas = np.array([c[2:6] for c in crudo[f]["dets"]], float).reshape(-1, 4)
        for j, det in enumerate(dets):
            k = int(np.argmin(np.abs(cajas - np.array(det[2:6], float)).sum(axis=1)))
            if np.abs(cajas[k] - np.array(det[2:6], float)).sum() < 1e-3:
                a_crudo[(f, j)] = (f, k)
    identidades = []
    for ident in ids_f:
        pares = [a_crudo[p] for p in ident if p in a_crudo]
        if pares:
            identidades.append(
                [SimpleNamespace(ts=[tiempo[f] for f, _k in pares], det_idxs=pares)]
            )
    z = np.load(a.siglip, allow_pickle=True)
    sig = {(int(f), int(j)): int(e) for (f, j), e in zip(z["claves"], z["etiqueta"])}
    largo, ancho = d["campo"]
    eje = EJE[a.pata]

    def dentro(p):
        return -1 <= p[0] <= largo + 1 and -1 <= p[1] <= ancho + 1

    claves = [k for k in colores if k in sig]
    # una feature conjunta: [HS..., indicador SigLIP]; las ventanas promedian las dos a la vez
    conjunta = {
        k: np.append(np.asarray(colores[k], float), float(sig[k])) for k in claves
    }
    medias, aisladas = ventanas_aisladas(
        identidades,
        conjunta,
        crudo_l,
        dentro,
        lambda p: float(p[eje]),
        aislamiento_m=2.0,
        ventana_s=1.5,
        hueco_max_s=0.5,
    )
    pares = parejas(aisladas, max_dt_s=6.0, min_dprof_m=6.0)
    params = ParametrosClasificadorColor()
    X = np.array([_feature_trabajo(m[:-1], params) for m in medias])
    km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(X)
    et_hs = km.predict(
        np.array([_feature_trabajo(v[3][:-1], params) for v in aisladas])
    )
    et_sig = np.array([int(v[3][-1] >= 0.5) for v in aisladas])
    tramo = np.array([v[0] for v in aisladas])
    i, j = np.array(pares).T if pares else (np.array([], int), np.array([], int))

    def kappas(sel):
        ii, jj = i[sel], j[sel]
        return round(_kappa(et_hs[ii], et_hs[jj]), 3), round(
            _kappa(et_sig[ii], et_sig[jj]), 3
        )

    todo = kappas(np.ones(len(i), bool))
    subs = []
    tramos = np.unique(tramo)
    for s in range(5):
        keep = set(
            np.random.default_rng(s).choice(tramos, len(tramos) // 2, replace=False)
        )
        subs.append(kappas(np.array([tramo[x] in keep for x in i])))
    elige = (
        "siglip"
        if len(pares) >= 100 and todo[1] >= todo[0] + 0.05
        else ("hs" if len(pares) >= 100 else "hs (pocas parejas)")
    )
    res = {
        "pata": a.pata,
        "parejas": len(pares),
        "kappa_hs": todo[0],
        "kappa_siglip": todo[1],
        "submuestras_hs_siglip": subs,
        "elige": elige,
    }
    print(json.dumps(res, ensure_ascii=False))
    if a.salida:
        a.salida.parent.mkdir(parents=True, exist_ok=True)
        a.salida.write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
