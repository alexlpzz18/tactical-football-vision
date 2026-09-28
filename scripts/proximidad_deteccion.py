#!/usr/bin/env python
"""¿Cuánto falla el detector cuando dos personas están CERCA en la imagen? (BACKLOG 19)

Alex (25-sep-2026), tras revisar 9 de las 120 imágenes de la hoja de recuento:
*«hay un fallo real y repetido, siempre la misma forma: cuando dos personas se
solapan en la imagen, el detector las mezcla en una sola caja. No es oclusión —se
distinguen CLARAMENTE a simple vista—, es un problema de separación ante proximidad.
Mide la TASA DE SOLAPE real: para cada par del GT, la DISTANCIA EN PÍXELES entre las
dos cajas, y compáralo con si el detector las encontró.»*

Mide, sobre los 60 frames del GT del benjamín:
  1. Para cada persona, la distancia en píxeles a su vecino más cercano (también GT).
  2. Si una detección CRUDA del caché la casó (1-a-1, radio en metros — la misma
     regla que el resto del proyecto).
  3. La tasa de fallo por tramo de distancia.

⚠️ Los porteros se excluyen: fallan por el encuadre cercano a la cámara
(`docs/portero_cortado.md`), no por proximidad, y su vecino más cercano está muy
lejos — meterlos invierte la curva (se comprueba y se muestra el porqué).

Uso:
    python scripts/proximidad_deteccion.py
"""

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.gt_parser import parsear_cvat  # noqa: E402
from src.evaluation.proximidad_deteccion import (  # noqa: E402
    personas_gt_por_frame,
    tabla_proximidad,
)

BINS = [0, 20, 30, 40, 50, 60, 80, 100, 10_000]
ETIQUETAS = ["0-20", "20-30", "30-40", "40-50", "50-60", "60-80", "80-100", ">100"]


def informar(R: pd.DataFrame) -> None:
    print("1. CONTROL: con porteros (los distorsionan) vs sin ellos")
    for nombre, sub in (
        ("con porteros", R),
        ("SIN porteros (jugadores de campo)", R[~R.portero]),
    ):
        print(
            f"   {nombre:36s} n={len(sub):4d}  encontrado global={sub.encontrado.mean():.1%}"
        )
        lejos = sub[sub.vecino_px > 150]
        if len(lejos):
            print(
                f"      vecino > 150px (n={len(lejos)}): encontrado={lejos.encontrado.mean():.1%}"
                "  ← debería ser ~100%: nadie cerca que confunda al detector"
            )

    J = R[~R.portero].copy()
    J["bin"] = pd.cut(J.vecino_px, BINS, labels=ETIQUETAS)
    print(
        "\n2. TASA DE FALLO POR DISTANCIA AL VECINO MÁS CERCANO (píxeles, sin porteros)"
    )
    print(f"   {'vecino (px)':>12s} {'n':>5s} {'encontrado':>11s} {'FALLO':>7s}")
    T = J.groupby("bin", observed=True).agg(
        n=("encontrado", "size"), tasa=("encontrado", "mean")
    )
    for etq, r in T.iterrows():
        print(f"   {etq:>12s} {int(r.n):5d} {r.tasa:10.1%} {1 - r.tasa:6.1%}")

    rng = np.random.default_rng(0)
    for umbral in (20, 30, 40):
        sub = J[J.vecino_px < umbral]
        fallo = 1 - sub.encontrado.mean()
        boot = [
            1 - sub.encontrado.to_numpy()[rng.integers(0, len(sub), len(sub))].mean()
            for _ in range(3000)
        ]
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(
            f"\n   vecino < {umbral} px: {len(sub)} personas, falla el {fallo:.1%}"
            f" (IC95% [{lo:.1%}, {hi:.1%}])"
        )

    print("\n3. MECANISMO (sin GPU no se puede re-ejecutar SAHI aquí):")
    print("   ver docs/colab_ios_jugadores.md para las celdas ya preparadas.")
    print(
        "   get_sliced_prediction() usa los DEFAULTS de SAHI en producción: postprocess_type="
        "'GREEDYNMM', postprocess_match_metric='IOS', postprocess_match_threshold=0.5"
        " (src/tracking_data/processor.py:721, sin overrides en ningún config)."
    )
    print(
        "   Es el MISMO mecanismo ya documentado para el balón (docs/sahi_balon.md, BACKLOG 16):"
        " con IOS, una caja grande que contiene a una pequeña da 1,00 aunque sean personas"
        " distintas, y la fusión se queda con la confianza de la pequeña y la geometría de la"
        " grande. BACKLOG 19 ya tenía las celdas de Colab listas para probar IOU en vez de IOS."
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument(
        "--dets", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    p.add_argument("--radio", type=float, default=2.0)
    args = p.parse_args()

    H = np.load(args.homografia)
    tracks = parsear_cvat(args.gt)
    por_frame = personas_gt_por_frame(tracks, H, args.offset, args.paso)
    with open(args.dets, "rb") as f:
        cache = {
            e["frame_idx"]: np.array(e["dets"]).reshape(-1, 7)
            for e in pickle.load(f)["cache"]
        }

    filas = tabla_proximidad(por_frame, cache, args.radio)
    R = pd.DataFrame(filas)
    print(f"GT: {len(por_frame)} frames, {len(R)} personas-frame\n")
    informar(R)


if __name__ == "__main__":
    main()
