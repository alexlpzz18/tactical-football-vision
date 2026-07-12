"""Tests de la Etapa B (cosido de tracklets) con casos sintéticos."""

import numpy as np

from src.tracking.field_tracker import Tracklet
from src.tracking.stitcher import ParametrosCosido, TrackletStitcher


def _tracklet_recto(tid, t0, x0, vx, n_frames, dt=0.12, y=10.0):
    """Crea un tracklet en línea recta a velocidad vx (m/s) por y constante."""
    tr = Tracklet(tid, t0, np.array([x0, y]), 0, int(t0 / dt) * 3)
    for k in range(1, n_frames):
        t = t0 + k * dt
        tr.anadir(t, np.array([x0 + vx * k * dt, y]), 0, int(t / dt) * 3)
    return tr


def test_cose_tracklet_partido():
    """Un tracklet partido artificialmente en dos debe volver a unirse."""
    # Jugador a 3 m/s: fragmento A (t=0..1.08) y fragmento B (t=2.28..3.36),
    # hueco de 1.2 s. B empieza donde A "habría llegado" extrapolando.
    tr_a = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=10)
    hueco = 1.2
    x_b = tr_a.pos[-1][0] + 3.0 * hueco
    tr_b = _tracklet_recto(2, t0=tr_a.ts[-1] + hueco, x0=x_b, vx=3.0, n_frames=10)

    identidades = TrackletStitcher().coser([tr_a, tr_b])
    assert len(identidades) == 1
    assert [tr.id for tr in identidades[0]] == [1, 2]


def test_no_cose_hueco_demasiado_largo():
    """Con hueco > max_hueco los fragmentos deben quedar separados."""
    tr_a = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=10)
    hueco = 7.0  # > max_hueco = 6.0 s
    tr_b = _tracklet_recto(
        2, t0=tr_a.ts[-1] + hueco, x0=tr_a.pos[-1][0] + 3.0 * hueco, vx=3.0, n_frames=10
    )
    identidades = TrackletStitcher().coser([tr_a, tr_b])
    assert len(identidades) == 2


def test_no_cose_posicion_incompatible():
    """B empieza lejísimos de donde A podría estar → no coser."""
    tr_a = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=10)
    tr_b = _tracklet_recto(2, t0=tr_a.ts[-1] + 1.0, x0=60.0, vx=3.0, n_frames=10)
    identidades = TrackletStitcher().coser([tr_a, tr_b])
    assert len(identidades) == 2


def test_veto_de_color():
    """Compatibles por movimiento pero con color incompatible → veto."""
    tr_a = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=10)
    hueco = 1.2
    tr_b = _tracklet_recto(
        2, t0=tr_a.ts[-1] + hueco, x0=tr_a.pos[-1][0] + 3.0 * hueco, vx=3.0, n_frames=10
    )
    # Features de color a distancia 2.0 > color_max_dist = 1.2 → veto
    color_medio = {1: np.zeros(4), 2: np.array([1.0, 1.0, 1.0, 1.0])}
    identidades = TrackletStitcher().coser([tr_a, tr_b], color_medio)
    assert len(identidades) == 2

    # Control: con colores idénticos SÍ debe coser
    color_igual = {1: np.zeros(4), 2: np.zeros(4)}
    identidades = TrackletStitcher().coser([tr_a, tr_b], color_igual)
    assert len(identidades) == 1


def test_sin_conflictos_en_union_golosa():
    """Tres fragmentos consecutivos del mismo jugador → UNA cadena A→B→C."""
    tr_a = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=10)
    tr_b = _tracklet_recto(
        2, t0=tr_a.ts[-1] + 0.5, x0=tr_a.pos[-1][0] + 3.0 * 0.5, vx=3.0, n_frames=10
    )
    tr_c = _tracklet_recto(
        3, t0=tr_b.ts[-1] + 0.5, x0=tr_b.pos[-1][0] + 3.0 * 0.5, vx=3.0, n_frames=10
    )
    identidades = TrackletStitcher().coser([tr_c, tr_a, tr_b])  # orden revuelto
    assert len(identidades) == 1
    assert [tr.id for tr in identidades[0]] == [1, 2, 3]


def test_parametros_desde_dict():
    p = ParametrosCosido.desde_dict(
        {
            "max_hueco": 5.0,
            "tol_base": 1.0,
            "tol_por_seg": 2.0,
            "peso_hueco": 0.2,
            "color_max_dist": 1.0,
            "peso_color": 0.1,
        }
    )
    assert p.max_hueco == 5.0
    assert p.peso_color == 0.1
