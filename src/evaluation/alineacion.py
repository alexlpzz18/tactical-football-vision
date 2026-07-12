"""Alineación temporal entre el ground truth y el caché de detecciones.

El GT tiene 1 de cada 15 frames reales del vídeo y el caché 1 de cada 3:
solo podemos evaluar sobre los frames presentes en AMBOS (los múltiplos
comunes). Este módulo encuentra esos frames y permite verificar
empíricamente que el offset configurado es correcto.
"""

import logging

import numpy as np

from src.evaluation.modelo import PorFrame

logger = logging.getLogger(__name__)


def frames_comunes(gt_por_frame: PorFrame, frames_cache: list[int]) -> list[int]:
    """Frames globales presentes tanto en el GT como en el caché, ordenados.

    Raises:
        ValueError: si no hay ningún frame común (offset mal configurado
            o datos de tramos distintos).
    """
    comunes = sorted(set(gt_por_frame) & set(frames_cache))
    if not comunes:
        raise ValueError(
            "No hay frames comunes entre GT y caché. Revisa 'alineacion' en "
            "configs/evaluation.yaml (frame_offset/paso_gt) y que ambos datos "
            "sean del mismo tramo del vídeo."
        )
    logger.info(
        "Frames comunes GT∩caché: %d (de %d GT y %d caché)",
        len(comunes),
        len(gt_por_frame),
        len(frames_cache),
    )
    return comunes


def distancia_media_gt_cache(
    gt_por_frame: PorFrame,
    dets_por_frame: dict[int, np.ndarray],
    comunes: list[int],
) -> float:
    """Chequeo de sanidad de la alineación: distancia media (en metros) de
    cada objeto GT a la detección del caché más cercana, sobre los frames
    comunes.

    Si el offset temporal es correcto, esta distancia debe ser pequeña
    (< ~1 m: error de detección + proyección). Si el GT y el caché
    estuvieran desalineados un frame o más, los jugadores en movimiento la
    dispararían.

    Args:
        gt_por_frame: GT en formato común.
        dets_por_frame: {frame_global: array Nx2 de posiciones en metros}.
        comunes: frames sobre los que comparar.
    """
    distancias = []
    for frame in comunes:
        dets = dets_por_frame.get(frame)
        if dets is None or len(dets) == 0:
            continue
        for obs in gt_por_frame[frame]:
            distancias.append(np.min(np.linalg.norm(dets - obs.pos, axis=1)))
    media = float(np.mean(distancias))
    logger.info(
        "Sanidad de alineación: distancia media GT→detección más cercana = %.3f m",
        media,
    )
    return media
