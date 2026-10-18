"""Parte los tracklets que contienen a DOS personas, con la apariencia.

## Por qué aquí y no en la re-entrada

Medido el 20-ago-2026 (`docs/oraculos.md`): desactivar la re-entrada por
completo sube la pureza solo de **80,1 % a 84,4 %**. O sea que la puerta
de re-entrada —donde se invirtieron semanas— explica 4 puntos de
contaminación, y los otros **16 nacen DENTRO del seguimiento continuo**,
en los cruces, sin ningún hueco temporal que los delate.

Consecuencia: un grafo global que solo UNA tracklets tiene un techo del
84 %, porque uniría bien piezas que ya vienen sucias. Hay que **partir y
luego unir**, en ese orden.

## Cómo se decide dónde cortar

No con DBSCAN sobre los embeddings sueltos, sino con **detección de punto
de cambio**: en una identidad, un intercambio de persona es un cambio
ORDENADO EN EL TIEMPO, no un grupo cualquiera. Se busca el instante `k`
que maximiza la distancia entre la firma de lo que va antes y la de lo
que va después, y se corta si supera el umbral.

La salvaguarda que evita el cuarto negativo del proyecto —tres cortes
fallidos por aplicar señales ruidosas a cada observación— es que aquí se
compara la **media de una ventana**, nunca un embedding suelto, y solo se
corta en el mejor punto de cada tracklet, no en todos los que pasen el
umbral.
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosPartir:
    """Umbrales del cortador, todos derivados de la distribución real."""

    activo: bool = False
    # Distancia de coseno mínima entre el "antes" y el "después" para
    # aceptar que son dos personas. La distancia entre recortes AL AZAR
    # de este partido tiene mediana 0,125 y p99 0,294, así que los
    # valores útiles viven muy por debajo de lo que "suena razonable".
    umbral: float = 0.08
    # Observaciones mínimas a cada lado. Con menos, la media es ruido y
    # el corte sería aleatorio.
    min_lado: int = 4
    # Cortes máximos por tracklet: se aplica en cascada.
    max_cortes: int = 3


def _firma(embeddings, pares):
    v = [embeddings[p] for p in pares if p in embeddings]
    return np.mean(v, axis=0) if v else None


def _coseno(a, b):
    na = float(np.linalg.norm(a)) + 1e-9
    nb = float(np.linalg.norm(b)) + 1e-9
    return float(1.0 - float(a @ b) / (na * nb))


def _mejor_corte(obs, embeddings, params):
    """(índice, distancia) del punto de cambio más marcado, o None."""
    mejor, dmax = None, -1.0
    for k in range(params.min_lado, len(obs) - params.min_lado + 1):
        ini, fin = max(0, k - 12), k + 12
        antes = _firma(embeddings, obs[ini:k])
        despues = _firma(embeddings, obs[k:fin])
        if antes is None or despues is None:
            continue
        d = _coseno(antes, despues)
        if d > dmax:
            mejor, dmax = k, d
    if mejor is None or dmax <= params.umbral:
        return None
    return mejor, dmax


def partir_tracklets(identidades, embeddings, params=None):
    """Devuelve las identidades con las contaminadas partidas en trozos."""
    params = params or ParametrosPartir()
    if not params.activo or not embeddings:
        return identidades

    salida, n_cortes = [], 0
    for identidad in identidades:
        obs = sorted(
            (par for tr in identidad for par in tr.det_idxs), key=lambda p: p[0]
        )
        pos = {}
        for tr in identidad:
            for p, par in zip(tr.pos, tr.det_idxs):
                pos[tuple(par)] = (p, tr)
        trozos = [obs]
        for _ in range(params.max_cortes):
            nuevos = []
            partido = False
            for trozo in trozos:
                r = _mejor_corte(trozo, embeddings, params) if len(trozo) > 8 else None
                if r is None:
                    nuevos.append(trozo)
                    continue
                k, _d = r
                nuevos.extend([trozo[:k], trozo[k:]])
                n_cortes += 1
                partido = True
            trozos = nuevos
            if not partido:
                break
        for trozo in trozos:
            if not trozo:
                continue
            nuevo = None
            lista = []
            for par in trozo:
                if par not in pos:
                    continue
                p, tr_orig = pos[par]
                i = tr_orig.det_idxs.index(par)
                if nuevo is None:
                    nuevo = Tracklet(tr_orig.id, tr_orig.ts[i], p, par[1], par[0])
                    lista.append(nuevo)
                else:
                    nuevo.anadir(tr_orig.ts[i], p, par[1], par[0])
            if lista:
                salida.append(lista)

    logger.info(
        "Partición por apariencia: %d cortes (%d → %d tracklets)",
        n_cortes,
        len(identidades),
        len(salida),
    )
    return salida
