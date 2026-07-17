"""Formato común de evaluación: observaciones por frame.

Tanto el ground truth como las predicciones del pipeline se convierten a
este formato antes de asociar y calcular métricas. Así el banco es agnóstico
al tracker: cualquier mejora futura se evalúa sin tocar el resto del banco.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class Observacion:
    """Un objeto (jugador/árbitro) visto en UN frame concreto.

    Attributes:
        obj_id: identidad persistente (track_id del GT o id de identidad
            cosida en las predicciones).
        pos: posición en el campo, en METROS (np.array de 2 floats).
        team: equipo ('A', 'B', 'portero_A', 'portero_B') o None si no aplica
            (árbitro, o predicciones sin clasificar).
        label: 'player' o 'referee'.
    """

    obj_id: int
    pos: np.ndarray
    team: str | None = None
    label: str = "player"


# Estructura de evaluación: {frame_global: [Observacion, ...]}
PorFrame = dict[int, list[Observacion]]
