"""Tests de la regla de porteros por posición."""

import numpy as np

from src.team_classification.porteros import ReglaPorteros, aplicar_regla_porteros
from src.tracking.field_tracker import Tracklet


def _identidad_en(mx, my, n=10):
    """Identidad sintética quieta alrededor de (mx, my)."""
    tr = Tracklet(1, 0.0, np.array([mx, my]), 0, 0)
    for k in range(1, n):
        tr.anadir(0.12 * k, np.array([mx + 0.1 * (k % 3), my]), 0, 3 * k)
    return [tr]


def test_portero_en_area_alta_es_portero_A():
    regla = ReglaPorteros()
    identidades = [_identidad_en(91.0, 37.0)]
    equipos = aplicar_regla_porteros({1: "otro"}, identidades, regla)
    assert equipos[1] == "portero_A"


def test_portero_en_area_baja_es_portero_B():
    regla = ReglaPorteros()
    identidades = [_identidad_en(15.0, 38.0)]
    equipos = aplicar_regla_porteros({1: "B"}, identidades, regla)
    assert equipos[1] == "portero_B"  # sobrescribe el color


def test_jugador_de_campo_no_cambia():
    regla = ReglaPorteros()
    identidades = [_identidad_en(60.0, 40.0)]
    equipos = aplicar_regla_porteros({1: "A"}, identidades, regla)
    assert equipos[1] == "A"


def test_mediana_robusta_a_salidas_del_area():
    """Un portero que sale puntualmente del área sigue siendo portero."""
    regla = ReglaPorteros()
    tr = Tracklet(1, 0.0, np.array([91.0, 37.0]), 0, 0)
    for k in range(1, 8):
        tr.anadir(0.12 * k, np.array([91.0, 37.0]), 0, 3 * k)
    for k in range(8, 11):  # sube a rematar un córner (minoría de frames)
        tr.anadir(0.12 * k, np.array([60.0, 40.0]), 0, 3 * k)
    equipos = aplicar_regla_porteros({1: "otro"}, [[tr]], regla)
    assert equipos[1] == "portero_A"


def test_fuera_de_rango_my_no_es_portero():
    """En la esquina (mx de área pero my extremo) no se reetiqueta."""
    regla = ReglaPorteros()
    identidades = [_identidad_en(91.0, 5.0)]
    equipos = aplicar_regla_porteros({1: "otro"}, identidades, regla)
    assert equipos[1] == "otro"
