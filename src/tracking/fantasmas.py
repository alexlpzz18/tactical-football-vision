"""Filas FANTASMA del CSV de posiciones: interpoladas pegadas a una detección real.

Caso que lo destapó (27-nov-2026, `docs/segunda_opinion_27nov.md`, sección 8): en el 3:00.0 del
alevín B, el portero verde real y, a 0,57 m, una pista solo INTERPOLADA etiquetada como jugador de
campo. La regla de portero corona al real y el fantasma queda como defensa: el bloque verde pasa de
29 a 79 m. Medido: en ~38 % de los fotogramas de F11 hay algún fantasma; el largo del bloque cambia
más de 5 m en el 1,6-3 % de los (fotograma, equipo), con picos (p99) de 20-35 m.

Fantasma = una fila con `es_real` 0 que, en su mismo fotograma, está a ≤ `radio_m` de una fila REAL
del mismo equipo o de un portero (V1). La variante «de cualquier equipo» (V2) se midió y NO pasa:
contra el GT del alevín A empeora la presencia (faltan 14,3 → 14,7 %), el centroide y la
profundidad, porque borra a jugadores tapados en cruces con rivales.

Se quitan del CSV que leen la superposición, la pizarra y el informe. Solo se tocan filas
interpoladas: ninguna detección real se pierde.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_EQUIPO = {"A": "A", "B": "B", "portero_A": "A", "portero_B": "B"}


def marcar_fantasmas(df: pd.DataFrame, radio_m: float = 1.5) -> pd.Series:
    """Serie booleana (índice de `df`): True en las filas fantasma."""
    salida = pd.Series(False, index=df.index)
    if df.empty:
        return salida
    d = df[df.etiqueta.isin(_EQUIPO)]
    for _f, g in d.groupby("frame", sort=False):
        real = g.es_real.to_numpy() == 1
        if real.all() or not real.any():
            continue
        xy = g[["x_m", "y_m"]].to_numpy(float)
        eq = g.etiqueta.map(_EQUIPO).to_numpy()
        portero = g.etiqueta.str.startswith("portero").to_numpy()
        ir, ii = np.flatnonzero(real), np.flatnonzero(~real)
        dist = np.linalg.norm(xy[ii, None, :] - xy[None, ir, :], axis=2)
        valido = (eq[ii, None] == eq[None, ir]) | portero[None, ir]
        fantasma = ((dist <= radio_m) & valido).any(axis=1)
        salida.loc[g.index[ii[fantasma]]] = True
    return salida


def quitar_fantasmas(
    df: pd.DataFrame, radio_m: float = 1.5
) -> tuple[pd.DataFrame, int]:
    """(CSV sin las filas fantasma, nº quitadas)."""
    m = marcar_fantasmas(df, radio_m)
    n = int(m.sum())
    if n:
        logger.info(
            "Fantasmas: %d filas interpoladas pegadas a una real fuera del CSV", n
        )
    return df[~m], n
