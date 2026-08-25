"""Tests del escalado por resolución, el espejado y los colores reales.

Las tres piezas salen del diagnóstico del benjamín (09-ago-2026): 138
cortes de velocidad por umbrales fijos en un encuadre donde un píxel vale
de 0,02 a 0,44 m, y un replay que obligaba a traducir mentalmente la
orientación y los colores.
"""

import json

import numpy as np
import pandas as pd
import pytest

from src.report.replay_tactico import colores_con_equipos, generar_replay
from src.team_classification.color_classifier import color_dominante
from src.tracking.consolidacion import consolidar_colocadas
from src.tracking.corte_velocidad import cortar_por_velocidad
from src.tracking.resolucion import ResolucionCampo

TIEMPOS = {100 + 3 * k: 0.12 * k for k in range(300)}


def _homografia_tras_porteria(altura=3.0, retroceso=12.0, f=1200.0, ancho=40.0):
    """H píxel→metros de una cámara baja detrás de la portería x=0."""
    import cv2

    metros, pixeles = [], []
    for x in (2.0, 20.0, 40.0, 60.0):
        for y in (5.0, 20.0, 35.0):
            dx = x + retroceso
            metros.append((x, y))
            pixeles.append((1280 + f * (y - ancho / 2) / dx, 540 + f * altura / dx))
    H, _ = cv2.findHomography(
        np.array(pixeles, dtype=np.float64), np.array(metros, dtype=np.float64)
    )
    return H


@pytest.fixture(scope="module")
def resolucion():
    return ResolucionCampo(_homografia_tras_porteria(), largo=62.0, ancho=40.0)


# ── resolución del campo ──────────────────────────────────────────────


def test_la_resolucion_empeora_al_alejarse_de_la_camara(resolucion):
    """Es la física del encuadre: cerca 1 px vale centímetros, lejos metros."""
    cerca = resolucion.metros_por_pixel((5.0, 20.0))
    medio = resolucion.metros_por_pixel((31.0, 20.0))
    lejos = resolucion.metros_por_pixel((58.0, 20.0))
    assert cerca < medio < lejos
    assert lejos > cerca * 5
    assert resolucion.factor((5.0, 20.0)) == pytest.approx(
        cerca / resolucion.mpp_min, rel=0.2
    )


def test_velocidad_de_ruido_crece_con_la_distancia(resolucion):
    """El mismo jitter de caja vale muchos más m/s en el fondo."""
    cerca = resolucion.velocidad_ruido((5.0, 20.0), jitter_px=2.0, dt=0.12)
    lejos = resolucion.velocidad_ruido((58.0, 20.0), jitter_px=2.0, dt=0.12)
    assert lejos > cerca * 5
    assert cerca < 2.0  # junto a la cámara el ruido no llega a 2 m/s


# ── el corte deja de trocear el fondo ─────────────────────────────────


def _tray_con_jitter(x_base, n=60, amplitud=0.0, semilla=0):
    """Identidad quieta en x_base cuya CAJA vibra `amplitud` metros.

    El temblor es alterno (la caja "respira" entre frames), que es lo que
    de verdad produce rachas sostenidas de velocidad aparente: un ruido
    puramente aleatorio se compensa y no dispara el criterio.
    """
    return [
        (
            100 + 3 * k,
            np.array([x_base + amplitud * (1 if k % 2 else -1), 20.0]),
            True,
        )
        for k in range(n)
    ]


def test_sin_escalado_el_ruido_del_fondo_destruye_la_identidad():
    """Documenta el problema que motivó todo esto.

    1,5 m de temblor de caja a dt=0,12 s son ~12 m/s de velocidad
    aparente: con el umbral fijo de 8,5 la racha nunca se interrumpe, así
    que la identidad se trocea en pedazos tan pequeños que ninguno llega
    al mínimo de observaciones y desaparece ENTERA. En el benjamín esto
    se vio como 138 cortes en un minuto.
    """
    tray = _tray_con_jitter(58.0, amplitud=1.5)
    nuevas, _ = cortar_por_velocidad(
        [tray], {1: "A"}, TIEMPOS, v_max=8.5, duracion_min=0.5, resolucion=None
    )
    assert len(nuevas) != 1  # no sobrevive intacta
    assert sum(len(t) for t in nuevas) < len(tray)  # se pierden observaciones


