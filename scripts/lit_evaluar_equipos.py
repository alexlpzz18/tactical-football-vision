#!/usr/bin/env python
"""Evalúa etiquetas de equipo por detección (método 5 de docs/plan_literatura.md) contra el GT.

Compara, en IGUALDAD de condiciones, el histograma HS de producción y las etiquetas de
`lit_siglip_equipos.py`:
- **por recorte**: cada detección casada con una persona del GT (1-a-1, ≤ 2 m, frames del GT);
- **con voto de 1,5 s**: la etiqueta de cada detección es la mayoría de las de SU identidad del
  seguimiento a ± 0,75 s (el voto por ventana de producción, aplicado igual a los dos métodos).

El clasificador HS y las identidades son los de una pasada de producción con los configs de `main`
(se capturan al correrla). Los dos nombres de grupo se prueban y vale el mejor (son arbitrarios).

Uso:
    python scripts/lit_evaluar_equipos.py --pata villa \\
        --etiquetas outputs/literatura/siglip/villa.npz --configs-de /ruta/worktree_main
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))


def capturar(pata: str, configs_de: Path | None):
    """Corre producción. Da (clasificador, identidades [(f, j) del caché filtrado], caché)."""
    import banco_mision as bm

    import src.team_classification.color_classifier as cc
    import src.tracking.perfiles as perfiles

    cls = next(
        v
        for v in vars(cc).values()
        if isinstance(v, type) and hasattr(v, "fit_features")
    )
    cap = {}
    o_fit, o_correr, o_post = (
        cls.fit_features,
        perfiles.correr_perfil,
        perfiles.postprocesar,
    )

    def fit(self, f):
        r = o_fit(self, f)
        cap["clf"] = self
        return r

    def correr(cache, *a, **k):
        cap["cache"] = {e["frame_idx"]: e["dets"] for e in cache}
        return o_correr(cache, *a, **k)

    def post(identidades, *a, **k):
        cap["ids"] = [
            sorted(
                (float(t), (int(f), int(j)))
                for tr in i
                for t, (f, j) in zip(tr.ts, tr.det_idxs)
            )
            for i in identidades
        ]
        return o_post(identidades, *a, **k)

    cls.fit_features, perfiles.correr_perfil, perfiles.postprocesar = fit, correr, post
    bm.BASE_CONFIGS = configs_de
    bm.SALIDA = R / "outputs/literatura/eval_equipos"
    try:
        bm.correr(pata, "captura", {}, {})
    finally:
        cls.fit_features, perfiles.correr_perfil, perfiles.postprocesar = (
            o_fit,
            o_correr,
            o_post,
        )
    return cap["clf"], cap["ids"], cap["cache"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pata", required=True, choices=["benja", "villa"])
    ap.add_argument("--etiquetas", type=Path, required=True)
    ap.add_argument("--configs-de", type=Path, default=None)
    ap.add_argument("--salida", type=Path, default=None)
    a = ap.parse_args()
    import logging
    import pickle

    from scipy.optimize import linear_sum_assignment

    import banco_mision as bm
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    logging.basicConfig(level=logging.ERROR)
    d = bm.PATAS[a.pata]
    clf, ids, cache_f = capturar(a.pata, a.configs_de)
    import yaml

    cfg = yaml.safe_load(open(R / d["config"]))
    crudo = pickle.load(open(R / d.get("cache", cfg["rutas"]["cache"]), "rb"))["cache"]
    colores = pickle.load(
        open(R / d.get("cache_colores", cfg["rutas"]["cache_colores"]), "rb")
    )
    crudo = {e["frame_idx"]: e["dets"] for e in crudo}
    z = np.load(a.etiquetas, allow_pickle=True)
    siglip = {(int(f), int(j)): int(e) for (f, j), e in zip(z["claves"], z["etiqueta"])}

    # (frame, j filtrado) → (frame, j crudo), por igualdad de caja
    a_crudo = {}
    for f, dets in cache_f.items():
        for j, det in enumerate(dets):
            for k, c in enumerate(crudo.get(f, [])):
                if (
                    np.abs(np.array(c[2:6], float) - np.array(det[2:6], float)).sum()
                    < 1e-3
                ):
                    a_crudo[(f, j)] = (f, k)
                    break
    etq = {
        "hs": {
            clave: clf.predict_color(colores[clave], solo_equipos=True)
            for clave in set(a_crudo.values())
            if clave in colores
        },
        "siglip": {clave: ("A" if siglip[clave] == 0 else "B") for clave in siglip},
    }
    # voto de 1,5 s a lo largo de la identidad, para cada método
    votado = {m: {} for m in etq}
    for obs in ids:
        t = np.array([o[0] for o in obs])
        claves = [a_crudo.get(o[1]) for o in obs]
        for m, e in etq.items():
            vals = np.array([e.get(c, "") for c in claves])
            for n, c in enumerate(claves):
                if c is None:
                    continue
                cerca = vals[(np.abs(t - t[n]) <= 0.75) & (vals != "")]
                if len(cerca):
                    votado[m][c] = (
                        "A" if (cerca == "A").sum() >= (cerca == "B").sum() else "B"
                    )
    gt_m = gt_a_por_frame(
        parsear_cvat(R / d["gt"]), np.load(R / d["homografia"]), d["offset"], 15
    )
    base = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}
    pares = []  # (equipo GT, clave cruda)
    for f, obs in gt_m.items():
        gente = [o for o in obs if base.get(str(o.team)) in ("A", "B")]
        dets = crudo.get(f, [])
        if not gente or not dets:
            continue
        gt = np.array([o.pos for o in gente], float)
        xy = np.array([dd[:2] for dd in dets], float)
        dist = np.linalg.norm(gt[:, None] - xy[None], axis=2)
        i, j = linear_sum_assignment(np.where(dist <= 2.0, dist, 1e6))
        pares += [
            (base[str(gente[p].team)], (f, int(q)))
            for p, q in zip(i, j)
            if dist[p, q] <= 2.0
        ]

    def error(etiquetas: dict) -> dict:
        ok = [(g, etiquetas.get(c)) for g, c in pares if etiquetas.get(c) in ("A", "B")]
        if not ok:
            return {"n": 0}
        directo = np.mean([g == e for g, e in ok])
        mejor = max(directo, 1 - directo)
        return {"n": len(ok), "error_pct": round(100 * (1 - mejor), 2)}

    res = {
        "pata": a.pata,
        "casadas_con_gt": len(pares),
        **{f"{m}_por_recorte": error(etq[m]) for m in etq},
        **{f"{m}_voto_1_5s": error(votado[m]) for m in votado},
    }
    print(json.dumps(res, ensure_ascii=False))
    if a.salida:
        a.salida.parent.mkdir(parents=True, exist_ok=True)
        a.salida.write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
