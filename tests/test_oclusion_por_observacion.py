"""Excluir los recortes ocluidos de la ventana del etiquetado por observación.

El baile de colores (docs/arbitro_y_baile_de_colores.md): el 73 % de los 741
cambios A↔B cae en una caja solapada con otra (57,6 % con IoU > 0,10 contra
15,7 % en la línea base). El recorte de un jugador que se pisa con un rival
contiene píxeles del rival, y en una ventana de ~15 recortes un solape de un
segundo la contamina ENTERA.
"""

import numpy as np

from src.team_classification.color_classifier import TeamClassifierColor
from src.team_classification.pipeline_equipos import etiquetar_por_observacion
from src.tracking.field_tracker import Tracklet


def _clasificador():
    clf = TeamClassifierColor()
    a = np.zeros(256)
    a[2 * 16 + 15] = 1.0  # equipo A: tono 2
    b = np.zeros(256)
    b[10 * 16 + 15] = 1.0  # equipo B: tono 10
    clf.fit_features(np.array([a] * 40 + [b] * 40))
    return clf, a, b


def _etq(clf, color):
    """La etiqueta que el clasificador da a un color (A y B son arbitrarias)."""
    return clf.predict_color(color)


def _identidad_de_A_con_solape(n=40, solape=range(15, 25)):
    """Un jugador de A cuyo recorte, mientras se pisa con un rival, sale del color de B."""
    clf, a, b = _clasificador()
    tr = Tracklet(1, 0.0, np.array([30.0, 20.0]), 0, 0)
    colores = {(0, 0): a}
    for i in range(1, n):
        tr.anadir(i * 0.1, np.array([30.0, 20.0]), 0, i)
        colores[(i, 0)] = b if i in solape else a
    ocluidas = {(i, 0) for i in solape}
    return clf, tr, colores, ocluidas


def _a(clf):
    v = np.zeros(256)
    v[2 * 16 + 15] = 1.0
    return v


def _b(clf):
    v = np.zeros(256)
    v[10 * 16 + 15] = 1.0
    return v


def _cfg(**extra):
    return {
        "agregacion": {
            "por_observacion": {
                "activo": True,
                "ventana_s": 1.0,
                "catalogo_arbitral": False,
                **extra,
            }
        }
    }


def _etiquetas(clf, tr, colores, ocluidas, **extra):
    salida = etiquetar_por_observacion(
        [[tr]], {1: "A"}, colores, clf, _cfg(**extra), ocluidas
    )
    return {frame: e for (_id, frame), e in salida.items()}


def test_sin_la_opcion_el_solape_hace_bailar_la_etiqueta():
    """La línea base: el jugador de A pasa a B mientras dura el solape."""
    clf, tr, colores, oc = _identidad_de_A_con_solape()
    et = _etiquetas(clf, tr, colores, oc)
    assert _etq(clf, _b(clf)) in et.values(), "el control ya no reproduce el baile"


def test_con_la_opcion_la_etiqueta_no_baila():
    clf, tr, colores, oc = _identidad_de_A_con_solape()
    et = _etiquetas(clf, tr, colores, oc, excluir_ocluidas=True)
    assert set(et.values()) == {_etq(clf, _a(clf))}


def test_si_TODA_la_ventana_esta_ocluida_se_cae_a_todos_como_antes():
    """Sin recortes limpios en el rango, no se deja la observación sin voto."""
    clf, tr, colores, oc = _identidad_de_A_con_solape(solape=range(0, 40))
    et = _etiquetas(clf, tr, colores, oc, excluir_ocluidas=True)
    assert et, "no hay etiquetas: la observación se quedó sin voto"
    # todo contaminado y sin limpios que heredar: manda el color contaminado
    assert set(et.values()) == {_etq(clf, _b(clf))}


def test_ampliar_la_ventana_hereda_de_los_limpios_cercanos():
    """Solape largo (2 s): con la ventana de 1 s toda contaminada; ampliada, hereda."""
    clf, tr, colores, oc = _identidad_de_A_con_solape(solape=range(10, 32))
    estrecha = _etiquetas(clf, tr, colores, oc, excluir_ocluidas=True)
    ampliada = _etiquetas(
        clf, tr, colores, oc, excluir_ocluidas=True, ampliar_ventana_s=6.0
    )
    assert (
        _etq(clf, _b(clf)) in estrecha.values()
    ), "el control: sin ampliar, contaminada"
    assert set(ampliada.values()) == {_etq(clf, _a(clf))}


def test_una_identidad_sin_ninguna_oclusion_da_lo_mismo_con_o_sin_opcion():
    """Control de que la opción no cambia lo que no toca."""
    clf, tr, colores, _oc = _identidad_de_A_con_solape(solape=range(0))
    con = _etiquetas(clf, tr, colores, {(99, 0)}, excluir_ocluidas=True)
    sin = _etiquetas(clf, tr, colores, {(99, 0)})
    assert con == sin


def test_sin_conjunto_de_ocluidas_la_opcion_no_hace_nada():
    clf, tr, colores, _oc = _identidad_de_A_con_solape()
    con = _etiquetas(clf, tr, colores, None, excluir_ocluidas=True)
    sin = _etiquetas(clf, tr, colores, None)
    assert con == sin
