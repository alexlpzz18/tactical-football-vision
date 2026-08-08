#!/usr/bin/env python
"""CLI del replay táctico 2D: CSV de posiciones → HTML autocontenido.

Uso:
    python scripts/generar_replay.py [--csv data/tracking/posiciones_v2.csv]
                                     [--salida outputs/replay.html]
                                     [--largo 105] [--ancho 68]
                                     [--titulo "Partido X"]
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.campo_modelo import cargar_modelo  # noqa: E402
from src.report.replay_tactico import generar_replay  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/tracking/posiciones_v2.csv")
    parser.add_argument("--salida", default="outputs/replay.html")
    parser.add_argument("--largo", type=float, default=None)
    parser.add_argument("--ancho", type=float, default=None)
    parser.add_argument("--max-hueco", type=float, default=3.0)
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
    parser.add_argument("--titulo", default="Replay táctico")
    parser.add_argument(
        "--max-edad-interp",
        type=float,
        default=0.6,
        help="Antigüedad máxima (s) de una posición interpolada respecto a "
        "una detección real para pintarla (credibilidad del replay)",
    )
    parser.add_argument(
        "--min-vida",
        type=float,
        default=2.0,
        help="Duración mínima (s) de detecciones reales para pintar una "
        "identidad (fuera el confeti de fragmentos)",
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
    ruta = generar_replay(
        args.csv,
        args.salida,
        modelo=modelo,
        max_edad_interp_s=args.max_edad_interp,
        min_vida_s=args.min_vida,
        largo=args.largo,
        ancho=args.ancho,
        max_hueco_s=args.max_hueco,
        titulo=args.titulo,
    )
    print(f"✓ Replay en {ruta}")


if __name__ == "__main__":
    main()
