"""Exclusión espacial dura: dos identidades no pueden ocupar la misma
posición en el mismo instante (Tarea 3, contexto de plantilla).

Si dos identidades comparten frames y en esos frames están sistemáticamente
a menos de `dist_max` metros, son el MISMO jugador visto dos veces
(detecciones duplicadas de SAHI en el solape de recortes, o fragmentos
paralelos que el cosido no unió porque ambos estaban "vivos" a la vez y el
cosido solo une final→inicio). Se fusionan en una sola identidad.

La mediana de las distancias (no la media) evita que un cruce puntual de
dos jugadores reales dispare una fusión errónea; el mínimo de frames
comunes evita decidir con evidencia anecdótica.
"""

import logging
from collections import defaultdict

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


def fusionar_identidades_duplicadas(
    identidades: list[list[Tracklet]],
    dist_max: float,
    min_frames_comunes: int,
    firmas: dict[int, tuple[str, np.ndarray]] | None = None,
    color_max_dist: float = 1.2,
) -> list[list[Tracklet]]:
    """Fusiona identidades que viven en el mismo sitio al mismo tiempo.

    Args:
        identidades: salida del cosido.
        dist_max: distancia mediana máxima (metros) en los frames comunes
            para considerar que dos identidades son el mismo jugador.
        min_frames_comunes: mínimo de frames compartidos para decidir.
        firmas: SALVAGUARDA DE MARCAJE (opcional): {índice_identidad
            (0-based): (etiqueta_equipo, feature_color_cercana)} solo para
            identidades con clasificación CONFIABLE (con recortes
            cercanos). Dos jugadores reales pueden ir pegados mucho rato
            (marcaje al hombre); si ambas identidades tienen firma, NO se
            fusionan cuando sus etiquetas difieren o sus colores son
            incompatibles (distancia > color_max_dist).
        color_max_dist: umbral de incompatibilidad de color entre firmas.

    Returns:
        Lista de identidades tras las fusiones (los tracklets de las
        fusionadas se concatenan en orden temporal).
    """
    # Posiciones por frame de cada identidad
    observaciones: list[dict[int, np.ndarray]] = []
    for identidad in identidades:
        por_frame: dict[int, np.ndarray] = {}
        for tracklet in identidad:
            for pos, (frame_idx, _det) in zip(tracklet.pos, tracklet.det_idxs):
                por_frame[frame_idx] = pos
        observaciones.append(por_frame)

    # Union-find para fusiones transitivas (A≈B y B≈C → {A,B,C})
    padre = list(range(len(identidades)))

    def raiz(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    n_pares = 0
    n_vetados = 0
    for i in range(len(identidades)):
        for j in range(i + 1, len(identidades)):
            comunes = observaciones[i].keys() & observaciones[j].keys()
            if len(comunes) < min_frames_comunes:
                continue
            distancias = [
                np.linalg.norm(observaciones[i][f] - observaciones[j][f])
                for f in comunes
            ]
            if float(np.median(distancias)) > dist_max:
                continue
            # Salvaguarda de marcaje: dos identidades con firma fiable de
            # equipos/colores distintos son jugadores REALES pegados, no
            # un duplicado → no fusionar
            if firmas is not None and i in firmas and j in firmas:
                etiqueta_i, color_i = firmas[i]
                etiqueta_j, color_j = firmas[j]
                if etiqueta_i != etiqueta_j or (
                    float(np.linalg.norm(color_i - color_j)) > color_max_dist
                ):
                    n_vetados += 1
                    continue
            padre[raiz(i)] = raiz(j)
            n_pares += 1

    grupos: dict[int, list[int]] = defaultdict(list)
    for i in range(len(identidades)):
        grupos[raiz(i)].append(i)

    resultado = []
    for miembros in grupos.values():
        if len(miembros) == 1:
            resultado.append(identidades[miembros[0]])
        else:
            resultado.append(_fusionar_grupo([identidades[m] for m in miembros]))

    logger.info(
        "Exclusión espacial: %d pares duplicados (%d vetados por firma) "
        "→ %d → %d identidades",
        n_pares,
        n_vetados,
        len(identidades),
        len(resultado),
    )
    return resultado


def _fusionar_grupo(grupo: list[list[Tracklet]]) -> list[Tracklet]:
    """Fusiona identidades duplicadas en UNA, deduplicando por frame.

    En los frames donde varias identidades del grupo tienen observación
    (la detección duplicada que originó el problema), se conserva la de la
    identidad con más observaciones (la más fiable). El resultado es un
    único tracklet reconstruido en orden temporal.
    """
    # Prioridad: identidades con más observaciones primero
    orden = sorted(grupo, key=lambda ident: -sum(len(tr) for tr in ident))
    por_frame: dict[int, tuple[float, np.ndarray, int]] = {}
    for identidad in orden:
        for tracklet in identidad:
            for t, pos, (frame_idx, det_idx) in zip(
                tracklet.ts, tracklet.pos, tracklet.det_idxs
            ):
                por_frame.setdefault(frame_idx, (t, pos, det_idx))

    frames = sorted(por_frame)
    t0, pos0, det0 = por_frame[frames[0]]
    fusionado = Tracklet(orden[0][0].id, t0, pos0, det0, frames[0])
    for frame_idx in frames[1:]:
        t, pos, det_idx = por_frame[frame_idx]
        fusionado.anadir(t, pos, det_idx, frame_idx)
    return [fusionado]
