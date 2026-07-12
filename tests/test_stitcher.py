"""Tests de la Etapa B (cosido de tracklets) con casos sintéticos."""

import numpy as np
import pytest

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


def test_filtrar_identidades_cortas():
    """Se conservan identidades con sustancia total; las aisladas cortas no."""
    from src.tracking.stitcher import filtrar_identidades_cortas

    larga = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=10)
    corta_cosida = Tracklet(2, 0.0, np.array([0.0, 0.0]), 0, 0)  # 1 frame
    corta_aislada = Tracklet(3, 5.0, np.array([50.0, 50.0]), 0, 0)  # 1 frame
    identidades = [[larga, corta_cosida], [corta_aislada]]
    filtradas = filtrar_identidades_cortas(identidades, min_frames_total=3)
    assert len(filtradas) == 1
    assert filtradas[0][0].id == 1  # la cadena con el tracklet largo sobrevive


def test_rescate_un_corto_se_cose_a_la_cadena():
    """Un tracklet de 1 frame en la prolongación de una cadena queda cosido."""
    tr_a = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=10)
    hueco = 0.5
    corto = Tracklet(
        2, tr_a.ts[-1] + hueco, np.array([tr_a.pos[-1][0] + 3.0 * hueco, 10.0]), 0, 0
    )
    identidades = TrackletStitcher().coser([tr_a, corto])
    assert len(identidades) == 1
    assert [tr.id for tr in identidades[0]] == [1, 2]


def test_fusionar_identidad():
    """La fusión concatena observaciones en orden y recalcula la velocidad."""
    from src.tracking.stitcher import fusionar_identidad

    tr_a = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=5)
    tr_b = _tracklet_recto(2, t0=1.0, x0=3.0, vx=3.0, n_frames=5)
    fusionado = fusionar_identidad([tr_a, tr_b])
    assert len(fusionado) == 10
    assert fusionado.ts == sorted(fusionado.ts)
    assert fusionado.id == 1  # conserva el id del primer tracklet
    # Velocidad ~3 m/s en x tras recorrer toda la trayectoria
    assert fusionado.vel[0] == pytest.approx(3.0, abs=0.2)


def test_global_resuelve_conflicto_que_el_goloso_bloquea():
    """Escenario: A y B acaban a la vez; X es buen sucesor de ambos, Y solo
    de A. El goloso une A→X (lo más barato) y deja a B sin continuación;
    el global prefiere A→Y + B→X (coste total menor que romper la cadena)."""
    tr_a = _tracklet_recto(
        1, t0=0.0, x0=7.0, vx=3.0, n_frames=10, y=10.0
    )  # acaba (10.2, 10)
    tr_b = _tracklet_recto(
        2, t0=0.0, x0=7.0, vx=3.0, n_frames=10, y=13.0
    )  # acaba (10.2, 13)
    hueco = 0.5
    t1 = tr_a.ts[-1] + hueco
    x1 = tr_a.pos[-1][0] + 3.0 * hueco  # donde "deberían" estar tras el hueco
    tr_x = _tracklet_recto(
        3, t0=t1, x0=x1, vx=3.0, n_frames=10, y=10.9
    )  # cerca de A, alcanzable por B
    tr_y = _tracklet_recto(
        4, t0=t1, x0=x1, vx=3.0, n_frames=10, y=8.4
    )  # solo alcanzable por A

    tracklets = [tr_a, tr_b, tr_x, tr_y]

    golosas = TrackletStitcher(ParametrosCosido(metodo="goloso")).coser(tracklets)
    globales = TrackletStitcher(ParametrosCosido(metodo="global")).coser(tracklets)

    # Goloso: A→X y B queda suelto → 3 identidades
    assert len(golosas) == 3
    # Global: A→Y + B→X → 2 identidades, y B recupera su continuación
    assert len(globales) == 2
    cadenas = sorted([tr.id for tr in ident] for ident in globales)
    assert cadenas == [[1, 4], [2, 3]]


def test_global_igual_que_goloso_sin_conflictos():
    """Sin conflictos, ambos métodos deben dar las mismas cadenas."""
    tr_a = _tracklet_recto(1, t0=0.0, x0=0.0, vx=3.0, n_frames=10)
    tr_b = _tracklet_recto(
        2, t0=tr_a.ts[-1] + 0.5, x0=tr_a.pos[-1][0] + 1.5, vx=3.0, n_frames=10
    )
    for metodo in ("goloso", "global"):
        ids = TrackletStitcher(ParametrosCosido(metodo=metodo)).coser([tr_a, tr_b])
        assert len(ids) == 1
        assert [tr.id for tr in ids[0]] == [1, 2]
