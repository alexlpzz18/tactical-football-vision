"""Partir una identidad donde se «teletransporta»: un cambio de nivel físicamente imposible.

docs/registro_mision.md (H1b / H3a). Tras el suavizado RTS, los saltos que quedan en el F11 no son
temblor: la detección de la identidad salta 6-15 m de un fotograma al siguiente (a veces, tras hueco
de 0,4-1,2 s) y SE QUEDA allí. Es el seguimiento saltando a otra persona. Ningún suavizado lo
arregla: lo honesto es que ahí acabe una ficha y empiece otra.

Regla: en cada frontera entre dos observaciones seguidas de la identidad se compara la MEDIANA de
las `n_lado` observaciones de antes con la de las `n_lado` de después. Hay teletransporte si están
más lejos de lo que un jugador puede correr en ese tiempo más el ruido de medida de esa zona:

    distancia > v_max · Δt + base + sigmas · (σ_antes + σ_después)

La mediana ignora un pico suelto de la caja (que vuelve a su sitio): solo corta lo que se queda.
El ruido σ es el LOCAL medido de los datos (`suavizado_rts.RuidoLocal`), así que en el fondo, donde
un píxel vale 0,4 m, hace falta un salto mayor que cerca.

No es el «corte de velocidad» (velocidad instantánea con umbral fijo: cortaba el ruido del fondo) ni
«cortar en cruces» (cortaba cada cruce y fragmentaba): ambos están cerrados en CLAUDE.md.
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet
from src.tracking.suavizado_rts import ParametrosRTS, RuidoLocal

logger = logging.getLogger(__name__)


@dataclass
class ParametrosCorte:
    v_max_ms: float = 10.0  # nadie corre más (un sprint de élite son ~10 m/s)
    base_m: float = 1.0  # holgura fija
    sigmas: float = 3.0  # holgura por ruido local
    n_lado: int = 3  # observaciones a cada lado para la mediana
    # Qué define el teletransporte:
    #   "nivel": cambio de nivel entre medianas (intento 1; corta de más: 14 cortes/min en el
    #       benjamín, donde no hay saltos. No usar.)
    #   "velocidad_suavizada": se suaviza con RTS y se corta donde la trayectoria suavizada sigue
    #       yendo a más de `v_corte_ms`: lo que el suavizado no pudo explicar como ruido.
    criterio: str = "velocidad_suavizada"
    v_corte_ms: float = 10.0  # el suavizado robusto reparte un salto de 6 m a ~12 m/s
    aceleracion_ms2: float = 3.0  # la del RTS con el que se busca el síntoma

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosCorte":
        d = d or {}
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def fronteras_de_corte(
    t: np.ndarray, pos: np.ndarray, ruido: RuidoLocal, params: ParametrosCorte
) -> list[int]:
    """Índices k donde la identidad se corta ENTRE la observación k−1 y la k."""
    n = len(t)
    if n < 2:
        return []
    sig = np.linalg.norm(ruido.sigma(pos), axis=1)
    exceso = np.zeros(n)
    for k in range(1, n):
        a, b = max(0, k - params.n_lado), min(n, k + params.n_lado)
        antes, despues = np.median(pos[a:k], axis=0), np.median(pos[k:b], axis=0)
        dt = float(np.median(t[k:b]) - np.median(t[a:k]))
        limite = (
            params.v_max_ms * dt
            + params.base_m
            + params.sigmas * (float(np.median(sig[a:k])) + float(np.median(sig[k:b])))
        )
        exceso[k] = float(np.linalg.norm(despues - antes)) - limite
    cortes = []
    k = 1
    while k < n:
        if exceso[k] > 0:
            # una racha de fronteras seguidas es UN salto: se corta en su paso crudo más largo
            fin = k
            while fin + 1 < n and exceso[fin + 1] > 0:
                fin += 1
            desde, hasta = k - 1, fin + 1
            pasos = np.linalg.norm(np.diff(pos[desde:hasta], axis=0), axis=1)
            cortes.append(k + int(np.argmax(pasos)))
            k = fin + 1
        else:
            k += 1
    return cortes


def fronteras_por_velocidad(
    t: np.ndarray, pos: np.ndarray, suave: np.ndarray, params: ParametrosCorte
) -> list[int]:
    """Cortes donde la trayectoria SUAVIZADA va a más de `v_corte_ms`.

    Una racha de pasos seguidos demasiado rápidos es UN teletransporte (el suavizado lo reparte
    en varios pasos): se corta en el paso CRUDO más largo de la racha y sus vecinos.
    """
    n = len(t)
    if n < 2:
        return []
    dt = np.maximum(np.diff(t), 1e-6)
    rapido = np.linalg.norm(np.diff(suave, axis=0), axis=1) / dt > params.v_corte_ms
    crudo = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    cortes, k = [], 0
    while k < n - 1:
        if rapido[k]:
            fin = k
            while fin + 1 < n - 1 and rapido[fin + 1]:
                fin += 1
            a, b = max(0, k - 1), min(n - 1, fin + 2)
            cortes.append(a + int(np.argmax(crudo[a:b])) + 1)
            k = fin + 1
        else:
            k += 1
    return sorted(set(cortes))


def cortar_teletransportes(
    identidades: list[list[Tracklet]], params: ParametrosCorte | None = None
) -> tuple[list[list[Tracklet]], int]:
    """Devuelve las identidades partidas en sus teletransportes y cuántos cortes se hicieron.

    Cada trozo es una identidad nueva de un solo tracklet (las observaciones no se tocan ni se
    pierden). Las identidades sin corte se devuelven tal cual, en su sitio.
    """
    params = params or ParametrosCorte()
    planas = []
    for identidad in identidades:
        obs = sorted(
            (
                (float(t), np.asarray(p, dtype=float), tuple(par))
                for tr in identidad
                for t, p, par in zip(tr.ts, tr.pos, tr.det_idxs)
            ),
            key=lambda o: o[0],
        )
        planas.append(obs)
    tiempo_de = {par[0]: t for obs in planas for t, _p, par in obs}
    ruido = RuidoLocal(
        [[(par[0], p, True) for _t, p, par in obs] for obs in planas],
        tiempo_de,
        ParametrosRTS(),
    )
    suaves = None
    if params.criterio == "velocidad_suavizada":
        from src.tracking.suavizado_rts import suavizar_rts

        suaves = suavizar_rts(
            [[(par[0], p, True) for _t, p, par in obs] for obs in planas],
            tiempo_de,
            ParametrosRTS(aceleracion_ms2=params.aceleracion_ms2),
        )
    elif params.criterio != "nivel":
        raise ValueError(
            f"corte_teletransporte.criterio desconocido: {params.criterio}"
        )
    salida, n_cortes = [], 0
    siguiente_id = 1 + max((tr.id for ident in identidades for tr in ident), default=0)
    for n_ident, (identidad, obs) in enumerate(zip(identidades, planas)):
        if len(obs) < 2:
            salida.append(identidad)
            continue
        t = np.array([o[0] for o in obs])
        pos = np.array([o[1] for o in obs])
        if suaves is not None:
            suave = np.array([p for _f, p, _r in suaves[n_ident]])
            cortes = fronteras_por_velocidad(t, pos, suave, params)
        else:
            cortes = fronteras_de_corte(t, pos, ruido, params)
        if not cortes:
            salida.append(identidad)
            continue
        n_cortes += len(cortes)
        for ini, fin in zip([0] + cortes, cortes + [len(obs)]):
            t0, p0, (f0, d0) = obs[ini]
            trozo = Tracklet(siguiente_id, t0, p0, d0, f0)
            siguiente_id += 1
            resto = ini + 1
            for tk, pk, (fk, dk) in obs[resto:fin]:
                trozo.anadir(tk, pk, dk, fk)
            salida.append([trozo])
    logger.info(
        "Corte de teletransportes: %d cortes, %d → %d identidades",
        n_cortes,
        len(identidades),
        len(salida),
    )
    return salida, n_cortes
