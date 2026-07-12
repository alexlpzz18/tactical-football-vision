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
    """La feature de un recorte sintético es un histograma normalizado."""
    crop = np.zeros((60, 30, 3), dtype=np.uint8)
    crop[:, :] = (0, 0, 200)  # camiseta roja (BGR)
    clf = TeamClassifierColor()
    feat = clf._color_torso(crop)
    assert feat.shape == (256,)
    assert feat.sum() == pytest.approx(1.0)


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
