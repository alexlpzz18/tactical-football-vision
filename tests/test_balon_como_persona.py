"""La regla de forma del balón detectado como persona (scripts/balon_como_persona.py)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_RUTA = Path(__file__).resolve().parent.parent / "scripts/balon_como_persona.py"
_spec = importlib.util.spec_from_file_location("balon_como_persona", _RUTA)
bcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bcp)

REF = 1.5  # altura implícita mediana del partido (m)


def test_balon_bajo_y_cuadrado_se_quita():
    assert bcp.forma_de_balon(0.25, 0.25, REF)


def test_agachado_bajo_pero_alto_que_ancho_se_queda():
    # 0,55 m de alto (< 0,6) pero ancho/alto 0,5: una persona agachada
    assert not bcp.forma_de_balon(0.55, 0.275, REF)


def test_tumbado_ancho_pero_no_bajo_se_queda():
    # ancho/alto 1,2 pero 0,7 m de alto (> 0,40 × 1,5 = 0,6)
    assert not bcp.forma_de_balon(0.70, 0.84, REF)


def test_altura_invalida_no_quita():
    assert not bcp.forma_de_balon(0.0, 0.2, REF)
    assert not bcp.forma_de_balon(None, 0.2, REF)
    assert not bcp.forma_de_balon(0.2, 0.2, 0.0)


def test_balon_dentro_de_la_caja():
    persona = (0, 0, 100, 100, 120, 120, 0.5)
    dentro = (0, 0, 108, 108, 112, 112, 0.6)
    fuera = (0, 0, 200, 200, 210, 210, 0.6)
    assert bcp.balon_dentro(persona, [fuera, dentro], margen=0)
    assert not bcp.balon_dentro(persona, [fuera], margen=0)
    # el margen amplía la caja
    borde = (0, 0, 121, 121, 123, 123, 0.6)  # centro en 122
    assert not bcp.balon_dentro(persona, [borde], margen=0)
    assert bcp.balon_dentro(persona, [borde], margen=4)


def test_persona_gt_por_cualquiera_de_los_dos_casados():
    det = (0, 0, 100, 100, 120, 160, 0.5)
    centro_dentro = SimpleNamespace(xtl=100, ytl=120, xbr=120, ybr=138)
    pie_cerca = SimpleNamespace(
        xtl=95, ytl=170, xbr=135, ybr=188
    )  # centro (115,179); pie a 29 px
    lejos = SimpleNamespace(xtl=400, ytl=400, xbr=440, ybr=418)
    assert bcp.es_persona_gt(det, [centro_dentro])
    assert bcp.es_persona_gt(det, [pie_cerca])
    assert not bcp.es_persona_gt(det, [lejos])


def test_veredicto():
    assert bcp.veredicto(1, 0, 50).startswith("NO SE ADOPTA (pierde personas del GT)")
    assert bcp.veredicto(0, 0, 0).startswith("NO SE ADOPTA (no quita")
    assert bcp.veredicto(0, None, 5).startswith("PENDIENTE")
    assert bcp.veredicto(0, 1, 5).startswith("NO SE ADOPTA (pierde jugadores")
    assert bcp.veredicto(0, 0, 5).startswith("PASA")
