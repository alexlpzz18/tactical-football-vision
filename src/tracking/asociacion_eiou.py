"""Asociación por IoU de CAJAS AMPLIADAS en rondas, sin Kalman (idea de Deep-EIoU, sin
reidentificación).

docs/plan_literatura.md, método 1. Alternativa a `asociacion_bytetrack.py` detrás del interruptor
`bytetrack.asociacion: eiou`. Implementación PROPIA a partir del artículo (Huang et al., «Iterative
Scale-Up ExpansionIoU and Deep Features Association for Multi-Object Tracking in Sports», WACV
2024): el repositorio público no tiene licencia, así que no se copia su código.

Por qué podría servirnos: con jugadores de 15-40 px el IoU entre dos fotogramas se hunde enseguida,
y por eso ByteTrack corre aquí con `umbral_emparejamiento: 0.995` (acepta solapes de 0,005). En un
cruce elige entre solapes casi nulos, y su Kalman predice con velocidades de cajas diminutas.
Ampliar las dos cajas antes de medir el IoU da un solape GRADUADO aunque las cajas reales no se
toquen, y emparejar con la última caja vista (sin predecir) evita que una pista «derive» en el
cruce.

Cómo empareja, en cada fotograma:
1. detecciones ALTAS (conf > `umbral_alto`) contra las pistas vivas y perdidas, en rondas con la
   ampliación creciente (`escala_inicial`, + `paso_escala` por ronda): primero se casa lo que
   solapa con poca ampliación, después lo que necesita más;
2. pistas vivas que quedan contra detecciones BAJAS (como ByteTrack), con ampliación `escala_baja`;
3. pistas recién nacidas sin confirmar contra las altas que sobran (si no casan, se borran);
4. las altas que sobran con conf ≥ `umbral_nueva` abren pista nueva (sin confirmar).

Ampliación de una caja de ancho w con escala e: el ARTÍCULO la define como w·(1 + 2e) (`variante:
articulo`, por defecto). El código público hace otra cosa, w·(2 + 2e) (`variante: codigo`): se deja
como parámetro para poder medir las dos.

Las posiciones que consume el resto del sistema siguen en METROS: aquí solo se decide qué detección
es quién, igual que con ByteTrack.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosEIoU:
    # Las confianzas del artículo (0,6 / 0,1 / 0,7) son de YOLOX en vídeos de retransmisión. En el
    # F11
    # la mediana de nuestras detecciones es 0,71-0,76 y solo el 52-67 % pasa de 0,7, así que con
    # aquellos valores la mitad de los jugadores no podría abrir pista. Se bajan a 0,5.
    umbral_alto: float = 0.5
    umbral_bajo: float = 0.1
    umbral_nueva: float = 0.5
    escala_inicial: float = 0.7
    paso_escala: float = 0.1
    rondas: int = 2
    escala_baja: float = 0.5
    # coste = 1 − EIoU; se empareja si el coste es ≤ que esto (los del código público)
    coste_max_altas: float = 0.8
    coste_max_bajas: float = 0.5
    coste_max_nuevas: float = 0.7
    # memoria de una pista perdida, en SEGUNDOS (la de ByteTrack en producción: 2 s)
    buffer_perdido_s: float = 2.0
    variante: str = "articulo"  # "articulo" (w·(1+2e)) o "codigo" (w·(2+2e))

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosEIoU":
        d = d or {}
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def ampliar(cajas: np.ndarray, e: float, variante: str = "articulo") -> np.ndarray:
    """Cajas (N, 4) x1 y1 x2 y2 ampliadas alrededor de su centro."""
    cajas = np.asarray(cajas, dtype=float).reshape(-1, 4)
    w = cajas[:, 2] - cajas[:, 0]
    h = cajas[:, 3] - cajas[:, 1]
    if variante == "articulo":
        extra_w, extra_h = 2 * e * w, 2 * e * h  # ancho final w·(1 + 2e)
    elif variante == "codigo":
        extra_w, extra_h = w * (1 + 2 * e), h * (1 + 2 * e)  # ancho final w·(2 + 2e)
    else:
        raise ValueError(f"eiou.variante desconocida: {variante}")
    return np.column_stack(
        [
            cajas[:, 0] - extra_w / 2,
            cajas[:, 1] - extra_h / 2,
            cajas[:, 2] + extra_w / 2,
            cajas[:, 3] + extra_h / 2,
        ]
    )


def iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU (len(a), len(b)) entre dos conjuntos de cajas x1 y1 x2 y2."""
    a = np.asarray(a, dtype=float).reshape(-1, 4)
    b = np.asarray(b, dtype=float).reshape(-1, 4)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


@dataclass
class _Pista:
    id: int
    caja: np.ndarray
    ultimo_t: float
    confirmada: bool = False
    viva: bool = True  # False = perdida (aún se puede recuperar)
    obs: list = field(default_factory=list)  # [(t, pos_m, det_idx, frame_idx)]


