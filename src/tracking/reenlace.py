"""Etapa final de fichas: partir donde la etiqueta cambia de equipo y re-enlazar dentro del equipo.

docs/registro_mision.md, H2' y H3. Trabaja sobre la tabla de posiciones YA suavizada y etiquetada
(una fila por ficha y frame), y solo cambia a qué ficha pertenece cada fila: ni mueve posiciones ni
cambia etiquetas.

1. **Partir** (`partir_por_equipo`): si la etiqueta de una ficha pasa de un equipo al otro, la ficha
   se parte ahí. Con la etiqueta decidida por secuencia, un cambio sostenido es la señal de que el
   seguimiento pasó a otra persona. (Así una ficha nunca cambia de color: es por construcción y no
   demuestra nada; lo que cuenta es lo que pasa después.)
2. **Re-enlazar** (`reenlazar`): una ficha que muere se une a otra que nace poco después si son del
   mismo equipo y sus movimientos casan: el final de una extrapolado hacia delante y el principio de
   la otra extrapolado hacia atrás se encuentran a mitad del hueco. Se decide con una asignación
   global (el mejor conjunto de uniones, no la primera que vale).

Diferencias con lo ya cerrado (CLAUDE.md): no corta en cruces (solo donde la etiqueta, decidida con
pasado y futuro, cambia), el veto es el EQUIPO ya decidido (no la distancia de color de un recorte)
y el movimiento se usa en los dos sentidos sobre posiciones suavizadas.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

logger = logging.getLogger(__name__)

EQUIPO = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}


@dataclass
class ParametrosReenlace:
    max_hueco_s: float = 3.0
    tol_base_m: float = 1.5
    tol_por_s: float = 4.0
    # Tramo del que se saca la velocidad de cada extremo, y cuánto se extrapola como mucho
    ventana_vel_s: float = 0.6
    max_extrapolar_s: float = 1.0
    v_max_ms: float = 9.0
    # Una racha del otro equipo más corta que esto no parte la ficha (ya la decide la secuencia)
    min_racha_s: float = 0.0

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosReenlace":
        d = d or {}
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def partir_por_equipo(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Parte cada ficha donde su etiqueta cambia de GRUPO (A, B o lo demás). Da (df, cortes)."""
    df = df.sort_values(["id_jugador", "tiempo_s"]).reset_index(drop=True)
    grupo = df.etiqueta.map(EQUIPO).fillna(df.etiqueta.astype(str))
    misma = df.id_jugador.to_numpy()[1:] == df.id_jugador.to_numpy()[:-1]
    cambia = misma & (grupo.to_numpy()[1:] != grupo.to_numpy()[:-1])
    nuevo_trozo = np.r_[True, ~misma | cambia]
    df = df.assign(id_jugador=np.cumsum(nuevo_trozo))
    return df, int(cambia.sum())


def _extremos(df: pd.DataFrame, p: ParametrosReenlace) -> pd.DataFrame:
    """Por ficha: tiempo, posición y velocidad en su principio y en su final, y su equipo."""
    filas = []
    for ident, g in df.groupby("id_jugador", sort=False):
        t, x, y = g.tiempo_s.to_numpy(), g.x_m.to_numpy(), g.y_m.to_numpy()
        equipo = g.etiqueta.map(EQUIPO).fillna(g.etiqueta.astype(str)).mode().iloc[0]

        def vel(mask):
            if mask.sum() < 2 or t[mask][-1] - t[mask][0] <= 0:
                return 0.0, 0.0
            dt = t[mask][-1] - t[mask][0]
            v = np.array([x[mask][-1] - x[mask][0], y[mask][-1] - y[mask][0]]) / dt
            n = np.linalg.norm(v)
            return tuple(v * min(1.0, p.v_max_ms / n) if n > 0 else v)

        vi = vel(t <= t[0] + p.ventana_vel_s)
        vf = vel(t >= t[-1] - p.ventana_vel_s)
        filas.append((ident, equipo, t[0], x[0], y[0], *vi, t[-1], x[-1], y[-1], *vf))
    return pd.DataFrame(
        filas,
        columns="id equipo t0 x0 y0 vx0 vy0 t1 x1 y1 vx1 vy1".split(),
    )


