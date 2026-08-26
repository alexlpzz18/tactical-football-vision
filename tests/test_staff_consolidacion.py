"""Tests de la regla de staff, la consolidación final y la concurrencia."""

import logging

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
    """Con menos de min_observaciones no se decide CERCA DE LA LÍNEA.

    ⚠️ El caso que probaba antes —3 observaciones a (-200, -300), o sea
    300 m fuera— ya NO se abstiene, y es a propósito: desde el
    26-ago-2026 hay `min_obs_lejos_m`, porque a esa distancia no hay error
    de proyección que lo explique y un señor del campo de al lado con 4
    detecciones se colaba como jugador. El mínimo sigue valiendo donde
    tiene sentido: junto a la línea.
    """
    resultado = aplicar_regla_staff(
        {1: "A"},
        [_identidad([(-3.0, 20.0)] * 3)],
        ReglaStaff(LARGO, ANCHO, min_observaciones=5, min_obs_lejos_m=6.0),
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


# ── corte por velocidad imposible ─────────────────────────────────────


def _serie(posiciones, frame0=100, paso=3):
    """Trayectoria (frame, pos, real) a partir de una lista de (x, y)."""
    return [
        (frame0 + paso * k, np.array(p, dtype=float), True)
        for k, p in enumerate(posiciones)
    ]


TIEMPOS_TEST = {100 + 3 * k: 0.12 * k for k in range(200)}


def test_corte_parte_la_identidad_en_el_teletransporte():
    """Una identidad que salta 40 m durante 1 s se parte en dos."""
    from src.tracking.corte_velocidad import cortar_por_velocidad

    quieto_a = [(10.0, 10.0)] * 10
    salto = [(10.0 + 5 * k, 10.0) for k in range(1, 9)]  # ~41 m/s sostenidos
    quieto_b = [(50.0, 10.0)] * 10
    tray = _serie(quieto_a + salto + quieto_b)
    nuevas, equipos = cortar_por_velocidad(
        [tray], {1: "A"}, TIEMPOS_TEST, v_max=8.5, duracion_min=0.5
    )
    assert len(nuevas) == 2
    assert equipos == {1: "A", 2: "A"}  # ambos trozos heredan el equipo
    # Y ya no queda ningún paso imposible dentro de un trozo
    for trozo in nuevas:
        for (f0, p0, _), (f1, p1, _) in zip(trozo[:-1], trozo[1:]):
            dt = TIEMPOS_TEST[f1] - TIEMPOS_TEST[f0]
            assert np.linalg.norm(p1 - p0) / dt <= 8.5


def test_corte_ignora_el_ruido_de_un_solo_paso():
    """Un salto puntual (ruido del fondo) NO parte la identidad."""
    from src.tracking.corte_velocidad import cortar_por_velocidad

    posiciones = [(10.0, 10.0)] * 5 + [(13.0, 10.0)] + [(10.0, 10.0)] * 5
    nuevas, _ = cortar_por_velocidad(
        [_serie(posiciones)], {1: "A"}, TIEMPOS_TEST, v_max=8.5, duracion_min=0.5
    )
    assert len(nuevas) == 1


def test_corte_descarta_los_trozos_de_parpadeo():
    """Los fragmentos por debajo de min_observaciones no sobreviven."""
    from src.tracking.corte_velocidad import cortar_por_velocidad

    salto = [(10.0 + 5 * k, 10.0) for k in range(8)]
    tray = _serie(salto + [(50.0, 10.0)] * 10)
    nuevas, _ = cortar_por_velocidad(
        [tray],
        {1: "A"},
        TIEMPOS_TEST,
        v_max=8.5,
        duracion_min=0.5,
        min_observaciones=3,
    )
    assert len(nuevas) == 1  # el trozo inicial (dentro de la racha) se cae


def test_metrica_de_transiciones_detecta_la_racha():
    """transiciones_imposibles cuenta la racha y reporta la v máxima."""
    from src.evaluation.metricas import transiciones_imposibles

    pred = {}
    for k in range(20):
        frame = 100 + 3 * k
        x = 10.0 if k < 5 else (10.0 + 5 * (k - 4) if k < 13 else 50.0)
        pred[frame] = [Observacion(1, np.array([x, 10.0]))]
    resultado = transiciones_imposibles(pred, TIEMPOS_TEST, v_max=8.5, duracion_min=0.5)
    assert resultado.n_rachas == 1
    assert resultado.n_identidades_afectadas == 1
    assert resultado.v_max_observada > 8.5


def test_corte_parte_el_salto_instantaneo():
    """Un teletransporte de un solo frame (>v_teleport) también parte."""
    from src.tracking.corte_velocidad import cortar_por_velocidad

    # 30 m de golpe en un frame (0.12 s) = 250 m/s: no es racha, es salto
    posiciones = [(10.0, 10.0)] * 8 + [(40.0, 10.0)] * 8
    nuevas, _ = cortar_por_velocidad(
        [_serie(posiciones)],
        {1: "A"},
        TIEMPOS_TEST,
        v_max=8.5,
        duracion_min=0.5,
        v_teleport=60.0,
    )
    assert len(nuevas) == 2


def test_corte_sin_v_teleport_no_parte_el_salto_suelto():
    """Con v_teleport=None solo actúa el criterio de racha sostenida."""
    from src.tracking.corte_velocidad import cortar_por_velocidad

    posiciones = [(10.0, 10.0)] * 8 + [(40.0, 10.0)] * 8
    nuevas, _ = cortar_por_velocidad(
        [_serie(posiciones)],
        {1: "A"},
        TIEMPOS_TEST,
        v_max=8.5,
        duracion_min=0.5,
        v_teleport=None,
    )
    assert len(nuevas) == 1


def test_teleport_no_dispara_con_el_ruido_del_fondo():
    """El umbral de teletransporte está por encima del ruido lejano.

    2,4 m entre frames es el p90 del error de localización en el fondo
    (≈20 m/s a dt=0,12 s): el criterio de SALTO no debe verlo. Se aísla
    subiendo v_max para que no intervenga el criterio de racha, que sí
    corta una oscilación sostenida de esa amplitud (y debe hacerlo).
    """
    from src.tracking.corte_velocidad import cortar_por_velocidad

    posiciones = [(10.0 + 2.4 * (k % 2), 60.0) for k in range(16)]
    nuevas, _ = cortar_por_velocidad(
        [_serie(posiciones)],
        {1: "A"},
        TIEMPOS_TEST,
        v_max=1e9,
        duracion_min=0.5,
        v_teleport=60.0,
    )
    assert len(nuevas) == 1


def test_racha_sostenida_de_ruido_grande_si_se_corta():
    """Documenta el reverso: una oscilación sostenida de 2,4 m SÍ corta.

    Es intencionado: 20 m/s mantenidos durante 2 s no es un jugador,
    aunque la amplitud individual parezca ruido.
    """
    from src.tracking.corte_velocidad import cortar_por_velocidad

    posiciones = [(10.0 + 2.4 * (k % 2), 60.0) for k in range(16)]
    nuevas, _ = cortar_por_velocidad(
        [_serie(posiciones)],
        {1: "A"},
        TIEMPOS_TEST,
        v_max=8.5,
        duracion_min=0.5,
        v_teleport=60.0,
    )
    assert nuevas == []  # todos los trozos quedan por debajo del mínimo


# ── Segunda tolerancia: fuera de la línea Y casi quieto ────────────────
#
# Regla adoptada el 25-ago-2026. Los tres casos que la definen y que
# salieron de medir, no de suponer:
#   - el entrenador: 0,23 m fuera y 0,67 m/s -> staff
#   - un jugador real: 0,22 m fuera y 3,50 m/s -> NO es staff (un
#     centímetro separa su mediana de la del entrenador)
#   - el portero: 0,60 m/s, el más lento del partido, pero DENTRO del
#     campo -> NO es staff (si la velocidad mandara sola, se lo llevaría)


def _identidad_recta(x0, y0, dx, dy, n=30, dt=0.12):
    """Identidad que avanza (dx, dy) metros por muestra."""
    from src.tracking.field_tracker import Tracklet

    tr = Tracklet(1, 0.0, np.array([x0, y0]), 0, 0)
    for i in range(1, n):
        tr.anadir(i * dt, np.array([x0 + dx * i, y0 + dy * i]), i, i)
    return [tr]


def test_staff_lento_caza_al_entrenador_fuera_de_la_linea():
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff

    # 0,23 m fuera de la banda y prácticamente quieto (0,67 m/s)
    ident = _identidad_recta(31.0, -0.23, 0.0, 0.0)
    ident[0].pos = [
        np.array([31.0 + 0.04 * (i % 3), -0.23]) for i in range(len(ident[0].pos))
    ]
    regla = ReglaStaff(
        largo=62.0,
        ancho=40.0,
        tolerancia_m=2.0,
        tolerancia_lento_m=0.15,
        vel_max_lento=1.5,
    )
    assert aplicar_regla_staff({1: "A"}, [ident], regla)[1] == "staff"


def test_staff_lento_respeta_al_jugador_rapido_pisando_la_banda():
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff

    # 0,22 m fuera de la banda contraria pero corriendo (3,5 m/s)
    ident = _identidad_recta(27.5, 40.22, 0.42, 0.0)
    regla = ReglaStaff(
        largo=62.0,
        ancho=40.0,
        tolerancia_m=2.0,
        tolerancia_lento_m=0.15,
        vel_max_lento=1.5,
    )
    assert aplicar_regla_staff({1: "B"}, [ident], regla)[1] == "B"


def test_staff_lento_no_toca_al_portero_aunque_sea_el_mas_lento():
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff

    # Dentro del campo y lentísimo: es el portero, y la regla no debe verlo
    ident = _identidad_recta(6.8, 22.2, 0.01, 0.0)
    regla = ReglaStaff(
        largo=62.0,
        ancho=40.0,
        tolerancia_m=2.0,
        tolerancia_lento_m=0.15,
        vel_max_lento=1.5,
    )
    assert aplicar_regla_staff({1: "portero_A"}, [ident], regla)[1] == "portero_A"


def test_staff_lento_no_toca_al_portero_NI_DETRAS_DE_SU_LINEA():
    """El caso de borde, que es el que de verdad muerde.

    Un portero vive SOBRE la línea de fondo y se mueve poco: cumple las
    dos condiciones de la rama lenta a la vez. La primera versión de la
    regla lo convertía en staff, y eso costaba más de lo que la regla
    gana (centroide del benjamín de 1,27 a 2,04 m).
    """
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff

    # Mediana 20 cm POR DETRÁS de la línea de fondo, y a 0,4 m/s
    ident = _identidad_recta(-0.20, 20.0, 0.05, 0.0, n=40)
    regla = ReglaStaff(
        largo=62.0,
        ancho=40.0,
        tolerancia_m=2.0,
        tolerancia_lento_m=0.15,
        vel_max_lento=1.5,
    )
    assert aplicar_regla_staff({1: "portero_A"}, [ident], regla)[1] == "portero_A"


def test_staff_rechaza_tolerancia_negativa_en_la_rama_NO_lenta():
    """`tolerancia_m` va contra la distancia ACOTADA: negativa no significa nada.

    ⚠️ `tolerancia_lento_m` SÍ puede serlo desde el 26-ago-2026: esa rama
    usa distancia CON SIGNO, y ahí "-1,5" quiere decir "hasta 1,5 m DENTRO
    de la línea", que es lo que hace falta para alcanzar al entrenador.
    Son dos comparaciones contra dos distancias distintas, y por eso una
    acepta negativos y la otra no.
    """
    from src.team_classification.staff import ReglaStaff

    with pytest.raises(ValueError, match="no puede ser negativa"):
        ReglaStaff.desde_dict({"largo": 62.0, "ancho": 40.0, "tolerancia_m": -1.0})
    regla = ReglaStaff.desde_dict(
        {"largo": 62.0, "ancho": 40.0, "tolerancia_lento_m": -1.5}
    )
    assert regla.tolerancia_lento_m == -1.5


def test_velocidad_media_devuelve_None_cuando_no_se_puede_saber():
    """No lo sé NO es 0, que es justo el lado que dispara la regla."""
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff
    from src.team_classification.staff import velocidad_media
    from src.tracking.field_tracker import Tracklet

    # 30 observaciones, todas con la MISMA marca de tiempo, yendo y
    # viniendo 3 m (recorrido real ~87 m) pero con la mediana quieta a
    # 0,30 m por fuera de la banda: el caso que la rama lenta mira.
    tr = Tracklet(1, 5.0, np.array([31.0, -0.30]), 0, 0)
    for i in range(1, 30):
        tr.anadir(5.0, np.array([31.0 + 3.0 * (i % 2), -0.30]), i, i)
    assert velocidad_media([tr]) is None
    regla = ReglaStaff(
        largo=62.0,
        ancho=40.0,
        tolerancia_m=2.0,
        tolerancia_lento_m=0.15,
        vel_max_lento=1.5,
    )
    assert aplicar_regla_staff({1: "A"}, [[tr]], regla)[1] == "A"


def test_staff_lento_no_juzga_la_velocidad_de_una_identidad_corta():
    """Con 5 muestras en medio segundo, "se mueve poco" no significa nada."""
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff

    ident = _identidad_recta(31.0, -0.30, 0.0, 0.0, n=6)
    regla = ReglaStaff(
        largo=62.0,
        ancho=40.0,
        tolerancia_m=2.0,
        tolerancia_lento_m=0.15,
        vel_max_lento=1.5,
        min_obs_lento=25,
    )
    assert aplicar_regla_staff({1: "A"}, [ident], regla)[1] == "A"


def test_staff_lento_desactivado_por_defecto():
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff

    ident = _identidad_recta(31.0, -0.23, 0.0, 0.0)
    regla = ReglaStaff(largo=62.0, ancho=40.0, tolerancia_m=2.0)
    assert aplicar_regla_staff({1: "A"}, [ident], regla)[1] == "A"


def test_velocidad_media_usa_el_tiempo_real_no_el_numero_de_muestras():
    """Una identidad con huecos no debe parecer más lenta por tenerlos."""
    from src.team_classification.staff import velocidad_media

    seguida = _identidad_recta(0.0, 0.0, 0.12, 0.0, n=11)  # 1 m/s
    assert velocidad_media(seguida) == pytest.approx(1.0, rel=1e-6)
    # Misma trayectoria y misma duración, pero con la mitad de muestras
    con_hueco = _identidad_recta(0.0, 0.0, 0.24, 0.0, n=6, dt=0.24)
    assert velocidad_media(con_hueco) == pytest.approx(1.0, rel=1e-6)


# ── El portero por ÚLTIMO HOMBRE, con sus dos salvaguardas ────────────
#
# Los tres hallazgos de diseño que costó medir y que hay que blindar:
#   (a) el voto incluye a las identidades 'otro' — pedirle al color que
#       identifique al portero es circular, viste distinto por reglamento;
#   (b) compiten en LOS DOS lados — su etiqueta de equipo no es fiable;
#   (c) ninguna salvaguarda separa sola, pero cada impostor falla una.


def _campo_f7():
    from src.campo_modelo import cargar_modelo

    return cargar_modelo("f7").con_dimensiones(62.0, 40.0)


def _ident_en(x, y, n=40, dt=0.12, ruido=0.05):
    from src.tracking.field_tracker import Tracklet

    tr = Tracklet(1, 0.0, np.array([x, y]), 0, 0)
    for i in range(1, n):
        tr.anadir(i * dt, np.array([x + ruido * (i % 3), y]), i, i)
    return [tr]


def test_portero_ultimo_hombre_corona_al_de_su_area():
    from src.team_classification.porteros import (
        ReglaPorteroUltimoHombre,
        aplicar_regla_portero_ultimo_hombre,
    )

    modelo = _campo_f7()
    portero = _ident_en(4.0, 20.0)  # dentro del área de x=0
    defensa = _ident_en(20.0, 20.0)
    delantero = _ident_en(45.0, 20.0)
    equipos = {1: "otro", 2: "A", 3: "A"}  # el portero, en 'otro' (hallazgo a)
    salida = aplicar_regla_portero_ultimo_hombre(
        equipos,
        [portero, defensa, delantero],
        modelo,
        {"A": -1, "B": +1},
        ReglaPorteroUltimoHombre(activo=True),
    )
    assert salida[1] == "portero_A"
    assert salida[2] == "A" and salida[3] == "A"


def test_portero_ultimo_hombre_SE_ABSTIENE_si_nadie_pisa_el_area():
    """El caso negativo: sin portero, la regla no puede coronar a un central."""
    from src.team_classification.porteros import (
        ReglaPorteroUltimoHombre,
        aplicar_regla_portero_ultimo_hombre,
    )

    modelo = _campo_f7()
    central = _ident_en(20.0, 20.0)
    delantero = _ident_en(45.0, 20.0)
    equipos = {1: "A", 2: "A"}
    salida = aplicar_regla_portero_ultimo_hombre(
        equipos,
        [central, delantero],
        modelo,
        {"A": -1},
        ReglaPorteroUltimoHombre(activo=True),
    )
    assert salida == equipos  # nadie coronado


def test_portero_ultimo_hombre_SE_ABSTIENE_con_un_fragmento_del_area():
    """Vive en el área el 100 % pero solo aparece en 4 de 40 frames."""
    from src.team_classification.porteros import (
        ReglaPorteroUltimoHombre,
        aplicar_regla_portero_ultimo_hombre,
    )

    modelo = _campo_f7()
    fragmento = _ident_en(4.0, 20.0, n=4)
    central = _ident_en(20.0, 20.0, n=40)
    salida = aplicar_regla_portero_ultimo_hombre(
        {1: "otro", 2: "A"},
        [fragmento, central],
        modelo,
        {"A": -1},
        ReglaPorteroUltimoHombre(activo=True),
    )
    assert salida[1] == "otro"


def test_portero_ultimo_hombre_ignora_el_fondo_lejano():
    """Sin este filtro, el público proyectado a x=176 ganaba la votación.

    La regla filtra por la etiqueta 'staff', pero en el pipeline el staff
    se etiqueta DESPUÉS, así que hace falta un filtro geométrico propio.
    """
    from src.team_classification.porteros import (
        ReglaPorteroUltimoHombre,
        aplicar_regla_portero_ultimo_hombre,
    )

    modelo = _campo_f7()
    portero = _ident_en(58.0, 20.0)  # área de x=62
    publico = _ident_en(176.0, 15.0)  # detrás del fondo, fuera del campo
    salida = aplicar_regla_portero_ultimo_hombre(
        {1: "otro", 2: "otro"},
        [portero, publico],
        modelo,
        {"B": +1},
        ReglaPorteroUltimoHombre(activo=True),
    )
    assert salida[1] == "portero_B"
    assert salida[2] == "otro"


def test_wilson_penaliza_la_muestra_pequena():
    from src.team_classification.porteros import _wilson

    assert _wilson(1, 1) < _wilson(55, 60)  # el impostor de una observación
    assert _wilson(0, 0) == 0.0


# ── La guarda del tercer grupo ────────────────────────────────────────
#
# El árbitro sale por ELIMINACIÓN, no porque ninguna señal lo distinga.
# Eso depende de `arbitro.margen_equipo`, cuya ventana en el benjamín es
# 0,62-0,75 con acantilado en 0,78: estrecha. En otro campo puede caerse,
# y el síntoma sería silencioso. Estos tests fijan que el aviso salte.


def _ident_simple(x, y, n=30):
    from src.tracking.field_tracker import Tracklet

    tr = Tracklet(1, 0.0, np.array([x, y]), 0, 0)
    for i in range(1, n):
        tr.anadir(i * 0.12, np.array([x + 0.02 * (i % 3), y]), i, i)
    return [tr]


def _modelo_f7():
    from src.campo_modelo import cargar_modelo

    return cargar_modelo("f7").con_dimensiones(62.0, 40.0)


def test_tercer_grupo_con_uno_es_lo_esperado(caplog):
    from src.team_classification.pipeline_equipos import avisar_tercer_grupo

    idents = [_ident_simple(31.0, 20.0), _ident_simple(20.0, 20.0)]
    with caplog.at_level(logging.WARNING):
        n = avisar_tercer_grupo({1: "otro", 2: "A"}, idents, _modelo_f7())
    assert n == 1
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_tercer_grupo_VACIO_avisa(caplog):
    """El árbitro se ha colado en un equipo: hay que enterarse por el log."""
    from src.team_classification.pipeline_equipos import avisar_tercer_grupo

    idents = [_ident_simple(31.0, 20.0), _ident_simple(20.0, 20.0)]
    with caplog.at_level(logging.WARNING):
        n = avisar_tercer_grupo({1: "A", 2: "B"}, idents, _modelo_f7())
    assert n == 0
    assert any("TERCER GRUPO VACÍO" in r.message for r in caplog.records)


def test_tercer_grupo_con_DOS_avisa(caplog):
    """El catálogo está robando jugadores."""
    from src.team_classification.pipeline_equipos import avisar_tercer_grupo

    idents = [_ident_simple(31.0, 20.0), _ident_simple(25.0, 30.0)]
    with caplog.at_level(logging.WARNING):
        n = avisar_tercer_grupo({1: "otro", 2: "otro"}, idents, _modelo_f7())
    assert n == 2
    assert any("TERCER GRUPO CON 2" in r.message for r in caplog.records)


def test_tercer_grupo_no_cuenta_lo_de_fuera_del_campo(caplog):
    """El público proyectado a 176 m no es un candidato a árbitro."""
    from src.team_classification.pipeline_equipos import avisar_tercer_grupo

    idents = [_ident_simple(31.0, 20.0), _ident_simple(176.0, 15.0)]
    with caplog.at_level(logging.WARNING):
        n = avisar_tercer_grupo({1: "otro", 2: "otro"}, idents, _modelo_f7())
    assert n == 1


# ── Un solo árbitro dentro del campo ──────────────────────────────────
#
# Misma forma que la exclusividad un-portero-por-área: conocimiento del
# reglamento, no un umbral. Y la evidencia son DOS señales porque cada una
# es estrecha en una pata: por observaciones el margen es 2,4× en el
# benjamín y 1,24× en Villaviciosa; por color 1,27× y 2,4×. Multiplicadas,
# 3,0× en las dos.


def _protos():
    a = np.zeros(256)
    a[10] = 1.0
    b = np.zeros(256)
    b[200] = 1.0
    return [a, b]


def _ident_con_color(x, y, n, color_idx, colores, base_frame):
    from src.tracking.field_tracker import Tracklet

    tr = Tracklet(1, 0.0, np.array([x, y]), 0, base_frame)
    colores[(base_frame, 0)] = np.eye(256)[color_idx]
    for i in range(1, n):
        tr.anadir(i * 0.12, np.array([x, y]), i, base_frame + i)
        colores[(base_frame + i, i)] = np.eye(256)[color_idx]
    return [tr]


def test_un_solo_arbitro_corona_al_de_mas_evidencia():
    from src.team_classification.arbitro import un_solo_arbitro

    colores = {}
    modelo = _modelo_f7()
    # el árbitro: muchas observaciones Y color lejos de los dos equipos
    arbitro = _ident_con_color(31.0, 20.0, 60, 120, colores, 0)
    # un jugador robado: menos observaciones y color cerca del equipo A
    robado = _ident_con_color(25.0, 20.0, 30, 11, colores, 1000)
    salida = un_solo_arbitro(
        {1: "otro", 2: "otro"}, [arbitro, robado], colores, _protos(), modelo
    )
    assert salida[1] == "otro"  # el árbitro se queda
    assert salida[2] == "otro"  # el otro NO se reasigna por color (medido)


def test_un_solo_arbitro_no_toca_nada_si_solo_hay_uno():
    from src.team_classification.arbitro import un_solo_arbitro

    colores = {}
    arbitro = _ident_con_color(31.0, 20.0, 60, 120, colores, 0)
    equipos = {1: "otro"}
    assert (
        un_solo_arbitro(equipos, [arbitro], colores, _protos(), _modelo_f7()) == equipos
    )


def test_un_solo_arbitro_ignora_lo_de_fuera_del_campo():
    """Quien está fuera es staff, no árbitro, y no debe competir."""
    from src.team_classification.arbitro import un_solo_arbitro

    colores = {}
    arbitro = _ident_con_color(31.0, 20.0, 40, 120, colores, 0)
    publico = _ident_con_color(176.0, 15.0, 200, 120, colores, 1000)
    salida = un_solo_arbitro(
        {1: "otro", 2: "otro"}, [arbitro, publico], colores, _protos(), _modelo_f7()
    )
    # el público tiene MÁS observaciones pero está fuera: ni se le mira
    assert salida[1] == "otro" and salida[2] == "otro"


def test_staff_no_exige_minimo_de_observaciones_muy_lejos():
    """Un señor en el campo de al lado con 3 detecciones es basura igual.

    El mínimo existe porque con 2-3 posiciones la mediana no significa
    nada. Eso vale cerca de la línea, no a 17 m fuera. Medido: ninguna
    persona real tiene su mediana fuera del campo.
    """
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff

    lejano = _identidad_recta(80.0, 56.0, 0.0, 0.0, n=3)
    regla = ReglaStaff(largo=62.0, ancho=40.0, tolerancia_m=2.0, min_obs_lejos_m=6.0)
    assert aplicar_regla_staff({1: "A"}, [lejano], regla)[1] == "staff"


def test_staff_sigue_exigiendo_el_minimo_cerca_de_la_linea():
    from src.team_classification.staff import ReglaStaff, aplicar_regla_staff

    # 3 m fuera: dentro del margen donde la proyección puede engañar
    cerca = _identidad_recta(31.0, -3.0, 0.0, 0.0, n=3)
    regla = ReglaStaff(largo=62.0, ancho=40.0, tolerancia_m=2.0, min_obs_lejos_m=6.0)
    assert aplicar_regla_staff({1: "A"}, [cerca], regla)[1] == "A"


# ── EL PORTERO ES UN CONJUNTO, no una identidad (26-ago-2026) ─────────
#
# Sobre tramos largos el seguimiento parte al portero en trozos y la
# regla, que coronaba a uno solo y medía SU presencia, se abstenía
# teniéndolo delante: 87 % de presencia a 60 s, 49 % a 5 min contra un
# mínimo de 0,50 (docs/portero.md). Ahora corona al conjunto y mide la
# presencia de la UNIÓN.
#
# Con una restricción física que hay que blindar: dos fragmentos
# presentes en el MISMO frame no son el portero antes y después, son el
# portero detectado dos veces, y coronar los dos lo mete dos veces en el
# centroide de su equipo (medido en Villaviciosa: +0,86 m de centroide).


def _ident_en_frames(x, y, frames, dt=0.12):
    """Identidad quieta en (x, y) presente exactamente en esos frames."""
    from src.tracking.field_tracker import Tracklet

    frames = list(frames)
    tr = Tracklet(1, frames[0] * dt, np.array([x, y]), 0, frames[0])
    for f in frames[1:]:
        tr.anadir(f * dt, np.array([x, y]), 0, f)
    return [tr]


def _coronar(identidades, equipos, lados, **kwargs):
    from src.team_classification.porteros import (
        ReglaPorteroUltimoHombre,
        aplicar_regla_portero_ultimo_hombre,
    )

    return aplicar_regla_portero_ultimo_hombre(
        equipos,
        identidades,
        _campo_f7(),
        lados,
        ReglaPorteroUltimoHombre(activo=True, **kwargs),
    )


def test_portero_partido_en_dos_trozos_corona_LOS_DOS():
    """Dos mitades consecutivas del mismo portero: las dos son portero."""
    primera = _ident_en_frames(4.0, 20.0, range(0, 20))
    segunda = _ident_en_frames(4.5, 20.0, range(20, 40))
    campo = _ident_en_frames(30.0, 20.0, range(0, 40))
    salida = _coronar(
        [primera, segunda, campo], {1: "otro", 2: "otro", 3: "A"}, {"A": -1}
    )
    assert salida[1] == "portero_A"
    assert salida[2] == "portero_A"
    assert salida[3] == "A"


def test_trozo_simultaneo_es_un_DUPLICADO_y_no_se_corona():
    """Mismo sitio y MISMOS frames: es el portero detectado dos veces."""
    portero = _ident_en_frames(4.0, 20.0, range(0, 40))
    duplicado = _ident_en_frames(4.2, 20.0, range(0, 40))
    campo = _ident_en_frames(30.0, 20.0, range(0, 40))
    salida = _coronar(
        [portero, duplicado, campo], {1: "otro", 2: "otro", 3: "A"}, {"A": -1}
    )
    coronados = [k for k, v in salida.items() if str(v).startswith("portero_")]
    assert len(coronados) == 1


def test_trozos_sueltos_que_no_cubren_el_tramo_SE_ABSTIENEN():
    """La unión sigue siendo una puerta: 8 frames de 40 no son un portero."""
    trozo_a = _ident_en_frames(4.0, 20.0, range(0, 4))
    trozo_b = _ident_en_frames(4.0, 20.0, range(30, 34))
    campo = _ident_en_frames(30.0, 20.0, range(0, 40))
    salida = _coronar(
        [trozo_a, trozo_b, campo], {1: "otro", 2: "otro", 3: "A"}, {"A": -1}
    )
    assert not any(str(v).startswith("portero_") for v in salida.values())


def test_la_regla_NO_depende_de_lo_largo_que_sea_el_tramo():
    """El mismo portero partido en 2 o en 8 trozos se corona igual.

    Es la propiedad que se rompió a los 5 minutos y la razón de este
    cambio: medir la presencia por fragmento hace que la decisión dependa
    de cuántas veces se haya partido el seguimiento.
    """
    for n_trozos in (2, 4, 8):
        paso = 80 // n_trozos
        trozos = [
            _ident_en_frames(4.0, 20.0, range(i * paso, (i + 1) * paso))
            for i in range(n_trozos)
        ]
        campo = [_ident_en_frames(30.0, 20.0, range(0, 80))]
        equipos = {k: "otro" for k in range(1, n_trozos + 1)}
        equipos[n_trozos + 1] = "A"
        salida = _coronar(trozos + campo, equipos, {"A": -1})
        coronados = [k for k, v in salida.items() if str(v).startswith("portero_")]
        assert len(coronados) == n_trozos, f"con {n_trozos} trozos: {coronados}"