def test_con_escalado_el_mismo_ruido_ya_no_corta(resolucion):
    """El umbral local absorbe el ruido de ESA zona."""
    tray = _tray_con_jitter(58.0, amplitud=1.5)
    nuevas, _ = cortar_por_velocidad(
        [tray],
        {1: "A"},
        TIEMPOS,
        v_max=8.5,
        duracion_min=0.5,
        resolucion=resolucion,
        jitter_px=2.0,
    )
    assert len(nuevas) == 1


def test_el_escalado_no_ciega_la_zona_cercana(resolucion):
    """Un teletransporte real junto a la cámara se sigue cortando."""
    quieto = [(100 + 3 * k, np.array([5.0, 20.0]), True) for k in range(20)]
    saltado = [
        (100 + 3 * (20 + k), np.array([5.0 + 4.0 * k, 20.0]), True) for k in range(10)
    ]
    lejos = [(100 + 3 * (30 + k), np.array([45.0, 20.0]), True) for k in range(20)]
    nuevas, _ = cortar_por_velocidad(
        [quieto + saltado + lejos],
        {1: "A"},
        TIEMPOS,
        v_max=8.5,
        duracion_min=0.5,
        resolucion=resolucion,
        jitter_px=2.0,
    )
    assert len(nuevas) > 1


# ── consolidación con umbral local ────────────────────────────────────


def test_consolidacion_es_mas_permisiva_donde_peor_se_ve(resolucion):
    """Dos fichas del mismo jugador se separan más lejos de la cámara."""

    def par(x_base, separacion):
        a = [(100 + 3 * k, np.array([x_base, 20.0]), True) for k in range(200)]
        b = [
            (100 + 3 * k, np.array([x_base, 20.0 + separacion]), True)
            for k in range(200)
        ]
        return [a, b]

    # 4,6 m de separación: por encima del dist_max fijo de 4,0
    fijo, _ = consolidar_colocadas(
        par(58.0, 4.6), {1: "A", 2: "A"}, dist_max=4.0, min_frames_comunes=100
    )
    assert len(fijo) == 2  # sin escalado no se fusionan

    local, _ = consolidar_colocadas(
        par(58.0, 4.6),
        {1: "A", 2: "A"},
        dist_max=4.0,
        min_frames_comunes=100,
        resolucion=resolucion,
        jitter_px=2.0,
    )
    assert len(local) == 1  # en el fondo, 4,6 m entra en el margen de ruido

    # Y junto a la cámara ese mismo margen NO se amplía apenas
    cerca, _ = consolidar_colocadas(
        par(5.0, 4.6),
        {1: "A", 2: "A"},
        dist_max=4.0,
        min_frames_comunes=100,
        resolucion=resolucion,
        jitter_px=2.0,
    )
    assert len(cerca) == 2


# ── colores reales de equipo ──────────────────────────────────────────


def test_color_dominante_de_un_histograma_naranja():
    hist = np.zeros((16, 16))
    hist[1, 13] = 1.0  # tono bajo (naranja) y saturación alta
    r, g, b = color_dominante(hist.flatten())
    assert r > g > b  # naranja: mucho rojo, algo de verde, poco azul
    assert r > 200


def test_color_dominante_sin_saturacion_es_claro():
    hist = np.zeros((16, 16))
    hist[0, 0] = 1.0
    r, g, b = color_dominante(hist.flatten())
    assert min(r, g, b) > 200  # blanco/gris claro, no negro


def test_feature_vacia_cae_a_gris():
    assert color_dominante(np.zeros(256)) == (128, 128, 128)


def test_la_paleta_usa_los_colores_del_equipo():
    paleta = colores_con_equipos({"A": "#e8721c", "B": "#f2f2f2"})
    assert paleta["A"][0] == "#e8721c"
    assert paleta["B"][0] == "#f2f2f2"
    # El portero lleva el color de su equipo, oscurecido
    assert paleta["portero_A"][0] != paleta["A"][0]
    assert paleta["portero_A"][0].startswith("#")


def test_sin_colores_se_mantiene_el_convenio():
    from src.report.replay_tactico import COLORES

    assert colores_con_equipos(None) == COLORES
    assert colores_con_equipos({})["A"] == COLORES["A"]


