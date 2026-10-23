"""La puntuación de CHALECO del árbitro por detección: la emisión de la pista Viterbi.

Fracción de los píxeles del torso de la caja que caen en la banda HSV del chaleco, SIN la máscara
anti-césped (la máscara borra el chaleco entero: docs/diagnostico_23oct_a.md).

Es la ÚNICA implementación del repo. La usan la pasada aparte (`scripts/cache_chaleco.py`) y la
pasada de detección del modo `full` (`processor.detectar_y_cachear`), para que las dos den el mismo
número sobre los mismos píxeles (docs/diagnostico_23oct_f.md, bloque 1).
"""

from __future__ import annotations

import cv2
import numpy as np

# La franja del torso dentro de la caja (fracción de alto y de ancho), la del 23-oct (a)
TORSO_FILAS, TORSO_COLS = (0.12, 0.45), (0.15, 0.85)


def torso_hsv(img: np.ndarray, caja) -> np.ndarray:
    """Píxeles HSV (N × 3) del torso de la caja (x1, y1, x2, y2 enteros), SIN máscara."""
    x1, y1, x2, y2 = caja
    h, w = y2 - y1, x2 - x1
    ya, yb = int(y1 + TORSO_FILAS[0] * h), int(y1 + TORSO_FILAS[1] * h)
    xa, xb = int(x1 + TORSO_COLS[0] * w), int(x1 + TORSO_COLS[1] * w)
    ya, xa = max(ya, 0), max(xa, 0)
    rec = img[slice(ya, max(yb, ya + 1)), slice(xa, max(xb, xa + 1))]
    if rec.size == 0:
        return np.zeros((0, 3))
    return cv2.cvtColor(rec, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)


def en_banda(px: np.ndarray, banda) -> np.ndarray:
    """¿Cada píxel HSV cae en la banda (H0, H1, S0, V0)?"""
    h0, h1, s0, v0 = banda
    return (px[:, 0] >= h0) & (px[:, 0] <= h1) & (px[:, 1] >= s0) & (px[:, 2] >= v0)


def fraccion_chaleco(img: np.ndarray, det, banda) -> float:
    """La puntuación de UNA detección (mx, my, x1, y1, x2, y2, conf): 0 si el torso está vacío.

    La caja se redondea a enteros igual que lo hacía la pasada aparte.
    """
    px = torso_hsv(img, [int(round(float(v))) for v in det[2:6]])
    return float(en_banda(px, banda).mean()) if len(px) else 0.0


def puntuaciones_del_frame(img: np.ndarray, frame_idx: int, dets, banda) -> dict:
    """{(frame_idx, det_idx): fracción} para todas las detecciones de un frame."""
    return {(frame_idx, j): fraccion_chaleco(img, d, banda) for j, d in enumerate(dets)}
