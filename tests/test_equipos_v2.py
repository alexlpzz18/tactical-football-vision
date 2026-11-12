"""Guardas del brillo y el pantalón en la decisión de equipo (docs/plan_equipos_v2.md).

- Con los pesos a 0, NADA cambia: mismos prototipos y mismas decisiones que con la feature v1.
- El interruptor hace algo (CLAUDE.md: un interruptor que nadie lee es peor que no tenerlo): con
  una camiseta negra contra una blanca, que en tono y saturación son lo mismo, el brillo las separa.
- Los prototipos que ven el árbitro y la pizarra se quedan en tono y saturación, en su escala.
"""

import numpy as np

from src.team_classification.color_classifier import (
    ParametrosClasificadorColor,
    TeamClassifierColor,
    _feature_trabajo,
)
from src.team_classification.feature_v2 import LONGITUD_V1, LONGITUD_V_PECHO


def _norm(v):
    return v / np.linalg.norm(v)


def _features_blanco_negro(n=200, semilla=0):
    """Dos equipos con el MISMO histograma HS (sin saturación) y brillo opuesto.

    Es el caso del alevín B: una camiseta clara y otra negra. En HS solo hay ruido; en V, blanco
    arriba y negro abajo.
    """
    rng = np.random.default_rng(semilla)
    feats, verdad = [], []
    for i in range(n):
        # sin saturación el tono no está definido: la masa se reparte por todos los tonos de la
        # columna S = 0 (bins h*16), igual para el blanco que para el negro
        hs = np.zeros(LONGITUD_V1)
        hs[0::16] = 1.0
        hs = _norm(hs + 0.05 * rng.random(LONGITUD_V1))
        v = np.zeros(LONGITUD_V_PECHO)
        blanco = i % 2 == 0
        v[12:16] = (
            1.0 if blanco else 0.0
        )  # el brillo de un pecho se reparte en varios bins
        v[0:4] = 0.0 if blanco else 1.0
        v = _norm(v + 0.05 * rng.random(LONGITUD_V_PECHO))
        pantalon = _norm(np.ones(64) + 0.05 * rng.random(64))
        feats.append(np.concatenate([hs, v, pantalon]))
        verdad.append("blanco" if blanco else "negro")
    return np.array(feats), np.array(verdad)


def _acierto(clf, feats, verdad):
    pred = np.array([clf.predict_color(f, solo_equipos=True) for f in feats])
    directo = np.mean((pred == "A") == (verdad == "blanco"))
    return max(directo, 1 - directo)


def test_pesos_cero_es_exactamente_lo_de_siempre():
    feats, _ = _features_blanco_negro()
    con_v2 = TeamClassifierColor(ParametrosClasificadorColor())
    con_v2.fit_features(feats)
    solo_v1 = TeamClassifierColor(ParametrosClasificadorColor())
    solo_v1.fit_features(feats[:, :LONGITUD_V1])
    for x, y in ((con_v2._prototipos.a, solo_v1._prototipos.a),
                 (con_v2._prototipos.b, solo_v1._prototipos.b)):  # fmt: skip
        np.testing.assert_array_equal(x, y)
    for f in feats[:50]:
        assert con_v2.predict_color(f) == solo_v1.predict_color(f[:LONGITUD_V1])


def test_el_brillo_separa_negro_de_blanco_y_sin_el_no():
    feats, verdad = _features_blanco_negro()
    sin = TeamClassifierColor(ParametrosClasificadorColor())
    sin.fit_features(feats)
    con = TeamClassifierColor(ParametrosClasificadorColor(peso_v_pecho=1.0))
    con.fit_features(feats)
    assert _acierto(con, feats, verdad) > 0.95
    assert _acierto(sin, feats, verdad) < 0.8  # en HS solo hay ruido


