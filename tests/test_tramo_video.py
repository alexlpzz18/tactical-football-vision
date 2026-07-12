"""Tests de unidad del recorte de tramo del modo full (_rango_de_frames).

El helper es puro (no necesita vídeo ni GPU): calcula el rango
[frame_ini, frame_fin) de frames ORIGINALES a procesar a partir de la
config de muestreo y los fps del vídeo.
"""

import pytest

from src.tracking_data.processor import _rango_de_frames


def test_sin_limites_procesa_todo():
    assert _rango_de_frames({"sample_every": 3}, fps=25.0) == (0, None)


def test_tramo_min5_60s_reproduce_el_tramo_de_validacion():
    """min 5 durante 60 s a 25 fps → frames globales [7500, 9000)."""
    cfg = {"sample_every": 3, "tramo": {"min_ini": 5.0, "dur_seg": 60.0}}
    assert _rango_de_frames(cfg, fps=25.0) == (7500, 9000)


def test_max_frames_solo():
    cfg = {"sample_every": 3, "max_frames": 1500}
    assert _rango_de_frames(cfg, fps=25.0) == (0, 1500)


def test_tramo_y_max_frames_manda_el_mas_corto():
    """max_frames acota DENTRO del tramo (fin relativo al inicio del tramo)."""
    cfg = {
        "sample_every": 3,
        "tramo": {"min_ini": 5.0, "dur_seg": 60.0},
        "max_frames": 500,
    }
    assert _rango_de_frames(cfg, fps=25.0) == (7500, 8000)
    # y si max_frames es más largo que el tramo, manda el tramo
    cfg["max_frames"] = 99999
    assert _rango_de_frames(cfg, fps=25.0) == (7500, 9000)


def test_fps_no_entero_redondea():
    """A 29.97 fps el inicio cae en el frame entero más cercano."""
    cfg = {"sample_every": 3, "tramo": {"min_ini": 1.0, "dur_seg": 10.0}}
    ini, fin = _rango_de_frames(cfg, fps=29.97)
    assert ini == round(60 * 29.97)  # 1798
    assert fin == ini + round(10 * 29.97)  # +300


def test_tramo_nulo_equivale_a_ausente():
    """tramo: null en el yaml no debe romper (dict vacío u omitido)."""
    assert _rango_de_frames({"sample_every": 3, "tramo": None}, fps=25.0) == (0, None)


def test_tramo_fraccional():
    """min_ini admite fracciones de minuto (p. ej. 2.5 = min 2:30)."""
    cfg = {"sample_every": 3, "tramo": {"min_ini": 2.5, "dur_seg": 30.0}}
    ini, fin = _rango_de_frames(cfg, fps=25.0)
    assert ini == pytest.approx(3750)
    assert fin == pytest.approx(3750 + 750)
