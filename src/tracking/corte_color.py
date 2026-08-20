"""Corte de identidades cuyo COLOR cambia de forma sostenida.

Observación visual de Alex (11-ago-2026): tras un cruce entre dos
jugadores, la clasificación de equipo falla y arrastra los ids. El primer
intento de arreglo —quitar el voto a los recortes ocluidos— no movió ni
una décima, y el resultado negativo señaló dónde estaba de verdad el
problema: nuestra clasificación es POR IDENTIDAD, una etiqueta para toda
la vida de la ficha, así que "fallar tras el cruce" solo puede significar
que la identidad cambió de PERSONA en el cruce. Es una quimera.

La firma de una quimera de este tipo es limpia: sus recortes votan un
equipo en la primera mitad de su vida y el otro en la segunda. Este
módulo la busca y parte la identidad por ahí.

Por qué esto sí y el corte de velocidad no: el corte de velocidad partía
por el ruido de proyección, que no dice nada sobre quién es quién, y por
eso destrozaba identidades sanas. El color, en cambio, es exactamente la
señal que distingue a un jugador de su rival — cuando cambia de forma
sostenida, no es ruido, es otra persona.
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosCorteColor:
    """Parámetros del corte por color."""

    activo: bool = True
    # Recortes mínimos para juzgar una identidad (con menos, el voto es
    # demasiado ruidoso para acusar a nadie).
    min_observaciones: int = 30
    # Solo se examinan identidades cuyo voto ya es dudoso: si el 90 % de
    # sus recortes dicen lo mismo, no hay nada que partir.
    pureza_max: float = 0.85
    # El corte debe mejorar la pureza al menos esto para hacerse.
    ganancia_min: float = 0.08
    # Observaciones mínimas a cada lado del corte.
    min_trozo: int = 10

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosCorteColor":
        if not d:
            return cls()
        conocidos = {c: d[c] for c in cls.__dataclass_fields__ if c in d}
        return cls(**conocidos)


def _partir_tracklet(tracklet: Tracklet, t_corte: float):
    """Parte un tracklet en (antes, después) de t_corte. Puede dar None."""
    partes = []
    for seleccion in (
        [i for i, t in enumerate(tracklet.ts) if t < t_corte],
        [i for i, t in enumerate(tracklet.ts) if t >= t_corte],
    ):
        if not seleccion:
            partes.append(None)
            continue
        primero = seleccion[0]
        frame, det = tracklet.det_idxs[primero]
        nuevo = Tracklet(
            tracklet.id, tracklet.ts[primero], tracklet.pos[primero], det, frame
        )
        for i in seleccion[1:]:
            frame, det = tracklet.det_idxs[i]
            nuevo.anadir(tracklet.ts[i], tracklet.pos[i], det, frame)
        partes.append(nuevo)
    return partes[0], partes[1]


def _mejor_corte(votos: np.ndarray, min_trozo: int):
    """(indice, pureza) del corte que deja los dos trozos más puros."""
    mejor = (None, -1.0)
    for k in range(min_trozo, len(votos) - min_trozo):
        izq, der = votos[:k], votos[k:]
        pureza = (
            max(izq.mean(), 1 - izq.mean()) * k
            + max(der.mean(), 1 - der.mean()) * len(der)
        ) / len(votos)
        if pureza > mejor[1]:
            mejor = (k, pureza)
    return mejor


def cortar_por_color(
    identidades: list[list[Tracklet]],
    colores: dict,
    clasificador,
    params: ParametrosCorteColor | None = None,
) -> list[list[Tracklet]]:
    """Parte las identidades cuyo voto de color cambia de forma sostenida.

    Args:
        identidades: identidades ya cosidas.
        colores: caché {(frame_idx, det_idx): feature}.
        clasificador: TeamClassifierColor entrenado.
        params: ver ParametrosCorteColor.

    Returns:
        Identidades, con las quimeras de color partidas en dos.
    """
    params = params or ParametrosCorteColor()
    if not params.activo:
        return identidades

    resultado, cortadas = [], 0
    for identidad in identidades:
        observaciones = []
        for tracklet in identidad:
            for t, par in zip(tracklet.ts, tracklet.det_idxs):
                if par in colores:
                    observaciones.append((t, clasificador.predict_color(colores[par])))
        if len(observaciones) < params.min_observaciones:
            resultado.append(identidad)
            continue

        observaciones.sort(key=lambda o: o[0])
        votos = np.array([1.0 if e == "A" else 0.0 for _t, e in observaciones])
        pureza_actual = max(votos.mean(), 1 - votos.mean())
        if pureza_actual >= params.pureza_max:
            resultado.append(identidad)
            continue

        indice, pureza = _mejor_corte(votos, params.min_trozo)
        if indice is None or pureza < pureza_actual + params.ganancia_min:
            resultado.append(identidad)
            continue

        t_corte = observaciones[indice][0]
        antes, despues = [], []
        for tracklet in identidad:
            izq, der = _partir_tracklet(tracklet, t_corte)
            if izq is not None:
                antes.append(izq)
            if der is not None:
                despues.append(der)
        for trozo in (antes, despues):
            if trozo:
                resultado.append(trozo)
        cortadas += 1

    logger.info(
        "Corte por color: %d identidades partidas → %d → %d identidades",
        cortadas,
        len(identidades),
        len(resultado),
    )
    return resultado
