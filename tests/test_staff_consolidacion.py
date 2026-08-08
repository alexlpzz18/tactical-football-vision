"""Tests de la regla de staff, la consolidación final y la concurrencia."""

import numpy as np
import pytest

from src.evaluation.metricas import concurrencia_por_frame
from src.evaluation.modelo import Observacion
from src.team_classification.staff import (
    ETIQUETA_STAFF,
    ReglaStaff,
    aplicar_regla_staff,
)
from src.tracking.consolidacion import consolidar_colocadas
from src.tracking.field_tracker import Tracklet

LARGO, ANCHO = 105.0, 68.0


def _identidad(posiciones, id_tracklet=1, frame0=100):
    """Identidad de un solo tracklet con las posiciones dadas."""
    tr = Tracklet(id_tracklet, 0.0, np.array(posiciones[0], dtype=float), 0, frame0)
    for k, pos in enumerate(posiciones[1:], start=1):
        tr.anadir(0.12 * k, np.array(pos, dtype=float), 0, frame0 + 3 * k)
    return [tr]


# ── regla de staff ────────────────────────────────────────────────────


def test_staff_marca_al_de_fuera_del_campo():
    """Quien vive por encima de la banda (y<0) se marca staff; el de dentro no."""
    dentro = _identidad([(50.0, 30.0)] * 10)
    linier = _identidad([(50.0, -4.0)] * 10, id_tracklet=2)
    equipos = {1: "A", 2: "A"}
    resultado = aplicar_regla_staff(
        equipos, [dentro, linier], ReglaStaff(LARGO, ANCHO, tolerancia_m=2.0)
    )
    assert resultado[1] == "A"
    assert resultado[2] == ETIQUETA_STAFF


def test_staff_respeta_la_tolerancia():
    """Un jugador que pisa la banda (1 m fuera) NO es staff con tol 2 m."""
    pisando = _identidad([(50.0, -1.0)] * 10)
    resultado = aplicar_regla_staff(
        {1: "B"}, [pisando], ReglaStaff(LARGO, ANCHO, tolerancia_m=2.0)
    )
    assert resultado[1] == "B"


def test_staff_usa_la_mediana_no_un_pico():
    """Una excursión puntual fuera no marca staff (la mediana manda)."""
    posiciones = [(50.0, 30.0)] * 9 + [(50.0, -30.0)]
    resultado = aplicar_regla_staff(
        {1: "A"}, [_identidad(posiciones)], ReglaStaff(LARGO, ANCHO)
    )
    assert resultado[1] == "A"


def test_staff_no_juzga_con_pocas_observaciones():
    """Con menos de min_observaciones no se decide (evita artefactos)."""
    resultado = aplicar_regla_staff(
        {1: "A"},
        [_identidad([(-200.0, -300.0)] * 3)],
        ReglaStaff(LARGO, ANCHO, min_observaciones=5),
    )
    assert resultado[1] == "A"


def test_staff_pilla_el_artefacto_de_proyeccion_lejano():
    """Con observaciones suficientes, el artefacto (-125,-313) sí es staff."""
    resultado = aplicar_regla_staff(
        {1: "A"},
        [_identidad([(-125.0, -313.0)] * 8)],
        ReglaStaff(LARGO, ANCHO, min_observaciones=5),
    )
    assert resultado[1] == ETIQUETA_STAFF


# ── consolidación final ───────────────────────────────────────────────


def _tray(desplazamiento, n=200, x0=50.0, y0=30.0, real=True):
    """Trayectoria recta con un offset constante respecto a (x0, y0)."""
    return [
        (
            100 + 3 * k,
            np.array([x0 + 0.05 * k + desplazamiento[0], y0 + desplazamiento[1]]),
            real,
        )
        for k in range(n)
    ]


def test_consolida_pareja_del_mismo_equipo_pegada():
    """Dos fichas de A a 2 m sostenidos se fusionan en una."""
    trayectorias = [_tray((0.0, 0.0)), _tray((0.0, 2.0))]
    nuevas, equipos = consolidar_colocadas(
        trayectorias, {1: "A", 2: "A"}, dist_max=4.0, min_frames_comunes=100
    )
    assert len(nuevas) == 1
    assert equipos[1] == "A"
    # Conserva un punto por frame (no duplica frames)
    frames = [f for f, _p, _r in nuevas[0]]
    assert len(frames) == len(set(frames)) == 200


def test_nunca_fusiona_equipos_distintos():
    """Aunque estén pegadísimas, A y B no se juntan: eso sería inventar."""
    trayectorias = [_tray((0.0, 0.0)), _tray((0.0, 0.5))]
    nuevas, _ = consolidar_colocadas(
        trayectorias, {1: "A", 2: "B"}, dist_max=4.0, min_frames_comunes=100
    )
    assert len(nuevas) == 2


def test_no_fusiona_staff_ni_otro():
    """'staff' y 'otro' quedan fuera de la consolidación."""
    trayectorias = [_tray((0.0, 0.0)), _tray((0.0, 1.0))]
    nuevas, _ = consolidar_colocadas(
        trayectorias, {1: "staff", 2: "staff"}, dist_max=4.0, min_frames_comunes=100
    )
    assert len(nuevas) == 2


def test_exige_proximidad_sostenida_no_un_cruce():
    """Pocos frames comunes → no se decide (aunque coincidan en ellos)."""
    corta = [(100 + 3 * k, np.array([50.0, 30.0]), True) for k in range(10)]
    larga = _tray((0.0, 0.0))
    nuevas, _ = consolidar_colocadas(
        [larga, corta], {1: "A", 2: "A"}, dist_max=4.0, min_frames_comunes=100
    )
    assert len(nuevas) == 2


def test_prioriza_las_posiciones_con_mas_observaciones_reales():
    """En los frames compartidos gana la ficha mejor soportada por detecciones."""
    fantasma = _tray((0.0, 1.0), real=False)  # todo interpolado
    solida = _tray((0.0, 0.0), real=True)
    nuevas, _ = consolidar_colocadas(
        [fantasma, solida], {1: "A", 2: "A"}, dist_max=4.0, min_frames_comunes=100
    )
    assert len(nuevas) == 1
    # La posición conservada es la de la sólida (y=30.0), no la del fantasma
    assert nuevas[0][0][1][1] == pytest.approx(30.0)


def test_fusion_transitiva_de_un_racimo():
    """A≈B y B≈C → un solo racimo fusionado."""
    trayectorias = [_tray((0.0, 0.0)), _tray((0.0, 3.0)), _tray((0.0, 6.0))]
    nuevas, _ = consolidar_colocadas(
        trayectorias, {1: "A", 2: "A", 3: "A"}, dist_max=4.0, min_frames_comunes=100
    )
    assert len(nuevas) == 1


# ── métrica de concurrencia ───────────────────────────────────────────


def test_concurrencia_cuenta_identidades_simultaneas():
    """Mediana/p90 de fichas por frame, y el exceso frente al GT."""
    gt = {
        f: [Observacion(i, np.array([0.0, 0.0])) for i in range(2)] for f in range(10)
    }
    pred = {
        f: [Observacion(i, np.array([0.0, 0.0])) for i in range(5)] for f in range(10)
    }
    resultado = concurrencia_por_frame(gt, pred, list(range(10)))
    assert resultado.mediana_pred == 5
    assert resultado.mediana_gt == 2
    assert resultado.exceso_mediana == 3
    assert resultado.max_pred == 5
