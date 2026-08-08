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

from src.campo_modelo import cargar_modelo  # noqa: E402
from src.report.informe_v2 import generar_informe_v2  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/tracking/posiciones_v2.csv")
    parser.add_argument("--salida", default="outputs/informe_v2.html")
    parser.add_argument("--largo", type=float, default=None)
    parser.add_argument("--ancho", type=float, default=None)
    parser.add_argument("--partido", default="Partido")
    parser.add_argument(
        "--campo",
        default=None,
        help="Modelo de campo a dibujar: f11 (defecto) o f7. Fija también "
        "las dimensiones salvo que se pasen --largo/--ancho.",
    )
    parser.add_argument(
        "--config-campo",
        default=None,
        help="YAML del campo (p. ej. configs/campo_benja.yaml). Tiene "
        "prioridad sobre --campo.",
    )
    parser.add_argument("--categoria", default="fútbol base")
    parser.add_argument(
        "--con-ia",
        action="store_true",
        help="Rellenar la sección de análisis táctico con IA (API de Anthropic)",
    )
    args = parser.parse_args()
    modelo = None
    if args.config_campo or args.campo:
        modelo = cargar_modelo(
            nombre=None if args.config_campo else args.campo,
            config=args.config_campo,
        )
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    ruta = generar_informe_v2(
        args.csv,
        args.salida,
        largo=args.largo,
        ancho=args.ancho,
        modelo=modelo,
        partido=args.partido,
        categoria=args.categoria,
        con_ia=args.con_ia,
    )
    print(f"✓ Informe v2 en {ruta}")


if __name__ == "__main__":
    main()
