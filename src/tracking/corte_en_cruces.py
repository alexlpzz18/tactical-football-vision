"""Cortar las pistas en los CRUCES y reenlazar los trozos (flag `tracking.corte_cruces`).

docs/diagnostico_22oct_g.md, bloque B2. APAGADO por defecto.

Por qué: el 80 % de los cambios de persona de ByteTrack ocurren con otra persona a < 2 m, y en el
86-94 % de esos cruces las dos personas son de equipos RIVALES (bloque A). Dentro del cruce las
cajas se solapan y ni el IoU ni el color sirven; fuera de él, sí. Así que no se decide DENTRO del
cruce: se corta la pista al entrar y al salir, y se vuelve a unir lo que sale con lo que entró,
mirando dos cosas que en el cruce no existían:
- el MOVIMIENTO: dónde estaría el que entró, a su velocidad, en el instante en que sale el otro;
- el COLOR de los frames LIMPIOS (sin solape) de cada trozo, relativo a la separación A−B.

Los frames del propio cruce se quedan con la cadena que ENTRA: son ambiguos (la caja fundida no es
el pie de nadie, CLAUDE.md) y así no generan identidades nuevas.

Esto es lo que CLAUDE.md llama «partir y luego unir».
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosCorteCruces:
    activo: bool = False
    iou_solape: float = (
        0.1  # una detección con IoU > esto con otra caja está en un cruce
    )
    dist_max_m: float = (
        1.5  # error máximo de la predicción de movimiento para reenlazar
    )
    hueco_max_s: float = 1.0  # tiempo máximo entre el último frame limpio y el primero
    lambda_rel: float = 0.5  # peso del color en el coste, relativo a la separación A−B
    umbral_rel: float = (
        0.973  # puerta de color (d / sep), como la del término de asociación
    )
    alfa: float = 0.2  # media móvil del modelo de color
    v_max_m_s: float = 10.0  # tope de la velocidad usada para predecir
    control_permutar_semilla: int | None = None  # SOLO control del diagnóstico
    # ── variante SIN COLOR (flag `corte_cruces_sin_color`, docs/diagnostico_23oct_b.md) ──
    usar_color: bool = True
    # la puerta de distancia CRECE con el hueco: dist_max_m + crecimiento_m_s · hueco
    crecimiento_m_s: float = 0.0
    # SOLO control del diagnóstico: corta en instantes AL AZAR (el mismo nº de cortes por pista)
    control_cortes_aleatorios_semilla: int | None = None

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosCorteCruces":
        if not d:
            return cls()
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def _trozos_de(ident, en_cruce) -> list[dict]:
    """Parte una pista en trozos: cada racha LIMPIA, con el cruce que la sigue pegado detrás.

    `entra_cruce`: el trozo acaba en un cruce (es un extremo que hay que reenlazar hacia delante).
    `sale_cruce`: el trozo empieza justo después de un cruce (extremo que llega desde atrás).
    Un cruce al principio de la pista se pega delante de su primera racha limpia.
    """
    obs = sorted(
        (t, np.asarray(pos), tuple(par))
        for tr in ident
        for t, pos, par in zip(tr.ts, tr.pos, tr.det_idxs)
    )
    # rachas alternadas [(es_cruce, [obs...]), ...]
    rachas: list[tuple[bool, list]] = []
    for o in obs:
        cruce = o[2] in en_cruce
        if rachas and rachas[-1][0] == cruce:
            rachas[-1][1].append(o)
        else:
            rachas.append((cruce, [o]))
    trozos: list[dict] = []
    prefijo: list = []
    for k, (cruce, lista) in enumerate(rachas):
        if cruce:
            if trozos and not prefijo and k > 0:
                trozos[-1]["cruce"].extend(lista)
                trozos[-1]["entra_cruce"] = True
            else:
                prefijo = lista  # cruce al principio de la pista
            continue
        trozos.append(
            {
                "limpias": lista,
                "cruce": prefijo,
                "entra_cruce": False,
                "sale_cruce": k > 0 and rachas[k - 1][0] and bool(trozos),
            }
        )
        prefijo = []
    if prefijo:  # una pista que es solo cruce
        trozos.append(
            {"limpias": [], "cruce": prefijo, "entra_cruce": False, "sale_cruce": False}
        )
    return trozos


def _velocidad(limpias) -> np.ndarray:
    ult = limpias[-5:]
    if len(ult) < 2 or ult[-1][0] <= ult[0][0]:
        return np.zeros(2)
    return (ult[-1][1] - ult[0][1]) / (ult[-1][0] - ult[0][0])


def _modelo(limpias, feat_de, alfa, desde_el_final: bool):
    serie = limpias if desde_el_final else limpias[::-1]
    m = None
    for _t, _p, par in serie:
        f = feat_de.get(par)
        if f is None:
            continue
        m = f if m is None else (1 - alfa) * m + alfa * f
    return m


def _cortes_al_azar(identidades, en_cruce, semilla: int) -> set[tuple[int, int]]:
    """CONTROL: el mismo nº de cortes por pista, en observaciones elegidas AL AZAR.

    Cada corte es un «cruce» de un frame. Si con esto el árbitro también sale de los equipos, el
    efecto del corte es PARTIR, no partir EN EL CRUCE.
    """
    rng = np.random.default_rng(semilla)
    falso: set[tuple[int, int]] = set()
    for ident in identidades:
        obs = sorted(tuple(par) for tr in ident for par in tr.det_idxs)
        n_cortes = sum(
            1
            for prev, act in zip(obs[:-1], obs[1:])
            if act in en_cruce and prev not in en_cruce
        )
        if n_cortes and len(obs) > 2:
            elegidos = rng.choice(
                np.arange(1, len(obs) - 1), min(n_cortes, len(obs) - 2), False
            )
            falso.update(obs[int(k)] for k in elegidos)
    return falso


def cortar_y_reenlazar(
    identidades: list[list[Tracklet]],
    cache: list[dict],
    colores: dict,
    separacion: float,
    params: ParametrosCorteCruces,
) -> list[list[Tracklet]]:
    """Identidades tras cortar en los cruces y reenlazar los trozos (ver el módulo)."""
    from scipy.optimize import linear_sum_assignment

    from src.team_classification.color_classifier import _solo_hs
    from src.tracking.asociacion_bytetrack import _iou_maximo

    rng = (
        np.random.default_rng(int(params.control_permutar_semilla))
        if params.control_permutar_semilla is not None
        else None
    )
    en_cruce: set[tuple[int, int]] = set()
    feat_de: dict[tuple[int, int], np.ndarray] = {}
    for e in cache:
        dets = e["dets"]
        if not dets:
            continue
        iou = _iou_maximo(np.array([d[2:6] for d in dets], dtype=float))
        f = e["frame_idx"]
        feats = [
            (
                _solo_hs(colores[(f, j)])
                if params.usar_color and colores and (f, j) in colores
                else None
            )
            for j in range(len(dets))
        ]
        if rng is not None:
            feats = [feats[k] for k in rng.permutation(len(feats))]
        for j in range(len(dets)):
            if iou[j] > params.iou_solape:
                en_cruce.add((f, j))
            elif feats[j] is not None:
                feat_de[(f, j)] = feats[j]

    if params.control_cortes_aleatorios_semilla is not None:
        en_cruce = _cortes_al_azar(
            identidades, en_cruce, int(params.control_cortes_aleatorios_semilla)
        )
    trozos = []
    for ident in identidades:
        trozos.extend(
            t for t in _trozos_de(ident, en_cruce) if t["limpias"] or t["cruce"]
        )
    # extremos: trozos que ENTRAN en un cruce (acaban en él) y trozos que SALEN de uno
    entran = [k for k, t in enumerate(trozos) if t["entra_cruce"] and t["limpias"]]
    salen = [k for k, t in enumerate(trozos) if t["sale_cruce"] and t["limpias"]]
    pares = []
    for a in entran:
        ta = trozos[a]
        t_fin, p_fin = ta["limpias"][-1][0], ta["limpias"][-1][1]
        v = _velocidad(ta["limpias"])
        rapidez = float(np.linalg.norm(v))
        if rapidez > params.v_max_m_s:
            v = v * params.v_max_m_s / rapidez
        m_a = _modelo(ta["limpias"], feat_de, params.alfa, desde_el_final=True)
        for b in salen:
            tb = trozos[b]
            t_ini, p_ini = tb["limpias"][0][0], tb["limpias"][0][1]
            dt = t_ini - t_fin
            if dt <= 0 or dt > params.hueco_max_s:
                continue
            dist = float(np.linalg.norm(p_fin + v * dt - p_ini))
            dist_max = params.dist_max_m + params.crecimiento_m_s * dt
            if dist > dist_max:
                continue
            m_b = _modelo(
                tb["limpias"][:10], feat_de, params.alfa, desde_el_final=False
            )
            d_col = (
                float(np.linalg.norm(m_a - m_b)) / separacion
                if m_a is not None and m_b is not None
                else None
            )
            if d_col is not None and d_col > params.umbral_rel:
                continue
            coste = dist / dist_max + params.lambda_rel * (d_col or 0.0)
            pares.append((a, b, coste))
    # asignación 1-a-1 por componentes conexas del grafo de pares posibles
    siguiente: dict[int, int] = {}
    if pares:
        izq = sorted({a for a, _b, _c in pares})
        der = sorted({b for _a, b, _c in pares})
        ia, ib = {a: i for i, a in enumerate(izq)}, {b: i for i, b in enumerate(der)}
        padre = list(range(len(izq) + len(der)))

        def raiz(x):
            while padre[x] != x:
                padre[x] = padre[padre[x]]
                x = padre[x]
            return x

        for a, b, _c in pares:
            padre[raiz(ia[a])] = raiz(len(izq) + ib[b])
        grupos: dict[int, list] = {}
        for a, b, c in pares:
            grupos.setdefault(raiz(ia[a]), []).append((a, b, c))
        for lista in grupos.values():
            aa = sorted({a for a, _b, _c in lista})
            bb = sorted({b for _a, b, _c in lista})
            M = np.full((len(aa), len(bb)), 1e6)
            for a, b, c in lista:
                M[aa.index(a), bb.index(b)] = c
            for i, j in zip(*linear_sum_assignment(M)):
                if M[i, j] < 1e6:
                    siguiente[aa[i]] = bb[j]
    # cadenas: se empieza por los trozos a los que no llega nadie
    llegan = set(siguiente.values())
    salida, usados, n = [], set(), 0
    for k in range(len(trozos)):
        if k in llegan or k in usados:
            continue
        cadena, actual = [], k
        while actual is not None and actual not in usados:
            usados.add(actual)
            cadena.append(trozos[actual])
            actual = siguiente.get(actual)
        tracklets = []
        vistos: set[int] = (
            set()
        )  # una cadena no puede tener dos observaciones en un frame
        for pos_c, trozo in enumerate(cadena):
            obs = sorted(trozo["limpias"] + trozo["cruce"], key=lambda o: o[0])
            # el cruce del que ENTRA se corta donde empieza el trozo con el que se reenlaza:
            # el cruce de una pista puede durar más que el de la otra
            if pos_c + 1 < len(cadena) and cadena[pos_c + 1]["limpias"]:
                t_sig = cadena[pos_c + 1]["limpias"][0][0]
                obs = [o for o in obs if o[0] < t_sig]
            obs = [o for o in obs if o[2][0] not in vistos]
            vistos.update(o[2][0] for o in obs)
            if not obs:
                continue
            t0, p0, par0 = obs[0]
            n += 1
            tr = Tracklet(n, t0, p0, par0[1], par0[0])
            for t, p, par in obs[1:]:
                tr.anadir(t, p, par[1], par[0])
            tracklets.append(tr)
        if tracklets:
            salida.append(tracklets)
    logger.info(
        "Corte en cruces: %d pistas → %d trozos; %d trozos entran en un cruce y %d salen; "
        "%d reenlaces → %d identidades",
        len(identidades),
        len(trozos),
        len(entran),
        len(salen),
        len(siguiente),
        len(salida),
    )
    return salida
