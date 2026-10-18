"""Piezas puras de scripts/causas_equipo_equivocado.py."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "causas",
    Path(__file__).resolve().parent.parent / "scripts/causas_equipo_equivocado.py",
)
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)

AREAS = {"bajo": ((0.0, 15.0), (10.0, 30.0)), "alto": ((47.0, 62.0), (10.0, 30.0))}


def test_el_orden_de_las_causas_es_el_fijado():
    assert ce.causa(True, True, True, True) == "arbitro"
    assert ce.causa(False, True, True, True) == "staff"
    assert ce.causa(False, False, True, True) == "portero"
    assert ce.causa(False, False, False, True) == "caja_dos_personas"
    assert ce.causa(False, False, False, False) == "recorte_limpio"


def test_fuera_del_campo_con_tolerancia():
    assert not ce.fuera_del_campo(-1.5, 20, 2.0)
    assert ce.fuera_del_campo(-2.5, 20, 2.0)
    assert ce.fuera_del_campo(30, 42.5, 2.0)


def test_portero_posicional_solo_si_es_el_mas_cercano_a_SU_porteria():
    assert ce.es_portero_posicional(3.0, 20.0, AREAS, [3.0, 10.0, 40.0])
    assert not ce.es_portero_posicional(
        10.0, 20.0, AREAS, [3.0, 10.0, 40.0]
    )  # hay uno detrás
    assert ce.es_portero_posicional(60.0, 20.0, AREAS, [3.0, 40.0, 60.0])
    assert not ce.es_portero_posicional(30.0, 20.0, AREAS, [30.0])  # fuera de las áreas


def test_caja_ancha_por_franja_de_alto():
    franjas = [0, 30, 45, 60]
    medianas = {0: 0.40, 1: 0.40, 2: 0.40}
    assert ce.caja_ancha(26, 50, medianas, franjas, 1.25)  # 0,52 / 0,40 = 1,3
    assert not ce.caja_ancha(24, 50, medianas, franjas, 1.25)  # 0,48 / 0,40 = 1,2
    assert not ce.caja_ancha(26, 0, medianas, franjas, 1.25)


def test_iou():
    assert ce.iou((0, 0, 10, 10), (0, 0, 10, 10)) > 0.99
    assert ce.iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_exceso_solo_por_encima_de_la_base():
    assert ce.exceso(100, 0.6, 0.2) == 40.0
    assert ce.exceso(100, 0.1, 0.2) == 0.0
