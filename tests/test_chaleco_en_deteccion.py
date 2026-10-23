"""La puntuación de chaleco dentro de la pasada de detección (docs/diagnostico_23oct_f.md, b. 1)."""

import copy

import cv2
import numpy as np
import pytest
import yaml

from src.team_classification.chaleco import fraccion_chaleco
from src.team_classification.color_classifier import extraer_color_torso
from src.tracking_data.processor import (
    _firma_de_deteccion,
    banda_chaleco,
    features_del_frame,
    puntuacion_chaleco,
)

BANDA = (38.0, 48.0, 112.0, 173.0)


def _frame_con_chaleco():
    """Un fotograma de césped con una persona de chaleco verde flúor y otra de naranja."""
    img = np.zeros((200, 200, 3), np.uint8)
    img[:] = cv2.cvtColor(np.uint8([[[55, 120, 120]]]), cv2.COLOR_HSV2BGR)[0, 0]
    img[40:120, 20:60] = cv2.cvtColor(np.uint8([[[44, 175, 247]]]), cv2.COLOR_HSV2BGR)[
        0, 0
    ]
    img[40:120, 120:160] = cv2.cvtColor(
        np.uint8([[[10, 220, 230]]]), cv2.COLOR_HSV2BGR
    )[0, 0]
    dets = [(0, 0, 20, 40, 60, 120, 0.9), (0, 0, 120, 40, 160, 120, 0.9)]
    return img, dets


def test_el_chaleco_puntua_y_el_naranja_no():
    img, dets = _frame_con_chaleco()
    assert fraccion_chaleco(img, dets[0], BANDA) > 0.9
    assert fraccion_chaleco(img, dets[1], BANDA) == 0.0


def test_features_del_frame_sin_banda_no_calcula_chaleco_y_el_color_no_cambia():
    img, dets = _frame_con_chaleco()
    c0, ch0 = features_del_frame(img, 7, dets, extraer_color_torso)
    c1, ch1 = features_del_frame(img, 7, dets, extraer_color_torso, banda=BANDA)
    assert ch0 == {}
    assert set(ch1) == {(7, 0), (7, 1)}
    assert set(c0) == set(c1) and all(np.array_equal(c0[k], c1[k]) for k in c0)


def test_la_banda_entra_en_la_firma_solo_si_esta_puesta():
    cfg = yaml.safe_load(open("configs/processor.yaml"))  # F11: chaleco_banda null
    assert banda_chaleco(cfg) is None
    assert "chaleco_banda" not in _firma_de_deteccion(cfg)
    con = copy.deepcopy(cfg)
    con["deteccion"]["chaleco_banda"] = list(BANDA)
    assert _firma_de_deteccion(con)["chaleco_banda"] == list(BANDA)
    with pytest.raises(ValueError):
        banda_chaleco({"deteccion": {"chaleco_banda": [1, 2]}})


def test_los_configs_f7_llevan_la_banda():
    for ruta in (
        "configs/processor_benja_parte_entera.yaml",
        "configs/processor_benja.yaml",
    ):
        assert banda_chaleco(yaml.safe_load(open(ruta))) == BANDA


def test_fuente_de_la_puntuacion_por_orden(tmp_path):
    import pickle

    aparte = tmp_path / "ch.pkl"
    pickle.dump({(1, 0): 0.5}, open(aparte, "wb"))
    assert puntuacion_chaleco({"rutas": {"cache_chaleco": str(aparte)}}, {}) == {
        (1, 0): 0.5
    }
    assert puntuacion_chaleco({"rutas": {}}, {"chaleco": {(2, 0): 0.1}}) == {
        (2, 0): 0.1
    }
    with pytest.raises(ValueError, match="chaleco_banda"):
        puntuacion_chaleco({"rutas": {}}, {"cache": []})
