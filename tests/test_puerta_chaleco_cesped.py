"""Piezas puras de scripts/puerta_chaleco_cesped.py."""

import importlib.util
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "puerta",
    Path(__file__).resolve().parent.parent / "scripts/puerta_chaleco_cesped.py",
)
pu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pu)


def test_solape_dentro_y_fuera_del_rectangulo_del_cesped():
    rng = np.random.default_rng(0)
    cesped = np.column_stack([rng.uniform(80, 150, 1000), rng.uniform(60, 140, 1000)])
    dentro = np.column_stack([np.full(100, 100), np.full(100, 100)])
    fuera = np.column_stack([np.full(100, 240), np.full(100, 220)])
    assert pu.solape(dentro, cesped) == 1.0
    assert pu.solape(fuera, cesped) == 0.0


def test_clase_de_minuto_y_veredicto():
    assert pu.clase_de_minuto(240) == "S alta"
    assert pu.clase_de_minuto(90) == "S baja"
    assert pu.clase_de_minuto(150) == "mixto"
    assert pu.veredicto(0.11).startswith("SE CIERRA")
    assert pu.veredicto(0.10).startswith("LA PUERTA PASA")
    assert pu.veredicto(None).startswith("NO CONCLUYENTE")


def test_recorte_centro():
    img = np.zeros((100, 100, 3), np.uint8)
    assert pu.recorte_centro(img, (0, 0, 100, 100)).shape == (25 * 30, 3)
