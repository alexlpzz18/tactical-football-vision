"""Máscara de zona de juego del balón (`balon.mascara_zona`, docs/diagnostico_23oct_f.md)."""

import pytest

from src.balon.tracking_balon import (
    ParametrosBalon,
    dentro_del_poligono,
    filtrar_por_mascara_zona,
    seleccionar_balon_activo,
)

CUADRADO = [[0, 0], [100, 0], [100, 100], [0, 100]]


def _det(cx, cy, mx=10.0, my=10.0):
    return (mx, my, cx - 5, cy - 5, cx + 5, cy + 5, 0.7)


def test_dentro_del_poligono():
    assert dentro_del_poligono(50, 50, CUADRADO)
    assert not dentro_del_poligono(150, 50, CUADRADO)
    # un polígono cóncavo en L: el hueco de la L queda fuera
    ele = [[0, 0], [100, 0], [100, 40], [40, 40], [40, 100], [0, 100]]
    assert dentro_del_poligono(20, 80, ele)
    assert not dentro_del_poligono(80, 80, ele)


def test_filtrar_quita_por_el_centro_y_vacia_frames():
    dets = {1: [_det(50, 50), _det(150, 50)], 2: [_det(200, 200)]}
    out = filtrar_por_mascara_zona(dets, CUADRADO)
    assert out == {1: [_det(50, 50)]}


def test_poligono_degenerado_da_error():
    with pytest.raises(ValueError):
        filtrar_por_mascara_zona({1: [_det(1, 1)]}, [[0, 0], [1, 1]])


def test_apagada_por_defecto_y_encendida_cambia_la_eleccion():
    """Comportamiento: con la máscara, la candidata de fuera deja de poder elegirse."""
    assert ParametrosBalon().mascara_zona is None
    # dos candidatas por frame; la de FUERA de la máscara es la más segura y la más cercana al
    # jugador, así que sin máscara gana ella
    dets = {
        f: [_det(500, 500, 10.0, 10.0), _det(50, 50, 30.0, 30.0)]
        for f in range(0, 20, 2)
    }
    jugadores = {f: [(10.0, 10.0)] for f in dets}
    params = ParametrosBalon(continuidad_activa=False, quitar_balon_de_staff=False)
    sin = seleccionar_balon_activo(dets, jugadores, params)
    con = seleccionar_balon_activo(
        dets,
        jugadores,
        ParametrosBalon(
            continuidad_activa=False, quitar_balon_de_staff=False, mascara_zona=CUADRADO
        ),
    )
    assert all(tuple(d[2:4]) == (495, 495) for d in sin.values())
    assert all(tuple(d[2:4]) == (45, 45) for d in con.values())
