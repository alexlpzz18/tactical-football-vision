#!/usr/bin/env python
"""Caché de color v2 (pecho HS + brillo + pantalón) recalculado en el Mac, SIN GPU.

docs/plan_equipos_v2.md. Las cajas ya están en el caché de detecciones; solo hace falta volver a
recortar cada detección sobre su fotograma y pasarle la feature v2. Se lee con el ffmpeg de línea
de comandos (CLAUDE.md: nunca cv2.VideoCapture para medir color).

CONTROL antes de fiarse (CLAUDE.md, «reproducir ≥ 99 % de la caché de producción»): los primeros
256 valores de la v2 son la v1 bit a bit, así que en los primeros `--control` fotogramas tienen que
coincidir con el caché de colores de producción. Si no llega al 99 %, se para.

Uso:
    python scripts/colores_v2_mac.py --cache data/tracking_alevinb/cache_alevinb_p1.pkl \\
        --colores data/tracking_alevinb/colores_alevinb_p1.pkl \\
        --video data/raw/alevinb_p1.mp4 --salida data/tracking_alevinb/colores_v2_alevinb_p1.pkl
"""

import argparse
import logging
import pickle
import sys
import time
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.team_classification.feature_v2 import extraer_color_torso_v2  # noqa: E402
from src.tracking_data.processor import features_del_frame  # noqa: E402
from src.utils.video_ffmpeg import leer_frames_ffmpeg  # noqa: E402

logger = logging.getLogger("colores_v2")
MIN_COINCIDENCIA = 0.99


def coincidencia_v1(nuevos: dict, produccion: dict, tol: float = 1e-6) -> float:
    """Fracción de detecciones cuyo bloque v1 (256) coincide con el caché de producción."""
    comunes = [k for k in nuevos if k in produccion]
    if not comunes:
        return 0.0
    iguales = sum(
        np.allclose(nuevos[k][:256], np.asarray(produccion[k])[:256], atol=tol)
        for k in comunes
    )
    return iguales / len(comunes)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument(
        "--colores", type=Path, required=True, help="caché v1 de producción (control)"
    )
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--control", type=int, default=50)
    a = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )

    cache = pickle.load(open(a.cache, "rb"))["cache"]
    produccion = pickle.load(open(a.colores, "rb"))
    por_frame = {e["frame_idx"]: e["dets"] for e in cache}
    frames = sorted(por_frame)
    nuevos, t0 = {}, time.time()
    # imagen ORIGINAL (k1 = k2 = 0 en el alevín B): el fotograma no se corrige
    for n, (f, img) in enumerate(leer_frames_ffmpeg(a.video, frames), start=1):
        colores, _ = features_del_frame(img, f, por_frame[f], extraer_color_torso_v2)
        nuevos.update(colores)
        if n == a.control:
            ok = coincidencia_v1(nuevos, produccion)
            logger.info(
                "CONTROL: bloque v1 igual al de producción en %.1f %%", 100 * ok
            )
            if ok < MIN_COINCIDENCIA:
                raise SystemExit(
                    f"El bloque v1 coincide solo en {100 * ok:.1f} % (< 99 %): el recorte o el "
                    "decodificador no son los de producción. No se sigue."
                )
        if n % 1000 == 0:
            ritmo = (time.time() - t0) / n
            logger.info(
                "%d/%d frames · %.0f ms/frame · faltan ~%.0f min",
                n, len(frames), 1000 * ritmo, (len(frames) - n) * ritmo / 60,
            )  # fmt: skip
    pickle.dump(nuevos, open(a.salida, "wb"))
    logger.info("✓ %s: %d features v2", a.salida, len(nuevos))


if __name__ == "__main__":
    main()
