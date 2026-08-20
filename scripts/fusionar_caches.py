#!/usr/bin/env python
"""Fusiona los cachés parciales de varios tramos en uno solo.

Flujo para procesar un partido entero sin sesiones de Colab de 3 horas:

  1. `scripts/planificar_tramos.py` dice qué tramos hay que lanzar y
     escribe un config por tramo.
  2. Cada sesión de Colab corre UNO de esos configs en modo `full` y deja
     su caché parcial en Drive.
  3. Este script los une, y a partir de ahí todo el trabajo local va con
     `--modo desde_cache` como siempre.

Uso:
    python scripts/fusionar_caches.py \\
        --detecciones data/tramos/cache_t*.pkl \\
        --colores     data/tramos/colores_t*.pkl \\
        --salida-detecciones data/tracking_benja/cache_detecciones_benja.pkl \\
        --salida-colores     data/tracking_benja/cache_colores_benja.pkl
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking.fusion_caches import (  # noqa: E402
    fusionar_desde_rutas,
    huecos_de_cobertura,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detecciones", nargs="+", required=True)
    parser.add_argument("--colores", nargs="*", default=None)
    parser.add_argument("--salida-detecciones", required=True)
    parser.add_argument("--salida-colores", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    detecciones, colores = fusionar_desde_rutas(args.detecciones, args.colores)

    Path(args.salida_detecciones).parent.mkdir(parents=True, exist_ok=True)
    with open(args.salida_detecciones, "wb") as f:
        pickle.dump(detecciones, f)
    print(f"✓ Detecciones en {args.salida_detecciones}")

    if colores is not None and args.salida_colores:
        with open(args.salida_colores, "wb") as f:
            pickle.dump(colores, f)
        print(f"✓ Colores en {args.salida_colores}")

    cache = detecciones["cache"]
    dt = detecciones["sample"] / detecciones["fps"]
    print(
        f"  {len(cache)} frames, del {cache[0]['frame_idx']} al "
        f"{cache[-1]['frame_idx']} "
        f"({(cache[-1]['frame_idx'] - cache[0]['frame_idx']) / detecciones['fps'] / 60:.1f} "
        f"min de partido, dt={dt:.3f} s)"
    )
    huecos = huecos_de_cobertura(cache, detecciones["sample"])
    if huecos:
        print(f"  ⚠ {len(huecos)} hueco(s): falta procesar algún tramo")
        for a, b in huecos[:5]:
            print(f"      frames {a} → {b}")
    else:
        print("  Sin huecos: la cobertura temporal es continua")


if __name__ == "__main__":
    main()