def test_los_prototipos_del_arbitro_siguen_en_tono_y_saturacion():
    feats, _ = _features_blanco_negro()
    con = TeamClassifierColor(ParametrosClasificadorColor(peso_v_pecho=1.0))
    con.fit_features(feats)
    assert len(con._prototipos.a) == LONGITUD_V1
    hs_medio = np.mean([f[:LONGITUD_V1] for f in feats], axis=0)
    # misma escala que las features HS (norma ~1), no reescalados por los bloques nuevos
    assert abs(np.linalg.norm(con._prototipos.a) - np.linalg.norm(hs_medio)) < 0.1


def test_feature_de_trabajo_en_escala_unidad_y_v1_con_ceros():
    p = ParametrosClasificadorColor(peso_v_pecho=0.5, peso_pantalon=0.5)
    feats, _ = _features_blanco_negro(n=4)
    t = _feature_trabajo(feats[0], p)
    assert abs(np.linalg.norm(t) - 1.0) < 1e-9
    t_v1 = _feature_trabajo(feats[0][:LONGITUD_V1], p)
    assert len(t_v1) == len(t) and np.all(t_v1[LONGITUD_V1:] == 0)


def test_config_acepta_los_pesos():
    p = ParametrosClasificadorColor.desde_dict(
        {"peso_v_pecho": 0.5, "peso_pantalon": 0.25}
    )
    assert (p.peso_v_pecho, p.peso_pantalon) == (0.5, 0.25)


# ── representación con embedding (docs/plan_equipos_embeddings.md) ───
def _con_embeddings(n=200, semilla=1):
    """Dos equipos con el MISMO color HS y embeddings distintos (lo que el HS no ve)."""
    feats, verdad = _features_blanco_negro(n, semilla)
    rng = np.random.default_rng(semilla)
    base = {e: _norm(rng.normal(size=768)) for e in ("blanco", "negro")}
    emb = np.array([_norm(base[v] + 0.3 * rng.normal(size=768) / 28) for v in verdad])
    return np.hstack([feats[:, :LONGITUD_V1], emb]), verdad


def test_embedding_separa_lo_que_el_color_no():
    feats, verdad = _con_embeddings()
    con = TeamClassifierColor(ParametrosClasificadorColor(representacion="embedding"))
    con.fit_features(feats)
    assert _acierto(con, feats, verdad) > 0.95
    sin = TeamClassifierColor(ParametrosClasificadorColor())
    sin.fit_features(feats)
    assert _acierto(sin, feats, verdad) < 0.8


def test_vector_sin_embedding_se_decide_con_el_color():
    """El tracking puede pasar una media de COLOR: no puede romper ni compararse con embeddings."""
    feats, _ = _con_embeddings()
    clf = TeamClassifierColor(ParametrosClasificadorColor(representacion="embedding"))
    clf.fit_features(feats)
    assert clf.predict_color(feats[0][:LONGITUD_V1]) in ("A", "B", "otro")
    assert len(clf._prototipos.a) == LONGITUD_V1  # árbitro y pizarra, en su escala


def test_colores_para_equipos(tmp_path):
    import pickle

    import pytest

    from src.tracking_data.processor import colores_para_equipos

    colores = {(1, 0): np.ones(256) / 16, (1, 1): np.ones(256) / 16}
    eq_hs = {"clasificador_color": {"representacion": "hs"}}
    assert colores_para_equipos(colores, {}, eq_hs) is colores  # hoy: ni se toca
    ruta = tmp_path / "emb.pkl"
    pickle.dump(
        {"claves": [(1, 0)], "embeddings": np.ones((1, 768)), "completo": True},
        open(ruta, "wb"),
    )
    eq = {"clasificador_color": {"representacion": "embedding"}}
    salida = colores_para_equipos(
        colores, {"rutas": {"cache_embeddings": str(ruta)}}, eq
    )
    assert list(salida) == [(1, 0)] and len(salida[(1, 0)]) == 256 + 768
    with pytest.raises(ValueError, match="cache_embeddings"):
        colores_para_equipos(colores, {"rutas": {}}, eq)
