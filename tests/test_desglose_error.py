"""Desglose del error: escalera de oráculos con reparto de Shapley.

21-sep-2026 (docs/desglose_del_error.md). Lo que estos tests guardan es la
PROPIEDAD que hace fiable el desglose: con las cuatro palancas aplicadas el
sistema ES el GT (error 0), y el reparto de Shapley suma exactamente el error.
Si alguna palanca no hiciera lo que dice, la escalera no cerraría.
"""

import numpy as np
import pytest

from src.evaluation.desglose_error import (
    FACTORES,
    casar_frame,
    conjunto_del_equipo,
    conjunto_gt,
    cuenta_de_recuento,
    equipo_de_etiqueta,
    error_de_conjunto,
    escalera_por_frame_equipo,
    shapley,
    subconjuntos,
)


def _frame(gt, filas, radio=2.0, **kwargs):
    """gt: [(equipo, x, y)]; filas: [(x, y, etiqueta)]."""
    x = np.array([f[0] for f in filas], dtype=float)
    y = np.array([f[1] for f in filas], dtype=float)
    etq = np.array([f[2] for f in filas], dtype=object)
    return casar_frame(0, gt, x, y, etq, radio, **kwargs)


def _caso_con_todos_los_fallos():
    """Equipo A de 5 personas y equipo B de 3; el sistema falla de cuatro maneras.

    · A1 (10,10): bien.
    · A2 (20,10): la fila cae a 1 m (LOC) con la etiqueta buena.
    · A3 (30,10): la fila lleva la etiqueta de B (LAB).
    · A4 (40,10): la fila está etiquetada `otro` (LAB, mandada fuera).
    · A5 (50,10): NO hay fila (MIS).
    · B1-B3 en x=10,20,30, y=30: bien.
    · Una fila A a 15 m de todo el mundo (EXT: árbitro/fantasma).
    """
    gt = [
        ("A", 10, 10),
        ("A", 20, 10),
        ("A", 30, 10),
        ("A", 40, 10),
        ("A", 50, 10),
        ("B", 10, 30),
        ("B", 20, 30),
        ("B", 30, 30),
    ]
    filas = [
        (10, 10, "A"),
        (20, 11, "A"),
        (30, 10, "B"),
        (40, 10, "otro"),
        (10, 30, "B"),
        (20, 30, "B"),
        (30, 30, "B"),
        (25, 25, "A"),  # a más de 2 m de cualquier persona
    ]
    return _frame(gt, filas)


def test_con_las_cuatro_palancas_el_sistema_ES_el_gt():
    """El cierre de la escalera: sin esto, ningún reparto significa nada."""
    fc = _caso_con_todos_los_fallos()
    for eq in ("A", "B"):
        P = conjunto_del_equipo(fc, eq, frozenset(FACTORES))
        V = conjunto_gt(fc, eq)
        assert sorted(map(tuple, P)) == sorted(map(tuple, V))
        assert error_de_conjunto(P, V)["centroide"] == pytest.approx(0.0)


def test_cada_palanca_hace_solo_lo_suyo():
    fc = _caso_con_todos_los_fallos()
    base = conjunto_del_equipo(fc, "A")
    # sistema: A1, A2 (20,11), el fantasma (25,25) y nada más (A3 va a B, A4 a otro)
    assert sorted(map(tuple, base)) == [(10, 10), (20, 11), (25, 25)]
    loc = conjunto_del_equipo(fc, "A", frozenset({"LOC"}))
    assert (20, 10) in map(tuple, loc) and (20, 11) not in map(tuple, loc)
    lab = conjunto_del_equipo(fc, "A", frozenset({"LAB"}))
    assert len(lab) == 5  # A3 y A4 entran en A (el fantasma sigue)
    ext = conjunto_del_equipo(fc, "A", frozenset({"EXT"}))
    assert (25, 25) not in map(tuple, ext) and len(ext) == 2
    mis = conjunto_del_equipo(fc, "A", frozenset({"MIS"}))
    assert (50, 10) in map(tuple, mis) and len(mis) == 4


def test_ext_solo_quita_filas_de_equipo_no_las_de_otro_o_staff():
    """Una fila `otro` sin persona es un árbitro bien clasificado: no es un sobrante."""
    fc = _frame([("A", 10, 10)], [(10, 10, "A"), (50, 30, "otro"), (51, 30, "staff")])
    con = conjunto_del_equipo(fc, "A", frozenset({"EXT"}))
    assert len(con) == 1


def test_el_casado_es_1_a_1():
    """Dos personas del GT NO pueden reclamar la misma fila (el 79 % del error de 4,0 %)."""
    fc = _frame([("A", 10, 10), ("B", 10.5, 10)], [(10.2, 10, "A")])
    cubiertas = [p for p in fc.personas if p.fila is not None]
    assert len(cubiertas) == 1, "una fila sirvió a dos personas"
    assert fc.persona_de_fila == {0: fc.personas.index(cubiertas[0])}


def test_el_radio_manda():
    gt = [("A", 10, 10)]
    filas = [(12.5, 10, "A")]
    assert _frame(gt, filas, radio=2.0).personas[0].fila is None
    assert _frame(gt, filas, radio=3.0).personas[0].fila == 0


def test_la_cuenta_del_recuento_cuadra_y_cada_partida_es_la_suya():
    fc = _caso_con_todos_los_fallos()
    c = cuenta_de_recuento(fc, "A")
    assert c["n_gt"] == 5 and c["n_sis"] == 3
    assert c["faltan"] == 1  # A5
    assert c["a_otro"] == 1  # A4
    assert c["equivocado"] == 1  # A3 va a B
    assert c["sobran"] == 1  # el fantasma
    assert c["entran"] == 0
    assert c["encuadre"] == 2  # 7 − 5
    cb = cuenta_de_recuento(fc, "B")
    assert cb["entran"] == 1 and cb["n_sis"] == 4  # la fila de A3 cuenta en B


