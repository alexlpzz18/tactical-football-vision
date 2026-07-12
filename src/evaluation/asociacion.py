"""Asociación GT↔predicción por frame, por DISTANCIA EN METROS.

Por qué metros y no IoU: los jugadores miden 15-40 px en esta cámara; con
cajas tan pequeñas un desplazamiento de pocos píxeles hunde el IoU a 0,
mientras que la distancia en metros degrada suavemente. Además todo el
pipeline (tracker, métricas colectivas) vive en coordenadas de campo.

El pie de la caja GT se proyecta con la MISMA homografía que sufren las
predicciones, así el error de proyección afecta a ambas por igual y se
cancela parcialmente al medir distancias relativas.
"""

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.evaluation.modelo import PorFrame


def asociar_frame(
    obs_gt: list,
    obs_pred: list,
    umbral_metros: float,
) -> list[tuple[int, int]]:
    """Empareja observaciones GT y predichas de UN frame (húngaro + umbral).

    Returns:
        Lista de pares (indice_gt, indice_pred) con distancia ≤ umbral.
    """
    if not obs_gt or not obs_pred:
        return []
    pos_gt = np.array([o.pos for o in obs_gt])
    pos_pred = np.array([o.pos for o in obs_pred])
    dist = np.linalg.norm(pos_gt[:, None, :] - pos_pred[None, :, :], axis=2)
    filas, cols = linear_sum_assignment(dist)
    return [(r, c) for r, c in zip(filas, cols) if dist[r, c] <= umbral_metros]


def asociar_todos(
    gt: PorFrame,
    pred: PorFrame,
    frames: list[int],
    umbral_metros: float,
) -> dict[int, list[tuple[int, int]]]:
    """Asocia GT↔pred en cada frame de la lista.

    Returns:
        {frame: [(obj_id_gt, obj_id_pred), ...]} — pares de IDs emparejados.
    """
    resultado = {}
    for frame in frames:
        obs_gt = gt.get(frame, [])
        obs_pred = pred.get(frame, [])
        pares = asociar_frame(obs_gt, obs_pred, umbral_metros)
        resultado[frame] = [(obs_gt[r].obj_id, obs_pred[c].obj_id) for r, c in pares]
    return resultado
