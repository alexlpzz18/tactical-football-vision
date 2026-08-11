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

    filas = pd.read_csv(args.gt)
    filas = filas[filas.equipo_real.notna() & (filas.equipo_real != "")]
    filas["real_n"] = filas.equipo_real.map(normalizar)

    # El GT viene por RECORTE, no por identidad: es lo que permite que
    # las quimeras salgan solas de los datos en vez de tener que
    # localizarlas a ojo. Una identidad cuyos recortes no dicen todos lo
    # mismo contiene más de una persona.
    resumen = []
    for id_j, g in filas.groupby("id_jugador"):
        cuenta = Counter(g.real_n)
        dominante, n_dom = cuenta.most_common(1)[0]
        resumen.append(
            {
                "id_jugador": int(id_j),
                "real_n": dominante,
                "pureza": n_dom / len(g),
                "n_etiquetas": len(cuenta),
                "n_recortes": len(g),
                "n_obs": float(g.n_obs.iloc[0]),
                "prediccion": g.prediccion.iloc[0],
                "personas": dict(cuenta),
            }
        )
    gt = pd.DataFrame(resumen)
    if args.csv:
        pos = pd.read_csv(args.csv)
        pred = (
            pos[pos.es_real == 1]
            .groupby("id_jugador")
            .etiqueta.agg(lambda s2: s2.mode().iloc[0])
        )
        gt["prediccion"] = gt.id_jugador.map(pred)
    gt["pred_n"] = gt.prediccion.map(normalizar)
    gt["acierto"] = gt.real_n == gt.pred_n
    gt["es_quimera"] = gt.n_etiquetas > 1

    quimeras = gt[gt.es_quimera]
    n = len(gt)
    print(
        f"\nIdentidades etiquetadas: {n} "
        f"({int(gt.n_obs.sum())} observaciones, {int(gt.n_recortes.sum())} recortes)"
    )

    print(
        f"\n  QUIMERAS detectadas por el propio etiquetado: "
        f"{len(quimeras)} de {n} ({100 * len(quimeras) / n:.0f} %)"
    )
    if len(quimeras):
        print("  (sus recortes NO dicen todos lo mismo: contienen más de una")
        print("   persona. Es un fallo de TRACKING, no de clasificación)")
        print(f"    {'id':>5} {'obs':>6} {'pureza':>7}  composición")
        for q in quimeras.sort_values("n_obs", ascending=False).itertuples():
            comp = ", ".join(
                f"{k}×{v}" for k, v in sorted(q.personas.items(), key=lambda kv: -kv[1])
            )
            print(f"    {q.id_jugador:>5} {q.n_obs:>6.0f} {q.pureza:>7.2f}  {comp}")
    # Las observaciones de una quimera solo cuentan en la proporción que
    # corresponde a su persona dominante: el resto pertenecen a otra.
    gt["n_obs_efectivas"] = gt.n_obs * gt.pureza
    print()

    acc = gt.acierto.mean()
    acc_pond = (gt.acierto * gt.n_obs_efectivas).sum() / gt.n_obs_efectivas.sum()
    print(f"  accuracy por identidad   : {acc:.3f}  ({gt.acierto.sum()}/{n})")
    print(f"  accuracy por OBSERVACIÓN : {acc_pond:.3f}   <- la que importa")

    limpias = gt[~gt.es_quimera]
    if len(limpias) and len(limpias) < n:
        acc_l = (limpias.acierto * limpias.n_obs).sum() / limpias.n_obs.sum()
        print(
            f"  solo identidades LIMPIAS : {acc_l:.3f}   "
            f"<- clasificación pura, sin el ruido del tracking"
        )

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
                f"  {f.id_jugador:>5} {f.n_obs:>6.0f} {f.real_n:>12} "
                f"{str(f.pred_n):>12}"
            )


if __name__ == "__main__":
    main()
