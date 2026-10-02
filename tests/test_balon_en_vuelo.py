"""El balón EN VUELO que tira la plausibilidad vuelve por continuidad (docs/balon_en_vuelo.md).

La homografía es de suelo: un balón alto se proyecta más allá de la portería
y el filtro de plausibilidad lo quita. Se readmite SOLO si la pista sale del
suelo hacia él y vuelve al suelo desde él, en poco tiempo. Y aun así sus
posiciones NO son posiciones: van como aéreas, con es_real=0.
"""

import numpy as np

from src.balon.tracking_balon import (
    ParametrosBalon,
    detectar_fases_aereas,
    marcar_vuelos_readmitidos,
    preparar_balon,
    seleccionar_balon_activo,
)

DT = 1 / 15.0
H = np.array([[0.01, 0.0, 0.0], [0.0, 0.01, 0.0], [0.0, 0.0, 1.0]])  # 100 px/m
P = ParametrosBalon()


def _det(px, py, mx=None, my=None, lado=36.0):
    m = (px / 100.0 if mx is None else mx, py / 100.0 if my is None else my)
    return (m[0], m[1], px - lado / 2, py - lado / 2, px + lado / 2, py + lado / 2, 0.8)


def _elegir(suelo, fuera, params=P):
    frames = set(suelo) | set(fuera)
    tiempos = {f: f * DT for f in range(max(frames) + 1)}
    jug = {f: [(d[0], d[1]) for d in suelo.get(f, [])] for f in frames}
    return seleccionar_balon_activo(
        suelo,
        jug,
        params,
        tiempos,
        H,
        posiciones_staff={},
        dimensiones_campo=(62.0, 40.0),
        detecciones_fuera_de_campo=fuera,
    )


def _vuelo(n_vuelo=10, vuelta=True):
    """Suelo 10 frames, vuelo de n_vuelo frames (proyecta a 100-500 m) y suelo otra vez."""
    suelo, fuera = {}, {}
    for f in range(10):
        suelo[f] = [_det(500 + 10 * f, 600)]
    for k in range(n_vuelo):
        f = 10 + k
        # la proyección de suelo de un balón alto salta decenas de metros por frame
        # parábola de 200 px de altura máxima, sea cual sea la duración: así el
        # vuelo largo falla por DURAR, no por saltar más que la puerta
        altura_px = 800 * k * (n_vuelo - k) / n_vuelo**2
        fuera[f] = [_det(600 + 10 * k, 600 - altura_px, mx=100.0 + 40.0 * k, my=20.0)]
    for k in range(10):
        f = 10 + n_vuelo + k
        x = (
            600 + 10 * n_vuelo + 10 * k if vuelta else 1800
        )  # sin vuelta: aterriza lejísimos
        suelo[f] = [_det(x, 600)]
    return suelo, fuera


def test_un_vuelo_que_sale_y_vuelve_al_suelo_se_readmite():
    suelo, fuera = _vuelo()
    elegido = _elegir(suelo, fuera)
    assert all(f in elegido for f in fuera)


def test_sin_vuelta_al_suelo_no_se_readmite():
    """La basura del fondo: la pista entra por continuidad pero no vuelve."""
    suelo, fuera = _vuelo(vuelta=False)
    elegido = _elegir(suelo, fuera)
    assert not any(f in elegido for f in fuera)


def test_un_readmitido_no_puede_abrir_pista():
    _, fuera = _vuelo()
    suelo = {0: [_det(100, 900)]}  # un único punto de suelo lejos de todo
    elegido = _elegir(suelo, fuera)
    assert not any(f in elegido for f in fuera)


def test_un_vuelo_demasiado_largo_no_se_readmite():
    suelo, fuera = _vuelo(n_vuelo=45)  # 3 s > vuelo_max_s
    assert not any(f in _elegir(suelo, fuera) for f in fuera)


def test_el_interruptor_apagado_no_readmite_nada():
    from dataclasses import replace

    suelo, fuera = _vuelo()
    elegido = _elegir(suelo, fuera, replace(P, readmitir_vuelos=False))
    assert not any(f in elegido for f in fuera)


def test_los_vuelos_readmitidos_NO_son_posiciones_reales():
    """Su posición en metros es basura (100-500 m): tienen que salir aéreos y es_real=0."""
    suelo, fuera = _vuelo()
    elegido = _elegir(suelo, fuera)
    tiempos = {f: f * DT for f in range(60)}
    tray = [(f, np.array(d[:2]), d[5] - d[3], d[6]) for f, d in sorted(elegido.items())]
    aereo = detectar_fases_aereas(tray, tiempos, P)
    assert marcar_vuelos_readmitidos(tray, aereo, suelo) >= 0
    por_frame = dict(zip([t[0] for t in tray], aereo))
    assert all(por_frame[f] for f in fuera)
    filas, _cortes = preparar_balon(tray, aereo, tiempos, P)
    reales = {f: es_real for f, _pos, _a, es_real in filas}
    assert not any(reales.get(f) for f in fuera)
    # y ninguna fila dibujada cae en la proyección absurda
    assert all(pos[0] < 62 for _f, pos, _a, _r in filas)


def test_la_basura_readmitida_no_le_quita_el_sitio_al_balon_de_suelo():
    """Sin la regla de "no abre pista", una basura del fondo detectada en TODOS
    los frames ganaría por cobertura al balón de suelo (visto uno de cada dos),
    el filtro de ida y vuelta la borraría después, y se perdería también el
    balón: el frame quedaría vacío."""
    suelo, fuera = {}, {}
    for f in range(40):
        fuera[f] = [_det(1500, 300, mx=200.0 + 37.0 * f, my=20.0)]  # quieta en píxeles
        if f % 2 == 0:
            suelo[f] = [_det(400 + 6 * f, 700)]
    elegido = _elegir(suelo, fuera)
    assert all(f in elegido and elegido[f][2] < 1000 for f in suelo)
