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


# ── El catálogo arbitral POR OBSERVACIÓN (28-ago-2026) ───────────────
#
# `identificar_arbitros` juzga la MEDIA DE LA IDENTIDAD, y eso lo rompe
# una identidad contaminada: el id 292 del benjamín mezcla al árbitro con
# jugadores naranjas, su media da un tono intermedio que no cae en ningún
# arquetipo, y con 3.187 recortes no dispara. NO ES CANTIDAD, ES PUREZA.


def _clasificador_de_dos_equipos():
    """Un clasificador con prototipos que NO chocan con verde flúor."""
    import numpy as np

    from src.team_classification.color_classifier import TeamClassifierColor

    clf = TeamClassifierColor()
    # 256 = 16 tonos x 16 saturaciones. Un equipo en el tono 2 (rojizo) y
    # otro en el 10 (azulado), los dos muy saturados.
    a = np.zeros(256)
    a[2 * 16 + 15] = 1.0
    b = np.zeros(256)
    b[10 * 16 + 15] = 1.0
    clf.fit_features(np.array([a] * 40 + [b] * 40))
    return clf


def test_una_ventana_con_color_de_ARBITRO_sale_de_los_equipos():
    """El caso del id 292: una identidad que mezcla árbitro y jugador."""
    import numpy as np

    from src.team_classification.pipeline_equipos import etiquetar_por_observacion
    from src.tracking.field_tracker import Tracklet

    clf = _clasificador_de_dos_equipos()
    pr = clf._prototipos
    # La identidad: primero 20 observaciones de un jugador del equipo A,
    # luego 20 del árbitro (verde flúor: tono 5 de 16, saturación alta).
    arbitro = np.zeros(256)
    arbitro[5 * 16 + 15] = 1.0

    tr = Tracklet(1, 0.0, np.array([30.0, 20.0]), 0, 0)
    colores = {(0, 0): np.asarray(pr.a)}
    for i in range(1, 40):
        tr.anadir(i * 0.1, np.array([30.0, 20.0]), 0, i)
        colores[(i, 0)] = np.asarray(pr.a) if i < 20 else arbitro

    cfg = {
        "agregacion": {
            "por_observacion": {
                "activo": True,
                "ventana_s": 1.0,
                "catalogo_arbitral": True,
            }
        }
    }
    salida = etiquetar_por_observacion([[tr]], {1: "A"}, colores, clf, cfg)
    primeras = [salida.get((1, i)) for i in range(0, 15)]
    ultimas = [salida.get((1, i)) for i in range(25, 40)]
    assert all(
        e == "A" for e in primeras if e
    ), f"las observaciones del JUGADOR tienen que seguir en su equipo: {primeras}"
    assert any(e == "otro" for e in ultimas), (
        "las observaciones con color de ÁRBITRO tienen que salir de los "
        f"equipos: {ultimas}"
    )


def test_sin_el_interruptor_el_catalogo_por_observacion_NO_actua():
    """Se puede apagar, y apagarlo cambia el resultado."""
    import numpy as np

    from src.team_classification.pipeline_equipos import etiquetar_por_observacion
    from src.tracking.field_tracker import Tracklet

    clf = _clasificador_de_dos_equipos()
    arbitro = np.zeros(256)
    arbitro[5 * 16 + 15] = 1.0
    tr = Tracklet(1, 0.0, np.array([30.0, 20.0]), 0, 0)
    colores = {(0, 0): arbitro}
    for i in range(1, 20):
        tr.anadir(i * 0.1, np.array([30.0, 20.0]), 0, i)
        colores[(i, 0)] = arbitro

    def correr(catalogo):
        cfg = {
            "agregacion": {
                "por_observacion": {
                    "activo": True,
                    "ventana_s": 1.0,
                    "catalogo_arbitral": catalogo,
                }
            }
        }
        return etiquetar_por_observacion([[tr]], {1: "A"}, colores, clf, cfg)

    con, sin = correr(True), correr(False)
    assert any(
        e == "otro" for e in con.values()
    ), "con el catálogo, sale de los equipos"
    assert not any(e == "otro" for e in sin.values()), "sin él, se queda en un equipo"
