"""El árbitro como seguimiento de un único objeto (flag `arbitro.viterbi`). 23-oct c."""

from pathlib import Path

import numpy as np

from src.team_classification.arbitro_viterbi import (
    ParametrosArbitroViterbi,
    estimar_modelo,
    pista_del_arbitro,
)

R = Path(__file__).resolve().parent.parent
BINS = [0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 1.0001]


def _escena(hueco=range(20, 30)):
    """60 frames a 0,1 s: el árbitro (chaleco 0,06) cruza; tres jugadores quietos (0,0).

    El árbitro no se detecta en los frames de `hueco` (1 s). El orden de las detecciones se
    baraja en cada frame, así que la pista tiene que encontrarlo por emisión y movimiento.
    """
    rng = np.random.default_rng(1)
    cache, chaleco, verdad = [], {}, {}
    for f in range(60):
        dets = [(10.0 + 0.15 * f, 20.0, 0, 0, 1, 1, 0.9)] if f not in hueco else []
        dets += [
            (30.0, 10.0, 0, 0, 1, 1, 0.9),
            (40.0, 30.0, 0, 0, 1, 1, 0.9),
            (50.0, 20.0, 0, 0, 1, 1, 0.9),
        ]
        orden = rng.permutation(len(dets))
        dets = [dets[k] for k in orden]
        for j, d in enumerate(dets):
            es_arb = d[1] == 20.0 and d[0] < 30
            chaleco[(f, j)] = 0.06 if es_arb else 0.0
            if es_arb:
                verdad[f] = j
        cache.append({"frame_idx": f, "t": f * 0.1, "dets": dets})
    modelo = estimar_modelo(np.full(50, 0.06), np.zeros(500), BINS)
    return (
        cache,
        chaleco,
        verdad,
        (np.asarray(modelo["bins"]), np.asarray(modelo["log_lr"])),
    )


def test_apagado_por_defecto():
    assert ParametrosArbitroViterbi().activo is False


def test_sigue_al_arbitro_y_salta_el_hueco():
    cache, chaleco, verdad, modelo = _escena()
    pista = pista_del_arbitro(
        cache, chaleco, modelo, ParametrosArbitroViterbi(activo=True), (62.0, 40.0)
    )
    aciertos = sum(pista.get(f) == j for f, j in verdad.items())
    assert aciertos >= 0.95 * len(verdad)
    assert not any(
        f in pista for f in range(20, 30)
    )  # en el hueco no se inventa a nadie


def test_con_la_emision_permutada_pierde_al_arbitro():
    cache, chaleco, verdad, modelo = _escena()
    params = ParametrosArbitroViterbi(activo=True, control_permutar_semilla=0)
    pista = pista_del_arbitro(cache, chaleco, modelo, params, (62.0, 40.0))
    aciertos = sum(pista.get(f) == j for f, j in verdad.items())
    assert aciertos < 0.7 * len(verdad)
