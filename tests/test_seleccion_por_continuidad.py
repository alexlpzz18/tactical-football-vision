"""Selección del balón por CONTINUIDAD (Viterbi) y tamaño (docs/selector_balon.md, 1b/1c).

Cada test fija uno de los fallos medidos del selector frame a frame:
el parpadeo a un objeto lejano, la bota pegada al balón y el objeto quieto
que se detecta más que el balón (el zapato del entrenador).
"""

from dataclasses import replace

import numpy as np
import pytest

from src.balon.tracking_balon import (
    ParametrosBalon,
    escala_px_por_m,
    seleccionar_balon_activo,
    tamano_relativo,
)

DT = 1 / 15.0
# Homografía de juguete: 1 px = 1 cm en las dos direcciones (100 px/m), así
# que un balón de 0,20 m "mide" 20 px y su tamaño relativo es lado / 20.
H = np.array([[0.01, 0.0, 0.0], [0.0, 0.01, 0.0], [0.0, 0.0, 1.0]])
P = ParametrosBalon()  # los de producción


def _det(px, py, lado=36.0, conf=0.8):
    """Candidato centrado en (px, py). Por defecto, del tamaño de un balón (1,8)."""
    m = (px / 100.0, py / 100.0)
    return (
        m[0],
        m[1],
        px - lado / 2,
        py - lado / 2,
        px + lado / 2,
        py + lado / 2,
        conf,
    )


def _jug_junto_a(dets):
    """Un jugador pegado a cada candidato: así la guarda de "quieto y lejos" no actúa."""
    return {f: [(d[0], d[1]) for d in v] for f, v in dets.items()}


def _elegir(dets, params=P, jug=None):
    tiempos = {f: f * DT for f in dets}
    return seleccionar_balon_activo(
        dets,
        jug or _jug_junto_a(dets),
        params,
        tiempos,
        H,
        posiciones_staff={},
        dimensiones_campo=(62.0, 40.0),
    )


def test_la_escala_sale_de_la_homografia():
    assert escala_px_por_m(H, 500, 500) == pytest.approx(100.0)
    assert tamano_relativo(_det(500, 500, lado=36), H) == pytest.approx(1.8)


def test_un_parpadeo_a_un_objeto_lejano_se_queda_sin_balon():
    """El balón avanza 5 px por frame; en el frame 10 NO se detecta y solo hay
    un objeto a 800 px. Frame a frame se elegía; con continuidad no compensa
    saltar allí y volver."""
    dets = {f: [_det(100 + 5 * f, 500)] for f in range(20)}
    dets[10] = [_det(900, 500)]
    elegido = _elegir(dets)
    assert 10 not in elegido
    assert all(elegido[f][2] < 300 for f in elegido)
    frame_a_frame = _elegir(dets, replace(P, continuidad_activa=False))
    assert frame_a_frame[10][2] > 800


def test_la_bota_pegada_pierde_contra_el_balon_por_tamano():
    """Bota (8 px, relativo 0,4) a 15 px del balón (36 px): los dos caben en la
    puerta de continuidad. Con la bota más cerca del jugador, la cercanía la
    elegía; el tamaño elige el balón."""
    dets = {
        f: [_det(100 + 5 * f, 500), _det(115 + 5 * f, 500, lado=8)] for f in range(20)
    }
    jug = {f: [(dets[f][1][0], dets[f][1][1])] for f in dets}  # el jugador, en la bota
    elegido = _elegir(dets, jug=jug)
    assert all(elegido[f][4] - elegido[f][2] == 36 for f in dets)
    sin_tamano = _elegir(
        dets,
        replace(
            P, continuidad_desempate_por_tamano=False, continuidad_umbral_pequeno=0.0
        ),
        jug=jug,
    )
    assert all(sin_tamano[f][4] - sin_tamano[f][2] == 8 for f in dets)


def test_un_objeto_quieto_y_pequeno_no_gana_por_detectarse_mas():
    """El zapato del entrenador: 5 px, quieto, detectado en TODOS los frames.
    El balón, lejos, solo en uno de cada dos. Por cobertura ganaba el zapato;
    siendo pequeño vale lo mismo que no ver nada."""
    dets = {}
    for f in range(60):
        dets[f] = [_det(1800, 700, lado=5)]
        if f % 2 == 0:
            dets[f].append(_det(400 + 3 * f, 500))
    elegido = _elegir(dets)
    assert not any(d[2] > 1700 for d in elegido.values())
    solo_continuidad = _elegir(dets, replace(P, continuidad_umbral_pequeno=0.0))
    assert sum(d[2] > 1700 for d in solo_continuidad.values()) > 30


def test_sin_conflicto_da_lo_mismo_que_frame_a_frame():
    dets = {f: [_det(100 + 5 * f, 500)] for f in range(30)}
    assert _elegir(dets) == _elegir(dets, replace(P, continuidad_activa=False))


def test_sin_tiempos_o_sin_homografia_falla_en_vez_de_elegir_otra_cosa():
    dets = {f: [_det(100 + 5 * f, 500)] for f in range(5)}
    jug, tiempos = _jug_junto_a(dets), {f: f * DT for f in dets}
    contexto = {"posiciones_staff": {}, "dimensiones_campo": (62.0, 40.0)}
    with pytest.raises(ValueError, match="staff"):
        seleccionar_balon_activo(dets, jug, P, tiempos, H)
    with pytest.raises(ValueError, match="tiempos"):
        seleccionar_balon_activo(dets, jug, P, **contexto)
    with pytest.raises(ValueError, match="homografía"):
        seleccionar_balon_activo(dets, jug, P, tiempos, **contexto)
