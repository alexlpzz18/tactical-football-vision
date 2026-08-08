#!/usr/bin/env python
"""CLI del informe táctico v2: CSV de posiciones → HTML por equipo.

Uso:
    python scripts/generar_informe_v2.py [--csv data/tracking/posiciones_v2.csv]
                                         [--salida outputs/informe_v2.html]
                                         [--partido "Partido X"]
                                         [--con-ia]

--con-ia rellena la sección "Análisis táctico con IA" llamando a la API
de Anthropic (necesita ANTHROPIC_API_KEY en .env; ver .env.example). Sin
el flag o sin clave, el informe sale igual con un placeholder.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.campo import ANCHO_M, LARGO_M  # noqa: E402
from src.report.informe_v2 import generar_informe_v2  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/tracking/posiciones_v2.csv")
    parser.add_argument("--salida", default="outputs/informe_v2.html")
    parser.add_argument("--largo", type=float, default=LARGO_M)
    parser.add_argument("--ancho", type=float, default=ANCHO_M)
    parser.add_argument("--partido", default="Partido")
    parser.add_argument("--categoria", default="fútbol base")
    parser.add_argument(
        "--con-ia",
        action="store_true",
        help="Rellenar la sección de análisis táctico con IA (API de Anthropic)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    ruta = generar_informe_v2(
        args.csv,
        args.salida,
        largo=args.largo,
        ancho=args.ancho,
        partido=args.partido,
        categoria=args.categoria,
        con_ia=args.con_ia,
    )
    print(f"✓ Informe v2 en {ruta}")


if __name__ == "__main__":
    main()
