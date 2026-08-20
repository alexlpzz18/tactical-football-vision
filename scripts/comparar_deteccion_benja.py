#!/usr/bin/env python
"""¿El v4 detecta mejor, igual o peor que el v4pre EN EL BENJAMÍN?

La pregunta que decide dónde va el esfuerzo de etiquetado: si el problema
del F7 es de DETECCIÓN, etiquetar frames del benjamín lo arregla; si es
de asociación o clasificación, ese esfuerzo no sirve de nada.

No hay GT de detección en este tramo, así que no se puede medir mAP. Lo
que sí se puede medir, y es suficiente para decidir:

- cajas por frame (con 14 jugadores + portero + árbitro en campo, quedarse
  corto es perder gente y pasarse es meter público);
- distribución de confianza (un detector inseguro en un dominio que no
  conoce lo enseña aquí);
- cuántas tira el filtro de 0,45 y, sobre todo, **si las que tira son
  jugadores reales lejanos** — que es la sospecha razonable: las
  detecciones de menos confianza son las del fondo del campo.

Uso:
    python scripts/comparar_deteccion_benja.py
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking.cache_io import cargar_cache  # noqa: E402

logger = logging.getLogger(__name__)

# Un F7 tiene 7v7 en campo (14) + árbitro. Con suplentes y cuerpo técnico
# en la banda, el detector ve legítimamente algunos más.
ESPERADAS_EN_CAMPO = 15


def resumen(
    nombre: str, ruta: str, conf_filtro: float, largo: float = 62.0, ancho: float = 40.0
) -> dict:
    datos = cargar_cache(ruta)
    cache = datos["cache"]
    por_frame = np.array([len(e["dets"]) for e in cache])
    confs = np.array([d[6] for e in cache for d in e["dets"]])
    # Profundidad: y en metros de cada detección. Los jugadores del fondo
    # son los que menos píxeles tienen y los que el detector duda.
    ys = np.array([d[1] for e in cache for d in e["dets"]])
    alturas = np.array([d[5] - d[3] for e in cache for d in e["dets"]])
    tiradas = confs < conf_filtro
    # ¿Están DENTRO del campo? Las de fuera son banquillo, público y
    # cuerpo técnico: detecciones legítimas del modelo pero que no son
    # jugadores, y que el tracker convierte en identidades fantasma.
    xs = np.array([d[0] for e in cache for d in e["dets"]])
    dentro = (xs >= 0) & (xs <= largo) & (ys >= 0) & (ys <= ancho)
    dentro_por_frame = []
    i = 0
    for e in cache:
        n = len(e["dets"])
        fin = i + n
        dentro_por_frame.append(int(dentro[i:fin].sum()))
        i = fin
    return {
        "dentro_frame": float(np.mean(dentro_por_frame)),
        "pct_fuera": float((~dentro).mean()),
        "pct_fuera_tiradas": (
            float((~dentro[tiradas]).mean()) if tiradas.any() else 0.0
        ),
        "nombre": nombre,
        "frames": len(cache),
        "dets": len(confs),
        "por_frame": por_frame.mean(),
        "p10_frame": np.percentile(por_frame, 10),
        "conf_media": confs.mean(),
        "conf_mediana": float(np.median(confs)),
        "pct_baja": float((confs < 0.5).mean()),
        "n_tiradas": int(tiradas.sum()),
        "pct_tiradas": float(tiradas.mean()),
        "altura_tiradas": float(np.median(alturas[tiradas])) if tiradas.any() else 0.0,
        "altura_resto": float(np.median(alturas[~tiradas])),
        "y_tiradas": float(np.median(ys[tiradas])) if tiradas.any() else 0.0,
        "y_resto": float(np.median(ys[~tiradas])),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v4pre", default="data/tracking_benja/cache_detecciones_benja.pkl")
    p.add_argument("--v4", default="data/tracking_benja/cache_detecciones_benja_v4.pkl")
    p.add_argument("--conf-filtro", type=float, default=0.45)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    filas = [
        resumen("v4pre", args.v4pre, args.conf_filtro),
        resumen("v4", args.v4, args.conf_filtro),
    ]

    print(f"\n── DETECCIÓN EN EL TRAMO DEL BENJAMÍN (filtro {args.conf_filtro}) ──\n")
    cab = (
        f"{'':<8}{'frames':>7}{'dets':>8}{'/frame':>8}{'p10':>6}"
        f"{'conf med':>10}{'% <0.5':>8}"
    )
    print(cab)
    print("-" * len(cab))
    for f in filas:
        print(
            f"{f['nombre']:<8}{f['frames']:>7}{f['dets']:>8}{f['por_frame']:>8.1f}"
            f"{f['p10_frame']:>6.0f}{f['conf_media']:>10.3f}{f['pct_baja']:>7.1%}"
        )
    print(f"\n(en campo hay ~{ESPERADAS_EN_CAMPO} personas: 7v7 + árbitro)")

    print(f"\n── QUÉ TIRA EL FILTRO DE {args.conf_filtro} ──\n")
    cab2 = (
        f"{'':<8}{'tiradas':>9}{'%':>8}{'altura tiradas':>16}"
        f"{'altura resto':>14}{'y tiradas':>11}{'y resto':>9}"
    )
    print(cab2)
    print("-" * len(cab2))
    for f in filas:
        print(
            f"{f['nombre']:<8}{f['n_tiradas']:>9}{f['pct_tiradas']:>7.1%}"
            f"{f['altura_tiradas']:>16.1f}{f['altura_resto']:>14.1f}"
            f"{f['y_tiradas']:>11.1f}{f['y_resto']:>9.1f}"
        )
    print("\naltura = píxeles de la caja; y = metros de profundidad en campo.")
    print("Si las tiradas son MÁS BAJAS y están MÁS LEJOS, el filtro se está")
    print("comiendo jugadores del fondo, no ruido.")

    a, b = filas
    print("\n── ¿SON JUGADORES O SON PÚBLICO? ──\n")
    cab3 = (
        f"{'':<8}{'dentro/frame':>14}{'% fuera del campo':>20}{'% de las tiradas':>18}"
    )
    print(cab3)
    print("-" * len(cab3))
    for f in filas:
        print(
            f"{f['nombre']:<8}{f['dentro_frame']:>14.1f}{f['pct_fuera']:>19.1%}"
            f"{f['pct_fuera_tiradas']:>18.1%}"
        )
    print("\nLa última columna es la que decide: si las detecciones que tira el")
    print("filtro están MAYORITARIAMENTE fuera del campo, el filtro quita")
    print("público, no jugadores.")

    print("\n── LECTURA ──")
    dif = b["por_frame"] - a["por_frame"]
    print(
        f"El v4 detecta {abs(dif):.1f} cajas/frame "
        f"{'MÁS' if dif > 0 else 'MENOS'} que el v4pre "
        f"({a['por_frame']:.1f} → {b['por_frame']:.1f})."
    )
    print(
        f"Confianza media {a['conf_media']:.3f} → {b['conf_media']:.3f}; "
        f"detecciones dudosas (<0.5) {a['pct_baja']:.1%} → {b['pct_baja']:.1%}."
    )


if __name__ == "__main__":
    main()
