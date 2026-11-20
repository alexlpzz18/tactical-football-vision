#!/usr/bin/env python
"""SigLIP frente a producción en el mini-GT a ojo del alevín B (docs/plan_siglip_por_partido.md).

El mini-GT (`outputs/gt_equipos_alevinb/detecciones_120.csv`, 79 jugadores B/V) está indexado por
caja y frame. Para cada fila se busca su detección y se compara:
- **producción**: la etiqueta de la fila del CSV de esa detección (la que da hoy la rama, con sus
  configs: dentro del campo, voto por ventana y selección automática de brillo);
- **SigLIP por recorte**: la etiqueta de UMAP + K-means de esa detección;
- **SigLIP con voto de 1,5 s**: la mayoría de SigLIP en su identidad a ± 0,75 s.
Los nombres de grupo se prueban en los dos sentidos.

Uso:
    python scripts/lit_evaluar_alevinb_siglip.py --siglip outputs/literatura/siglip/alevinb.npz
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

GT = R / "outputs/gt_equipos_alevinb/detecciones_120.csv"


def acierto(pares: list[tuple[str, str]]) -> float | None:
    """% de acierto con el mejor emparejamiento de nombres (B ↔ A/0 o B ↔ B/1)."""
    ok = [(o, s) for o, s in pares if s is not None and not pd.isna(s)]
    if not ok:
        return None
    nombres = sorted({s for _o, s in ok})
    mejor = 0.0
    for n_blanco in nombres:
        aciertos = np.mean([(o == "B") == (s == n_blanco) for o, s in ok])
        mejor = max(mejor, aciertos)
    return round(100 * mejor, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--siglip", type=Path, required=True)
    ap.add_argument("--salida", type=Path, default=None)
    a = ap.parse_args()
    import logging

    import yaml

    import banco_mision as bm

    logging.basicConfig(level=logging.ERROR)
    bm.SALIDA = R / "outputs/literatura/siglip_alevinb"
    csv, ids_f, cache_f = bm.correr_capturando("alevinb", "captura", {}, {})
    cfg = yaml.safe_load(open(R / bm.PATAS["alevinb"]["config"]))
    crudo_l = pickle.load(open(cfg["rutas"]["cache"], "rb"))["cache"]
    crudo = {e["frame_idx"]: e["dets"] for e in crudo_l}
    tiempo = {e["frame_idx"]: e["t"] for e in crudo_l}
    z = np.load(a.siglip, allow_pickle=True)
    sig = {(int(f), int(j)): int(e) for (f, j), e in zip(z["claves"], z["etiqueta"])}

    def a_crudo(f: int, caja) -> int | None:
        cajas = np.array([d[2:6] for d in crudo.get(f, [])], float).reshape(-1, 4)
        if not len(cajas):
            return None
        k = int(np.argmin(np.abs(cajas - np.asarray(caja, float)).sum(axis=1)))
        return k if np.abs(cajas[k] - np.asarray(caja, float)).sum() < 1e-3 else None

    # identidad (en claves crudas) de cada detección, y sus observaciones en el tiempo
    obs_de, id_de = [], {}
    for n, ident in enumerate(ids_f, start=1):
        claves = []
        for f, j in ident:
            k = a_crudo(f, cache_f[f][j][2:6])
            if k is not None:
                claves.append((tiempo[f], (f, k)))
                id_de[(f, k)] = (n, (f, j))
        obs_de.append(sorted(claves))
    filas = pd.read_csv(csv)
    etiqueta = {
        (int(r.frame), int(r.id_jugador)): r.etiqueta for r in filas.itertuples()
    }
    base = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}
    gt = pd.read_csv(GT)
    gt = gt[gt.equipo_a_ojo.isin(["B", "V"])]
    res_filas = []
    for r in gt.itertuples():
        k = a_crudo(int(r.frame), [r.x1, r.y1, r.x2, r.y2])
        clave = (int(r.frame), k) if k is not None else None
        prod = sig_rec = sig_voto = None
        if clave in id_de:
            n, _fj = id_de[clave]
            prod = base.get(str(etiqueta.get((int(r.frame), n))))
            t0 = tiempo[int(r.frame)]
            cerca = [
                sig[c] for t, c in obs_de[n - 1] if abs(t - t0) <= 0.75 and c in sig
            ]
            if cerca:
                sig_voto = str(int(np.mean(cerca) >= 0.5))
        if clave in sig:
            sig_rec = str(sig[clave])
        res_filas.append((r.equipo_a_ojo, r.franja, prod, sig_rec, sig_voto))
    df = pd.DataFrame(
        res_filas, columns=["ojo", "franja", "prod", "sig_rec", "sig_voto"]
    )
    res = {"jugadores": len(df)}
    for m in ("prod", "sig_rec", "sig_voto"):
        res[m] = {
            "acierto_pct": acierto(list(zip(df.ojo, df[m]))),
            "sin_etiqueta": int(df[m].isna().sum()),
            "por_franja": {
                fr: acierto(list(zip(g.ojo, g[m]))) for fr, g in df.groupby("franja")
            },
        }
    print(json.dumps(res, ensure_ascii=False))
    if a.salida:
        a.salida.parent.mkdir(parents=True, exist_ok=True)
        a.salida.write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
