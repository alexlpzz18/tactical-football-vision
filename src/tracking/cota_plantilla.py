"""Cota blanda de plantilla: fusión de identidades ENTRELAZADAS (Tarea 3).

Diagnóstico que motiva esto: en el candidato hay ~21 identidades
OBSERVADAS por frame (≈ los 22-23 jugadores reales del GT) pero ~77
ACTIVAS simultáneas (su primer y último frame se solapan). Son fragmentos
del mismo jugador cuyas observaciones se alternan en el tiempo: los
frames de uno caen en los huecos del otro. El cosido no puede unirlos
(solo une final→inicio, hueco > 0) y la exclusión espacial tampoco
(apenas comparten frames observados). Aquí se fusionan por
COMPATIBILIDAD ESPACIAL: las observaciones de J deben caer cerca de la
trayectoria interpolada de I (y viceversa).

La cota (~23: 22 jugadores + árbitro) es BLANDA: es el objetivo del bucle
goloso, pero solo se fusiona mientras exista un par cuya compatibilidad
sea mejor que `coste_max`; si no lo hay, se para aunque la concurrencia
siga por encima (hay entradas/salidas de encuadre y fragmentos
genuinamente inconexos).
"""

import logging

import numpy as np

from src.tracking.exclusion_espacial import _fusionar_grupo
from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


def _observaciones(identidad: list[Tracklet]) -> tuple[np.ndarray, np.ndarray]:
    """(tiempos ordenados, posiciones Nx2) de todas las obs de la identidad."""
    ts, poss = [], []
    for tracklet in identidad:
        ts.extend(tracklet.ts)
        poss.extend(tracklet.pos)
    orden = np.argsort(ts)
    return np.array(ts)[orden], np.array(poss)[orden]


def _coste_entrelazado(
    obs_a: tuple[np.ndarray, np.ndarray],
    obs_b: tuple[np.ndarray, np.ndarray],
) -> float:
    """Compatibilidad espacial de dos identidades entrelazadas.

    Mediana de la distancia de cada observación de una identidad a la
    posición INTERPOLADA de la otra en ese instante (en ambos sentidos;
    solo se interpola dentro del rango temporal, nunca se extrapola).
    inf si no hay solape temporal evaluable.
    """
    distancias = []
    for (ts_x, pos_x), (ts_y, pos_y) in ((obs_a, obs_b), (obs_b, obs_a)):
        dentro = (ts_y >= ts_x[0]) & (ts_y <= ts_x[-1])
        if not dentro.any():
            continue
        interp_x = np.interp(ts_y[dentro], ts_x, pos_x[:, 0])
        interp_y = np.interp(ts_y[dentro], ts_x, pos_x[:, 1])
        d = np.hypot(pos_y[dentro, 0] - interp_x, pos_y[dentro, 1] - interp_y)
        distancias.extend(d.tolist())
    return float(np.median(distancias)) if distancias else float("inf")


def _concurrencia_mediana(identidades: list[list[Tracklet]]) -> float:
    """Mediana (ponderada por duración) del nº de identidades activas.

    Una identidad está "activa" en todo el rango entre su primer y último
    frame observado. El perfil se construye frame a frame para que la
    mediana pese cada instante por igual.
    """
    rangos = []
    for identidad in identidades:
        frames = [f for tr in identidad for f, _ in tr.det_idxs]
        rangos.append((min(frames), max(frames)))
    lo = min(r[0] for r in rangos)
    hi = max(r[1] for r in rangos)
    delta = np.zeros(hi - lo + 2)
    for inicio, fin in rangos:
        delta[inicio - lo] += 1
        delta[fin - lo + 1] -= 1
    perfil = np.cumsum(delta)[:-1]
    return float(np.median(perfil))


def fusionar_hasta_cota(
    identidades: list[list[Tracklet]],
    cota: int,
    coste_max: float,
) -> list[list[Tracklet]]:
    """Fusiona golosamente pares entrelazados hasta acercarse a la cota.

    En cada paso se fusiona el par con MENOR coste de compatibilidad; se
    para cuando la concurrencia mediana baja de `cota` o cuando el mejor
    par disponible supera `coste_max` (cota blanda: no se fuerza).
    """
    identidades = list(identidades)
    n_fusiones = 0
    while _concurrencia_mediana(identidades) > cota:
        observaciones = [_observaciones(ident) for ident in identidades]
        mejor = (float("inf"), -1, -1)
        for i in range(len(identidades)):
            for j in range(i + 1, len(identidades)):
                coste = _coste_entrelazado(observaciones[i], observaciones[j])
                if coste < mejor[0]:
                    mejor = (coste, i, j)
        coste, i, j = mejor
        if coste > coste_max:
            break  # no queda ningún par creíble: la cota es blanda
        fusionada = _fusionar_grupo([identidades[i], identidades[j]])
        identidades = [ident for k, ident in enumerate(identidades) if k not in (i, j)]
        identidades.append(fusionada)
        n_fusiones += 1
    logger.info(
        "Cota de plantilla: %d fusiones → %d identidades (concurrencia mediana %.0f)",
        n_fusiones,
        len(identidades),
        _concurrencia_mediana(identidades) if identidades else 0,
    )
    return identidades