def _emparejar(pistas, cajas_det, idx_det, e, coste_max, variante):
    """Hungarian con coste 1 − EIoU. Devuelve (pares [(pista, det)], pistas sin casar, dets sin)."""
    if not pistas or not len(idx_det):
        return [], list(pistas), list(idx_det)
    a = ampliar(np.array([p.caja for p in pistas]), e, variante)
    b = ampliar(cajas_det[idx_det], e, variante)
    coste = 1.0 - iou(a, b)
    filas, cols = linear_sum_assignment(coste)
    pares, usadas_p, usadas_d = [], set(), set()
    for i, j in zip(filas, cols):
        if coste[i, j] <= coste_max:
            pares.append((pistas[i], idx_det[j]))
            usadas_p.add(i)
            usadas_d.add(j)
    resto_p = [p for i, p in enumerate(pistas) if i not in usadas_p]
    resto_d = [d for j, d in enumerate(idx_det) if j not in usadas_d]
    return pares, resto_p, resto_d


def asociar_con_eiou(
    cache: list[dict], fps: float, sample: int, params: ParametrosEIoU | None = None
) -> list[list[Tracklet]]:
    """Identidades por IoU ampliado sobre las detecciones del caché (mismo formato que
    ByteTrack)."""
    p = params or ParametrosEIoU()
    pistas: list[_Pista] = []
    terminadas: list[_Pista] = []
    siguiente = 1
    primero = True
    for entrada in cache:
        t, frame = entrada["t"], entrada["frame_idx"]
        dets = entrada["dets"]
        # las perdidas demasiado tiempo se cierran
        for q in [
            q for q in pistas if not q.viva and t - q.ultimo_t > p.buffer_perdido_s
        ]:
            pistas.remove(q)
            terminadas.append(q)
        if not dets:
            for q in pistas:
                q.viva = False  # nada que casar: todas pasan a perdidas
            primero = False
            continue
        cajas = np.array([d[2:6] for d in dets], dtype=float)
        conf = np.array([d[6] for d in dets], dtype=float)
        altas = list(np.flatnonzero(conf > p.umbral_alto))
        bajas = list(np.flatnonzero((conf > p.umbral_bajo) & (conf <= p.umbral_alto)))

        def casar(q: _Pista, j: int) -> None:
            d = dets[j]
            q.caja = cajas[j]
            q.ultimo_t = t
            q.viva = True
            q.obs.append((t, np.array([d[0], d[1]]), int(j), frame))

        # 1. altas contra confirmadas (vivas y perdidas), en rondas de ampliación creciente
        pool = [q for q in pistas if q.confirmada]
        for r in range(p.rondas):
            e = p.escala_inicial + p.paso_escala * r
            pares, pool, altas = _emparejar(
                pool, cajas, altas, e, p.coste_max_altas, p.variante
            )
            for q, j in pares:
                casar(q, j)
        # 2. las VIVAS que quedan contra las bajas
        vivas = [q for q in pool if q.viva]
        pares, sin_casar, _ = _emparejar(
            vivas, cajas, bajas, p.escala_baja, p.coste_max_bajas, p.variante
        )
        for q, j in pares:
            casar(q, j)
        for q in sin_casar:
            q.viva = False
        # 3. recién nacidas sin confirmar contra las altas que sobran
        nuevas = [q for q in pistas if not q.confirmada]
        pares, sin_casar, altas = _emparejar(
            nuevas, cajas, altas, p.escala_baja, p.coste_max_nuevas, p.variante
        )
        for q, j in pares:
            casar(q, j)
            q.confirmada = True
        for q in sin_casar:
            pistas.remove(q)  # una detección suelta no es una persona
        # 4. pistas nuevas
        for j in altas:
            if conf[j] >= p.umbral_nueva:
                # en el primer fotograma se confirman directamente (como en ByteTrack)
                q = _Pista(siguiente, cajas[j], t, confirmada=primero)
                siguiente += 1
                casar(q, j)
                pistas.append(q)
        primero = False
    terminadas += [q for q in pistas if q.confirmada]
    identidades = []
    for q in sorted(terminadas, key=lambda q: q.id):
        if not q.confirmada or not q.obs:
            continue
        t0, pos0, det0, f0 = q.obs[0]
        tr = Tracklet(q.id, t0, pos0, det0, f0)
        for tk, pk, dk, fk in q.obs[1:]:
            tr.anadir(tk, pk, dk, fk)
        identidades.append([tr])
    asignadas = sum(len(i[0].ts) for i in identidades)
    totales = sum(len(e["dets"]) for e in cache)
    logger.info(
        "EIoU: %d identidades, %d/%d detecciones asignadas (%.0f %%)",
        len(identidades),
        asignadas,
        totales,
        100 * asignadas / max(totales, 1),
    )
    return identidades
