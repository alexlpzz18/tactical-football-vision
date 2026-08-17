"""Puerta de APARIENCIA en la re-entrada: la firma de color decide si un
track recuperado sigue siendo la misma persona.

## Por qué aquí y no en el instante del cruce

El diseño original (docs/apariencia_en_asociacion.md) ponía la puerta en
el solape de cajas, imitando a BoT-SORT. El paso 0
(`scripts/diagnostico_quimeras.py`) lo midió y lo refutó en parte:

| señal antes del cambio de persona | en CAMBIOS | en normales | ratio |
|---|---|---|---|
| caja solapada (IoU>0,1, ventana 3) | 39,0 % | 21,1 % | 1,8× |
| pérdida real del track (hueco largo) | 19,5 % | 6,4 % | **3,0×** |

Seis de cada diez cambios de persona ocurren **sin** solape apreciable
cerca. La señal limpia es la otra: el salto no ocurre tanto al cruzarse
dos jugadores como al RECUPERAR una identidad que se había perdido y
engancharla a la persona equivocada. Por eso la puerta va aquí.

## Qué hace exactamente

ByteTrack conserva una identidad `buffer_perdido_s` segundos sin verla y
la reasigna al reaparecer. Esta etapa revisa esas reapariciones: si la
firma de color de ANTES no casa con la de DESPUÉS, la identidad se PARTE
en ese punto y el trozo nuevo sale como identidad aparte, para que el
cosido por pureza decida después con su propio criterio.

Es un corte, y este proyecto lleva tres cortes fallidos a la espalda
(velocidad, post-proceso completo, color) por la misma razón: aplicar un
criterio ruidoso a TODAS las observaciones destruye identidades buenas.
La diferencia aquí es la doctrina que fijó Alex: **no cortar en todos los
frames, solo decidir mejor donde el sistema ya está adivinando.** La
puerta solo mira los puntos de re-entrada, que son el 6 % de las
transiciones.

`sv.ByteTrack` es una caja cerrada y no admite un coste de apariencia
dentro, así que esto va justo después de la asociación — antes del
cosido, que es quien puede volver a unir lo que aquí se parta.
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)

# Observaciones a cada lado del corte con las que se calcula la firma.
_VENTANA_FIRMA = 8


@dataclass
class ParametrosPuertaReentrada:
    """Umbrales de la puerta, en unidades físicas."""

    activa: bool = False
    # Qué cuenta como "pérdida real". Por debajo de esto la identidad no
    # llegó a perderse: es el hueco normal entre muestras del caché.
    hueco_min_s: float = 0.5
    # Distancia máxima de color admitida entre el trozo de antes y el de
    # después. Misma escala que el veto del cosido (bloque HS, v1), donde
    # 1,2 es el veto adoptado: aquí se parte de algo MÁS exigente porque
    # el punto de re-entrada ya es sospechoso de por sí.
    color_max_dist: float = 0.9
    # Observaciones a cada lado para calcular la firma. Con una sola
    # muestra la firma es ruido puro y la puerta cortaría al azar.
    min_obs_firma: int = 3

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosPuertaReentrada":
        return cls(**(d or {}))


def _firma(colores: dict, pares: list[tuple[int, int]]) -> np.ndarray | None:
    """Color medio de unas observaciones, en la escala v1 (bloque HS)."""
    from src.team_classification.feature_v2 import parte_camiseta_hs

    muestras = [parte_camiseta_hs(colores[p]) for p in pares if p in colores]
    return np.mean(muestras, axis=0) if muestras else None


def _observaciones(identidad: list[Tracklet]) -> list[tuple[int, tuple[int, int]]]:
    """(frame, (frame, det_idx)) de la identidad, en orden temporal."""
    obs = [(par[0], par) for tr in identidad for par in tr.det_idxs]
    obs.sort(key=lambda o: o[0])
    return obs


def aplicar_puerta_reentrada(
    identidades: list[list[Tracklet]],
    colores: dict | None,
    dt: float,
    params: ParametrosPuertaReentrada | None = None,
) -> list[list[Tracklet]]:
    """Parte las identidades cuyo color no case tras una pérdida real.

    Args:
        identidades: salida de la asociación (listas de tracklets).
        colores: caché {(frame_idx, det_idx): feature}. Sin él no hay
            apariencia que consultar y la etapa se salta entera.
        dt: segundos entre muestras del caché.
        params: umbrales; si es None o `activa` es False, no toca nada.

    Returns:
        Las identidades, con las sospechosas partidas en dos o más.
    """
    params = params or ParametrosPuertaReentrada()
    if not params.activa or colores is None:
        return identidades

    hueco_min_frames = max(1, int(round(params.hueco_min_s / dt))) if dt > 0 else 1
    salida: list[list[Tracklet]] = []
    n_cortes = n_reentradas = 0

    for identidad in identidades:
        obs = _observaciones(identidad)
        # Puntos de re-entrada: dónde la identidad estuvo perdida de veras
        cortes = []
        for k in range(1, len(obs)):
            salto = obs[k][0] - obs[k - 1][0]
            if salto < hueco_min_frames * 1.5:
                continue
            n_reentradas += 1
            ini = max(0, k - _VENTANA_FIRMA)
            previas = [p for _f, p in obs[ini:k]]
            fin = k + _VENTANA_FIRMA
            siguientes = [p for _f, p in obs[k:fin]]
            antes = _firma(colores, previas)
            despues = _firma(colores, siguientes)
            n_antes = sum(1 for p in previas if p in colores)
            n_desp = sum(1 for p in siguientes if p in colores)
            if (
                antes is None
                or despues is None
                or n_antes < params.min_obs_firma
                or n_desp < params.min_obs_firma
            ):
                # Sin firma fiable la puerta se abstiene: cortar a ciegas
                # es exactamente el error que costó los tres negativos.
                continue
            if float(np.linalg.norm(antes - despues)) > params.color_max_dist:
                cortes.append(obs[k][0])

        if not cortes:
            salida.append(identidad)
            continue

        n_cortes += len(cortes)
        # Partir los tracklets por los frames de corte
        trozos: list[list[Tracklet]] = [[] for _ in range(len(cortes) + 1)]
        for tr in identidad:
            for i in range(len(tr.pos)):
                f = tr.det_idxs[i][0]
                destino = sum(1 for c in cortes if f >= c)
                nuevo = trozos[destino]
                if not nuevo or nuevo[-1].det_idxs[-1][0] > f:
                    nuevo.append(_tracklet_de(tr, i))
                else:
                    _anadir(nuevo[-1], tr, i)
        salida.extend([t for t in trozos if t])

    if n_reentradas:
        logger.info(
            "Puerta de re-entrada: %d reapariciones revisadas, %d cortes "
            "por color (%d → %d identidades)",
            n_reentradas,
            n_cortes,
            len(identidades),
            len(salida),
        )
    return salida


def _tracklet_de(tr: Tracklet, i: int) -> Tracklet:
    """Tracklet nuevo que arranca en la observación i de `tr`."""
    f, d = tr.det_idxs[i]
    return Tracklet(tr.id, tr.ts[i], tr.pos[i], d, f)


def _anadir(nuevo: Tracklet, tr: Tracklet, i: int) -> None:
    f, d = tr.det_idxs[i]
    nuevo.anadir(tr.ts[i], tr.pos[i], d, f)
