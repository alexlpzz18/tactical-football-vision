"""Tests de la puerta de apariencia en la re-entrada."""

import numpy as np

from src.tracking.field_tracker import Tracklet
from src.tracking.puerta_reentrada import (
    ParametrosPuertaReentrada,
    aplicar_puerta_reentrada,
)

DT = 0.12


def _identidad(frames, colores_dict, color, base=0.0):
    """Una identidad con observaciones en `frames` y un color dado."""
    tr = None
    for k, f in enumerate(frames):
        if tr is None:
            tr = Tracklet(1, f * DT, np.array([base + k, 0.0]), 0, f)
        else:
            tr.anadir(f * DT, np.array([base + k, 0.0]), 0, f)
        v = np.zeros(256)
        v[color] = 1.0
        colores_dict[(f, 0)] = v
    return [tr]


def test_inactiva_no_toca_nada():
    colores = {}
    ident = _identidad(range(10), colores, 3)
    fuera = aplicar_puerta_reentrada([ident], colores, DT)
    assert len(fuera) == 1


def test_corta_cuando_el_color_cambia_tras_una_perdida():
    """El caso que motiva la etapa: se pierde y vuelve siendo otro."""
    colores = {}
    ident = _identidad(range(6), colores, 3)
    # Reaparece 30 frames después (3,6 s) con un color muy distinto
    segunda = _identidad(range(36, 42), colores, 200, base=50.0)
    ident = ident + segunda
    fuera = aplicar_puerta_reentrada(
        [ident], colores, DT, ParametrosPuertaReentrada(activa=True)
    )
    assert len(fuera) == 2, "debería partirse en dos identidades"


def test_no_corta_si_el_color_casa():
    """Perderse no basta: si vuelve con el mismo color, no se toca."""
    colores = {}
    ident = _identidad(range(6), colores, 3) + _identidad(
        range(36, 42), colores, 3, base=50.0
    )
    fuera = aplicar_puerta_reentrada(
        [ident], colores, DT, ParametrosPuertaReentrada(activa=True)
    )
    assert len(fuera) == 1


def test_se_abstiene_sin_firma_fiable():
    """Con menos observaciones que `min_obs_firma` no se corta a ciegas."""
    colores = {}
    ident = _identidad(range(2), colores, 3) + _identidad(
        range(36, 38), colores, 200, base=50.0
    )
    fuera = aplicar_puerta_reentrada(
        [ident], colores, DT, ParametrosPuertaReentrada(activa=True, min_obs_firma=3)
    )
    assert len(fuera) == 1, "sin firma fiable la puerta se abstiene"


def test_no_pierde_observaciones():
    colores = {}
    ident = _identidad(range(6), colores, 3) + _identidad(
        range(36, 42), colores, 200, base=50.0
    )
    antes = sum(len(t.pos) for t in ident)
    fuera = aplicar_puerta_reentrada(
        [ident], colores, DT, ParametrosPuertaReentrada(activa=True)
    )
    assert sum(len(t.pos) for ident2 in fuera for t in ident2) == antes
