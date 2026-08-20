"""Tests del coste mixto geometría + apariencia."""

import numpy as np

from src.tracking.coste_asociacion import (
    IncertidumbrePosicion,
    ParametrosCosteMixto,
    coste,
    peso_geometrico,
    radio_plausibilidad,
)

P = ParametrosCosteMixto()
INC = IncertidumbrePosicion()


def test_el_radio_crece_con_el_hueco():
    """Cuanto más tiempo perdido, más lejos puede estar. Es física."""
    assert radio_plausibilidad(2.0, 10, P, INC) > radio_plausibilidad(0.5, 10, P, INC)


def test_el_radio_crece_con_la_profundidad():
    """En el fondo la posición es menos fiable: el radio tiene que dar más
    margen o se vetarían emparejamientos correctos."""
    assert radio_plausibilidad(1.0, 60, P, INC) > radio_plausibilidad(1.0, 0, P, INC)


def test_el_peso_de_la_geometria_baja_en_el_fondo():
    """Donde la proyección es mala, la apariencia debe mandar."""
    assert peso_geometrico(0.5, 60, P, INC) < peso_geometrico(0.5, 0, P, INC)


def test_el_peso_de_la_geometria_baja_con_el_hueco():
    assert peso_geometrico(5.0, 10, P, INC) < peso_geometrico(0.2, 10, P, INC)


def test_lo_imposible_es_imposible_aunque_se_parezca():
    """El veto por radio va ANTES que la apariencia: un jugador no puede
    estar donde no ha podido llegar."""
    v = np.ones(8)
    lejos = coste((0, 10), (100, 10), 0.5, v, v, P, INC)
    assert lejos == float("inf")


def test_la_apariencia_desempata_dentro_de_lo_posible():
    a, b = np.array([1.0, 0, 0, 0]), np.array([0, 1.0, 0, 0])
    igual = coste((0, 10), (1, 10), 0.5, a, a, P, INC)
    distinto = coste((0, 10), (1, 10), 0.5, a, b, P, INC)
    assert distinto > igual


def test_sin_embeddings_es_solo_geometria():
    c = coste((0, 10), (1, 10), 0.5, None, None, P, INC)
    assert 0 < c < 1
