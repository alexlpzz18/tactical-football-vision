"""Término de color en la asociación de ByteTrack (flag `tracking.coste_color`, apagado).

docs/diagnostico_22oct_g.md, bloque B.
"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from src.tracking.asociacion_bytetrack import (
    ParametrosCosteColor,
    _iou_maximo,
    asociar_con_bytetrack,
)

R = Path(__file__).resolve().parent.parent


def _cache(n_frames=30):
    """Dos jugadores quietos y separados, con colores muy distintos."""
    cache, colores = [], {}
    for f in range(n_frames):
        cache.append(
            {
                "frame_idx": f,
                "t": f * 0.1,
                "dets": [
                    (10.0, 10.0, 100, 100, 120, 140, 0.9),
                    (30.0, 10.0, 400, 100, 420, 140, 0.9),
                ],
            }
        )
        colores[(f, 0)] = np.eye(256)[3] * (1 + 0.01 * (f % 2))
        colores[(f, 1)] = np.eye(256)[200]
    return cache, colores


def test_apagado_en_los_configs_de_produccion():
    for ruta in ("configs/tracking_benja.yaml", "configs/tracking.yaml"):
        assert yaml.safe_load(open(R / ruta))["coste_color"]["activo"] is False
    assert ParametrosCosteColor().activo is False


def test_iou_maximo():
    cajas = np.array([[0, 0, 10, 10], [5, 0, 15, 10], [100, 100, 110, 110]], float)
    iou = _iou_maximo(cajas)
    assert iou[0] == pytest.approx(1 / 3) and iou[2] == 0.0


def test_encendido_sin_colores_da_error():
    cache, _c = _cache()
    with pytest.raises(ValueError):
        asociar_con_bytetrack(
            cache, 30.0, 3, params_color=ParametrosCosteColor(activo=True)
        )


def test_encender_el_interruptor_cambia_el_resultado():
    """Guarda de COMPORTAMIENTO: con una puerta de color imposible, las pistas se rompen."""
    cache, colores = _cache()
    base = asociar_con_bytetrack(cache, 30.0, 3)
    igual = asociar_con_bytetrack(
        cache,
        30.0,
        3,
        colores=colores,
        separacion=1.0,
        params_color=ParametrosCosteColor(),
    )
    assert len(igual) == len(base) == 2  # apagado: lo de siempre
    roto = asociar_con_bytetrack(
        cache,
        30.0,
        3,
        colores=colores,
        separacion=1.0,
        params_color=ParametrosCosteColor(activo=True, umbral_rel=-1.0),
    )
    assert len(roto) > len(base)
