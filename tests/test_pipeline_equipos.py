"""Tests del camino ÚNICO de entrenamiento del clasificador de equipos.

Regresión del bug de producción (12-jul-2026): el fit con todos los
recortes podía colapsar en un solo equipo; el fit filtrado a recortes
cercanos debe separar los grupos limpios aunque haya una masa de features
ruidosas lejanas.
"""

import numpy as np
import pytest

from src.team_classification.pipeline_equipos import entrenar_clasificador

RNG = np.random.default_rng(11)


def _feature(bin_dominante, ruido=0.0005):
    f = RNG.random(256) * ruido
    f[bin_dominante] = 1.0
    return f / f.sum()


def _escenario():
    """200 recortes cercanos limpios (2 equipos) + 800 lejanos ruidosos.

    Las features lejanas son ruido casi uniforme (jugador de 20 px: el
    histograma no ve la camiseta), la mayoría de la población — como en
    el caché real.
    """
    colores = {}
    cache = []
    dets, frame = [], 0

    def anadir(my, feature):
        nonlocal dets, frame
        colores[(frame, len(dets))] = feature
        dets.append((50.0, my, 0, 0, 10, 30, 0.9))
        if len(dets) == 25:  # 25 detecciones por frame
            cache.append({"frame_idx": frame, "t": frame / 25.0, "dets": dets})
            frame += 3
            dets = []

    for i in range(100):
        anadir(my=20.0, feature=_feature(10))  # equipo 1, cercano
        anadir(my=25.0, feature=_feature(200))  # equipo 2, cercano
    for i in range(800):
        anadir(my=60.0, feature=_feature(int(RNG.integers(0, 256)), ruido=0.5))
    if dets:
        cache.append({"frame_idx": frame, "t": frame / 25.0, "dets": dets})
    return colores, cache


CFG = {"entrenamiento": {"solo_cercanos": True, "umbral_my": 34.0, "min_features": 100}}


def test_fit_filtrado_separa_equipos_pese_al_ruido_lejano():
    colores, cache = _escenario()
    clf = entrenar_clasificador(colores, CFG, cache)
    # Las features cercanas limpias deben clasificarse en dos equipos
    pred_1 = clf.predict_color(_feature(10))
    pred_2 = clf.predict_color(_feature(200))
    assert {pred_1, pred_2} == {"A", "B"}


def test_filtro_activo_sin_cache_falla_claro():
    colores, _ = _escenario()
    with pytest.raises(ValueError, match="cach[eé] de detecciones"):
        entrenar_clasificador(colores, CFG, cache=None)


def test_fallback_con_pocas_cercanas_usa_todo():
    """Si no hay suficientes cercanas, entrena con todo (aviso, no crash)."""
    colores, cache = _escenario()
    cfg = {"entrenamiento": {**CFG["entrenamiento"], "min_features": 100000}}
    clf = entrenar_clasificador(colores, cfg, cache)
    assert clf._prototipos is not None  # entrenó con la población completa


def test_filtro_desactivable_por_config():
    colores, cache = _escenario()
    cfg = {"entrenamiento": {"solo_cercanos": False}}
    clf = entrenar_clasificador(colores, cfg, cache=None)  # sin cache: OK
    assert clf._prototipos is not None
