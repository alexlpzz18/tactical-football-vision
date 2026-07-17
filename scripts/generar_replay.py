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

from src.report.replay_tactico import generar_replay  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/tracking/posiciones_v2.csv")
    parser.add_argument("--salida", default="outputs/replay.html")
    parser.add_argument("--largo", type=float, default=105.0)
    parser.add_argument("--ancho", type=float, default=68.0)
    parser.add_argument("--max-hueco", type=float, default=3.0)
    parser.add_argument("--titulo", default="Replay táctico")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    ruta = generar_replay(
        args.csv,
        args.salida,
        largo=args.largo,
        ancho=args.ancho,
        max_hueco_s=args.max_hueco,
        titulo=args.titulo,
    )
    print(f"✓ Replay en {ruta}")


if __name__ == "__main__":
    main()
