#!/usr/bin/env python
"""¿El error del fondo es de CALIBRACIÓN o de ÓPTICA? Son cosas distintas.

Separa dos efectos que se confunden fácil:

1. **Amplificación por perspectiva** (óptica/geometría). Cerca del
   horizonte, un píxel vale muchos metros. Es intrínseco a proyectar un
   plano con una cámara: **ninguna calibración lo arregla**, por buena
   que sea.
2. **Error de ajuste** (calibración). Si los puntos de referencia están
   mal repartidos, la homografía se ajusta bien donde hay puntos y deriva
   donde no los hay. Eso **sí** se arregla marcando más puntos.

La medida que los separa es el RESIDUO: cuánto se desvía cada punto de
calibración al reproyectarlo con la H que salió de ellos. Residuos
pequeños en todas partes = el ajuste es bueno y lo que queda es óptica.
Residuos grandes arriba = merece la pena recalibrar.

Uso:
    python scripts/auditar_homografia.py --config configs/processor_benja_emb.yaml
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking_data.processor import project_point  # noqa: E402

logger = logging.getLogger("auditar_h")

BANDA_ALTA = 700  # y_px por encima del cual 1 px vale 0,3-1 m


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_emb.yaml")
    p.add_argument(
        "--puntos", default="data/calibracion_benja/puntos_marcados_benja.json"
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(open(args.config))
    H = np.load(cfg["rutas"]["homografia"])
    puntos = json.load(open(args.puntos))

    px, metros = [], []
    for pt in puntos:
        if isinstance(pt, dict):
            xy = pt.get("pixel") or pt.get("px") or [pt.get("x"), pt.get("y")]
            mm = pt.get("metros") or pt.get("m") or [pt.get("mx"), pt.get("my")]
        else:
            xy, mm = pt[0], pt[1]
        px.append([float(xy[0]), float(xy[1])])
        metros.append([float(mm[0]), float(mm[1])])
    px, metros = np.array(px), np.array(metros)

    print(f"\n── REPARTO DE LOS {len(px)} PUNTOS DE CALIBRACIÓN ──\n")
    alta = px[:, 1] < BANDA_ALTA
    print(
        f"  banda ALTA (y_px < {BANDA_ALTA}, donde 1 px vale 0,3-1 m): "
        f"{alta.sum()} puntos"
    )
    print(f"  banda baja  (y_px >= {BANDA_ALTA}): {(~alta).sum()} puntos")
    print(f"  rango y_px: {px[:,1].min():.0f} – {px[:,1].max():.0f}")
    print(f"  rango x_px: {px[:,0].min():.0f} – {px[:,0].max():.0f}")

    print("\n── RESIDUOS: ¿está bien AJUSTADA la homografía? ──\n")
    cab = f"{'x_px':>7}{'y_px':>7}{'real (m)':>18}{'proyectado':>18}{'error m':>9}"
    print(cab)
    print("-" * len(cab))
    errores = []
    for (x, y), (mx, my) in zip(px, metros):
        a, b = project_point(x, y, H)
        e = float(np.hypot(a - mx, b - my))
        errores.append(e)
        marca = "  ← banda alta" if y < BANDA_ALTA else ""
        print(
            f"{x:>7.0f}{y:>7.0f}{f'({mx:.1f}, {my:.1f})':>18}"
            f"{f'({a:.1f}, {b:.1f})':>18}{e:>9.2f}{marca}"
        )
    errores = np.array(errores)
    print("-" * len(cab))
    print(
        f"  error medio {errores.mean():.2f} m · mediana {np.median(errores):.2f} m "
        f"· max {errores.max():.2f} m"
    )
    if alta.sum():
        print(f"  en la banda ALTA: mediana {np.median(errores[alta]):.2f} m")
    print(f"  en la banda baja:  mediana {np.median(errores[~alta]):.2f} m")

    print("\n── AMPLIFICACIÓN: lo que NO arregla recalibrar ──\n")
    print(f"{'y_px':>7}{'m por píxel vertical':>24}{'error de 3 px':>16}")
    print("-" * 47)
    for ypx in (600, 650, 700, 800, 900, 1000):
        a = project_point(960, ypx, H)
        b = project_point(960, ypx + 1, H)
        mpp = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        print(f"{ypx:>7}{mpp:>24.3f}{mpp*3:>15.2f} m")

    print("\n── VEREDICTO ──\n")
    umbral = 0.5
    if errores.max() < umbral:
        print(
            f"  El ajuste es BUENO en todos los puntos (max {errores.max():.2f} m).\n"
            "  Lo que se ve en el fondo es AMPLIFICACIÓN POR PERSPECTIVA, y eso\n"
            "  no lo arregla marcar más puntos: es geometría de la cámara.\n"
            "  Recalibrar no compensa."
        )
    else:
        print(
            f"  Hay puntos con error de hasta {errores.max():.2f} m: el ajuste NO\n"
            "  es uniforme. Marcar puntos donde faltan sí puede bajar el error."
        )


if __name__ == "__main__":
    main()
