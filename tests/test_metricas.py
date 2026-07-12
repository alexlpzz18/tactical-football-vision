"""Tests de las métricas del banco con casos sintéticos de resultado conocido."""

import numpy as np
import pytest

from src.evaluation.adaptador import identidades_a_por_frame
from src.evaluation.metricas import accuracy_equipos, calcular_metricas_tracking
from src.evaluation.modelo import Observacion
from src.tracking.field_tracker import Tracklet

UMBRAL = 2.0
FRAMES = list(range(10))


def _obs(obj_id, x, y, team=None, label="player"):
    return Observacion(obj_id=obj_id, pos=np.array([x, y]), team=team, label=label)


def _gt_dos_jugadores():
    """GT: jugador 1 (equipo A) quieto en (10,10); jugador 2 (B) en (30,30)."""
    return {f: [_obs(1, 10.0, 10.0, "A"), _obs(2, 30.0, 30.0, "B")] for f in FRAMES}


def test_tracker_perfecto_idf1_1():
    """Predicciones idénticas al GT → IDF1=1.0, 0 switches, 0 fragmentaciones."""
    gt = _gt_dos_jugadores()
    pred = {f: [_obs(7, 10.0, 10.0), _obs(9, 30.0, 30.0)] for f in FRAMES}
    r = calcular_metricas_tracking(gt, pred, FRAMES, UMBRAL)
    assert r.idf1 == pytest.approx(1.0)
    assert r.id_switches == 0
    assert r.fragmentaciones == 0
    assert r.recall == pytest.approx(1.0)
    assert r.precision == pytest.approx(1.0)


def test_intercambio_de_ids_a_mitad():
    """Las predicciones intercambian IDs en el frame 5 → IDF1=0.5, IDSW=2."""
    gt = _gt_dos_jugadores()
    pred = {}
    for f in FRAMES:
        if f < 5:
            pred[f] = [_obs(7, 10.0, 10.0), _obs(9, 30.0, 30.0)]
        else:
            pred[f] = [_obs(9, 10.0, 10.0), _obs(7, 30.0, 30.0)]
    r = calcular_metricas_tracking(gt, pred, FRAMES, UMBRAL)
    # Cada identidad pred cubre 5 frames de cada GT → IDTP=10 de 20
    assert r.idf1 == pytest.approx(0.5)
    assert r.id_switches == 2  # ambos jugadores cambian de ID en el frame 5
    assert r.fragmentaciones == 0


def test_fragmentacion_sin_switch():
    """El jugador se pierde 3 frames y vuelve con el MISMO id → 1 frag, 0 IDSW."""
    gt = {f: [_obs(1, 10.0, 10.0, "A")] for f in FRAMES}
    pred = {f: [_obs(7, 10.0, 10.0)] for f in FRAMES if f not in (4, 5, 6)}
    r = calcular_metricas_tracking(gt, pred, FRAMES, UMBRAL)
    assert r.id_switches == 0
    assert r.fragmentaciones == 1
    assert r.idf1 == pytest.approx(2 * 7 / (2 * 7 + 0 + 3))


def test_prediccion_lejana_no_empareja():
    """Una predicción a más del umbral no cuenta como acierto."""
    gt = {0: [_obs(1, 10.0, 10.0, "A")]}
    pred = {0: [_obs(7, 15.0, 10.0)]}  # a 5 m > umbral 2 m
    r = calcular_metricas_tracking(gt, pred, [0], UMBRAL)
    assert r.idf1 == pytest.approx(0.0)
    assert r.recall == 0.0


def test_accuracy_equipos_voto_mayoritario():
    """Identidades con equipo declarado se puntúan contra el voto GT."""
    gt = _gt_dos_jugadores()
    pred = {
        f: [_obs(7, 10.0, 10.0, team="A"), _obs(9, 30.0, 30.0, team="A")]
        for f in FRAMES
    }
    r = accuracy_equipos(gt, pred, FRAMES, UMBRAL)
    # id 7 declara A y su GT mayoritario es A (acierto); id 9 declara A pero
    # cubre al jugador de B (fallo) → accuracy 0.5
    assert r.accuracy == pytest.approx(0.5)
    assert r.n_identidades_evaluadas == 2
    assert r.detalle[7] == ("A", "A")
    assert r.detalle[9] == ("A", "B")


