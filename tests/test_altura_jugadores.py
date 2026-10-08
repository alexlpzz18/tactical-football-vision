"""Altura de jugadores en un vídeo nuevo (scripts/colab_altura_jugadores.py)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import colab_altura_jugadores as aj  # noqa: E402


def test_solo_cuentan_las_cajas_con_el_pie_en_el_cesped():
    region = np.zeros((100, 100), np.uint8)
    region[50:, :] = 255  # el césped, la mitad de abajo
    cajas = [
        (10, 60, 20, 90),
        (10, 5, 20, 40),
        (95, 60, 120, 90),
    ]  # en césped, en grada, fuera
    assert aj.pie_en_cesped(cajas, region) == [(10, 60, 20, 90)]


def test_resumen_y_lectura_de_la_prediccion():
    r = aj.resumen([20, 24, 26, 30, 50])
    assert r["n"] == 5 and r["mediana"] == 26 and r["frac_menor_25"] == 0.4
    assert aj.resumen([]) == {"n": 0}
    assert aj.lectura(45) == "sirve de pata"
    assert aj.lectura(33).startswith("intermedio")
    assert aj.lectura(26).startswith("no aporta")
    assert aj.lectura(None) == "sin cajas"
