"""Postproceso GLOBAL de fichas tipo GTA-link: partir por equipo sostenido y unir con agrupamiento.

docs/plan_literatura.md, método 2. La idea es la de GTA-link (Sun et al., 2024; código MIT), con
código propio y sin su reidentificación por apariencia:

1. **Partir** cada ficha donde su etiqueta de EQUIPO cambia de forma sostenida: una racha del otro
   equipo de al menos `min_racha_s` abre una ficha nueva. Las rachas más cortas no parten (son el
   ruido de la etiqueta, no otra persona).
2. **Unir** con un agrupamiento jerárquico global DENTRO de cada equipo: se empieza con un grupo por
   ficha y se van fusionando los dos grupos más compatibles mientras quede alguna fusión posible.
   - Nunca se fusionan grupos con fichas que se solapen en el tiempo: una persona no está en dos
     sitios a la vez. Es una regla dura de TODO el grupo, no solo de la pareja.
   - Al fusionar se ordenan las fichas de los dos grupos por tiempo, y cada empalme nuevo tiene que
     caber físicamente: distancia ≤ `v_max_ms`·hueco + `margen_m`, con hueco ≤ `max_hueco_s`.
   - Coste de una fusión = la media, sobre sus empalmes nuevos, de distancia / (lo que cabe).
   A diferencia del reenlace de dos en dos (sucesor inmediato), un grupo puede intercalar fichas de
   otro: una ficha de A puede continuar a través de un trozo que ya era de otra cadena.

Solo cambia a qué ficha pertenece cada fila; en cada empalme nuevo se añaden filas interpoladas.
"""

import heapq
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EQUIPO = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}


@dataclass
class ParametrosGTA:
    min_racha_s: float = 1.5
    max_hueco_s: float = 3.0
    v_max_ms: float = 8.0
    margen_m: float = 1.5

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosGTA":
        d = d or {}
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def partir_por_equipo_sostenido(
    df: pd.DataFrame, min_racha_s: float
) -> tuple[pd.DataFrame, int]:
    """Nueva ficha donde empieza una racha de ≥ `min_racha_s` del OTRO equipo. Da (df, cortes)."""
    df = df.sort_values(["id_jugador", "tiempo_s"]).reset_index(drop=True)
    eq = df.etiqueta.map(EQUIPO).fillna("-").to_numpy()
    ids = df.id_jugador.to_numpy()
    t = df.tiempo_s.to_numpy()
    nuevo = np.zeros(len(df), dtype=bool)
    nuevo[0] = True
    cortes = 0
    ini = 0
    for fin in list(np.flatnonzero(ids[1:] != ids[:-1]) + 1) + [len(df)]:
        nuevo[ini] = True
        # rachas de la misma etiqueta dentro de esta ficha
        tramo = eq[ini:fin]
        cambia = np.flatnonzero(tramo[1:] != tramo[:-1]) + ini + 1
        bordes = [ini] + list(cambia) + [fin]
        actual = None  # equipo de la ficha en curso
        for a, b in zip(bordes[:-1], bordes[1:]):
            e = eq[a]
            if e not in ("A", "B"):
                continue
            larga = t[b - 1] - t[a] >= min_racha_s
            if actual is None:
                actual = e
            elif e != actual and larga:
                nuevo[a] = True
                cortes += 1
                actual = e
        ini = fin
    return df.assign(id_jugador=np.cumsum(nuevo)), cortes