# ── espejado de la vista ──────────────────────────────────────────────


def _csv_minimo(tmp_path):
    filas = [
        dict(
            frame=100 + 3 * k,
            tiempo_s=round(0.12 * k, 2),
            id_jugador=1,
            equipo=0,
            etiqueta="A",
            x_m=20.0,
            y_m=15.0,
            es_real=1,
        )
        for k in range(40)
    ]
    ruta = tmp_path / "pos.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    return ruta


def test_espejar_solo_afecta_al_dibujo(tmp_path):
    """Los datos embebidos no cambian; cambia cómo se proyectan."""
    ruta = _csv_minimo(tmp_path)
    normal = generar_replay(ruta, tmp_path / "n.html").read_text()
    espejado = generar_replay(ruta, tmp_path / "e.html", espejar="x").read_text()

    def datos(html):
        return json.loads(html.split("const DATOS = ")[1].split(";\n")[0])

    assert datos(normal) == datos(espejado)  # las posiciones son las mismas
    assert "ESPEJO_X = false" in normal
    assert "ESPEJO_X = true" in espejado
    assert "ESPEJO_Y = false" in espejado


def test_espejar_xy_voltea_los_dos_ejes(tmp_path):
    html = generar_replay(
        _csv_minimo(tmp_path), tmp_path / "r.html", espejar="xy"
    ).read_text()
    assert "ESPEJO_X = true" in html and "ESPEJO_Y = true" in html


def test_espejar_invalido_falla_claro(tmp_path):
    with pytest.raises(ValueError, match="espejar debe ser"):
        generar_replay(_csv_minimo(tmp_path), tmp_path / "r.html", espejar="z")


def test_el_replay_lleva_los_colores_reales(tmp_path):
    html = generar_replay(
        _csv_minimo(tmp_path),
        tmp_path / "r.html",
        colores_equipo={"A": "#e8721c", "B": "#f2f2f2"},
    ).read_text()
    colores = json.loads(html.split("const COLORES = ")[1].split(";\n")[0])
    assert colores["A"][0] == "#e8721c"
    assert "#2563eb" not in html  # el azul por convenio ya no aparece


# ── n_init del KMeans: era el canal de ruido de Villaviciosa ───────────


def test_n_init_se_lee_del_config_y_llega_al_kmeans(monkeypatch):
    """Si `n_init` no llega al KMeans, el arreglo no existe y nadie se entera.

    Adoptado 10 → 50 el 25-ago-2026: con 10, dos inicializaciones caían en
    óptimos locales distintos y una detección de más bastaba para que
    ganase otro, cambiando la partición A/B entera.
    """
    import numpy as np
    from sklearn.cluster import KMeans as KMeansReal

    from src.team_classification import color_classifier as cc

    # Se espía con una FÁBRICA y no con una subclase: sklearn valida que
    # sus estimadores declaren los parámetros en la firma de __init__ y
    # rechaza un *args/**kw.
    vistos = []

    def kmeans_espia(**kw):
        vistos.append(kw.get("n_init"))
        return KMeansReal(**kw)

    monkeypatch.setattr(cc, "KMeans", kmeans_espia)
    params = cc.ParametrosClasificadorColor.desde_dict({"k_clusters": 4, "n_init": 37})
    assert params.n_init == 37
    rng = np.random.RandomState(0)
    features = np.abs(rng.randn(60, 256))
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    cc.TeamClassifierColor(params).fit_features(features)
    assert 37 in vistos


def test_el_fit_es_determinista_con_los_mismos_datos():
    """Mismo caché, mismos prototipos. Sin esto, nada de lo medido se repite."""
    import numpy as np

    from src.team_classification.color_classifier import (
        ParametrosClasificadorColor,
        TeamClassifierColor,
    )

    rng = np.random.RandomState(3)
    features = np.abs(rng.randn(120, 256))
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    params = ParametrosClasificadorColor.desde_dict({"k_clusters": 6, "n_init": 20})
    protos = []
    for _ in range(2):
        clf = TeamClassifierColor(params)
        clf.fit_features(features)
        protos.append(clf._prototipos)
    assert np.allclose(protos[0].a, protos[1].a)
    assert np.allclose(protos[0].b, protos[1].b)
