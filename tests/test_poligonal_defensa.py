"""Poligonal defensiva y altura media (scripts/poligonal_defensa.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import poligonal_defensa as pd_  # noqa: E402


def test_los_n_mas_retrasados_segun_el_lado():
    xs, ids = [10, 30, 5, 50, 20], ["a", "b", "c", "d", "e"]
    assert pd_.mas_retrasados(xs, ids, 2, defiende_bajo=True) == ["c", "a"]
    assert pd_.mas_retrasados(xs, ids, 2, defiende_bajo=False) == ["d", "b"]


def test_poligonal_ordenada_por_y_y_altura_desde_su_porteria():
    xs, ys = [30, 31, 29, 32, 50], [35, 5, 20, 12, 18]
    p = pd_.poligonal(xs, ys, 4, defiende_bajo=True)
    assert [list(v) for v in p["vertices"]] == [[31, 5], [32, 12], [29, 20], [30, 35]]
    assert p["altura_m"] == 30.5 and p["visible"]
    q = pd_.poligonal(xs, ys, 1, defiende_bajo=False)
    assert q["altura_m"] == 62 - 50  # distancia a SU portería (x = 62)


def test_sin_n_jugadores_no_hay_poligonal_y_zona_visible():
    assert pd_.poligonal([30, 31, 29], [1, 2, 3], 4, True) is None
    assert not pd_.poligonal([27.9, 31, 29, 40], [1, 2, 3, 4], 4, True)["visible"]


def test_veredicto():
    assert pd_.veredicto([0.5] * 10, [1.0] * 40)["pasa"] is True
    assert (
        pd_.veredicto([0.5] * 8 + [3.5] * 2, [1.0] * 40)["pasa"] is False
    )  # p90 de altura > 3
    assert (
        pd_.veredicto([1.2] * 10, [1.0] * 40)["pasa"] is False
    )  # mediana de altura > 1
    assert pd_.veredicto([0.5] * 10, [1.6] * 40)["pasa"] is False  # vértices > 1,5
    assert pd_.veredicto([0.5] * 9, [1.0] * 36)["pasa"] is None  # < 10 frames
