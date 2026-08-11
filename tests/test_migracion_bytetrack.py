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


# ── porteros cruzados (bug del benjamín, 11-ago-2026) ─────────────────


def _en(x, y, n=30, tid=1):
    tr = Tracklet(tid, 0.0, np.array([x, y]), 0, 100)
    for k in range(1, n):
        tr.anadir(k * DT, np.array([x, y]), 0, 100 + 3 * k)
    return [tr]


def _escena_f7():
    """Equipo A defiende x=0 (sus jugadores empujan hacia x=62)."""
    from src.campo_modelo import MODELO_F7
    from src.team_classification.porteros import ReglaPorteros

    identidades, equipos = [], {}

    def anadir(x, y, etiqueta):
        identidades.append(_en(x, y, tid=len(identidades) + 1))
        equipos[len(identidades)] = etiqueta

    for x in (28.0, 32.0, 35.0, 38.0):
        anadir(x, 20.0, "A")  # A ataca hacia x=62 → media ~33
    for x in (34.0, 38.0, 42.0, 46.0):
        anadir(x, 20.0, "B")  # B ataca hacia x=0 → media ~40
    # Los porteros visten distinto, así que el clasificador de color les
    # pone un equipo casi al azar. Aquí, como en el benjamín, cada uno
    # cae del lado equivocado: el de la portería lejana como "A" y el de
    # la cercana como "B". Con sus posiciones extremas, esos dos votos
    # basura bastan para invertir el orden de las medias.
    anadir(58.0, 20.0, "A")
    anadir(4.0, 20.0, "B")
    return identidades, equipos, MODELO_F7, ReglaPorteros.desde_modelo(MODELO_F7)


def test_los_lados_se_deducen_de_las_posiciones():
    """El equipo que ataca hacia x=62 defiende la portería x=0."""
    from src.team_classification.porteros import deducir_lados

    identidades, equipos, modelo, regla = _escena_f7()
    assert deducir_lados(
        equipos, identidades, modelo.largo, regla=regla, ancho=modelo.ancho
    ) == ("A", "B")


def test_el_voto_del_portero_no_invierte_el_resultado():
    """Regresión directa del bug del benjamín.

    Un portero viste distinto, así que su etiqueta de color es azarosa; y
    como vive en un extremo, ese voto basura arrastra la media de quien
    le toque y da la vuelta al signo.
    """
    from src.team_classification.porteros import deducir_lados

    identidades, equipos, modelo, regla = _escena_f7()
    sin_excluir = deducir_lados(
        equipos, identidades, modelo.largo, regla=None, ancho=modelo.ancho
    )
    assert sin_excluir == ("B", "A")  # invertido: el fallo que se arregló
    con_regla = deducir_lados(
        equipos, identidades, modelo.largo, regla=regla, ancho=modelo.ancho
    )
    assert con_regla == ("A", "B")


def test_el_publico_del_fondo_no_invierte_el_resultado():
    """Segunda causa del bug: esto corre ANTES de la regla de staff, y en
    el benjamín había gente proyectada a x=71, 80 y 95 sobre 62 m."""
    from src.team_classification.porteros import deducir_lados

    identidades, equipos, modelo, regla = _escena_f7()
    for x in (71.0, 80.0, 95.0):
        identidades.append(_en(x, 50.0, tid=len(identidades) + 1))
        equipos[len(identidades)] = "A"  # público mal clasificado como A

    assert deducir_lados(
        equipos, identidades, modelo.largo, regla=regla, ancho=modelo.ancho
    ) == ("A", "B")


def test_sin_separacion_clara_no_se_decide():
    """Ante la duda, manda lo configurado (y se avisa)."""
    from src.campo_modelo import MODELO_F7
    from src.team_classification.porteros import deducir_lados

    identidades, equipos = [], {}
    for i, etiqueta in enumerate(["A", "B"] * 4):
        identidades.append(_en(31.0, 20.0, tid=i + 1))
        equipos[i + 1] = etiqueta
    assert (
        deducir_lados(equipos, identidades, MODELO_F7.largo, ancho=MODELO_F7.ancho)
        is None
    )