def _fichas(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for ident, g in df.groupby("id_jugador", sort=False):
        e = g.etiqueta.map(EQUIPO).dropna()
        if e.empty:
            continue
        filas.append(
            (
                int(ident),
                e.mode().iloc[0],
                float(g.tiempo_s.iloc[0]),
                float(g.tiempo_s.iloc[-1]),
                float(g.x_m.iloc[0]),
                float(g.y_m.iloc[0]),
                float(g.x_m.iloc[-1]),
                float(g.y_m.iloc[-1]),
            )
        )
    return pd.DataFrame(filas, columns="id equipo t0 t1 x0 y0 x1 y1".split())


def _coste_fusion(a: list, b: list, p: ParametrosGTA) -> float | None:
    """Coste de fusionar dos grupos (listas de fichas ordenadas), o None si no se puede."""
    todas = sorted(a + b, key=lambda f: f[2])
    costes = []
    origen = {id(f): 0 for f in a} | {id(f): 1 for f in b}
    for f0, f1 in zip(todas[:-1], todas[1:]):
        if f1[2] <= f0[3]:
            return None  # solape en el tiempo: dos sitios a la vez
        if origen[id(f0)] == origen[id(f1)]:
            continue  # empalme que ya existía dentro de un grupo
        hueco = f1[2] - f0[3]
        if hueco > p.max_hueco_s:
            return None
        cabe = p.v_max_ms * hueco + p.margen_m
        d = float(np.hypot(f1[4] - f0[6], f1[5] - f0[7]))
        if d > cabe:
            return None
        costes.append(d / cabe)
    return float(np.mean(costes)) if costes else None


def agrupar(df: pd.DataFrame, p: ParametrosGTA) -> dict[int, int]:
    """{id de ficha: id de su grupo} con el agrupamiento jerárquico global dentro de cada equipo."""
    fichas = _fichas(df)
    asignacion = {}
    for _equipo, sub in fichas.groupby("equipo"):
        filas = [
            tuple(r) for r in sub.itertuples(index=False)
        ]  # (id, eq, t0, t1, x0, y0, x1, y1)
        grupos = {k: [f] for k, f in enumerate(filas)}
        version = {k: 0 for k in grupos}
        inicios = np.array([f[2] for f in filas])
        finales = np.array([f[3] for f in filas])
        por_inicio, por_final = np.argsort(inicios), np.argsort(finales)
        inicios_o, finales_o = inicios[por_inicio], finales[por_final]
        heap = []

        def candidatos(k):
            """Grupos con una ficha que empieza justo después de una de k, o acaba justo antes.

            Toda fusión válida tiene al menos un empalme nuevo, y un empalme es una ficha que acaba
            y otra que empieza a ≤ max_hueco: basta con mirar esas parejas.
            """
            vistos = set()
            for f in grupos[k]:
                a = np.searchsorted(inicios_o, f[3], "right")
                b = np.searchsorted(inicios_o, f[3] + p.max_hueco_s, "right")
                vistos.update(dueno[i] for i in por_inicio[a:b])
                a = np.searchsorted(finales_o, f[2] - p.max_hueco_s, "left")
                b = np.searchsorted(finales_o, f[2], "left")
                vistos.update(dueno[i] for i in por_final[a:b])
            vistos.discard(k)
            return vistos

        dueno = {k: k for k in grupos}  # índice de ficha → grupo

        def empujar(k):
            for g in candidatos(k):
                if g not in grupos:
                    continue
                c = _coste_fusion(grupos[k], grupos[g], p)
                if c is not None:
                    heapq.heappush(heap, (c, k, g, version[k], version[g]))

        for k in list(grupos):
            empujar(k)
        siguiente = len(filas)
        while heap:
            c, a, b, va, vb = heapq.heappop(heap)
            if (
                a not in grupos
                or b not in grupos
                or version[a] != va
                or version[b] != vb
            ):
                continue
            if _coste_fusion(grupos[a], grupos[b], p) is None:
                continue
            nuevo = siguiente
            siguiente += 1
            grupos[nuevo] = grupos.pop(a) + grupos.pop(b)
            version[nuevo] = 0
            for idx, f in enumerate(filas):
                if dueno[idx] in (a, b):
                    dueno[idx] = nuevo
            empujar(nuevo)
        for k, fs in grupos.items():
            raiz = min(f[0] for f in fs)
            for f in fs:
                asignacion[f[0]] = raiz
    return asignacion


def postproceso_gta(
    df: pd.DataFrame, params: ParametrosGTA | None = None
) -> tuple[pd.DataFrame, dict]:
    """Parte y une. Devuelve (df, informe)."""
    p = params or ParametrosGTA()
    antes = int(df.id_jugador.nunique())
    df, cortes = partir_por_equipo_sostenido(df, p.min_racha_s)
    grupo = agrupar(df, p)
    # filas interpoladas en los empalmes nuevos (entre fichas consecutivas del mismo grupo)
    frames = df[["frame", "tiempo_s"]].drop_duplicates().sort_values("tiempo_s")
    extremos = df.sort_values("tiempo_s").groupby("id_jugador")
    primera, ultima = extremos.first(), extremos.last()
    nuevas = []
    por_grupo: dict = {}
    for ficha, g in grupo.items():
        por_grupo.setdefault(g, []).append(ficha)
    for fichas in por_grupo.values():
        fichas.sort(key=lambda f: primera.loc[f, "tiempo_s"])
        for f0, f1 in zip(fichas[:-1], fichas[1:]):
            fin, ini = ultima.loc[f0], primera.loc[f1]
            dentro = frames[
                (frames.tiempo_s > fin.tiempo_s) & (frames.tiempo_s < ini.tiempo_s)
            ]
            for f, t in zip(dentro.frame, dentro.tiempo_s):
                w = (t - fin.tiempo_s) / (ini.tiempo_s - fin.tiempo_s)
                fila = fin.to_dict()
                fila.update(
                    frame=f,
                    tiempo_s=t,
                    id_jugador=f0,
                    x_m=round(float(fin.x_m + w * (ini.x_m - fin.x_m)), 2),
                    y_m=round(float(fin.y_m + w * (ini.y_m - fin.y_m)), 2),
                    es_real=0,
                )
                nuevas.append(fila)
    if nuevas:
        nuevo_df = pd.DataFrame(nuevas)
        nuevo_df["id_jugador"] = nuevo_df["id_jugador"].astype(int)
        df = pd.concat([df, nuevo_df[df.columns]], ignore_index=True)
    df = df.assign(id_jugador=df.id_jugador.map(lambda i: grupo.get(int(i), int(i))))
    df = df.sort_values(["frame", "id_jugador"]).reset_index(drop=True)
    informe = {
        "fichas_antes": antes,
        "cortes": cortes,
        "fichas_despues": int(df.id_jugador.nunique()),
    }
    logger.info("GTA: %s", informe)
    return df, informe
