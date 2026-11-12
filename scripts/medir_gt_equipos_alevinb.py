#!/usr/bin/env python
"""Acierto de equipo del alevín B contra un mini-GT a ojo de 120 detecciones (posición y tiempo).

docs/plan_equipos_embeddings.md. El mini-GT (`outputs/gt_equipos_alevinb/detecciones_120.csv`) se
etiquetó mirando los recortes ANTES de ver qué decía ningún brazo: B = blanco con rayas, V = verde
oscuro, R = árbitro, K = portero, X = dudoso (dos personas, borroso, césped). Se mide sobre B y V.

Está indexado por CAJA y frame, no por id del sistema (CLAUDE.md: un GT por id caduca). Para cada
brazo se corre el `desde_cache` capturando la asignación del tracker, y la etiqueta que cuenta es la
de la fila de la identidad que contiene ESA detección en ESE frame (la «caja de la fila»).

Uso:
    python scripts/medir_gt_equipos_alevinb.py --representacion hs
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

GT = R / "outputs/gt_equipos_alevinb/detecciones_120.csv"


def correr_capturando(
    rep: str, peso: float, brazo: str | None = None
) -> tuple[Path, list, dict]:
    """CSV del brazo + identidades [(frame, j)] + caché filtrado {frame: dets} del tracker."""
    import src.tracking.perfiles as perfiles
    from banco_equipos_v2 import correr_brazo, correr_representacion

    cap = {}
    orig_correr, orig_post = perfiles.correr_perfil, perfiles.postprocesar

    def espia_correr(cache, *a, **k):
        cap["cache"] = {e["frame_idx"]: e["dets"] for e in cache}
        return orig_correr(cache, *a, **k)

    def espia_post(identidades, *a, **k):
        cap["identidades"] = [
            [(int(f), int(j)) for tr in ident for (f, j) in tr.det_idxs]
            for ident in identidades
        ]
        return orig_post(identidades, *a, **k)

    perfiles.correr_perfil, perfiles.postprocesar = espia_correr, espia_post
    try:
        csv = (
            correr_brazo("alevinb", brazo)
            if brazo
            else correr_representacion("alevinb", rep, peso)
        )
    finally:
        perfiles.correr_perfil, perfiles.postprocesar = orig_correr, orig_post
    return csv, cap["identidades"], cap["cache"]


def medir(csv: Path, identidades: list, cache: dict) -> dict:
    gt = pd.read_csv(GT)
    gt = gt[gt.equipo_a_ojo.isin(["B", "V"])]
    filas = pd.read_csv(csv)
    etiqueta = {
        (int(r.frame), int(r.id_jugador)): r.etiqueta for r in filas.itertuples()
    }
    id_de = {}
    for id_jugador, ident in enumerate(identidades, start=1):
        for f, j in ident:
            id_de[(f, j)] = id_jugador
    pares = []
    for r in gt.itertuples():
        dets = cache.get(int(r.frame), [])
        caja = np.array([r.x1, r.y1, r.x2, r.y2])
        j = next(
            (
                i
                for i, d in enumerate(dets)
                if np.abs(np.array(d[2:6], float) - caja).sum() < 1e-3
            ),
            None,
        )
        ident = id_de.get((int(r.frame), j)) if j is not None else None
        sis = etiqueta.get((int(r.frame), ident)) if ident is not None else None
        sis = str(sis).replace("portero_", "") if sis is not None else "sin fila"
        pares.append((r.equipo_a_ojo, sis, r.franja))
    p = pd.DataFrame(pares, columns=["ojo", "sistema", "franja"])
    directo = ((p.ojo == "B") & (p.sistema == "A")) | (
        (p.ojo == "V") & (p.sistema == "B")
    )
    cruzado = ((p.ojo == "B") & (p.sistema == "B")) | (
        (p.ojo == "V") & (p.sistema == "A")
    )
    acierto = directo if directo.sum() >= cruzado.sum() else cruzado
    p["ok"] = acierto
    return {
        "jugadores": len(p),
        "acierto_pct": round(100 * acierto.mean(), 1),
        "fuera_de_equipo": int((~p.sistema.isin(["A", "B"])).sum()),
        "por_franja": {f: round(100 * g.ok.mean(), 1) for f, g in p.groupby("franja")},
        "confusion": pd.crosstab(p.ojo, p.sistema).to_dict(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--representacion", default="hs")
    ap.add_argument("--peso", type=float, default=1.0)
    ap.add_argument(
        "--brazo", default=None, help="brazo del tercer intento (banco_equipos_v2)"
    )
    a = ap.parse_args()
    import logging

    logging.basicConfig(level=logging.ERROR)
    csv, identidades, cache = correr_capturando(a.representacion, a.peso, a.brazo)
    r = medir(csv, identidades, cache)
    print(
        json.dumps(
            {"brazo": a.brazo or f"{a.representacion}_w{a.peso:g}", **r},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
