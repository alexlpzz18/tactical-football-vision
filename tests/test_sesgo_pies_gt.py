"""El emparejado caja↔clic de scripts/sesgo_pies_gt.py no mira dónde cae el pie."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sesgo_pies_gt", Path(__file__).resolve().parent.parent / "scripts/sesgo_pies_gt.py"
)
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)


def test_mismo_coste_con_el_clic_en_el_pie_o_en_la_media():
    caja = [(100, 100, 120, 160)]
    # dentro de la caja da igual la altura: no se condiciona en dy
    assert sp.emparejar(caja, [(110, 158)]) == [(0, 0)]
    assert sp.emparejar(caja, [(110, 130)]) == [(0, 0)]
    # un poco por debajo del pie (dentro del 25 % alargado) también
    assert sp.emparejar(caja, [(110, 170)]) == [(0, 0)]
    # lejos en horizontal, no
    assert sp.emparejar(caja, [(160, 150)]) == []


def test_uno_a_uno():
    cajas = [(100, 100, 120, 160), (118, 100, 138, 160)]
    pares = sp.emparejar(cajas, [(110, 150), (128, 150)])
    assert sorted(pares) == [(0, 0), (1, 1)]


def test_cambia_de_signo():
    assert sp.cambia_de_signo([3, 4, 5], [-1, -2, -3])
    assert not sp.cambia_de_signo([10, 12, 14], [3, 5, 7])
