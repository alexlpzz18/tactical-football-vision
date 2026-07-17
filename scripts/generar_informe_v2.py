#!/usr/bin/env python
"""CLI del informe táctico v2: CSV de posiciones → HTML por equipo.

Uso:
    python scripts/generar_informe_v2.py [--csv data/tracking/posiciones_v2.csv]
                                         [--salida outputs/informe_v2.html]
                                         [--partido "Partido X"]
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.report.informe_v2 import generar_informe_v2  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/tracking/posiciones_v2.csv")
    parser.add_argument("--salida", default="outputs/informe_v2.html")
    parser.add_argument("--largo", type=float, default=105.0)
    parser.add_argument("--ancho", type=float, default=68.0)
    parser.add_argument("--partido", default="Partido")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    ruta = generar_informe_v2(
        args.csv, args.salida, largo=args.largo, ancho=args.ancho, partido=args.partido
    )
    print(f"✓ Informe v2 en {ruta}")


if __name__ == "__main__":
    main()
