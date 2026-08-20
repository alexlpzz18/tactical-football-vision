#!/usr/bin/env python
"""Accuracy REAL del v4 en el benjamín, sin traslados.

Por qué esto existe: la cifra anterior (0,802) salía de trasladar por
posición las etiquetas de un mini-GT hecho sobre los ids del v4pre, y ese
traslado pierde — solo 35 de 84 identidades encontraban equivalente, y
cinco identidades nuevas caían sobre una vieja. Este mini-GT está hecho
SOBRE el tracking del v4, así que la comparación es directa: no hay
traslado, no hay pérdida.

La predicción no hay que recalcularla: la herramienta de etiquetado ya
guardó en el CSV lo que el sistema decía de cada identidad (`prediccion`)
junto a lo que dijo Alex (`equipo_real`). Comparar esas dos columnas es
exacto y no depende de reproducir la pasada.

Uso:
    python scripts/medir_mini_gt_v4.py \\
        --gt data/tracking_benja/gt_equipos_benja_v4.csv
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

# Árbitro y staff van al mismo cajón: ninguno de los dos entra en las
# métricas por equipo del informe.
EQUIV = {"arbitro": "otro", "staff": "otro"}

# El 0,883 histórico del v4pre NO se puede usar tal cual como referencia:
# se calculó con otra ponderación (n_obs × pureza de la etiqueta dentro
# del grupo) y esta usa n_obs a secas. Con la fórmula de aquí, el mismo
# GT del v4pre da 0,857. Mezclar las dos cifras haría parecer peor o
# mejor al v4 por un cambio de fórmula, no por un cambio de sistema.
#
# Por eso la referencia se RECALCULA con `--referencia`, pasándole el GT
# del v4pre, y las dos cifras salen de la misma función.
HISTORICO_TRASLADO = 0.802


def normalizar(x) -> str:
    s = str(x).strip()
    return EQUIV.get(s, s)


def accuracy(gt: pd.DataFrame, sin_porteros: bool):
    """(accuracy ponderada por observaciones, lista de fallos)."""
    aciertos = pesos = 0.0
    fallos = []
    for id_j, g in gt.groupby("id_jugador"):
        real = Counter(normalizar(v) for v in g.equipo_real).most_common(1)[0][0]
        pred = Counter(normalizar(v) for v in g.prediccion).most_common(1)[0][0]
        if sin_porteros:
            real = real.replace("portero_", "")
            pred = pred.replace("portero_", "")
        peso = float(g.n_obs.iloc[0])
        pesos += peso
        if real == pred:
            aciertos += peso
        else:
            fallos.append((int(id_j), real, pred, int(peso)))
    return (aciertos / pesos if pesos else 0.0), fallos


def cargar(ruta: str) -> pd.DataFrame:
    gt = pd.read_csv(ruta)
    faltan = {"id_jugador", "equipo_real", "prediccion", "n_obs"} - set(gt.columns)
    if faltan:
        raise SystemExit(f"A {ruta} le faltan columnas: {sorted(faltan)}")
    gt = gt[gt.equipo_real.notna() & (gt.equipo_real.astype(str) != "")]
    if gt.empty:
        raise SystemExit(f"{ruta} no tiene ninguna etiqueta rellenada")
    return gt


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gt", required=True)
    p.add_argument(
        "--referencia",
        default="data/tracking_benja/gt_equipos_benja.csv",
        help="GT del v4pre, para recalcular su cifra con ESTA misma fórmula",
    )
    p.add_argument(
        "--sin-porteros",
        action="store_true",
        help="Cuenta portero_A como A (el informe los agrupa con su equipo)",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    gt = cargar(args.gt)

    tiene_ancla = {"frame", "x_m", "y_m"}.issubset(gt.columns)
    print(
        f"\n{len(gt)} filas etiquetadas · "
        f"{gt.id_jugador.nunique()} identidades · "
        + (
            "CON ancla de posición y tiempo"
            if tiene_ancla
            else "SIN ancla (formato viejo)"
        )
    )
    if not tiene_ancla:
        print(
            "  ⚠ Sin las columnas frame/x_m/y_m este GT caduca en cuanto\n"
            "    cambie el detector: los ids no sobreviven, la posición sí."
        )

    acc, fallos = accuracy(gt, args.sin_porteros)

    referencias = {"v4 (traslado con pérdida)": HISTORICO_TRASLADO}
    ruta_ref = Path(args.referencia)
    if ruta_ref.exists():
        acc_ref, _ = accuracy(cargar(str(ruta_ref)), args.sin_porteros)
        referencias["v4pre (MISMA fórmula)"] = acc_ref

    print("\n── ACCURACY POR OBSERVACIÓN (v4 ajustado + puerta) ──\n")
    print(f"  {acc:.3f}")
    for nombre, valor in referencias.items():
        print(f"    vs {nombre:<28} {valor:.3f}  ({acc - valor:+.3f})")

    if fallos:
        print(f"\n── LAS QUE FALLAN ({len(fallos)} identidades) ──\n")
        print(f"  {'id':>4}  {'real':<12}{'sistema':<12}{'obs':>6}")
        print("  " + "-" * 36)
        for id_j, real, pred, peso in sorted(fallos, key=lambda f: -f[3]):
            print(f"  {id_j:>4}  {real:<12}{pred:<12}{peso:>6}")
        confusion = Counter((r, p) for _i, r, p, _n in fallos)
        print("\n  Confusiones más repetidas:")
        for (r, p), n in confusion.most_common(5):
            print(f"    {r} → {p}: {n}")

    ref = referencias.get("v4pre (MISMA fórmula)")
    if ref is not None:
        print(
            "\n→ El v4 "
            + (
                "SUPERA al v4pre en esta pata."
                if acc > ref
                else "sigue POR DEBAJO del v4pre en esta pata."
            )
        )
    else:
        print("\n(sin --referencia no hay con qué comparar de forma honesta)")


if __name__ == "__main__":
    main()
