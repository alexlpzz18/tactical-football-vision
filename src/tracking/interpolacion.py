"""Interpolación de huecos DENTRO de identidades cosidas (Tarea 3a).

El pipeline conservador fragmenta mucho: solo ~34% de las detecciones acaba
en tracklets ≥3 frames, y las identidades cosidas tienen huecos (dentro de
un tracklet, por frames sin asociar; y entre tracklets, por el hueco del
cosido). Este módulo rellena esos huecos por interpolación LINEAL entre dos
posiciones reales consecutivas de la misma identidad.

Reglas estrictas:
- Solo se interpola ENTRE dos observaciones reales (nunca se extrapola
  antes de la primera ni después de la última).
- Solo en los instantes de frames que existen en el caché (no inventamos
  frames nuevos).
- Huecos mayores que `max_hueco` segundos no se rellenan (una recta de
  muchos segundos ya no es una trayectoria creíble).
"""

import bisect
import logging

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


def identidades_a_trayectorias(
    identidades: list[list[Tracklet]],
) -> list[list[tuple[int, np.ndarray, bool]]]:
    """Identidades (tracklets) → trayectorias crudas, todas REALES.

    Formato común de la fase post-cosido: (frame_idx, pos, es_real). Sirve
    para que la consolidación pueda trabajar sobre observaciones reales
    ANTES de interpolar (medido: fusionar antes densifica la identidad y
    la interpolación rellena menos — ver docs/experimentos_tracking.md).
    """
    trayectorias = []
    for identidad in identidades:
        observaciones = [
            (frame_idx, pos, True)
            for tracklet in identidad
            for pos, (frame_idx, _det) in zip(tracklet.pos, tracklet.det_idxs)
        ]
        trayectorias.append(sorted(observaciones, key=lambda x: x[0]))
    return trayectorias


def interpolar_trayectorias(
    trayectorias: list[list[tuple[int, np.ndarray, bool]]],
    frames_ts: list[tuple[int, float]],
    max_hueco: float,
    resolucion=None,
    hueco_min: float = 1.0,
) -> list[list[tuple[int, np.ndarray, bool]]]:
    """Rellena los huecos de trayectorias ya en formato (frame, pos, real).

    Mismas reglas que interpolar_identidad: solo entre observaciones
    REALES consecutivas, solo en frames del caché y solo si el hueco no
    supera max_hueco segundos.

    Con `resolucion`, el hueco máximo se REDUCE donde la resolución es
    peor: rellenar una zona en la que un píxel vale medio metro parte de
    anclajes mucho menos fiables. El límite baja de `max_hueco` (mejor
    zona) a `hueco_min` (peor) con la RAÍZ del factor de resolución, no
    con el factor entero: el error de una recta interpolada lo domina la
    duración del hueco, y solo en parte la calidad de sus dos extremos;
    escalar con el factor completo recortaba la interpolación casi a cero
    a partir del primer tercio del campo. Es una heurística — el reparto
    exacto habrá que medirlo con el primer tramo etiquetado.
    """
    indices_frames = [f for f, _ in frames_ts]
    t_por_frame = dict(frames_ts)

    resultado = []
    for trayectoria in trayectorias:
        reales = sorted(
            (t_por_frame[f], f, pos) for f, pos, es_real in trayectoria if es_real
        )
        salida = [(f, pos, True) for _t, f, pos in reales]
        for (t0, f0, p0), (t1, f1, p1) in zip(reales[:-1], reales[1:]):
            limite = max_hueco
            if resolucion is not None:
                # factor 1 en la mejor zona → max_hueco; factor alto en la
                # peor → hueco_min. Interpolación suave entre ambos.
                factor = resolucion.factor((p0 + p1) / 2)
                limite = max(hueco_min, max_hueco / np.sqrt(max(factor, 1.0)))
            if t1 - t0 > limite:
                continue
            inicio = bisect.bisect_right(indices_frames, f0)
            fin = bisect.bisect_left(indices_frames, f1)
            for frame_idx, t in frames_ts[inicio:fin]:
                alfa = (t - t0) / (t1 - t0)
                salida.append((frame_idx, p0 + alfa * (p1 - p0), False))
        resultado.append(sorted(salida, key=lambda x: x[0]))

    n_interp = sum(1 for t in resultado for _f, _p, real in t if not real)
    logger.info(
        "Interpolación de trayectorias: %d posiciones rellenadas (hueco ≤ %.1f s)",
        n_interp,
        max_hueco,
    )
    return resultado


def interpolar_identidad(
    identidad: list[Tracklet],
    frames_ts: list[tuple[int, float]],
    max_hueco: float,
) -> list[tuple[int, np.ndarray, bool]]:
    """Trayectoria continua de una identidad: observaciones reales + interpoladas.

    Args:
        identidad: cadena de tracklets cosidos (una identidad).
        frames_ts: [(frame_idx, t), ...] de TODOS los frames del caché,
            ordenados por tiempo.
        max_hueco: hueco máximo (segundos) que se permite rellenar.

    Returns:
        Lista ordenada de (frame_idx, pos, es_real); es_real=False para las
        posiciones interpoladas.
    """
    # Observaciones reales de la identidad, ordenadas por tiempo
    reales = []
    for tracklet in identidad:
        for t, pos, (frame_idx, _det) in zip(
            tracklet.ts, tracklet.pos, tracklet.det_idxs
        ):
            reales.append((t, frame_idx, pos))
    reales.sort(key=lambda x: x[0])

    resultado = [(frame_idx, pos, True) for _, frame_idx, pos in reales]

    indices_frames = [f for f, _ in frames_ts]
    for (t0, f0, p0), (t1, f1, p1) in zip(reales[:-1], reales[1:]):
        if t1 - t0 > max_hueco:
            continue  # hueco demasiado largo: no es creíble rellenarlo
        # Frames del caché estrictamente entre f0 y f1
        inicio = bisect.bisect_right(indices_frames, f0)
        fin = bisect.bisect_left(indices_frames, f1)
        for frame_idx, t in frames_ts[inicio:fin]:
            alfa = (t - t0) / (t1 - t0)
            resultado.append((frame_idx, p0 + alfa * (p1 - p0), False))

    resultado.sort(key=lambda x: x[0])
    return resultado


def interpolar_identidades(
    identidades: list[list[Tracklet]],
    frames_ts: list[tuple[int, float]],
    max_hueco: float,
) -> list[list[tuple[int, np.ndarray, bool]]]:
    """Interpola todas las identidades y reporta cuánto se rellenó."""
    trayectorias = [
        interpolar_identidad(identidad, frames_ts, max_hueco)
        for identidad in identidades
    ]
    n_reales = sum(sum(1 for _, _, real in tr if real) for tr in trayectorias)
    n_interp = sum(sum(1 for _, _, real in tr if not real) for tr in trayectorias)
    logger.info(
        "Interpolación: %d observaciones reales + %d interpoladas (+%.0f%%)",
        n_reales,
        n_interp,
        100 * n_interp / n_reales if n_reales else 0,
    )
    return trayectorias
