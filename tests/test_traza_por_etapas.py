"""Contabilidad de la traza por etapas (scripts/traza_por_etapas.py)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_RUTA = Path(__file__).resolve().parent.parent / "scripts/traza_por_etapas.py"
_spec = importlib.util.spec_from_file_location("traza_por_etapas", _RUTA)
tz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tz)


def _cas(*vivas):
    return {e: (e in vivas) for e in tz.ETAPAS}


def test_primera_perdida_en_orden():
    assert tz.primera_perdida(_cas()) == "a_caja_cruda"
    assert tz.primera_perdida(_cas("a_caja_cruda", "b_filtros")) == "c_identidad"
    assert tz.primera_perdida(_cas(*tz.ETAPAS)) is None


def test_reaparece_solo_si_vuelve_despues():
    # pierde en c pero el CSV (suavizado) la vuelve a cubrir
    assert tz.reaparece(_cas("a_caja_cruda", "b_filtros", "e_csv"))
    assert not tz.reaparece(_cas("a_caja_cruda", "b_filtros"))
    assert not tz.reaparece(_cas(*tz.ETAPAS))


def test_casado_en_pixeles():
    det = (0, 0, 100, 100, 130, 180, 0.5)
    caja_dentro = SimpleNamespace(xtl=95, ytl=130, xbr=135, ybr=148)  # centro (115,139)
    caja_pie = SimpleNamespace(
        xtl=96, ytl=180, xbr=136, ybr=198
    )  # centro fuera; pie a 18 px
    caja_lejos = SimpleNamespace(xtl=300, ytl=300, xbr=340, ybr=318)
    assert tz.casado_en_pixeles(det, caja_dentro)
    assert tz.casado_en_pixeles(det, caja_pie)
    assert not tz.casado_en_pixeles(det, caja_lejos)


def test_reconcilian_con_un_punto():
    assert tz.reconcilian(0.967, 0.960)
    assert not tz.reconcilian(0.967, 0.950)
