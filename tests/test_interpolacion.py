"""Tests de la interpolación de huecos dentro de identidades (Tarea 3a)."""

import numpy as np

from src.tracking.field_tracker import Tracklet
from src.tracking.interpolacion import interpolar_identidad, interpolar_identidades

DT = 0.12
# Caché sintético: frames 0,3,6,... con t = k*DT
FRAMES_TS = [(k * 3, k * DT) for k in range(30)]


def _tracklet(tid, observaciones):
    """Crea un tracklet a partir de [(frame_idx, t, x, y), ...]."""
    f0, t0, x0, y0 = observaciones[0]
    tr = Tracklet(tid, t0, np.array([x0, y0]), det_idx=0, frame_idx=f0)
    for f, t, x, y in observaciones[1:]:
        tr.anadir(t, np.array([x, y]), det_idx=0, frame_idx=f)
    return tr


def test_rellena_hueco_lineal():
    """Un hueco de 3 frames se rellena con posiciones sobre la recta."""
    # Observado en frames 0,3 y luego 15,18: faltan 6,9,12
    tr = _tracklet(
        1,
        [
            (0, 0.0, 0.0, 10.0),
            (3, DT, 0.6, 10.0),
            (15, 5 * DT, 3.0, 10.0),
            (18, 6 * DT, 3.6, 10.0),
        ],
    )
    tray = interpolar_identidad([tr], FRAMES_TS, max_hueco=6.0)
    frames = [f for f, _, _ in tray]
    assert frames == [0, 3, 6, 9, 12, 15, 18]
    interpoladas = {f: pos for f, pos, real in tray if not real}
    assert set(interpoladas) == {6, 9, 12}
    # Movimiento uniforme a 5 m/s en x → la interpolación cae en la recta
    np.testing.assert_allclose(interpoladas[6], [1.2, 10.0], atol=1e-9)
    np.testing.assert_allclose(interpoladas[9], [1.8, 10.0], atol=1e-9)
    np.testing.assert_allclose(interpoladas[12], [2.4, 10.0], atol=1e-9)


def test_nunca_extrapola():
    """No se generan posiciones antes de la primera ni después de la última."""
    tr = _tracklet(1, [(6, 2 * DT, 1.0, 5.0), (9, 3 * DT, 1.5, 5.0)])
    tray = interpolar_identidad([tr], FRAMES_TS, max_hueco=6.0)
    frames = [f for f, _, _ in tray]
    assert min(frames) == 6 and max(frames) == 9


def test_hueco_mayor_que_max_no_se_rellena():
    """Huecos por encima de max_hueco quedan vacíos."""
    tr = _tracklet(1, [(0, 0.0, 0.0, 5.0), (27, 9 * DT, 5.4, 5.0)])
    # hueco = 1.08 s; con max_hueco=0.5 no debe rellenar nada
    tray = interpolar_identidad([tr], FRAMES_TS, max_hueco=0.5)
    assert [f for f, _, _ in tray] == [0, 27]


def test_interpola_el_hueco_del_cosido():
    """El hueco ENTRE dos tracklets de la misma identidad también se rellena."""
    tr_a = _tracklet(1, [(0, 0.0, 0.0, 5.0), (3, DT, 0.3, 5.0)])
    tr_b = _tracklet(2, [(12, 4 * DT, 1.2, 5.0), (15, 5 * DT, 1.5, 5.0)])
    tray = interpolar_identidad([tr_a, tr_b], FRAMES_TS, max_hueco=6.0)
    frames = [f for f, _, _ in tray]
    assert frames == [0, 3, 6, 9, 12, 15]
    reales = [f for f, _, real in tray if real]
    assert reales == [0, 3, 12, 15]


def test_interpolar_identidades_multiples():
    tr_1 = _tracklet(1, [(0, 0.0, 0.0, 5.0), (9, 3 * DT, 0.9, 5.0)])
    tr_2 = _tracklet(2, [(0, 0.0, 20.0, 30.0), (3, DT, 20.3, 30.0)])
    trayectorias = interpolar_identidades([[tr_1], [tr_2]], FRAMES_TS, max_hueco=6.0)
    assert len(trayectorias) == 2
    assert [f for f, _, _ in trayectorias[0]] == [0, 3, 6, 9]
    assert [f for f, _, _ in trayectorias[1]] == [0, 3]
