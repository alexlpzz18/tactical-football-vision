"""Puerta de calidad de caja (docs/diagnostico_28oct_g.md): cajas anormales para su posición."""

import numpy as np

from src.team_classification.calidad_caja import cajas_anormales
from src.team_classification.color_classifier import TeamClassifierColor
from src.team_classification.pipeline_equipos import etiquetar_por_observacion
from src.tracking.field_tracker import Tracklet


def _cache_con_una_fundida(n=200):
    """Cajas cuyo alto crece con la fila de la imagen (perspectiva), y UNA el doble de ancha."""
    rng = np.random.default_rng(0)
    cache = []
    for f in range(n):
        v = 300 + 3 * f % 700
        h = 20 + 0.05 * v
        u = rng.uniform(200, 1700)  # independiente de v: si no, el ajuste es degenerado
        w = 0.45 * h * (1 + 0.03 * rng.standard_normal())
        cache.append(
            {"frame_idx": f, "dets": [(0, 0, u - w / 2, v - h, u + w / 2, v, 0.9)]}
        )
    d = cache[50]["dets"][0]
    ancho = d[4] - d[2]
    cache[50]["dets"][0] = (0, 0, d[2] - ancho, d[3], d[4], d[5], 0.9)  # ancho ×2
    return cache


def test_marca_la_caja_fundida_y_solo_esa():
    assert cajas_anormales(_cache_con_una_fundida()) == {(50, 0)}


def _clasificador():
    clf = TeamClassifierColor()
    a = np.zeros(256)
    a[2 * 16 + 15] = 1.0
    b = np.zeros(256)
    b[10 * 16 + 15] = 1.0
    clf.fit_features(np.array([a] * 40 + [b] * 40))
    return clf, a, b


def _cfg(activo):
    return {
        "agregacion": {
            "por_observacion": {
                "activo": True,
                "ventana_s": 1.0,
                "catalogo_arbitral": False,
                "excluir_cajas_anormales": {"activo": activo},
            }
        }
    }


def _jugador_de_A_con_cajas_fundidas():
    """Un jugador de A cuyas cajas fundidas (frames 15-24) salen del color de B."""
    clf, a, b = _clasificador()
    tr = Tracklet(1, 0.0, np.array([30.0, 20.0]), 0, 0)
    colores = {(0, 0): a}
    for i in range(1, 40):
        tr.anadir(i * 0.1, np.array([30.0, 20.0]), 0, i)
        colores[(i, 0)] = b if 15 <= i < 25 else a
    return clf, tr, colores, {(i, 0) for i in range(15, 25)}


def test_el_interruptor_cambia_el_resultado():
    """Guarda de COMPORTAMIENTO (CLAUDE.md): encender el flag tiene que mover la etiqueta."""
    clf, tr, colores, anormales = _jugador_de_A_con_cajas_fundidas()
    apagado = etiquetar_por_observacion(
        [[tr]], {1: "A"}, colores, clf, _cfg(False), None, anormales
    )
    encendido = etiquetar_por_observacion(
        [[tr]], {1: "A"}, colores, clf, _cfg(True), None, anormales
    )
    eti_a = clf.predict_color(colores[(0, 0)])
    assert len(set(apagado.values())) == 2, "el control ya no reproduce el error"
    assert set(encendido.values()) == {eti_a}
