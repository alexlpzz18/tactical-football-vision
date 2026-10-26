#!/usr/bin/env python
"""Caché de CHALECO: por detección, la fracción de píxeles del torso en la banda del árbitro.

docs/diagnostico_23oct_c.md. Es la emisión del seguimiento del árbitro (`arbitro_viterbi.py`). Se
calcula como la caché de color: una vez, desde el vídeo, con el ffmpeg CLI (los mismos píxeles que
producción; CLAUDE.md) y la misma corrección de distorsión del modo `full`, SIN máscara anti-césped
(la máscara borra el chaleco entero: AUC 0,50, 23-oct a).

Uso:
    python scripts/cache_chaleco.py --config configs/processor_benja_parte_entera.yaml \\
        --salida outputs/diagnostico_23oct_c/cache_chaleco_benja_p1.pkl
    # Villaviciosa (Colab): --config configs/processor.yaml --banda H0 H1 S0 V0
"""

import argparse
import importlib.util
import pickle
import sys
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
BANDA_BENJA = (
    38.0,
    48.0,
    112.0,
    173.0,
)  # medida el 23-oct (a) sobre el árbitro del benjamín


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def calcular(config: Path, banda=BANDA_BENJA) -> dict:
    """{(frame, det): fracción de píxeles del torso en la banda} para todo el caché."""
    from src.tracking.cache_io import cargar_cache

    from src.team_classification.chaleco import puntuaciones_del_frame

    ch = _mod("diag23a_chaleco")
    cfg = yaml.safe_load(open(config))
    cache = cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    dets = {e["frame_idx"]: e["dets"] for e in cache}
    out = {}
    for f, img in ch.leer(R / cfg["rutas"]["video"], [f for f in dets if dets[f]], cfg):
        out.update(puntuaciones_del_frame(img, f, dets[f], banda))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument(
        "--banda",
        nargs=4,
        type=float,
        default=None,
        help="por defecto, deteccion.chaleco_banda del config (o la del benjamín)",
    )
    args = ap.parse_args()
    banda = args.banda
    if banda is None:
        from src.tracking_data.processor import banda_chaleco

        banda = banda_chaleco(yaml.safe_load(open(args.config))) or BANDA_BENJA
    res = calcular(Path(args.config), tuple(banda))
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    pickle.dump(res, open(args.salida, "wb"))
    v = np.array(list(res.values()))
    print(f"{len(res)} detecciones; fracción > 0 en el {100 * (v > 0).mean():.1f} %")


if __name__ == "__main__":
    main()