def reenlazar(
    df: pd.DataFrame, params: ParametrosReenlace | None = None
) -> tuple[pd.DataFrame, int]:
    """Une fichas del mismo equipo cuyo final y principio casan. Devuelve (df, uniones).

    Las filas no cambian salvo `id_jugador`; en el hueco de cada unión se añaden filas
    interpoladas (`es_real` = 0) en los frames que existen en la tabla.
    """
    p = params or ParametrosReenlace()
    ext = _extremos(df, p)
    ext = ext[ext.equipo.isin(["A", "B"])].reset_index(drop=True)
    if len(ext) < 2:
        return df, 0
    n = len(ext)
    GRANDE = 1e6
    coste = np.full((n, n), GRANDE)
    orden = np.argsort(ext.t0.to_numpy())
    t0s = ext.t0.to_numpy()[orden]
    for i in range(n):
        fin = ext.iloc[i]
        a = np.searchsorted(t0s, fin.t1, side="right")
        b = np.searchsorted(t0s, fin.t1 + p.max_hueco_s, side="right")
        for j in orden[a:b]:
            ini = ext.iloc[j]
            if j == i or ini.equipo != fin.equipo:
                continue
            hueco = ini.t0 - fin.t1
            mitad = min(hueco / 2.0, p.max_extrapolar_s)
            adelante = np.array([fin.x1 + fin.vx1 * mitad, fin.y1 + fin.vy1 * mitad])
            atras = np.array([ini.x0 - ini.vx0 * mitad, ini.y0 - ini.vy0 * mitad])
            d = float(np.linalg.norm(adelante - atras))
            if d <= p.tol_base_m + p.tol_por_s * hueco:
                coste[i, j] = d + 0.5 * hueco
    filas, cols = linear_sum_assignment(coste)
    sigue = {int(i): int(j) for i, j in zip(filas, cols) if coste[i, j] < GRANDE}
    if not sigue:
        return df, 0
    # cadenas: cada ficha hereda el id de la primera de su cadena
    raiz = {}
    tiene_anterior = set(sigue.values())
    for i in range(n):
        if i in tiene_anterior:
            continue
        k = i
        while True:
            raiz[int(ext.id.iloc[k])] = int(ext.id.iloc[i])
            if k not in sigue:
                break
            k = sigue[k]
    # filas interpoladas en cada hueco
    frames = df[["frame", "tiempo_s"]].drop_duplicates().sort_values("tiempo_s")
    nuevas = []
    ultima = df.sort_values("tiempo_s").groupby("id_jugador").last()
    for i, j in sigue.items():
        fin, ini = ext.iloc[i], ext.iloc[j]
        dentro = frames[(frames.tiempo_s > fin.t1) & (frames.tiempo_s < ini.t0)]
        plantilla = ultima.loc[int(fin.id)]
        for f, t in zip(dentro.frame, dentro.tiempo_s):
            w = (t - fin.t1) / (ini.t0 - fin.t1)
            fila = plantilla.to_dict()
            fila.update(
                frame=f,
                tiempo_s=t,
                id_jugador=int(fin.id),
                x_m=round(float(fin.x1 + w * (ini.x0 - fin.x1)), 2),
                y_m=round(float(fin.y1 + w * (ini.y0 - fin.y1)), 2),
                es_real=0,
            )
            nuevas.append(fila)
    if nuevas:
        df = pd.concat([df, pd.DataFrame(nuevas)[df.columns]], ignore_index=True)
    df = df.assign(id_jugador=df.id_jugador.map(lambda i: raiz.get(int(i), int(i))))
    df = df.sort_values(["frame", "id_jugador"]).reset_index(drop=True)
    logger.info("Re-enlace: %d uniones entre %d fichas de equipo", len(sigue), n)
    return df, len(sigue)
