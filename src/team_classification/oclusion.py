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


def torsos_tapados(
    cache: list[dict],
    umbral: float = 0.15,
    torso_alto: tuple[float, float] = (0.12, 0.45),
    torso_ancho: tuple[float, float] = (0.15, 0.85),
) -> set[tuple[int, int]]:
    """{(frame_idx, det_idx)} cuyo TORSO está tapado por otra caja en más de `umbral` de su área.

    docs/plan_parpadeo_torso.md. A diferencia de `detecciones_ocluidas` (IoU de las cajas enteras,
    la ruta cerrada el 21-sep), aquí se mide la parte del recorte de la que sale el color: la banda
    del pecho (`torso_alto`, `torso_ancho`, las fracciones del clasificador). Dos cajas que solo se
    pisan en las piernas no cuentan; un torso tapado por la cabeza de otro, sí. La fracción tapada
    es la suma de las intersecciones con las otras cajas, acotada a 1.
    """
    tapados: set[tuple[int, int]] = set()
    total = 0
    for entrada in cache:
        cajas = np.array([d[2:6] for d in entrada["dets"]], dtype=float).reshape(-1, 4)
        total += len(cajas)
        if len(cajas) < 2:
            continue
        w = cajas[:, 2] - cajas[:, 0]
        h = cajas[:, 3] - cajas[:, 1]
        tx1 = cajas[:, 0] + torso_ancho[0] * w
        tx2 = cajas[:, 0] + torso_ancho[1] * w
        ty1 = cajas[:, 1] + torso_alto[0] * h
        ty2 = cajas[:, 1] + torso_alto[1] * h
        area = np.maximum((tx2 - tx1) * (ty2 - ty1), 1e-9)
        ix = np.clip(
            np.minimum(tx2[:, None], cajas[None, :, 2])
            - np.maximum(tx1[:, None], cajas[None, :, 0]),
            0,
            None,
        )
        iy = np.clip(
            np.minimum(ty2[:, None], cajas[None, :, 3])
            - np.maximum(ty1[:, None], cajas[None, :, 1]),
            0,
            None,
        )
        inter = ix * iy
        np.fill_diagonal(inter, 0.0)
        frac = np.minimum(inter.sum(axis=1) / area, 1.0)
        for i in np.flatnonzero(frac > umbral):
            tapados.add((entrada["frame_idx"], int(i)))
    logger.info(
        "Torsos tapados (> %.0f %% del pecho): %d de %d (%.1f %%) — no votan color",
        100 * umbral,
        len(tapados),
        total,
        100 * len(tapados) / total if total else 0,
    )
    return tapados


def dilatar_por_identidad(identidades, marcadas: set, n: int) -> set:
    """Amplía las observaciones marcadas a las `n` anteriores y siguientes de SU identidad.

    Un torso tapado contamina también los fotogramas de justo antes y después del solape (las cajas
    ya se separan pero el recorte aún coge a la otra persona, o el detector va un paso por detrás).
    """
    if n <= 0:
        return set(marcadas)
    salida = set(marcadas)
    for identidad in identidades:
        obs = sorted(
            (t, tuple(par)) for tr in identidad for t, par in zip(tr.ts, tr.det_idxs)
        )
        pares = [p for _t, p in obs]
        for k, par in enumerate(pares):
            if par in marcadas:
                salida.update(pares[max(0, k - n) : k + n + 1])  # noqa: E203
    return salida


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
