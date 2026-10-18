#!/usr/bin/env python
"""¿Por qué el sistema saca 5-6 jugadores de A y 7-8 de B, si son 7 y 7?

Encargo de Alex (28-ago-2026): *"Es lo más urgente. Un entrenador lo ve en
tres segundos y deja de creerse el informe entero antes de leer una
línea."*

El GT del benjamín anota 14 personas: 6 de campo + portero por equipo, y
la mediana por frame es **7 y 7**. Así que el desequilibrio es un error
real, no una peculiaridad del partido.

Tres preguntas, y el script las separa a propósito porque tienen arreglos
distintos:

  (a) ¿A se FRAGMENTA (sus jugadores no llegan al CSV) o B recibe
      INTRUSOS (árbitro, staff, público) que le suman?
  (b) ¿Es de CONTEO o de DIBUJO? ¿Faltan del CSV, o están y la pizarra no
      las pinta por sus filtros de credibilidad?
  (c) Contra el GT: ¿en cuántos frames el recuento por equipo es correcto?

Uso:
    python scripts/recuento_por_equipo.py
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("recuento")

RADIO_M = 2.0


def equipo_de(etiqueta):
    e = str(etiqueta)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1.csv")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    H = np.load(args.homografia)
    gt = gt_a_por_frame(parsear_cvat(args.gt), H, args.offset, args.paso)
    df = pd.read_csv(args.csv)
    df = df[df.es_real == 1]
    df = df.assign(equipo_sis=df.etiqueta.map(equipo_de))

    comunes = sorted(set(df.frame) & set(gt))
    print(f"\nframes comparables: {len(comunes)}")

    # ── (c) El recuento, frame a frame ───────────────────────────────
    filas = []
    faltan_de = Counter()
    sobran_en = Counter()
    destino_de_los_que_faltan = Counter()
    for f in comunes:
        sub = df[df.frame == f]
        gente_gt = [o for o in gt[f] if equipo_de(o.team) in ("A", "B")]
        n_gt = Counter(equipo_de(o.team) for o in gente_gt)
        n_sis = Counter(sub[sub.equipo_sis.isin(["A", "B"])].equipo_sis)
        filas.append((f, n_gt["A"], n_sis["A"], n_gt["B"], n_sis["B"]))

        # (a) ¿qué le pasa a cada persona del GT que el sistema no cuenta?
        xy = sub[["x_m", "y_m"]].to_numpy()
        etq = sub.equipo_sis.to_numpy()
        casadas = set()
        for o in gente_gt:
            eq = equipo_de(o.team)
            if not len(xy):
                faltan_de[eq] += 1
                destino_de_los_que_faltan["sin fila en el CSV"] += 1
                continue
            d = np.hypot(xy[:, 0] - o.pos[0], xy[:, 1] - o.pos[1])
            k = int(np.argmin(d))
            if d[k] > RADIO_M:
                faltan_de[eq] += 1
                destino_de_los_que_faltan["sin fila en el CSV"] += 1
                continue
            casadas.add(k)
            if etq[k] != eq:
                faltan_de[eq] += 1
                destino_de_los_que_faltan[f"etiquetado como {etq[k]}"] += 1
        # filas del sistema en equipos que NO casan con nadie del GT
        for k, e in enumerate(etq):
            if e in ("A", "B") and k not in casadas:
                sobran_en[e] += 1

    tab = pd.DataFrame(filas, columns=["frame", "gt_A", "sis_A", "gt_B", "sis_B"])
    print("\n(c) EL RECUENTO CONTRA EL GT")
    print(f"  {'':<10}{'GT':>8}{'sistema':>10}{'error medio':>14}")
    for eq in ("A", "B"):
        g, s = tab[f"gt_{eq}"], tab[f"sis_{eq}"]
        print(
            f"  equipo {eq:<4}{g.median():>8.0f}{s.median():>10.0f}"
            f"{(s - g).mean():>+14.2f}"
        )
    ok_a = (tab.sis_A == tab.gt_A).mean()
    ok_b = (tab.sis_B == tab.gt_B).mean()
    ok_2 = ((tab.sis_A == tab.gt_A) & (tab.sis_B == tab.gt_B)).mean()
    print(
        f"\n  frames con el recuento correcto: A {100*ok_a:.0f} % · "
        f"B {100*ok_b:.0f} % · LOS DOS {100*ok_2:.0f} %"
    )

    print("\n(a) ¿FRAGMENTACIÓN DE A O INTRUSOS EN B?")
    total_gt = sum(faltan_de.values()) or 1
    print("  personas del GT que el sistema NO cuenta en su equipo:")
    for eq, n in faltan_de.most_common():
        print(f"     equipo {eq}: {n}")
    print("  y a dónde van a parar:")
    for destino, n in destino_de_los_que_faltan.most_common():
        print(f"     {destino:<28} {n:>5} ({100*n/total_gt:.0f} %)")
    print("\n  filas del sistema en A o B que NO casan con nadie del GT (intrusos):")
    for eq, n in sobran_en.most_common():
        print(f"     equipo {eq}: {n}")


if __name__ == "__main__":
    main()