def test_accuracy_equipos_sin_predicciones():
    """Sin clasificador conectado (team=None) la accuracy es None, no 0."""
    gt = _gt_dos_jugadores()
    pred = {f: [_obs(7, 10.0, 10.0), _obs(9, 30.0, 30.0)] for f in FRAMES}
    r = accuracy_equipos(gt, pred, FRAMES, UMBRAL)
    assert r.accuracy is None
    assert r.n_identidades_evaluadas == 0
    # Pero el detalle sí registra el equipo GT mayoritario de cada identidad
    assert r.detalle[7] == (None, "A")
    assert r.detalle[9] == (None, "B")


def test_el_arbitro_no_vota_equipo():
    """Los frames emparejados con el árbitro (team=None) no votan."""
    gt = {f: [_obs(1, 10.0, 10.0, team=None, label="referee")] for f in FRAMES}
    pred = {f: [_obs(7, 10.0, 10.0, team="A")] for f in FRAMES}
    r = accuracy_equipos(gt, pred, FRAMES, UMBRAL)
    assert r.accuracy is None  # ningún voto de equipo → nada evaluable
    assert 7 not in r.detalle


def test_adaptador_identidades():
    """El adaptador convierte identidades cosidas al formato común."""
    tr_a = Tracklet(1, 0.0, np.array([5.0, 5.0]), det_idx=0, frame_idx=100)
    tr_a.anadir(0.12, np.array([5.5, 5.0]), det_idx=1, frame_idx=103)
    tr_b = Tracklet(2, 0.36, np.array([6.0, 5.0]), det_idx=0, frame_idx=109)
    identidad = [tr_a, tr_b]  # una identidad cosida de dos tracklets
    por_frame = identidades_a_por_frame([identidad])
    assert set(por_frame) == {100, 103, 109}
    # Todos los frames llevan el MISMO id de identidad (1)
    assert {obs.obj_id for v in por_frame.values() for obs in v} == {1}
    np.testing.assert_allclose(por_frame[109][0].pos, [6.0, 5.0])


def test_umbral_profundidad_recta_y_recortes():
    """umbral(my) = clip(base + por_metro*my, minimo, maximo)."""
    from src.evaluation.asociacion import UmbralProfundidad

    u = UmbralProfundidad(base=0.4, por_metro=0.045, minimo=1.0, maximo=4.0)
    assert u.para(0.0) == pytest.approx(1.0)  # 0.4 < minimo → recorta
    assert u.para(30.0) == pytest.approx(0.4 + 0.045 * 30)  # zona lineal
    assert u.para(100.0) == pytest.approx(4.0)  # > maximo → recorta


def test_asociacion_umbral_depende_de_profundidad():
    """El mismo error de 2.5 m empareja en el fondo pero no en el cercano."""
    from src.evaluation.asociacion import UmbralProfundidad, asociar_frame

    u = UmbralProfundidad(base=0.4, por_metro=0.045, minimo=1.0, maximo=4.0)
    # Cerca (my=10 → umbral 1.0): error de 2.5 m NO empareja
    cerca_gt = [_obs(1, 20.0, 10.0)]
    cerca_pred = [_obs(7, 22.5, 10.0)]
    assert asociar_frame(cerca_gt, cerca_pred, u) == []
    # Lejos (my=60 → umbral 3.1): el mismo error SÍ empareja
    lejos_gt = [_obs(1, 20.0, 60.0)]
    lejos_pred = [_obs(7, 22.5, 60.0)]
    assert asociar_frame(lejos_gt, lejos_pred, u) == [(0, 0)]


