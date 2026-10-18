"""Puerta de continuidad EN PÍXELES: un salto imposible no es un vuelo.

21-sep-2026 (docs/balon_sin_alas.md, BACKLOG 28). `detectar_fases_aereas` marca
como aéreo cualquier salto por velocidad proyectada, así que un CAMBIO DE
CANDIDATO (dos detecciones que no son el mismo balón) se disfrazaba de vuelo y
`preparar_para_replay` dibujaba una recta entre los dos. En píxeles se separan:
los 44 "vuelos" imposibles saltaban una mediana de 539 px contra 33 de los 651
físicos, y 1.000 px/s caza 38 de 44 tocando al 1,4 % de los físicos.
"""

import numpy as np

from src.balon.tracking_balon import (
    ParametrosBalon,
    id_de_tramo,
    preparar_balon,
    preparar_para_replay,
)

PASO_S = 0.0667


def _serie(posiciones, aereo=None, huecos_s=None):
    huecos_s = huecos_s or {}
    tray, tiempos, t = [], {}, 0.0
    for i, p in enumerate(posiciones):
        t += PASO_S + huecos_s.get(i, 0.0)
        tiempos[i * 2] = t
        tray.append((i * 2, np.array(p, dtype=float), 14.0, 0.9))
    return tray, list(aereo or [False] * len(posiciones)), tiempos


def _centros(tray, px):
    """{frame: (cx, cy)} con `px` = lista de centros en píxeles, uno por muestra."""
    return {t[0]: tuple(c) for t, c in zip(tray, px)}


def _vuelo(px_despues):
    """6 de suelo · 3 aéreas · 6 de suelo, con el aterrizaje en `px_despues`."""
    posiciones = [(10.0, 20.0)] * 6 + [(25.0, 20.0)] * 3 + [(40.0, 20.0)] * 6
    aereo = [False] * 6 + [True] * 3 + [False] * 6
    tray, aereo, tiempos = _serie(posiciones, aereo)
    px = [(500.0, 600.0)] * 6 + [(700.0, 500.0)] * 3 + [px_despues] * 6
    return tray, aereo, tiempos, _centros(tray, px)


def test_un_vuelo_cuyos_extremos_saltan_en_pixeles_NO_se_dibuja():
    """Extremos a 1.500 px en ~0,27 s (5.500 px/s): dos objetos, no un vuelo."""
    tray, aereo, tiempos, centros = _vuelo((2000.0, 300.0))
    salida, cortes = preparar_balon(tray, aereo, tiempos, ParametrosBalon(), centros)
    assert not [f for f in salida if f[2]], "se dibujó una recta entre dos objetos"
    assert cortes == {tray[9][0]}, "el aterrizaje debe abrir un tramo nuevo"
    assert sum(1 for f in salida if f[3]) == 12, "las filas de suelo se conservan"


def test_un_vuelo_real_se_sigue_dibujando():
    """Control: extremos a 60 px (220 px/s): un vuelo de verdad, con su recta."""
    tray, aereo, tiempos, centros = _vuelo((560.0, 600.0))
    salida, cortes = preparar_balon(tray, aereo, tiempos, ParametrosBalon(), centros)
    assert len([f for f in salida if f[2]]) == 3
    assert cortes == set()


def test_un_salto_entre_dos_filas_de_suelo_contiguas_corta_el_tramo():
    posiciones = [(10.0, 20.0)] * 6 + [(10.5, 20.0)] * 6
    tray, aereo, tiempos = _serie(posiciones)
    px = [(500.0, 600.0)] * 6 + [(1800.0, 200.0)] * 6  # 1.300 px en 0,067 s
    salida, cortes = preparar_balon(
        tray, aereo, tiempos, ParametrosBalon(), _centros(tray, px)
    )
    assert cortes == {tray[6][0]}


