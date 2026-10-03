"""Validación de un vídeo al recibirlo (src/validacion_video.py)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.validacion_video import bordes_cortados, validar_video  # noqa: E402

VERDE = (60, 140, 50)  # BGR de césped
CIELO = (230, 200, 180)


def _imagen(cesped_hasta_bordes: bool):
    img = np.zeros((200, 300, 3), np.uint8)
    img[:] = CIELO
    if cesped_hasta_bordes:
        img[80:, :] = VERDE  # el césped llega a izquierda, derecha y abajo
    else:
        img[60:170, 40:260] = VERDE  # el campo entero, rodeado de otra cosa
    return img


def test_campo_cortado_por_los_bordes():
    assert set(bordes_cortados(_imagen(True))) == {"izquierda", "derecha", "abajo"}
    assert bordes_cortados(_imagen(False)) == []


def test_aviso_de_jugadores_pequenos_y_campo_cortado():
    v = validar_video([_imagen(True)] * 10, [20.0, 22.0, 24.0, 30.0])
    assert v.jugadores_pequenos and v.mediana_px == 23.0 and not v.campo_entero
    assert len(v.avisos) == 2


def test_sin_avisos_cuando_todo_esta_bien():
    v = validar_video([_imagen(False)] * 10, [40.0, 60.0, 80.0])
    assert not v.jugadores_pequenos and v.campo_entero and v.avisos == []


def test_sin_cajas_avisa():
    assert validar_video([_imagen(False)], []).avisos
