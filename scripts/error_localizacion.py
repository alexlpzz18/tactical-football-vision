#!/usr/bin/env python
"""Línea base: error de localización en METROS, por franjas de profundidad.

Antes de tocar nada. Sin esta tabla no se puede saber si el anclaje por
pose —o cualquier otra cosa— mejora algo, y con la amplificación de la
perspectiva un promedio global no dice nada: el error de cerca y el del
fondo no son la misma magnitud ni de lejos.

Se apoya en que el GT del benjamín ya tiene el anclaje corregido: 0,42 m
de sesgo mediano, **por debajo del error de la propia calibración**
(0,91 m), así que deja de ser el factor limitante.

Dos cosas que el medidor tiene que tratar bien o mentirá:

1. **Falta el árbitro en el GT.** Sus detecciones aparecerán sin
   correspondencia. Se cuentan aparte como "sin GT", NUNCA como fallo: si
   no, el sistema parecería peor por haber detectado bien a alguien que
   nadie etiquetó.
2. **El emparejamiento usa un radio generoso y por profundidad.** Emparejar
   con radio fijo penalizaría el fondo dos veces: una por el error real y
   otra por no encontrar pareja.

Uso:
    python scripts/error_localizacion.py
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402

FRANJAS = [
    ("0-10 m", 0, 10),
    ("10-20 m", 10, 20),
    ("20-30 m", 20, 30),
    ("30+ m", 30, 1e9),
]
# Radio de emparejamiento: crece con la profundidad, como el del banco.
RADIO_BASE, RADIO_POR_METRO, RADIO_MAX = 1.5, 0.09, 6.0

logger = logging.getLogger("error_loc")


def radio(y):
    return float(np.clip(RADIO_BASE + RADIO_POR_METRO * y, RADIO_BASE, RADIO_MAX))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_emb.csv")
    p.add_argument("--config", default="configs/processor_benja_emb.yaml")
    p.add_argument("--frame-ini", type=int, default=9750)
    p.add_argument("--paso-gt", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    H = np.load(cfg["rutas"]["homografia"])
    gt = gt_a_por_frame(
        parsear_cvat(args.gt), H, frame_offset=args.frame_ini, paso_gt=args.paso_gt
    )
    sis = pd.read_csv(args.csv)
    if "es_real" in sis.columns:
        sis = sis[sis.es_real == 1]

    errores, sin_pareja, huerfanas = [], [], 0
    for frame, observaciones in gt.items():
        cand = sis[sis.frame == frame]
        usados = set()
        for o in observaciones:
            gx, gy = float(o.pos[0]), float(o.pos[1])
            r = radio(gy)
            mejor, dmin = None, r
            for fila in cand.itertuples():
                if fila.Index in usados:
                    continue
                dist = float(np.hypot(fila.x_m - gx, fila.y_m - gy))
                if dist < dmin:
                    mejor, dmin = fila, dist
            if mejor is None:
                sin_pareja.append(gy)
            else:
                usados.add(mejor.Index)
                errores.append({"y": gy, "e": dmin, "gid": o.obj_id})
        huerfanas += len(cand) - len(usados)

    e = pd.DataFrame(errores)
    n_gt = sum(len(v) for v in gt.values())
    print(f"\nGT: {n_gt} observaciones en {len(gt)} fotogramas\n")

    cab = (
        f"{'franja':<10}{'n GT':>7}{'emparej.':>10}{'error medio':>13}"
        f"{'mediana':>10}{'p90':>8}"
    )
    print(cab)
    print("-" * len(cab))
    for nombre, lo, hi in FRANJAS:
        en = e[(e.y >= lo) & (e.y < hi)] if len(e) else e
        n_franja = len(en) + sum(1 for y in sin_pareja if lo <= y < hi)
        if not n_franja:
            continue
        if len(en):
            print(
                f"{nombre:<10}{n_franja:>7}{len(en)/n_franja:>9.0%}"
                f"{en.e.mean():>12.2f} m{en.e.median():>9.2f}{en.e.quantile(.9):>8.2f}"
            )
        else:
            print(f"{nombre:<10}{n_franja:>7}{0:>9.0%}{'—':>13}{'—':>10}{'—':>8}")
    print("-" * len(cab))
    if len(e):
        print(
            f"{'TOTAL':<10}{n_gt:>7}{len(e)/n_gt:>9.0%}"
            f"{e.e.mean():>12.2f} m{e.e.median():>9.2f}{e.e.quantile(.9):>8.2f}"
        )

    print(
        f"\n  Observaciones del GT SIN pareja: {len(sin_pareja)} "
        f"({len(sin_pareja)/max(n_gt,1):.0%})"
    )
    print(f"  Detecciones del sistema sin GT: {huerfanas} — incluyen al ÁRBITRO,")
    print("    que no se etiquetó. NO se cuentan como fallo.")
    print(
        "\n  El emparejamiento usa radio por profundidad "
        f"({RADIO_BASE} + {RADIO_POR_METRO}·y, máx {RADIO_MAX} m):\n"
        "  con radio fijo, el fondo se penalizaría dos veces."
    )


if __name__ == "__main__":
    main()
