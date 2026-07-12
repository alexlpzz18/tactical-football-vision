"""Adaptador: salida del pipeline (identidades cosidas) → formato de evaluación.

Convierte las identidades (listas de tracklets cosidos) en observaciones por
frame, el mismo formato al que se convierte el ground truth. A partir de ahí
el banco no sabe (ni le importa) qué tracker generó las predicciones.
"""

import logging

from src.evaluation.modelo import Observacion, PorFrame
from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


def identidades_a_por_frame(
    identidades: list[list[Tracklet]],
    equipos: dict[int, str] | None = None,
) -> PorFrame:
    """Convierte identidades cosidas al formato común de evaluación.

    Cada identidad recibe un id secuencial (1..N). El frame de cada
    observación es el frame_idx GLOBAL guardado en el tracklet.

    Args:
        identidades: salida de TrackletStitcher.coser().
        equipos: opcional, {id_identidad: 'A'/'B'/'otro'} cuando el
            clasificador de equipos esté conectado. None = sin clasificar.

    Returns:
        {frame_global: [Observacion, ...]}
    """
    por_frame: PorFrame = {}
    for id_identidad, tracklets in enumerate(identidades, start=1):
        team = equipos.get(id_identidad) if equipos else None
        for tracklet in tracklets:
            for pos, (frame_global, _det_idx) in zip(tracklet.pos, tracklet.det_idxs):
                por_frame.setdefault(frame_global, []).append(
                    Observacion(obj_id=id_identidad, pos=pos, team=team)
                )
    n_obs = sum(len(v) for v in por_frame.values())
    logger.info(
        "Adaptador: %d identidades → %d observaciones en %d frames",
        len(identidades),
        n_obs,
        len(por_frame),
    )
    return por_frame
