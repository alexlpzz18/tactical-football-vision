"""Tests de la exclusión espacial dura (fusión de identidades duplicadas)."""

import numpy as np

from src.tracking.exclusion_espacial import fusionar_identidades_duplicadas
from src.tracking.field_tracker import Tracklet

DT = 0.12


def _identidad(tid, x0, y, vx=2.0, n=10, t0=0.0, ruido_y=0.0):
    tr = Tracklet(tid, t0, np.array([x0, y]), 0, int(t0 / DT) * 3)
    for k in range(1, n):
        t = t0 + k * DT
        tr.anadir(t, np.array([x0 + vx * k * DT, y + ruido_y]), 0, int(t / DT) * 3)
    return [tr]


def test_fusiona_duplicado_colocalizado():
    """Dos identidades pegadas (0.3 m) todo el rato → una sola."""
    a = _identidad(1, 10.0, 20.0)
    b = _identidad(2, 10.0, 20.3)  # misma trayectoria, 0.3 m al lado
    resultado = fusionar_identidades_duplicadas(
        [a, b], dist_max=0.7, min_frames_comunes=3
    )
    assert len(resultado) == 1
    # Fusión deduplicada: una observación por frame (ambas cubrían los mismos 10)
    assert sum(len(tr) for tr in resultado[0]) == 10


def test_no_fusiona_jugadores_separados():
    a = _identidad(1, 10.0, 20.0)
    b = _identidad(2, 10.0, 25.0)  # a 5 m: otro jugador
    resultado = fusionar_identidades_duplicadas(
        [a, b], dist_max=0.7, min_frames_comunes=3
    )
    assert len(resultado) == 2


def test_cruce_puntual_no_fusiona():
    """Dos jugadores que se cruzan: mediana de distancias alta → no fusión."""
    a = _identidad(1, 0.0, 20.0, vx=4.0, n=20)  # va hacia la derecha
    b = _identidad(2, 9.0, 20.0, vx=-4.0, n=20)  # va hacia la izquierda
    resultado = fusionar_identidades_duplicadas(
        [a, b], dist_max=0.7, min_frames_comunes=3
    )
    assert len(resultado) == 2


def test_sin_solape_temporal_no_fusiona():
    """Fragmentos secuenciales (sin frames comunes) no se tocan aquí."""
    a = _identidad(1, 10.0, 20.0, n=10, t0=0.0)
    b = _identidad(2, 12.4, 20.0, n=10, t0=2.4)  # empieza cuando a acabó
    resultado = fusionar_identidades_duplicadas(
        [a, b], dist_max=0.7, min_frames_comunes=3
    )
    assert len(resultado) == 2


def test_fusion_transitiva():
    """A≈B y B≈C → un solo grupo {A, B, C}."""
    a = _identidad(1, 10.0, 20.0)
    b = _identidad(2, 10.0, 20.3)
    c = _identidad(3, 10.0, 20.6)
    resultado = fusionar_identidades_duplicadas(
        [a, b, c], dist_max=0.7, min_frames_comunes=3
    )
    assert len(resultado) == 1
    assert sum(len(tr) for tr in resultado[0]) == 10  # deduplicado por frame
