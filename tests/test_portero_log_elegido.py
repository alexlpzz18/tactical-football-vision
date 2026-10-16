"""El log del portero describe un fragmento ELEGIDO, no la candidata con más frames.

16-oct-2026 (docs/plan_ablacion_1a1.md): el mensaje imprimía `filas[0]`, la candidata del lado
con MÁS frames, y en la ablación 1/1 era un jugador de campo («9/8933, área 0 %») que no estaba
en el conjunto. Parecía que el portero de A estaba roto y no lo estaba.
"""

import logging

import numpy as np

from src.campo_modelo import cargar_modelo
from src.team_classification.porteros import (
    ReglaPorteroUltimoHombre,
    aplicar_regla_portero_ultimo_hombre,
)
from src.tracking.field_tracker import Tracklet


def _quieta(x, y, frames, dt=0.12):
    frames = list(frames)
    tr = Tracklet(1, frames[0] * dt, np.array([x, y]), 0, frames[0])
    for f in frames[1:]:
        tr.anadir(f * dt, np.array([x, y]), 0, f)
    return [tr]


def test_el_log_describe_al_portero_elegido(caplog):
    portero = _quieta(4.0, 20.0, range(0, 300))  # el más profundo, dentro del área
    campo = _quieta(
        30.0, 20.0, range(0, 500)
    )  # MÁS frames que el portero, fuera del área
    modelo = cargar_modelo("f7").con_dimensiones(62.0, 40.0)
    with caplog.at_level(logging.INFO, logger="src.team_classification.porteros"):
        salida = aplicar_regla_portero_ultimo_hombre(
            {1: "otro", 2: "A"},
            [portero, campo],
            modelo,
            {"A": -1},
            ReglaPorteroUltimoHombre(activo=True),
        )
    assert salida[1] == "portero_A" and salida[2] == "A"
    msg = next(
        r.getMessage() for r in caplog.records if r.getMessage().startswith("Portero")
    )
    assert "id 1: último hombre 300/300, área 100 %" in msg
    assert "/500" not in msg  # la candidata con más frames no es del conjunto
