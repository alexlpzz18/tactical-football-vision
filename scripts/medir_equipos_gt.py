#!/usr/bin/env python
"""Mide la clasificación de equipos contra el mini-GT etiquetado a mano.

Cierra la pata que faltaba: hasta ahora la accuracy de equipos solo se
podía medir en Villaviciosa, que es donde hay ground truth de tracking.
Este script la mide en CUALQUIER partido a partir del CSV que exporta
scripts/etiquetar_equipos_gt.py.

Uso:
    python scripts/medir_equipos_gt.py --gt gt_equipos_posiciones_benja.csv
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# El GT usa 'arbitro'; el sistema no tiene esa etiqueta y lo saca del
# juego como 'otro'. Marcar al árbitro como no-jugador ES el acierto.
EQUIVALENCIAS = {"arbitro": "otro", "staff": "otro"}


def normalizar(etiqueta: str) -> str:
    return EQUIVALENCIAS.get(str(etiqueta), str(etiqueta))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", required=True, help="CSV exportado por la herramienta")
    parser.add_argument(
        "--csv",
        default=None,
        help="CSV de posiciones (si se omite, se usa la columna "
        "`prediccion` que ya trae el GT)",
    )
    args = parser.parse_args()

    gt = pd.read_csv(args.gt)
    gt = gt[gt.equipo_real.notna() & (gt.equipo_real != "")]
    if args.csv:
        pos = pd.read_csv(args.csv)
        pred = (
            pos[pos.es_real == 1]
            .groupby("id_jugador")
            .etiqueta.agg(lambda s: s.mode().iloc[0])
        )
        gt["prediccion"] = gt.id_jugador.map(pred)

    gt["real_n"] = gt.equipo_real.map(normalizar)
    gt["pred_n"] = gt.prediccion.map(normalizar)
    gt["acierto"] = gt.real_n == gt.pred_n

    n = len(gt)
    print(f"\nIdentidades etiquetadas: {n} " f"({int(gt.n_obs.sum())} observaciones)\n")

    # Accuracy PONDERADA por observaciones: fallar una identidad de 600
    # posiciones no cuesta lo mismo que fallar una de 30, y lo que llega
    # al informe son posiciones, no identidades.
    acc = gt.acierto.mean()
    acc_pond = (gt.acierto * gt.n_obs).sum() / gt.n_obs.sum()
    print(f"  accuracy por identidad   : {acc:.3f}  ({gt.acierto.sum()}/{n})")
    print(f"  accuracy por OBSERVACIÓN : {acc_pond:.3f}   <- la que importa")

    solo_campo = gt[gt.real_n.isin(["A", "B"])]
    if len(solo_campo):
        print(
            f"  solo jugadores de campo  : {solo_campo.acierto.mean():.3f} "
            f"({solo_campo.acierto.sum()}/{len(solo_campo)})"
        )

    print("\nMatriz de confusión (fila = real, columna = predicho):")
    etiquetas = sorted(set(gt.real_n) | set(gt.pred_n.dropna()))
    ancho = max(len(e) for e in etiquetas) + 2
    print(" " * ancho + "".join(f"{e:>{ancho}}" for e in etiquetas))
    for real in etiquetas:
        fila = gt[gt.real_n == real]
        cuenta = Counter(fila.pred_n)
        print(
            f"{real:>{ancho}}"
            + "".join(f"{cuenta.get(p, 0):>{ancho}}" for p in etiquetas)
        )

    fallos = gt[~gt.acierto].sort_values("n_obs", ascending=False)
    if len(fallos):
        print(f"\nFallos, por peso ({len(fallos)}):")
        print(f"  {'id':>5} {'obs':>6} {'real':>12} {'predicho':>12}")
        for f in fallos.head(12).itertuples():
            print(
                f"  {f.id_jugador:>5} {f.n_obs:>6} {f.real_n:>12} {str(f.pred_n):>12}"
            )


if __name__ == "__main__":
    main()
