"""Líneas tácticas (scripts/lineas_tacticas.py): cálculo, zona visible y criterio."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import lineas_tacticas as lt  # noqa: E402


def test_lineas_segun_el_sentido_de_ataque():
    xs, ys = [30, 35, 40, 50], [5, 20, 30, 12]
    bajo = lt.lineas_equipo(xs, ys, defiende_bajo=True)
    assert (bajo["defensa"], bajo["presion"], bajo["distancia"]) == (30, 50, 20)
    alto = lt.lineas_equipo(xs, ys, defiende_bajo=False)
    assert (alto["defensa"], alto["presion"], alto["distancia"]) == (50, 30, 20)
    assert bajo["anchura"] == 25


def test_zona_visible_exige_el_bloque_entero_desde_28_m():
    assert lt.lineas_equipo([28, 40, 50], [1, 2, 3], True)["medible"]
    assert not lt.lineas_equipo([27.9, 40, 50], [1, 2, 3], True)["medible"]


def test_menos_de_tres_jugadores_no_hay_lineas():
    assert lt.lineas_equipo([30, 40], [1, 2], True) is None


def test_veredicto_de_cada_metrica():
    assert lt.veredicto_metrica([1.0] * 10)["ensenable"] is True
    assert lt.veredicto_metrica([1.0] * 8 + [6.0] * 2)["ensenable"] is False  # p90 > 5
    assert lt.veredicto_metrica([3.0] * 12)["ensenable"] is False  # mediana > 2
    assert (
        lt.veredicto_metrica([1.0] * 9)["ensenable"] is None
    )  # n < 10: no concluyente


def test_reloj():
    assert (
        lt.reloj(325.0) == "5:25.0"
        and lt.reloj(325.0 + lt.ADELANTO_REPRODUCTOR_S) == "6:58.0"
    )
