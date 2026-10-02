"""Herramienta del GT de balón en vuelo (scripts/gt_balon_en_vuelo.py)."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import gt_balon_en_vuelo as g  # noqa: E402


def test_la_celda_va_y_vuelve():
    for x, y in [(10, 10), (1915, 1075), (700, 540)]:
        cx, cy = g.celda_a_px(g.celda_de_px(x, y))
        assert abs(cx - x) <= g.CELDA_PX / 2 and abs(cy - y) <= g.CELDA_PX / 2


def test_respuestas():
    assert g.parsear_respuesta("K7") == ("visible", (840.0, 520.0))
    assert g.parsear_respuesta(" k7 ")[0] == "visible"
    for t in ("no_visible", "No visible", "fuera", "tapado", "Fuera de plano"):
        assert g.parsear_respuesta(t) == ("no_visible", None)
    assert g.parsear_respuesta("no_se") == ("no_se", None)
    assert g.parsear_respuesta("Z99") == (None, None)  # fuera de la rejilla
    assert g.parsear_respuesta("K15") == (None, None)  # solo hay 14 filas


def _det(mx, my, px=500.0, py=500.0):
    return (mx, my, px - 5, py - 5, px + 5, py + 5, 0.7)


def test_solo_frames_de_vuelo_sin_balon_y_sin_deteccion_que_no_sea_marca():
    tiempos = {f: f / 15 for f in range(40)}
    # balón en el frame 0 y en el 10 a 20 m: un vuelo de 0,67 s con 1-9 dentro
    sel = {0: _det(10, 10), 10: _det(30, 10), 20: _det(31, 10), 30: _det(31.5, 10)}
    produccion = dict(sel)
    produccion[3] = _det(15, 10)  # el selector de producción resolvió el 3
    crudo = {4: [_det(0, 0, px=12, py=12)], 5: [_det(0, 0, px=900, py=900)]}

    def en_marca(d):
        return d[2] < 100  # la del frame 4 es marca; la del 5, no

    fr = g.frames_de_vuelo_sin_deteccion(sel, produccion, crudo, en_marca, tiempos)
    assert fr == [1, 2, 4, 6, 7, 8, 9]  # ni el 3 (resuelto) ni el 5 (tiene detección)
    # entre 10 y 20 el salto es de 1 m: no es vuelo
    assert not any(11 <= f <= 19 for f in fr)


def test_espaciados_respetan_la_separacion():
    tiempos = {f: f * 0.5 for f in range(200)}
    el = g.elegir_espaciados(range(200), tiempos, 10, 5.0, random.Random(1))
    ts = sorted(tiempos[f] for f in el)
    assert len(el) == 10 and all(b - a >= 5.0 for a, b in zip(ts, ts[1:]))
