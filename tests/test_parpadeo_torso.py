"""Máscara de torso tapado e intercambio de colas (docs/plan_parpadeo_torso.md)."""

from types import SimpleNamespace

import numpy as np

from src.team_classification.intercambio_colas import (
    ParametrosIntercambio,
    intercambiar_colas,
)
from src.team_classification.oclusion import dilatar_por_identidad, torsos_tapados
from src.tracking.field_tracker import Tracklet


def test_solo_cuenta_el_solape_sobre_el_pecho():
    # caja 0: 0-20 × 0-100; su pecho es x 3-17, y 12-45
    piernas = {
        "frame_idx": 1,
        "t": 0.0,
        "dets": [(0, 0, 0, 0, 20, 100, 0.9), (0, 0, 0, 60, 20, 160, 0.9)],
    }  # solo pisa las piernas
    pecho = {
        "frame_idx": 2,
        "t": 0.1,
        "dets": [(0, 0, 0, 0, 20, 100, 0.9), (0, 0, 5, 10, 25, 110, 0.9)],
    }  # tapa el pecho
    tapados = torsos_tapados([piernas, pecho], umbral=0.15)
    assert (1, 0) not in tapados
    assert (2, 0) in tapados and (2, 1) in tapados


def test_la_dilatacion_marca_los_vecinos_de_la_misma_identidad():
    tr = SimpleNamespace(ts=[0, 1, 2, 3, 4, 5, 6], det_idxs=[(f, 0) for f in range(7)])
    otra = SimpleNamespace(ts=[3], det_idxs=[(3, 1)])
    salida = dilatar_por_identidad([[tr], [otra]], {(3, 0)}, 2)
    assert salida == {(1, 0), (2, 0), (3, 0), (4, 0), (5, 0)}


class _Clf:
    """Margen = primera componente de la feature (positivo = A)."""

    def margen_ab(self, f):
        return float(f[0])


def _ident(tid, xs, frames, t0=0.0, dt=0.1):
    tr = Tracklet(tid, t0, np.array([xs[0], 0.0]), 0, frames[0])
    for k in range(1, len(xs)):
        tr.anadir(t0 + k * dt, np.array([xs[k], 0.0]), 0 if tid == 1 else 1, frames[k])
    return [tr]


def test_intercambia_las_colas_si_los_rivales_salen_con_los_colores_invertidos():
    frames = list(range(30))
    cache = []
    colores = {}
    for f in frames:
        solapan = 12 <= f <= 16
        caja_a = (100, 100, 120, 150)
        caja_b = (105, 100, 125, 150) if solapan else (300, 100, 320, 150)
        cache.append(
            {
                "frame_idx": f,
                "t": f * 0.1,
                "dets": [(0, 0, *caja_a, 0.9), (0, 0, *caja_b, 0.9)],
            }
        )
        # antes del solape la 1 es A y la 2 es B; después, al revés (se han cruzado)
        colores[(f, 0)] = np.array([0.5 if f < 12 else -0.5])
        colores[(f, 1)] = np.array([-0.5 if f < 12 else 0.5])
    i1 = _ident(1, [0.0] * 30, frames)
    i2 = _ident(2, [5.0] * 30, frames)
    i2[0].det_idxs = [(f, 1) for f in frames]
    i1[0].det_idxs = [(f, 0) for f in frames]
    salida, n = intercambiar_colas(
        [i1, i2], cache, colores, _Clf(), ParametrosIntercambio(activo=True)
    )
    assert n == 1
    # tras el solape, la identidad 1 lleva ahora las detecciones 1 (las del jugador A)
    cola_1 = [par for t, par in zip(salida[0][0].ts, salida[0][0].det_idxs) if t > 1.6]
    assert all(j == 1 for _f, j in cola_1)
    apagado, n0 = intercambiar_colas(
        [i1, i2], cache, colores, _Clf(), ParametrosIntercambio()
    )
    assert n0 == 0 and apagado[0] is i1
