"""Máscara por posición de la feature de color (flag apagado por defecto)."""

import cv2
import numpy as np

from src.team_classification.color_classifier import extraer_color_torso
from src.team_classification.mascara_posicion import rango_cesped_del_frame


def _bgr(hsv_color, forma=(60, 30)):
    hsv = np.zeros((*forma, 3), np.uint8)
    hsv[:] = hsv_color
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


CHALECO = (46, 175, 247)  # medido en píxeles el 19-oct
CESPED = (55, 80, 120)


def test_sin_rango_es_la_feature_de_siempre_y_borra_el_chaleco():
    crop = _bgr(CHALECO)
    assert np.array_equal(
        extraer_color_torso(crop), extraer_color_torso(crop, rango_cesped=None)
    )
    assert extraer_color_torso(crop).sum() == 0  # la máscara fija se lo come entero


def test_con_el_rango_del_cesped_el_chaleco_se_conserva_y_el_cesped_no():
    hsv_c = cv2.cvtColor(_bgr(CESPED), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    rango = (hsv_c.min(0) - 2, hsv_c.max(0) + 2)
    assert extraer_color_torso(_bgr(CHALECO), rango_cesped=rango).sum() > 0
    assert extraer_color_torso(_bgr(CESPED), rango_cesped=rango).sum() == 0


def test_rango_del_frame_desde_cajas_vacias():
    frame = np.zeros((400, 800, 3), np.uint8)
    frame[:] = _bgr(CESPED, (1, 1))[0, 0]
    cajas = [(380, 200, 400, 260)]  # una caja; las vacías se buscan a los lados
    rango = rango_cesped_del_frame(
        frame, cajas, lambda u, v: (30.0, 20.0), (62.0, 40.0)
    )
    assert rango is not None
    lo, hi = rango
    hsv = cv2.cvtColor(frame[:1, :1], cv2.COLOR_BGR2HSV)[0, 0]
    assert np.all(lo <= hsv) and np.all(hsv <= hi)
    # fuera del campo, no hay césped que medir
    assert (
        rango_cesped_del_frame(frame, cajas, lambda u, v: (90.0, 20.0), (62.0, 40.0))
        is None
    )


def test_el_flag_esta_apagado_por_defecto_en_los_configs():
    import yaml

    for ruta in ("configs/processor_benja_parte_entera.yaml", "configs/processor.yaml"):
        cfg = yaml.safe_load(open(ruta))
        assert cfg.get("deteccion", {}).get("mascara_color", "verde") == "verde"