def test_el_suavizado_no_cruza_un_corte():
    posiciones = [(10.0, 20.0)] * 6 + [(30.0, 20.0)] * 6
    tray, aereo, tiempos = _serie(posiciones)
    px = [(500.0, 600.0)] * 6 + [(1800.0, 200.0)] * 6
    salida, _cortes = preparar_balon(
        tray, aereo, tiempos, ParametrosBalon(), _centros(tray, px)
    )
    crudas = {f: p for f, p, _a, _c in tray}
    for f, p, _aereo, _real in salida:
        assert np.linalg.norm(p - crudas[f]) < 0.5


def test_no_se_rellena_a_traves_de_un_corte():
    """Hueco de 0,27 s con el balón parado: se rellenaría, pero hay un cambio de balón."""
    fps = 29.97
    frames = [0, 2, 4, 6, 14, 16, 18, 20]  # faltan 8, 10, 12 (muestreados sin balón)
    tiempos = {f: f / fps for f in range(0, 22, 2)}
    tray = [(f, np.array([30.0, 20.0]), 14.0, 0.9) for f in frames]
    aereo = [False] * len(tray)
    px = {f: (500.0, 600.0) if f < 10 else (1800.0, 200.0) for f in frames}
    con_puerta, cortes = preparar_balon(tray, aereo, tiempos, ParametrosBalon(), px)
    sin_puerta = preparar_para_replay(tray, aereo, tiempos, ParametrosBalon())
    assert cortes == {14}
    assert any(not f[3] and not f[2] for f in sin_puerta), "el control ya no rellena"
    assert not any(not f[3] and not f[2] for f in con_puerta)


def test_sin_pixeles_la_puerta_no_actua_y_el_resultado_es_el_de_siempre():
    tray, aereo, tiempos, _centros_ = _vuelo((2000.0, 300.0))
    salida, cortes = preparar_balon(tray, aereo, tiempos, ParametrosBalon())
    assert cortes == set()
    igual = preparar_para_replay(tray, aereo, tiempos, ParametrosBalon())
    assert [(f, a, r) for f, _p, a, r in salida] == [(f, a, r) for f, _p, a, r in igual]
    assert all(np.allclose(p, q) for (_f, p, *_), (_g, q, *_) in zip(salida, igual))
    assert len([f for f in salida if f[2]]) == 3


def test_el_umbral_es_un_parametro_y_manda():
    tray, aereo, tiempos, centros = _vuelo((2000.0, 300.0))
    apagada = ParametrosBalon(vel_max_px_s=1e9)
    salida, cortes = preparar_balon(tray, aereo, tiempos, apagada, centros)
    assert cortes == set() and len([f for f in salida if f[2]]) == 3


def test_los_ids_de_tramo_son_distintos_y_no_pisan_los_del_balon():
    ids = {id_de_tramo(k) for k in range(5)} | {id_de_tramo(k, True) for k in range(5)}
    assert len(ids) == 10
    assert id_de_tramo(0) == -1 and id_de_tramo(0, True) == -2
    assert all(i <= -1 for i in ids)


def test_la_puerta_de_un_vuelo_admite_extremos_a_mas_de_0_3_s():
    """Un vuelo dura más que el hueco entre dos filas de suelo contiguas (0,3 s).

    12 muestras aéreas (0,8 s) y extremos a 1.500 px (1.800 px/s): sigue siendo
    un cambio de balón. Con el límite del par (0,3 s) no se detectaría.
    """
    posiciones = [(10.0, 20.0)] * 6 + [(25.0, 20.0)] * 12 + [(40.0, 20.0)] * 6
    aereo = [False] * 6 + [True] * 12 + [False] * 6
    tray, aereo, tiempos = _serie(posiciones, aereo)
    px = [(500.0, 600.0)] * 6 + [(700.0, 500.0)] * 12 + [(2000.0, 300.0)] * 6
    salida, cortes = preparar_balon(
        tray, aereo, tiempos, ParametrosBalon(), _centros(tray, px)
    )
    assert cortes == {tray[18][0]}
    assert not [f for f in salida if f[2]]
