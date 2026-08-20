"""Tests de la cota blanda de plantilla (fusión de identidades entrelazadas)."""

import numpy as np

from src.tracking.cota_plantilla import fusionar_hasta_cota
from src.tracking.field_tracker import Tracklet

DT = 0.12


def _identidad_frames(tid, frames, x_de_t, y=20.0):
    """Identidad con observaciones en los frames dados, x = x_de_t(t)."""
    f0 = frames[0]
    tr = Tracklet(tid, f0 * DT / 3, np.array([x_de_t(f0 * DT / 3), y]), 0, f0)
    for f in frames[1:]:
        t = f * DT / 3
        tr.anadir(t, np.array([x_de_t(t), y]), 0, f)
    return [tr]


def test_fusiona_entrelazadas_compatibles():
    """Dos identidades que se alternan sobre la MISMA trayectoria → una."""
    recta = lambda t: 10.0 + 2.0 * t  # noqa: E731
    a = _identidad_frames(1, [0, 6, 12, 18, 24], recta)
    b = _identidad_frames(2, [3, 9, 15, 21, 27], recta)  # en los huecos de a
    resultado = fusionar_hasta_cota([a, b], cota=1, coste_max=1.5)
    assert len(resultado) == 1


def test_no_fusiona_trayectorias_distintas():
    """Entrelazadas en tiempo pero lejos en el campo → no fusionar."""
    a = _identidad_frames(1, [0, 6, 12, 18, 24], lambda t: 10.0 + 2.0 * t, y=20.0)
    b = _identidad_frames(2, [3, 9, 15, 21, 27], lambda t: 10.0 + 2.0 * t, y=45.0)
    resultado = fusionar_hasta_cota([a, b], cota=1, coste_max=1.5)
    assert len(resultado) == 2  # cota blanda: no se fuerza


def test_respeta_la_cota():
    """Si la concurrencia ya está en cota, no se toca nada."""
    recta = lambda t: 10.0 + 2.0 * t  # noqa: E731
    a = _identidad_frames(1, [0, 6, 12], recta)
    b = _identidad_frames(2, [30, 36, 42], recta)  # sin solape temporal
    resultado = fusionar_hasta_cota([a, b], cota=2, coste_max=1.5)
    assert len(resultado) == 2


def test_exclusion_por_coobservacion():
    """Pares co-observados >= k frames no se fusionan (variante 3j, en off)."""
    recta = lambda t: 10.0 + 2.0 * t  # noqa: E731
    a = _identidad_frames(1, [0, 3, 6, 9, 12], recta)
    b = _identidad_frames(2, [0, 3, 6, 9, 12], recta)  # co-observada SIEMPRE
    con_excl = fusionar_hasta_cota([a, b], cota=1, coste_max=1.5, excl_coobservacion=3)
    sin_excl = fusionar_hasta_cota([a, b], cota=1, coste_max=1.5)
    assert len(con_excl) == 2  # co-observados: jugadores distintos, no fusionar
    assert len(sin_excl) == 1  # sin la exclusión sí se fusionarían
