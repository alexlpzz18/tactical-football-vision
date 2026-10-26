"""El detector del árbitro por observación (scripts/arbitro_por_observacion.py)."""

import importlib.util
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "apo", Path(__file__).resolve().parent.parent / "scripts/arbitro_por_observacion.py"
)
apo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apo)


def _img(color_hsv_torso, color_hsv_resto=(40, 150, 120)):
    import cv2

    hsv = np.zeros((100, 100, 3), np.uint8)
    hsv[:] = color_hsv_resto  # césped
    hsv[15:50, 30:70] = color_hsv_torso
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def test_chaleco_fluor_llena_el_torso_y_el_cesped_no_cuenta():
    caja = (0, 0, 100, 100)
    assert apo.fraccion_fluor(_img((62, 240, 220)), caja) > 0.9
    assert apo.fraccion_fluor(_img((62, 85, 200)), caja) > 0.9  # el chaleco a S baja
    assert apo.fraccion_fluor(_img((40, 150, 120)), caja) < 0.05  # todo césped
    assert apo.fraccion_fluor(_img((10, 230, 230)), caja) < 0.05  # naranja


def test_las_botas_lima_quedan_fuera_del_torso():
    import cv2

    hsv = np.zeros((100, 100, 3), np.uint8)
    hsv[:] = (10, 230, 230)
    hsv[90:100, :] = (62, 240, 230)  # botas
    assert (
        apo.fraccion_fluor(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR), (0, 0, 100, 100))
        == 0.0
    )


def test_umbral_elegido_es_el_menor_que_cumple():
    assert apo.umbral_elegido({0.05: 4, 0.10: 1, 0.15: 0}) == 0.10
    assert apo.umbral_elegido({0.05: 3, 0.10: 2}) is None
