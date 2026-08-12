"""Detecciones ocluidas: qué recortes NO son de fiar para el color.

Patrón visual del benjamín (11-ago-2026): cuando dos jugadores se cruzan,
la clasificación de equipo falla justo después del cruce. La causa es
mecánica — durante la oclusión, el recorte de la caja de A contiene
píxeles de la camiseta de B, así que el color que se extrae es una MEZCLA
de las dos equipaciones. Ese voto contaminado entra en la media de la
identidad con el mismo peso que un recorte limpio.

Este módulo marca esos recortes para que no voten. No los descarta del
tracking: la detección sigue existiendo, la posición sigue contando para
la cobertura y la identidad no se toca. Solo se les quita el voto de
color, que es lo único que la oclusión estropea.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def _iou(a, b) -> float:
    """IoU de dos cajas (x1, y1, x2, y2)."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def detecciones_ocluidas(
    cache: list[dict], iou_max: float = 0.10
) -> set[tuple[int, int]]:
    """{(frame_idx, det_idx)} de los recortes que se pisan con otro.

    El umbral es BAJO a propósito: no hace falta que dos cajas se solapen
    mucho para que el torso de una entre en la otra, que es justo la parte
    del recorte de la que sale el color.

    Args:
        cache: entradas del caché de detecciones.
        iou_max: IoU con la caja vecina más solapada por encima del cual
            el recorte deja de votar.

    Returns:
        Conjunto de pares (frame_idx, det_idx) contaminados.
    """
    ocluidas: set[tuple[int, int]] = set()
    total = 0
    for entrada in cache:
        cajas = [(d[2], d[3], d[4], d[5]) for d in entrada["dets"]]
        total += len(cajas)
        for i, caja_i in enumerate(cajas):
            for j in range(i + 1, len(cajas)):
                if _iou(caja_i, cajas[j]) > iou_max:
                    ocluidas.add((entrada["frame_idx"], i))
                    ocluidas.add((entrada["frame_idx"], j))
    logger.info(
        "Recortes ocluidos (IoU > %.2f): %d de %d (%.1f %%) — no votan color",
        iou_max,
        len(ocluidas),
        total,
        100 * len(ocluidas) / total if total else 0,
    )
    return ocluidas


def color_medio_limpio(
    pares_y_colores: list[tuple[tuple[int, int], np.ndarray]],
    ocluidas: set[tuple[int, int]] | None,
) -> np.ndarray | None:
    """Media de color usando solo recortes limpios, con red de seguridad.

    Si una identidad no tiene NINGÚN recorte limpio (pasa con jugadores
    que viven en un racimo), se usan todos: es mejor un voto contaminado
    que ninguno, porque sin voto la identidad se queda sin equipo y sale
    de las métricas colectivas.
    """
    from src.team_classification.feature_v2 import parte_camiseta_hs

    pares_y_colores = [(par, parte_camiseta_hs(c)) for par, c in pares_y_colores]
    if not pares_y_colores:
        return None
    if ocluidas:
        limpios = [c for par, c in pares_y_colores if par not in ocluidas]
        if limpios:
            return np.mean(limpios, axis=0)
    return np.mean([c for _par, c in pares_y_colores], axis=0)