def test_faltar_uno_y_sobrar_uno_se_compensan_en_el_recuento_no_en_el_centroide():
    """La razón de repartir con Shapley: EXT y MIS van acoplados."""
    gt = [("A", 10, 10), ("A", 20, 10), ("A", 30, 10), ("A", 40, 10)]
    filas = [
        (10, 10, "A"),
        (20, 10, "A"),
        (30, 10, "A"),
        (25, 30, "A"),
    ]  # falta A4, sobra uno
    fc = _frame(gt, filas)
    c = cuenta_de_recuento(fc, "A")
    assert c["n_sis"] == c["n_gt"]  # el recuento sale perfecto…
    e = error_de_conjunto(conjunto_del_equipo(fc, "A"), conjunto_gt(fc, "A"))
    assert e["centroide"] > 3.0  # …y el centroide, muy mal


def test_shapley_suma_exactamente_el_error_del_sistema():
    rng = np.random.default_rng(0)
    valor = {S: float(rng.uniform(0, 5)) for S in subconjuntos()}
    valor[frozenset(FACTORES)] = 0.0
    sh = shapley(valor)
    assert sum(sh.values()) == pytest.approx(valor[frozenset()])


def test_shapley_de_una_palanca_sin_efecto_es_cero_y_la_aditiva_recibe_lo_suyo():
    aporte = {"LOC": 0.5, "LAB": 0.0, "EXT": 1.0, "MIS": 2.0, "DES": 0.25}
    valor = {S: sum(aporte[f] for f in FACTORES if f not in S) for S in subconjuntos()}
    sh = shapley(valor)
    for f, a in aporte.items():
        assert sh[f] == pytest.approx(a)


def test_la_escalera_cierra_sobre_frames_reales_y_descarta_los_de_menos_de_3():
    fc = _caso_con_todos_los_fallos()
    pocos = _frame([("A", 10, 10), ("A", 20, 10)], [(10, 10, "A"), (20, 10, "A")])
    filas, descartados = escalera_por_frame_equipo([fc, pocos])
    # el frame «pocos» tiene 2 personas por equipo: 2 pares descartados, y se cuentan
    assert descartados >= 2
    todos = [f for f in filas if f["arreglos"] == frozenset(FACTORES)]
    assert todos and all(f["centroide"] == pytest.approx(0.0) for f in todos)
    v0 = np.mean([f["centroide"] for f in filas if f["arreglos"] == frozenset()])
    v = {
        S: np.mean([f["centroide"] for f in filas if f["arreglos"] == S])
        for S in subconjuntos()
    }
    assert sum(shapley(v).values()) == pytest.approx(v0)


def test_los_porteros_cuentan_con_su_equipo():
    assert equipo_de_etiqueta("portero_A") == "A"
    assert equipo_de_etiqueta("B") == "B"
    assert equipo_de_etiqueta("staff") == "staff"


def _caso_de_fila_desplazada():
    """Una persona sin fila a 2 m y, a 3 m de ella, una fila A sin persona: es UNA fila
    mal colocada, no un faltante más un sobrante."""
    gt = [("A", 10, 10), ("A", 20, 10), ("A", 30, 10), ("A", 50, 10)]
    filas = [(10, 10, "A"), (20, 10, "A"), (30, 10, "A"), (47, 10, "A")]
    return _frame(gt, filas, radio=2.0)


def test_una_fila_desplazada_es_UNA_pareja_y_no_un_faltante_mas_un_sobrante():
    fc = _caso_de_fila_desplazada()
    assert fc.pareja_de_fila == {3: 3}
    c = cuenta_de_recuento(fc, "A")
    assert c["faltan"] == 1 and c["sobran"] == 1 and c["desplazadas"] == 1
    # EXT y MIS, solos, NO tocan la pareja: es cosa de DES
    base = conjunto_del_equipo(fc, "A")
    for palanca in ("EXT", "MIS"):
        assert len(conjunto_del_equipo(fc, "A", frozenset({palanca}))) == len(base)
    con = conjunto_del_equipo(fc, "A", frozenset({"DES"}))
    assert (50, 10) in map(tuple, con) and (47, 10) not in map(tuple, con)


def test_lejos_de_todo_no_es_una_pareja():
    """A más de 5 m, un faltante y un sobrante son de verdad un faltante y un sobrante."""
    gt = [("A", 10, 10), ("A", 20, 10), ("A", 30, 10), ("A", 50, 10)]
    filas = [(10, 10, "A"), (20, 10, "A"), (30, 10, "A"), (42, 10, "A")]  # a 8 m
    fc = _frame(gt, filas)
    assert fc.pareja_de_fila == {}


def test_una_fila_otro_sin_persona_no_se_empareja_aunque_este_cerca():
    """Solo las filas A/B se emparejan: un árbitro bien clasificado no es un jugador movido."""
    gt = [("A", 10, 10), ("A", 20, 10), ("A", 30, 10), ("A", 50, 10)]
    filas = [(10, 10, "A"), (20, 10, "A"), (30, 10, "A"), (47, 10, "otro")]
    assert _frame(gt, filas).pareja_de_fila == {}


def test_el_radio_de_pareja_manda():
    gt = [("A", 10, 10), ("A", 50, 10)]
    filas = [(10, 10, "A"), (47, 10, "A")]
    assert _frame(gt, filas, radio_pareja=5.0).pareja_de_fila == {1: 1}
    assert _frame(gt, filas, radio_pareja=2.0).pareja_de_fila == {}
