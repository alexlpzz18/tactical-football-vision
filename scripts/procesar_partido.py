#!/usr/bin/env python
"""CLI del procesador end-to-end: vídeo (o cachés) → CSV de posiciones + meta.

Uso:
    python scripts/procesar_partido.py [--config configs/processor.yaml]

Todo se decide en el yaml: pipeline nuevo/legacy, modo full/desde_cache,
perfil de tracking oficial/candidato. Ver configs/processor.yaml.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking_data.processor import procesar_partido  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/processor.yaml")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    df = procesar_partido(args.config)
    print(f"\n✓ {len(df)} posiciones exportadas")


if __name__ == "__main__":
    main()
