"""Tests del tracking de balón.

El balón no es "un jugador pequeño": puede haber varios, vuela (y
entonces la homografía deja de aplicar) y lo que importa de verdad son
los contactos. Estos tests fijan esas tres cosas.
"""

import numpy as np

from src.balon.tracking_balon import (
    ParametrosBalon,
    detectar_contactos,
    detectar_fases_aereas,
    seleccionar_balon_activo,
)

DT = 1 / 15.0
TIEMPOS = {k: k * DT for k in range(0, 400)}


def _det(mx, my, alto_px=8, conf=0.8):
    return (mx, my, 100.0, 100.0, 100.0 + alto_px, 100.0 + alto_px, conf)


# ── selección del balón activo ───────────────────────────────────────


def test_descarta_el_balon_parado_lejos_del_juego():
    """Un balón de calentamiento en la banda es un balón perfecto: lo que
    lo delata no es su aspecto sino que no se mueve y nadie lo rodea."""
    detecciones, jugadores = {}, {}
    for k in range(60):
        detecciones[k] = [
            _det(30.0 + 0.3 * k, 20.0),  # el del partido, moviéndose
            _det(5.0, 39.0),  # parado en la banda
        ]
        jugadores[k] = [(30.0 + 0.3 * k + 1.0, 20.5), (28.0, 19.0)]
    activo = seleccionar_balon_activo(detecciones, jugadores, ParametrosBalon())
    assert len(activo) == 60
    for k in range(60):
        assert abs(activo[k][0] - (30.0 + 0.3 * k)) < 0.01


def test_un_balon_parado_pero_CERCA_no_se_descarta():
    """El balón bueno también se para: un saque de banda, una falta. Si se
    descartara por estar quieto, se perdería justo el momento previo a la
    jugada."""
    detecciones = {k: [_det(30.0, 20.0)] for k in range(60)}
    jugadores = {k: [(31.0, 20.0)] for k in range(60)}
    activo = seleccionar_balon_activo(detecciones, jugadores, ParametrosBalon())
    assert len(activo) == 60


# ── fases aéreas ─────────────────────────────────────────────────────


def test_la_velocidad_imposible_marca_fase_aerea():
    """La proyección supone que el balón está EN EL SUELO. Un vuelo viola
    esa suposición y produce saltos que ningún balón raso da."""
    tray = [(k, np.array([10.0 + 0.3 * k, 20.0]), 8, 0.9) for k in range(10)]
    tray += [(10 + k, np.array([13.0 + 5.0 * k, 20.0]), 8, 0.9) for k in range(5)]
    tray += [(15 + k, np.array([38.0 + 0.3 * k, 20.0]), 8, 0.9) for k in range(10)]
    aereo = detectar_fases_aereas(tray, TIEMPOS, ParametrosBalon())
    assert any(aereo[10:15]), "el tramo rápido debe marcarse aéreo"
    assert not aereo[0] and not aereo[-1]


def test_el_tamano_incoherente_marca_fase_aerea():
    """La señal más específica: un balón por el aire está más cerca de la
    cámara que el punto del suelo al que se le proyecta, así que se ve
    MÁS GRANDE de lo que le tocaría por su distancia. No depende de la
    velocidad, así que caza también los globos lentos."""
    tray = [(k, np.array([float(40 + k * 0.1), 20.0]), 6, 0.9) for k in range(20)]
    # Mismo sitio, misma velocidad, pero de golpe se ve el triple
    for i in range(8, 13):
        f, p, _alto, c = tray[i]
        tray[i] = (f, p, 20, c)
    aereo = detectar_fases_aereas(tray, TIEMPOS, ParametrosBalon())
    assert any(aereo[8:13])
    assert not aereo[0]


def test_un_parpadeo_no_es_un_vuelo():
    """Una sola observación rara es ruido del detector, no una fase aérea."""
    tray = [(k, np.array([10.0 + 0.3 * k, 20.0]), 8, 0.9) for k in range(20)]
    f, _p, a, c = tray[10]
    tray[10] = (f, np.array([13.0, 24.0]), a, c)  # un salto de un frame
    aereo = detectar_fases_aereas(
        tray, TIEMPOS, ParametrosBalon(duracion_min_aerea=0.5)
    )
    assert not any(aereo)


# ── contactos ────────────────────────────────────────────────────────


def test_un_cambio_brusco_de_direccion_es_un_contacto():
    tray = [(k, np.array([10.0 + 1.0 * k, 20.0]), 8, 0.9) for k in range(10)]
    tray += [
        (10 + k, np.array([19.0, 20.0 + 1.0 * (k + 1)]), 8, 0.9) for k in range(10)
    ]
    jugadores = {k: [(19.5, 20.5, 7)] for k in range(30)}
    contactos = detectar_contactos(tray, TIEMPOS, jugadores, None, ParametrosBalon())
    assert len(contactos) == 1
    assert contactos[0]["angulo"] > 45
    assert contactos[0]["id_jugador"] == 7


def test_un_balon_recto_no_genera_contactos():
    tray = [(k, np.array([10.0 + 1.0 * k, 20.0]), 8, 0.9) for k in range(30)]
    jugadores = {k: [(15.0, 20.0, 3)] for k in range(30)}
    assert detectar_contactos(tray, TIEMPOS, jugadores, None, ParametrosBalon()) == []


def test_el_contacto_sin_jugador_cerca_se_registra_igual():
    """Información honesta: hubo un contacto y no sabemos de quién. Es
    mejor que atribuirlo al jugador más cercano esté donde esté."""
    tray = [(k, np.array([10.0 + 1.0 * k, 20.0]), 8, 0.9) for k in range(10)]
    tray += [
        (10 + k, np.array([19.0, 20.0 + 1.0 * (k + 1)]), 8, 0.9) for k in range(10)
    ]
    jugadores = {k: [(50.0, 35.0, 3)] for k in range(30)}
    contactos = detectar_contactos(tray, TIEMPOS, jugadores, None, ParametrosBalon())
    assert len(contactos) == 1
    assert contactos[0]["id_jugador"] is None


def test_el_balon_casi_parado_no_genera_contactos_por_ruido():
    """Con el balón quieto, el ángulo entre pasos lo decide el ruido."""
    rng = np.random.default_rng(0)
    tray = [
        (k, np.array([20.0, 20.0]) + rng.normal(0, 0.02, 2), 8, 0.9) for k in range(30)
    ]
    jugadores = {k: [(20.5, 20.0, 1)] for k in range(30)}
    assert detectar_contactos(tray, TIEMPOS, jugadores, None, ParametrosBalon()) == []
