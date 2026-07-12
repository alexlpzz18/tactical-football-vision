"""Asociación GT↔predicción por frame, por DISTANCIA EN METROS.

Por qué metros y no IoU: los jugadores miden 15-40 px en esta cámara; con
cajas tan pequeñas un desplazamiento de pocos píxeles hunde el IoU a 0,
mientras que la distancia en metros degrada suavemente. Además todo el
pipeline (tracker, métricas colectivas) vive en coordenadas de campo.

El pie de la caja GT se proyecta con la MISMA homografía que sufren las
predicciones, así el error de proyección afecta a ambas por igual y se
cancela parcialmente al medir distancias relativas.

UMBRAL DEPENDIENTE DE PROFUNDIDAD
---------------------------------
El error de localización crece con la profundidad del campo: en el lado
lejano un jugador ocupa pocos píxeles y 1 píxel de error en el pie se
convierte en metros tras la homografía. Medido empíricamente en el tramo
de validación (distancia GT→detección más cercana): mediana 0.25 m en
my<17 frente a 2.54 m en my>51. Un umbral fijo penaliza como "fallo" a
jugadores bien detectados del fondo. Por eso el umbral oficial es una
recta de la profundidad con recorte:

    umbral(my) = clip(base + por_metro * my, minimo, maximo)

El umbral se evalúa en la posición del objeto GT (el ancla de la métrica).
El umbral fijo se mantiene disponible para comparar.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.evaluation.modelo import PorFrame


@dataclass
class UmbralProfundidad:
    """Umbral de asociación que crece linealmente con la profundidad (my).

    Calibrado sobre la curva empírica de error por profundidad del tramo de
    validación (ver docstring del módulo); parámetros en configs/evaluation.yaml.
    """

    base: float  # metros de umbral en my=0
    por_metro: float  # metros extra de umbral por metro de profundidad
    minimo: float  # recorte inferior (ruido de anotación/detección)
    maximo: float  # recorte superior (no tragarse al vecino)

    def para(self, my: float) -> float:
        """Umbral en metros para un objeto a profundidad `my`."""
        return float(np.clip(self.base + self.por_metro * my, self.minimo, self.maximo))

    @classmethod
    def desde_dict(cls, d: dict) -> "UmbralProfundidad":
        return cls(**d)


# Un umbral es un float (fijo) o un UmbralProfundidad (variable con my)
Umbral = float | UmbralProfundidad


def _umbral_por_obs(observaciones: list, umbral: Umbral) -> np.ndarray:
    """Vector de umbrales, uno por observación GT."""
    if isinstance(umbral, UmbralProfundidad):
        return np.array([umbral.para(o.pos[1]) for o in observaciones])
    return np.full(len(observaciones), float(umbral))


def asociar_frame(
    obs_gt: list,
    obs_pred: list,
    umbral: Umbral,
) -> list[tuple[int, int]]:
    """Empareja observaciones GT y predichas de UN frame (húngaro + umbral).

    El umbral puede ser fijo (float) o dependiente de la profundidad del
    objeto GT (UmbralProfundidad).

    Returns:
        Lista de pares (indice_gt, indice_pred) con distancia ≤ umbral.
    """
    if not obs_gt or not obs_pred:
        return []
    pos_gt = np.array([o.pos for o in obs_gt])
    pos_pred = np.array([o.pos for o in obs_pred])
    dist = np.linalg.norm(pos_gt[:, None, :] - pos_pred[None, :, :], axis=2)
    filas, cols = linear_sum_assignment(dist)
    umbrales = _umbral_por_obs(obs_gt, umbral)
    return [(r, c) for r, c in zip(filas, cols) if dist[r, c] <= umbrales[r]]


def asociar_todos(
    gt: PorFrame,
    pred: PorFrame,
    frames: list[int],
    umbral_metros: Umbral,
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
