"""Tests de la base nueva: ByteTrack + cosido por pureza.

El criterio que ordena estos tests es el hallazgo del banco (10-ago-2026):
fragmentar es un error recuperable, mezclar dos jugadores no lo es. Por
eso casi todos comprueban que el cosido PREFIERE NO UNIR cuando hay duda,
no que una lo máximo posible.
"""

import numpy as np
import pytest

from src.tracking.asociacion_bytetrack import (
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cosido_pureza import (
    ParametrosCosidoPureza,
    coser_por_pureza,
)
from src.tracking.field_tracker import Tracklet

DT = 0.12


def _identidad(tid, k_ini, n, x0, y0, vx=0.0, vy=0.0, det_base=0):
    """Fragmento recto que empieza en el frame k_ini (paso de 3 frames)."""
    t0 = k_ini * DT
    tracklet = Tracklet(tid, t0, np.array([x0, y0]), det_base, 100 + 3 * k_ini)
    for j in range(1, n):
        t = (k_ini + j) * DT
        tracklet.anadir(
            t,
            np.array([x0 + vx * j * DT, y0 + vy * j * DT]),
            det_base,
            100 + 3 * (k_ini + j),
        )
    return [tracklet]


# ── la asociación ─────────────────────────────────────────────────────


def _cache_sintetico(n_frames=20, n_personas=3):
    """Personas que se cruzan el campo en línea recta, sin ambigüedad."""
    cache = []
    for k in range(n_frames):
        dets = []
        for p in range(n_personas):
            x = 200 + p * 300 + k * 8
            y = 400 + p * 120
            dets.append((x / 20.0, y / 20.0, x, y, x + 30, y + 70, 0.9))
        cache.append({"frame_idx": 100 + 3 * k, "t": k * DT, "dets": dets})
    return cache


def test_bytetrack_sigue_a_cada_persona_con_una_identidad():
    cache = _cache_sintetico()
    identidades = asociar_con_bytetrack(cache, fps=25.0, sample=3)
    assert len(identidades) == 3
    for identidad in identidades:
        assert sum(len(tr.ts) for tr in identidad) >= 15


def test_las_posiciones_salen_del_cache_en_metros():
    """ByteTrack empareja en píxeles, pero lo que guarda son NUESTROS metros."""
    cache = _cache_sintetico()
    del_cache = {
        (e["frame_idx"], round(d[0], 6), round(d[1], 6))
        for e in cache
        for d in e["dets"]
    }
    for identidad in asociar_con_bytetrack(cache, fps=25.0, sample=3):
        for tracklet in identidad:
            for pos, (frame, _det) in zip(tracklet.pos, tracklet.det_idxs):
                assert (frame, round(pos[0], 6), round(pos[1], 6)) in del_cache


def test_el_det_idx_es_exacto_y_no_se_repite_en_un_frame():
    """Va pegado a la detección, no reconstruido por la geometría de la caja."""
    cache = _cache_sintetico()
    vistos = {}
    for identidad in asociar_con_bytetrack(cache, fps=25.0, sample=3):
        for tracklet in identidad:
            for frame, det_idx in tracklet.det_idxs:
                assert det_idx not in vistos.setdefault(frame, set())
                vistos[frame].add(det_idx)


def test_los_parametros_se_declaran_en_segundos():
    p = ParametrosByteTrack.desde_dict({"buffer_perdido_s": 3.0, "inventado": 1})
    assert p.buffer_perdido_s == 3.0  # y la clave desconocida no revienta


# ── el cosido por pureza ──────────────────────────────────────────────


def test_cose_dos_trozos_del_mismo_jugador():
    """Caso limpio: uno acaba, el otro sigue justo donde tocaba."""
    a = _identidad(1, 0, 10, 20.0, 30.0, vx=2.0)
    b = _identidad(2, 14, 10, 20.0 + 2.0 * 14 * DT, 30.0, vx=2.0)
    unidas = coser_por_pureza([a, b], colores=None, dt=DT)
    assert len(unidas) == 1


def test_no_cose_si_hay_DOS_candidatos_igual_de_buenos():
    """El corazón del criterio: ante el empate, fragmentar.

    Dos jugadores simétricos a la misma distancia del final de A. Unir a
    cualquiera de ellos es tirar una moneda, y acertar la mitad de las
    veces es exactamente cómo se fabrica una quimera.
    """
    a = _identidad(1, 0, 10, 20.0, 30.0)
    b = _identidad(2, 14, 10, 21.0, 31.0)
    c = _identidad(3, 14, 10, 21.0, 29.0)
    unidas = coser_por_pureza([a, b, c], colores=None, dt=DT)
    assert len(unidas) == 3, "con dos candidatos empatados no debe coser ninguno"


def test_sin_veto_de_ambiguedad_ese_mismo_caso_si_se_cose():
    """Contraprueba: el veto es lo que decide, no otra cosa del camino."""
    a = _identidad(1, 0, 10, 20.0, 30.0)
    b = _identidad(2, 14, 10, 21.0, 31.0)
    c = _identidad(3, 14, 10, 21.0, 29.0)
    unidas = coser_por_pureza(
        [a, b, c],
        colores=None,
        params=ParametrosCosidoPureza(margen_ambiguedad=0.0),
        dt=DT,
    )
    assert len(unidas) == 2


def test_no_cose_dos_fragmentos_que_coexisten():
    """Nadie está en dos sitios a la vez: son dos personas."""
    a = _identidad(1, 0, 20, 20.0, 30.0)
    b = _identidad(2, 10, 20, 21.0, 30.5)  # solapa en el tiempo con a
    unidas = coser_por_pureza([a, b], colores=None, dt=DT)
    assert len(unidas) == 2


def test_no_cose_saltos_fisicamente_imposibles():
    """40 m en medio segundo no los hace nadie."""
    a = _identidad(1, 0, 10, 20.0, 30.0)
    b = _identidad(2, 14, 10, 60.0, 30.0)
    unidas = coser_por_pureza([a, b], colores=None, dt=DT)
    assert len(unidas) == 2


def test_el_color_veta_una_union_geometricamente_perfecta():
    """Equipaciones distintas: aunque encaje el movimiento, no es la misma."""
    a = _identidad(1, 0, 10, 20.0, 30.0, vx=2.0, det_base=0)
    b = _identidad(2, 14, 10, 20.0 + 2.0 * 14 * DT, 30.0, vx=2.0, det_base=1)
    naranja = np.zeros(256)
    naranja[13] = 1.0
    blanco = np.zeros(256)
    blanco[200] = 1.0
    colores = {}
    for tr in a[0].det_idxs:
        colores[tr] = naranja
    for tr in b[0].det_idxs:
        colores[tr] = blanco

    assert len(coser_por_pureza([a, b], colores=None, dt=DT)) == 1  # sin color, cose
    assert len(coser_por_pureza([a, b], colores=colores, dt=DT)) == 2  # con color, no


def test_no_hay_cota_de_plantilla():
    """Con 40 jugadores separados no se fuerza ninguna fusión hacia 23.

    Es la lección explícita de la migración: el número de identidades es
    un proxy, no un objetivo.
    """
    identidades = [
        _identidad(i, 0, 20, 5.0 + 2.0 * i, 10.0 + (i % 5)) for i in range(40)
    ]
    assert len(coser_por_pureza(identidades, colores=None, dt=DT)) == 40


def test_una_sola_identidad_no_rompe():
    a = _identidad(1, 0, 10, 20.0, 30.0)
    assert coser_por_pureza([a], colores=None, dt=DT) == [a]


def test_desactivado_devuelve_lo_mismo():
    a = _identidad(1, 0, 10, 20.0, 30.0, vx=2.0)
    b = _identidad(2, 14, 10, 20.0 + 2.0 * 14 * DT, 30.0, vx=2.0)
    params = ParametrosCosidoPureza(activo=False)
    assert len(coser_por_pureza([a, b], colores=None, params=params, dt=DT)) == 2


@pytest.mark.parametrize("clave,valor", [("max_hueco", 9.0), ("v_max_salto", 3.0)])
def test_los_parametros_se_leen_del_dict(clave, valor):
    p = ParametrosCosidoPureza.desde_dict({clave: valor, "no_existe": 0})
    assert getattr(p, clave) == valor
