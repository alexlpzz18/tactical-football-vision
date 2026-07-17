"""Tests del clasificador de equipos por color con datos sintéticos."""

import numpy as np
import pytest

from src.team_classification.color_classifier import (
    ParametrosClasificadorColor,
    TeamClassifierColor,
)

RNG = np.random.default_rng(7)


def _feature_sintetica(bin_dominante: int, ruido: float = 0.0005) -> np.ndarray:
    """Histograma 256 con masa concentrada en un bin + ruido, normalizado.

    El ruido es bajo para que la masa quede en el bin dominante (como una
    camiseta de color uniforme) y los grupos disten >0.5 entre sí, dentro
    del rango del barrido de fusión del clasificador.
    """
    feat = RNG.random(256) * ruido
    feat[bin_dominante] = 1.0
    return feat / feat.sum()


def _poblacion(bin_a=10, bin_b=200, bin_otro=120, n_a=200, n_b=180, n_otro=25):
    """Población sintética: dos equipos grandes + un grupo pequeño (árbitro)."""
    feats = (
        [_feature_sintetica(bin_a) for _ in range(n_a)]
        + [_feature_sintetica(bin_b) for _ in range(n_b)]
        + [_feature_sintetica(bin_otro) for _ in range(n_otro)]
    )
    etiquetas = ["eq1"] * n_a + ["eq2"] * n_b + ["otro"] * n_otro
    return np.array(feats), etiquetas


def test_fit_separa_dos_equipos_y_otro():
    """Con 3 grupos de color, los 2 grandes son A/B y el pequeño 'otro'."""
    feats, etiquetas = _poblacion()
    clf = TeamClassifierColor()
    clf.fit_features(feats)
    pred = [clf.predict_color(f) for f in feats]
    # Cada grupo real debe recibir una etiqueta ÚNICA y consistente
    por_grupo = {}
    for etiqueta_real, etiqueta_pred in zip(etiquetas, pred):
        por_grupo.setdefault(etiqueta_real, []).append(etiqueta_pred)
    mayoritaria = {g: max(set(v), key=v.count) for g, v in por_grupo.items()}
    # Los dos equipos reciben A y B (en algún orden); el grupo chico, 'otro'
    assert {mayoritaria["eq1"], mayoritaria["eq2"]} == {"A", "B"}
    assert mayoritaria["otro"] == "otro"
    # Y la consistencia dentro de cada grupo es alta
    for g, v in por_grupo.items():
        assert v.count(mayoritaria[g]) / len(v) > 0.95


def test_el_equipo_mas_grande_es_A():
    """Los meta-grupos se ordenan POR TAMAÑO: el mayor es A."""
    feats, etiquetas = _poblacion(n_a=300, n_b=100, n_otro=20)
    clf = TeamClassifierColor()
    clf.fit_features(feats)
    pred_eq1 = clf.predict_color(feats[0])  # miembro del grupo grande
    assert pred_eq1 == "A"


def test_predict_sin_fit_lanza_error():
    clf = TeamClassifierColor()
    with pytest.raises(RuntimeError, match="no está entrenado"):
        clf.predict_color(np.zeros(256))


def test_fit_con_pocas_features_lanza_error():
    clf = TeamClassifierColor()
    with pytest.raises(ValueError, match="al menos"):
        clf.fit_features(np.zeros((3, 256)))


def test_color_torso_feature_valida():
    """La feature de un recorte sintético es un histograma normalizado L2."""
    crop = np.zeros((60, 30, 3), dtype=np.uint8)
    crop[:, :] = (0, 0, 200)  # camiseta roja (BGR)
    clf = TeamClassifierColor()
    feat = clf._color_torso(crop)
    assert feat.shape == (256,)
    assert np.linalg.norm(feat) == pytest.approx(1.0)


def test_color_torso_ignora_el_verde():
    """Un recorte 100% césped (verde saturado) da feature nula."""
    crop = np.zeros((60, 30, 3), dtype=np.uint8)
    crop[:, :] = (60, 200, 60)  # verde césped en BGR
    clf = TeamClassifierColor()
    feat = clf._color_torso(crop)
    assert feat.sum() == pytest.approx(0.0)


