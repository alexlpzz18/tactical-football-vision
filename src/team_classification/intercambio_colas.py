"""Intercambiar las COLAS de dos rivales que salen de un solape con los colores invertidos.

docs/plan_parpadeo_torso.md (tarea 2 de la noche, variante b). Cuando dos jugadores de equipos
distintos se solapan en la imagen, el seguimiento a veces sale del solape con las identidades
cambiadas: la que venía siendo de A continúa sobre el jugador de B, y al revés. Lo delata el color:
antes del solape la identidad i parecía de un equipo y la j del otro; después, cada una parece del
equipo de la otra.

Regla (sobre la evidencia CONTINUA de color, `margen_ab` del clasificador: positivo = A):
1. solape = fotogramas seguidos en los que las cajas de i y j tienen IoU > `iou_min`;
2. antes del solape (ventana `ventana_s`) i y j tienen márgenes de signo contrario y los dos de
   magnitud ≥ `margen_min` (son rivales, con seguridad);
3. después del solape, los dos han dado la vuelta con la misma seguridad;
⇒ se intercambian las observaciones de i y j posteriores al solape.

Diferencia con la ruta cerrada «intercambiar colas por continuidad de MOVIMIENTO» (20-ago, sin
construir: arreglaría 3 de 24 fallos): aquella decidía con la geometría; esta, solo entre RIVALES
(el 86-94 % de los cambios en cruce) y con el color medio de ventanas limpias de antes y después,
nunca con un recorte suelto.

Las observaciones no se tocan ni se pierden: solo cambian de identidad. Cada identidad se devuelve
como un único Tracklet (ordenado por tiempo).
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosIntercambio:
    activo: bool = False
    iou_min: float = 0.10
    ventana_s: float = 1.5
    margen_min: float = 0.15

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosIntercambio":
        d = d or {}
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def intercambiar_colas(
    identidades,
    cache: list[dict],
    colores: dict,
    clasificador,
    params: ParametrosIntercambio,
) -> tuple[list, int]:
    """Devuelve (identidades con las colas intercambiadas, número de intercambios)."""
    if not params.activo:
        return identidades, 0
    obs = [
        sorted(
            (float(t), np.asarray(p, float), tuple(par))
            for tr in ident
            for t, p, par in zip(tr.ts, tr.pos, tr.det_idxs)
        )
        for ident in identidades
    ]
    cajas = {
        (e["frame_idx"], j): d[2:6] for e in cache for j, d in enumerate(e["dets"])
    }
    tiempo = {e["frame_idx"]: e["t"] for e in cache}
    dueno = {o[2]: i for i, os_ in enumerate(obs) for o in os_}
    # solapes por pareja: {(i, j): [frames]}
    solapes: dict[tuple[int, int], list[int]] = {}
    for e in cache:
        f = e["frame_idx"]
        presentes = [
            (dueno[(f, j)], j) for j in range(len(e["dets"])) if (f, j) in dueno
        ]
        for a in range(len(presentes)):
            for b in range(a + 1, len(presentes)):
                (ia, ja), (ib, jb) = presentes[a], presentes[b]
                if ia != ib and _iou(cajas[(f, ja)], cajas[(f, jb)]) > params.iou_min:
                    solapes.setdefault((min(ia, ib), max(ia, ib)), []).append(f)

    def margen(i: int, t0: float, t1: float) -> float | None:
        vals = [colores[o[2]] for o in obs[i] if t0 <= o[0] <= t1 and o[2] in colores]
        if len(vals) < 3:
            return None
        return clasificador.margen_ab(np.mean(vals, axis=0))

    eventos = []
    for (i, j), frames in solapes.items():
        frames = sorted(frames)
        # tramos seguidos de solape (huecos de más de 3 frames del caché parten el tramo)
        tramos, ini = [], 0
        orden = sorted(tiempo)
        pos = {f: k for k, f in enumerate(orden)}
        for k in range(1, len(frames) + 1):
            if k == len(frames) or pos[frames[k]] - pos[frames[k - 1]] > 3:
                tramos.append((frames[ini], frames[k - 1]))
                ini = k
        for fa, fb in tramos:
            ta, tb = tiempo[fa], tiempo[fb]
            mi_a = margen(i, ta - params.ventana_s, ta - 1e-6)
            mj_a = margen(j, ta - params.ventana_s, ta - 1e-6)
            mi_d = margen(i, tb + 1e-6, tb + params.ventana_s)
            mj_d = margen(j, tb + 1e-6, tb + params.ventana_s)
            if None in (mi_a, mj_a, mi_d, mj_d):
                continue
            seguros = (
                min(abs(mi_a), abs(mj_a), abs(mi_d), abs(mj_d)) >= params.margen_min
            )
            rivales = np.sign(mi_a) != np.sign(mj_a)
            invertidos = np.sign(mi_d) == np.sign(mj_a) and np.sign(mj_d) == np.sign(
                mi_a
            )
            if seguros and rivales and invertidos:
                eventos.append((tb, i, j))
    # se aplican en orden de tiempo; cada uno cambia las colas a partir de su instante
    tocadas = set()
    for tb, i, j in sorted(eventos):
        tocadas.update((i, j))
        cola_i = [o for o in obs[i] if o[0] > tb]
        cola_j = [o for o in obs[j] if o[0] > tb]
        obs[i] = [o for o in obs[i] if o[0] <= tb] + cola_j
        obs[j] = [o for o in obs[j] if o[0] <= tb] + cola_i
    salida = []
    for k, os_ in enumerate(obs):
        if k not in tocadas:
            salida.append(identidades[k])  # sin intercambio: la identidad tal cual
            continue
        if not os_:
            continue
        os_.sort(key=lambda o: o[0])
        t0, p0, (f0, d0) = os_[0]
        tr = Tracklet(k + 1, t0, p0, d0, f0)
        for t, p, (f, d) in os_[1:]:
            tr.anadir(t, p, d, f)
        salida.append([tr])
    logger.info("Intercambio de colas entre rivales: %d intercambios", len(eventos))
    return salida, len(eventos)
