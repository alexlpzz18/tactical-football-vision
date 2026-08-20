"""Tests del recorte de la herramienta de etiquetado."""

import importlib.util
import sys
from pathlib import Path

import numpy as np

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "etiquetar_equipos_gt.py"
spec = importlib.util.spec_from_file_location("etiquetar_equipos_gt", RUTA)
mod = importlib.util.module_from_spec(spec)
sys.modules["etiquetar_equipos_gt"] = mod
spec.loader.exec_module(mod)


def test_recorte_marca_al_jugador():
    """El recorte lleva holgura y a menudo entra otro jugador: hay que
    señalar cuál es el de la pregunta (lo pidió Alex etiquetando)."""
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    crop = mod.recortar(frame, (80, 80, 100, 130))
    assert crop is not None
    # El fondo era negro puro; el rectángulo tiene que haber pintado algo.
    assert crop.max() > 0, "no se ha dibujado la marca del jugador"


def test_recorte_no_modifica_el_frame_original():
    """Dibujar la marca no debe ensuciar el frame, que se reutiliza para
    los demás jugadores del mismo instante."""
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    mod.recortar(frame, (80, 80, 100, 130))
    assert frame.max() == 0, "la marca se ha pintado sobre el frame compartido"


def test_recorte_fuera_de_rango():
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    assert mod.recortar(frame, (60, 60, 70, 70)) is None


def test_pinta_a_los_vecinos_en_otro_color():
    """El caso que rompió la v1: en el recorte entran dos personas y hay
    que ver cuál es la de la pregunta (azul) y cuál el vecino (gris)."""
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    objetivo = (100, 100, 120, 150)
    vecino = (118, 100, 138, 150)
    crop = mod.recortar(frame, objetivo, [objetivo, vecino])
    assert crop is not None
    colores = {tuple(c) for fila in crop for c in fila if tuple(c) != (0, 0, 0)}
    assert mod.AZUL_OSCURO in colores, "falta la caja del jugador (azul oscuro)"
    assert mod.GRIS_OTROS in colores, "falta la caja del vecino (gris)"


def test_sin_cajas_del_frame_sigue_marcando_al_jugador():
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    crop = mod.recortar(frame, (100, 100, 120, 150))
    colores = {tuple(c) for fila in crop for c in fila if tuple(c) != (0, 0, 0)}
    assert mod.AZUL_OSCURO in colores