def test_camisetas_distintas_features_distantes():
    """Camiseta roja vs azul → features claramente separadas."""
    rojo = np.zeros((60, 30, 3), dtype=np.uint8)
    rojo[:, :] = (0, 0, 200)
    azul = np.zeros((60, 30, 3), dtype=np.uint8)
    azul[:, :] = (200, 0, 0)
    clf = TeamClassifierColor()
    d = np.linalg.norm(clf._color_torso(rojo) - clf._color_torso(azul))
    assert d > 1.0  # histogramas disjuntos → distancia ~sqrt(2)


def test_parametros_desde_dict():
    p = ParametrosClasificadorColor.desde_dict(
        {"torso_alto": [0.1, 0.5], "k_clusters": 6}
    )
    assert p.torso_alto == (0.1, 0.5)
    assert p.k_clusters == 6


# ── Regresión de la EXTRACCIÓN (bug de producción 12-jul-2026) ──────────
# La extracción es una única función compartida (extraer_color_torso) con
# normalización L2 — la escala del extractor validado del notebook, en la
# que están calibrados todos los umbrales del sistema. Estos tests fijan
# features CONOCIDAS bin a bin: si alguien cambia banda, máscara, orden de
# canales o normalización, fallan.


def _crop_uniforme(bgr, alto=60, ancho=30):
    crop = np.zeros((alto, ancho, 3), dtype=np.uint8)
    crop[:, :] = bgr
    return crop


def test_extraccion_rojo_bin_exacto():
    """Camiseta roja BGR(0,0,200): H=0 (bin 0), S=255 (bin 15) → índice 15."""
    from src.team_classification.color_classifier import extraer_color_torso

    feat = extraer_color_torso(_crop_uniforme((0, 0, 200)))
    assert feat[15] == pytest.approx(1.0)  # todo el torso en un bin, L2=1
    assert np.count_nonzero(feat) == 1


def test_extraccion_azul_bin_exacto():
    """Camiseta azul BGR(200,0,0): H=120 (bin 10), S=255 (bin 15) → 175."""
    from src.team_classification.color_classifier import extraer_color_torso

    feat = extraer_color_torso(_crop_uniforme((200, 0, 0)))
    assert feat[10 * 16 + 15] == pytest.approx(1.0)
    assert np.count_nonzero(feat) == 1


def test_extraccion_mitad_y_mitad_es_l2():
    """Torso mitad rojo / mitad azul → dos bins a 1/√2 (normalización L2,
    NO por suma: por suma darían 0.5 y el fit colapsa — el bug de Colab)."""
    from src.team_classification.color_classifier import extraer_color_torso

    crop = _crop_uniforme((0, 0, 200))
    crop[:, 15:] = (200, 0, 0)  # media camiseta azul
    feat = extraer_color_torso(crop)
    # La banda del torso es el 15-85% del ancho (cols 4..24): quedan 11
    # columnas rojas y 10 azules → pesos exactos 11/√221 y 10/√221
    assert feat[15] == pytest.approx(11 / np.sqrt(11**2 + 10**2), abs=1e-6)
    assert feat[175] == pytest.approx(10 / np.sqrt(11**2 + 10**2), abs=1e-6)
    assert np.linalg.norm(feat) == pytest.approx(1.0)


def test_extraccion_cesped_da_cero():
    """Verde césped puro → máscara lo elimina todo → vector nulo."""
    from src.team_classification.color_classifier import extraer_color_torso

    feat = extraer_color_torso(_crop_uniforme((60, 200, 60)))
    assert feat.sum() == pytest.approx(0.0)


def test_extraccion_misma_escala_que_referencia():
    """Toda feature no-nula debe vivir en la esfera unidad L2 (la firma del
    caché de referencia del notebook: 96% con ||f||=1 exacto, resto ceros)."""
    from src.team_classification.color_classifier import extraer_color_torso

    rng = np.random.default_rng(3)
    for _ in range(10):
        crop = rng.integers(0, 256, size=(40, 20, 3), dtype=np.uint8)
        feat = extraer_color_torso(crop)
        if feat.sum() > 0:
            assert np.linalg.norm(feat) == pytest.approx(1.0)