def test_resumen_equipos_permutacion_optima():
    """Si el clasificador llama B al equipo A del GT, el mapeo lo corrige."""
    from src.evaluation.metricas import resumen_equipos

    detalle = {
        1: ("B", "A"),  # el clasificador etiqueta al revés...
        2: ("B", "A"),
        3: ("A", "B"),  # ...consistentemente
        4: ("A", "B"),
        5: ("otro", "portero_A"),  # el portero no entra en accuracy de campo
    }
    r = resumen_equipos(detalle)
    assert r.permutado is True
    assert r.accuracy_campo == pytest.approx(1.0)
    assert r.n_campo == 4
    # La confusión se reporta YA mapeada
    assert r.confusion["A"] == {"A": 2}
    assert r.confusion["B"] == {"B": 2}
    assert r.confusion["portero_A"] == {"otro": 1}


def test_resumen_equipos_sin_predicciones():
    from src.evaluation.metricas import resumen_equipos

    r = resumen_equipos({1: (None, "A"), 2: (None, "B")})
    assert r.accuracy_campo is None
    assert r.n_campo == 0


def test_cobertura_colectiva_tracker_perfecto():
    """Posiciones y equipos correctos → cobertura 1.0."""
    from src.evaluation.metricas import cobertura_colectiva

    gt = _gt_dos_jugadores()
    pred = {
        f: [_obs(7, 10.0, 10.0, team="A"), _obs(9, 30.0, 30.0, team="B")]
        for f in FRAMES
    }
    r = cobertura_colectiva(gt, pred, FRAMES, UMBRAL)
    assert r.cobertura == pytest.approx(1.0)
    assert r.por_grupo == {"A": 1.0, "B": 1.0}


def test_cobertura_switch_dentro_del_equipo_no_penaliza():
    """Dos jugadores del MISMO equipo intercambian IDs → cobertura 1.0."""
    from src.evaluation.metricas import cobertura_colectiva

    gt = {f: [_obs(1, 10.0, 10.0, "A"), _obs(2, 30.0, 30.0, "A")] for f in FRAMES}
    pred = {}
    for f in FRAMES:
        a, b = (7, 9) if f < 5 else (9, 7)  # switch de identidad a mitad
        pred[f] = [_obs(a, 10.0, 10.0, team="A"), _obs(b, 30.0, 30.0, team="A")]
    r = cobertura_colectiva(gt, pred, FRAMES, UMBRAL)
    assert r.cobertura == pytest.approx(1.0)  # el equipo es lo que cuenta


def test_cobertura_equipo_incorrecto_penaliza():
    from src.evaluation.metricas import cobertura_colectiva

    gt = _gt_dos_jugadores()  # jugador 1 = A, jugador 2 = B
    pred = {
        f: [_obs(7, 10.0, 10.0, team="A"), _obs(9, 30.0, 30.0, team="A")]
        for f in FRAMES
    }
    r = cobertura_colectiva(gt, pred, FRAMES, UMBRAL)
    assert r.cobertura == pytest.approx(0.5)  # B mal etiquetado no cubre


def test_cobertura_portero_cuenta_con_su_equipo():
    from src.evaluation.metricas import cobertura_colectiva

    gt = {0: [_obs(1, 91.0, 37.0, team="portero_A")]}
    pred = {0: [_obs(7, 91.0, 37.0, team="portero_A")]}
    r = cobertura_colectiva(gt, pred, [0], UMBRAL)
    assert r.cobertura == pytest.approx(1.0)
    # y también si la pred dice 'A' a secas (mismo grupo)
    pred = {0: [_obs(7, 91.0, 37.0, team="A")]}
    assert cobertura_colectiva(gt, pred, [0], UMBRAL).cobertura == pytest.approx(1.0)


def test_cobertura_sin_emparejar_o_sin_equipo_no_cubre():
    from src.evaluation.metricas import cobertura_colectiva

    gt = {0: [_obs(1, 10.0, 10.0, "A"), _obs(2, 30.0, 30.0, "B")]}
    pred = {0: [_obs(7, 10.0, 10.0, team=None)]}  # sin clasificar + B sin pred
    r = cobertura_colectiva(gt, pred, [0], UMBRAL)
    assert r.cobertura == pytest.approx(0.0)
