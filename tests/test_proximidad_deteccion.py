"""¿El detector separa a dos personas cerca en la imagen? — 25-sep-2026.

docs/proximidad_deteccion.md. La revisión manual encontró casos de una caja que
funde a dos personas claramente visibles: esto mide la relación distancia-en-
píxeles↔fallo, y guarda las propiedades que la hacen fiable.
"""

import numpy as np
import pytest

from src.evaluation.proximidad_deteccion import (
    PersonaGT,
    encontrado_en_deteccion,
    es_portero,
    tabla_proximidad,
    vecino_mas_cercano_px,
)


def _p(track_id, equipo, px, py, mx, my):
    return PersonaGT(track_id, equipo, (px, py), (mx, my))


def test_vecino_mas_cercano_es_la_distancia_al_mas_proximo_no_al_promedio():
    personas = [
        _p(1, "A", 0, 0, 0, 0),
        _p(2, "A", 10, 0, 0, 0),
        _p(3, "A", 100, 0, 0, 0),
    ]
    v = vecino_mas_cercano_px(personas)
    assert v[0] == pytest.approx(10.0)  # el 2, no el 3
    assert v[1] == pytest.approx(10.0)
    assert v[2] == pytest.approx(90.0)


def test_una_persona_sola_en_el_frame_da_infinito():
    assert vecino_mas_cercano_px([_p(1, "A", 0, 0, 0, 0)])[0] == np.inf


def test_sin_personas_no_revienta():
    assert len(vecino_mas_cercano_px([])) == 0


def test_encontrado_casa_1_a_1_no_deja_dos_personas_con_la_misma_deteccion():
    """El control de siempre: una detección no puede servir a dos personas."""
    personas = [_p(1, "A", 0, 0, 10.0, 20.0), _p(2, "B", 5, 0, 10.5, 20.0)]
    dets = np.array(
        [[10.2, 20.0, 0, 0, 0, 0, 0.9]]
    )  # solo UNA detección, a mitad de camino
    h = encontrado_en_deteccion(personas, dets, radio_m=2.0)
    assert h.sum() == 1, "las dos personas no pueden compartir la misma detección"


def test_fuera_del_radio_no_se_casa():
    personas = [_p(1, "A", 0, 0, 10.0, 20.0)]
    dets = np.array([[13.5, 20.0, 0, 0, 0, 0, 0.9]])  # a 3.5 m, fuera del radio 2 m
    assert not encontrado_en_deteccion(personas, dets, radio_m=2.0)[0]
    assert encontrado_en_deteccion(personas, dets, radio_m=4.0)[0]


def test_sin_detecciones_en_el_frame_nadie_se_encuentra():
    personas = [_p(1, "A", 0, 0, 10.0, 20.0)]
    assert not encontrado_en_deteccion(personas, np.zeros((0, 7)))[0]


def test_es_portero_reconoce_el_prefijo():
    assert es_portero("portero_A")
    assert es_portero("portero_B")
    assert not es_portero("A")
    assert not es_portero("B")


def test_tabla_proximidad_una_fila_por_persona_frame_con_sus_columnas():
    por_frame = {
        100: [_p(1, "A", 0, 0, 10.0, 20.0), _p(2, "portero_A", 500, 500, 4.0, 20.0)],
    }
    cache = {100: np.array([[10.0, 20.0, 0, 0, 0, 0, 0.9]])}
    filas = tabla_proximidad(por_frame, cache, radio_m=2.0)
    assert len(filas) == 2
    por_id = {f["track_id"]: f for f in filas}
    assert por_id[1]["encontrado"] is True
    assert por_id[1]["portero"] is False
    assert por_id[2]["encontrado"] is False  # nadie casó con su detección
    assert por_id[2]["portero"] is True


def test_frame_sin_entrada_en_el_cache_no_revienta():
    por_frame = {100: [_p(1, "A", 0, 0, 10.0, 20.0)]}
    filas = tabla_proximidad(por_frame, cache={}, radio_m=2.0)
    assert filas[0]["encontrado"] is False


def test_la_curva_es_monotona_cerca_falla_mas_que_lejos():
    """El hallazgo central: juntar dos personas y hacer que compitan por UNA detección
    reproduce en miniatura lo que se vio en la hoja de revisión (una caja se come a la
    otra)."""
    rng = np.random.default_rng(0)
    filas = []
    for _ in range(200):
        # Dos personas: una pareja CERCA (10-30 px) y una persona SOLA y lejos.
        cerca = rng.uniform(10, 30)
        a = _p(1, "A", 0, 0, 10.0, 20.0)
        b = _p(
            2, "B", cerca, 0, 10.0 + cerca / 40, 20.0
        )  # separación análoga en metros
        lejos = _p(3, "A", 300, 300, 30.0, 20.0)
        personas = [a, b, lejos]
        # El detector real sería el que decide cuántas cajas salen; aquí se simula que,
        # cuando están MUY cerca (< 15 px), el detector solo saca UNA caja (se funden).
        if cerca < 15:
            dets = np.array([[10.0, 20.0, 0, 0, 0, 0, 0.9]])
        else:
            dets = np.array(
                [
                    [10.0, 20.0, 0, 0, 0, 0, 0.9],
                    [10.0 + cerca / 40, 20.0, 0, 0, 0, 0, 0.9],
                ]
            )
        dets = np.vstack([dets, [30.0, 20.0, 0, 0, 0, 0, 0.9]])
        h = encontrado_en_deteccion(personas, dets, radio_m=1.0)
        filas.append((cerca, h[0] and h[1]))
    cerquisima = [ok for d, ok in filas if d < 15]
    normal = [ok for d, ok in filas if d >= 15]
    assert np.mean(cerquisima) < np.mean(normal)
