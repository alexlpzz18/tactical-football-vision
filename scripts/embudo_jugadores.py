#!/usr/bin/env python
"""Dónde se caen los jugadores entre el detector y el recuento.

BACKLOG 20. Encargo de Alex (29-ago-2026), y sale de refutar la premisa
del 19: *"si entran 17,6 cajas por frame y salen 5-6 por equipo, el
problema no es la detección. Cuenta el EMBUDO etapa por etapa, con el
control de que parte de esas 17,6 tienen que perderse legítimamente"*.

Las etapas:

    detección  →  track con id  →  etiqueta de equipo  →  recuento

⚠️ EL CONTROL QUE HACE HONESTO EL NÚMERO. No todas las detecciones son
jugadores en juego: hay árbitro, banquillo, entrenadores y público
asomando por la banda. Esas **tienen que perderse**, y contarlas como
pérdida convertiría un sistema que funciona en uno que parece roto. Por
eso cada escalón se parte en dos: lo que cae DENTRO del campo (donde una
pérdida es un jugador perdido) y lo que cae FUERA (donde perderlo es el
comportamiento correcto).

Uso:
    python scripts/embudo_jugadores.py
"""

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Un jugador en juego está dentro de las líneas. El margen es generoso a
# propósito: un extremo pisa la banda, un portero sale del área, y el
# error de proyección en el fondo del campo es grande.
MARGEN_M = 2.0


def _dentro(x, y, largo, ancho, margen=MARGEN_M):
    return (
        (-margen <= x) & (x <= largo + margen) & (-margen <= y) & (y <= ancho + margen)
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--cache", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v2.csv")
    p.add_argument("--largo", type=float, default=62.0)
    p.add_argument("--ancho", type=float, default=40.0)
    args = p.parse_args()

    with open(args.cache, "rb") as f:
        datos = pickle.load(f)
    cache = datos["cache"]
    n_frames = len(cache)

    # ── Escalón 0: las detecciones crudas, partidas por posición ─────
    xs = np.array([t[0] for e in cache for t in e["dets"]])
    ys = np.array([t[1] for e in cache for t in e["dets"]])
    n_det = len(xs)
    dentro_det = _dentro(xs, ys, args.largo, args.ancho)
    n_dentro = int(dentro_det.sum())

    df = pd.read_csv(args.csv)
    n_filas = len(df)
    dentro_csv = _dentro(df.x_m.to_numpy(), df.y_m.to_numpy(), args.largo, args.ancho)
    n_csv_dentro = int(dentro_csv.sum())

    equipos = ["A", "B", "portero_A", "portero_B"]
    con_etiqueta = df[df.etiqueta.isin(equipos)]
    reales = con_etiqueta[con_etiqueta.es_real == 1]

    print(f"\n{'=' * 72}")
    print(f"EL EMBUDO · {n_frames} frames de la parte entera")
    print(f"{'=' * 72}\n")
    print(f"{'escalón':<34} {'total':>10} {'por frame':>11} {'queda':>8}")
    filas = [
        ("1. detecciones del detector", n_det),
        ("2. con id de track (en el CSV)", n_filas),
        ("3. con etiqueta de equipo", len(con_etiqueta)),
        ("4. y además es_real (se cuenta)", len(reales)),
    ]
    base = n_det
    for nombre, n in filas:
        print(f"{nombre:<34} {n:>10} {n / n_frames:>11.2f} {100 * n / base:>7.1f}%")

    # ── El control: cuánto SE TIENE que perder ───────────────────────
    print(f"\n{'─' * 72}")
    print("EL CONTROL · ¿cuánto de lo perdido se pierde bien?\n")
    print(
        f"  detecciones DENTRO del campo (±{MARGEN_M:.0f} m): "
        f"{n_dentro} ({n_dentro / n_frames:.2f} por frame, "
        f"{100 * n_dentro / n_det:.1f} %)"
    )
    print(
        f"  detecciones FUERA                    : "
        f"{n_det - n_dentro} ({(n_det - n_dentro) / n_frames:.2f} por frame)"
    )
    print("    ↑ banquillo, entrenadores, público: perderlas es CORRECTO")
    print("\n  en un fútbol 7 hay 16 personas en juego (14 + 2 porteros),")
    print(
        f"  17 con el árbitro. Detectadas dentro del campo: "
        f"{n_dentro / n_frames:.2f}"
    )
    sobran = n_dentro / n_frames - 17
    print(
        f"  {'SOBRAN' if sobran > 0 else 'FALTAN'} {abs(sobran):.2f} por frame "
        f"dentro del campo"
    )

    print(
        f"\n  del CSV, filas dentro del campo: {n_csv_dentro / n_frames:.2f} por frame"
    )
    perdidas_dentro = (n_dentro - n_csv_dentro) / n_frames
    print(f"  ⇒ el tracking pierde {perdidas_dentro:+.2f} por frame DENTRO del campo")

    # ── El recuento por equipo, que es el síntoma ────────────────────
    print(f"\n{'─' * 72}")
    print("EL RECUENTO POR EQUIPO · el síntoma que hay que explicar\n")
    print(f"  {'equipo':<12} {'por frame':>11} {'esperado':>10} {'déficit':>9}")
    for eq in ("A", "B"):
        n = len(reales[reales.etiqueta.isin([eq, f"portero_{eq}"])])
        print(f"  {eq:<12} {n / n_frames:>11.2f} {8:>10} {n / n_frames - 8:>+9.2f}")
    otras = df[~df.etiqueta.isin(equipos)]
    print(f"\n  y las que NO son de equipo: {len(otras) / n_frames:.2f} por frame")
    for et, g in otras.groupby("etiqueta"):
        d = _dentro(g.x_m.to_numpy(), g.y_m.to_numpy(), args.largo, args.ancho)
        print(
            f"    {et:<10} {len(g) / n_frames:>6.2f} por frame · "
            f"{100 * d.mean():>5.1f} % dentro del campo"
        )
    print()


if __name__ == "__main__":
    main()
