"""El ÁRBITRO como seguimiento de UN único objeto (flag `arbitro.viterbi`, apagado por defecto).

docs/diagnostico_23oct_c.md. Por qué así y no por identidad: el árbitro se parte en ~10 identidades
y se mezcla con jugadores en los cruces (22-oct f), y toda regla que decide sobre la IDENTIDAD lo
reparte. Pero hay exactamente UN árbitro en el campo y su chaleco SÍ se ve por fila cuando se mira
sin la máscara anti-césped (AUC 0,85-0,90, 23-oct a). Así que se le busca como lo que es: un objeto
que se mueve de forma continua y viste de verde flúor.

- **Emisión** de cada detección: log de la razón de verosimilitud de su puntuación de chaleco
  (fracción del torso en la banda), con un modelo por bins estimado en la ventana del GT.
- **Transición**: continuidad de movimiento en metros (predicción a velocidad constante, ≤ 8 m/s),
  saltando frames si hace falta (hueco ≤ 2,5 s), más un estado «no visible».
- **Una sola pista** por partido: la de máxima verosimilitud (Viterbi).

Las filas de la pista pasan a `otro` (no cuentan para los equipos). En la variante «sustituye»,
además, las identidades del tercer grupo que NO están en la pista vuelven al voto de color por
observación.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ParametrosArbitroViterbi:
    activo: bool = False
    variante: str = "sustituye"  # o «anade»
    modelo_emision: str = ""  # JSON con los bins y el log LR de cada bin
    v_max_m_s: float = 8.0
    holgura_m: float = 0.5
    sigma0_m: float = 0.5
    sigma_m_s: float = 1.0
    hueco_max_s: float = 2.5
    coste_frame_saltado: float = 1.0
    coste_no_visible: float = 1.0
    coste_readquirir: float = 8.0
    margen_campo_m: float = 2.0
    ventana_voto_s: float = 1.5
    control_permutar_semilla: int | None = None  # SOLO control del diagnóstico

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosArbitroViterbi":
        if not d:
            return cls()
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def cargar_modelo_emision(ruta: str | Path) -> tuple[np.ndarray, np.ndarray]:
    m = json.loads(Path(ruta).read_text())
    return np.asarray(m["bins"], float), np.asarray(m["log_lr"], float)


def log_lr(puntuaciones: np.ndarray, modelo) -> np.ndarray:
    """log LR del bin de cada puntuación (bins = bordes; el último incluye el 1)."""
    bins, valores = modelo
    k = np.clip(
        np.searchsorted(bins, puntuaciones, side="right") - 1, 0, len(valores) - 1
    )
    return valores[k]


def estimar_modelo(arbitro: np.ndarray, jugador: np.ndarray, bins) -> dict:
    """Modelo por bins con suavizado de Laplace; log LR recortado a ±5."""
    bins = np.asarray(bins, float)
    na = np.histogram(arbitro, bins)[0] + 1.0
    nj = np.histogram(jugador, bins)[0] + 1.0
    llr = np.clip(np.log((na / na.sum()) / (nj / nj.sum())), -5, 5)
    return {
        "bins": bins.tolist(),
        "log_lr": llr.tolist(),
        "n_arbitro": int(len(arbitro)),
        "n_jugador": int(len(jugador)),
    }


def reindexar_chaleco(
    chaleco: dict, cache_crudo: list[dict], cache_filtrado: list[dict]
) -> dict:
    """La caché de chaleco está indexada sobre el caché CRUDO; el tracker ve el FILTRADO.

    Los filtros de confianza y de plausibilidad quitan cajas y renumeran las demás. Se casa cada
    caja filtrada con la cruda IDÉNTICA del mismo frame (la caja no cambia, solo su índice).
    """
    crudo = {e["frame_idx"]: e["dets"] for e in cache_crudo}
    out = {}
    for e in cache_filtrado:
        f = e["frame_idx"]
        indice = {tuple(d[2:6]): i for i, d in enumerate(crudo.get(f, []))}
        for j, d in enumerate(e["dets"]):
            i = indice.get(tuple(d[2:6]))
            if i is not None and (f, i) in chaleco:
                out[(f, j)] = chaleco[(f, i)]
    return out


def pista_del_arbitro(
    cache: list[dict],
    chaleco: dict,
    modelo,
    params: ParametrosArbitroViterbi,
    dimensiones: tuple[float, float],
) -> dict[int, int]:
    """{frame: índice de la detección} de la pista del árbitro (frames «no visible» fuera)."""
    largo, ancho = dimensiones
    m = params.margen_campo_m
    rng = (
        np.random.default_rng(int(params.control_permutar_semilla))
        if params.control_permutar_semilla is not None
        else None
    )
    frames, P, E, J, T = [], [], [], [], []
    for e in sorted(cache, key=lambda x: x["frame_idx"]):
        dets = e["dets"]
        idx = [
            j
            for j, d in enumerate(dets)
            if -m <= d[0] <= largo + m and -m <= d[1] <= ancho + m
        ]
        pos = np.array([dets[j][:2] for j in idx], float).reshape(-1, 2)
        s = np.array([chaleco.get((e["frame_idx"], j), 0.0) for j in idx], float)
        em = log_lr(s, modelo) if len(s) else np.zeros(0)
        if rng is not None and len(em) > 1:
            em = em[rng.permutation(len(em))]
        frames.append(e["frame_idx"])
        P.append(pos)
        E.append(em)
        J.append(idx)
        T.append(float(e["t"]))
    n = len(frames)
    V = [None] * n  # puntuación de cada detección
    vel = [None] * n
    atras = [None] * n  # (t_prev, i_prev) o ("nv", t_prev)
    v_nv = np.zeros(n)
    atras_nv = [None] * n
    for t in range(n):
        nj = len(J[t])
        mejor = np.full(nj, -np.inf)
        bp = [None] * nj
        vv = np.zeros((nj, 2))
        # desde «no visible» en t−1 (o arranque): readquirir en cualquier sitio
        base = (v_nv[t - 1] if t > 0 else 0.0) - params.coste_readquirir
        mejor[:] = base
        bp = [("nv", t - 1)] * nj
        # desde una detección en t−k (k frames atrás, Δt ≤ hueco_max_s)
        k = 1
        while t - k >= 0 and T[t] - T[t - k] <= params.hueco_max_s + 1e-9:
            tp = t - k
            if len(J[tp]) and nj:
                dt = T[t] - T[tp]
                pred = P[tp] + vel[tp] * dt
                d = np.hypot(
                    pred[:, None, 0] - P[t][None, :, 0],
                    pred[:, None, 1] - P[t][None, :, 1],
                )
                sigma = params.sigma0_m + params.sigma_m_s * dt
                val = (
                    V[tp][:, None]
                    - (k - 1) * params.coste_frame_saltado
                    - d**2 / (2 * sigma**2)
                )
                val = np.where(
                    d <= params.v_max_m_s * dt + params.holgura_m, val, -np.inf
                )
                i = np.argmax(val, axis=0)
                cand = val[i, np.arange(nj)]
                mejora = cand > mejor
                for j in np.flatnonzero(mejora):
                    mejor[j] = cand[j]
                    bp[j] = (tp, int(i[j]))
                    v = (P[t][j] - P[tp][int(i[j])]) / dt
                    rap = float(np.linalg.norm(v))
                    vv[j] = (
                        v * (params.v_max_m_s / rap) if rap > params.v_max_m_s else v
                    )
            k += 1
        for j in range(nj):
            if bp[j][0] == "nv":
                vv[j] = 0.0
        V[t] = mejor + E[t]
        vel[t] = vv
        atras[t] = bp
        # «no visible» en t
        desde_nv = (v_nv[t - 1] if t > 0 else 0.0) - params.coste_no_visible
        desde_det = (
            float(V[t - 1].max()) - params.coste_no_visible
            if t > 0 and len(V[t - 1])
            else -np.inf
        )
        if desde_det > desde_nv:
            v_nv[t], atras_nv[t] = desde_det, (t - 1, int(np.argmax(V[t - 1])))
        else:
            v_nv[t], atras_nv[t] = desde_nv, ("nv", t - 1)
    # reconstrucción hacia atrás desde el mejor estado del último frame
    pista: dict[int, int] = {}
    t = n - 1
    if n == 0:
        return pista
    if len(V[t]) and float(V[t].max()) > v_nv[t]:
        estado = ("det", int(np.argmax(V[t])))
    else:
        estado = ("nv", None)
    while t >= 0:
        if estado[0] == "det":
            pista[frames[t]] = J[t][estado[1]]
            prev = atras[t][estado[1]]
        else:
            prev = atras_nv[t]
        if prev is None:
            break
        if prev[0] == "nv":  # ("nv", t_prev): t_prev = −1 es el arranque
            if prev[1] < 0:
                break
            t, estado = prev[1], ("nv", None)
        else:
            t, estado = prev[0], ("det", prev[1])
    logger.info(
        "Árbitro (Viterbi): pista en %d de %d frames (%.0f %%)",
        len(pista),
        n,
        100 * len(pista) / max(n, 1),
    )
    return pista


def aplicar_pista(
    identidades,
    equipos: dict[int, str],
    etiquetas_por_obs: dict,
    pista: dict[int, int],
    colores: dict,
    clasificador,
    params: ParametrosArbitroViterbi,
) -> dict:
    """Las filas de la pista a `otro`; con «sustituye», el tercer grupo fuera de la pista, a A/B."""
    from src.team_classification.pipeline_equipos import color_medio_limpio

    salida = dict(etiquetas_por_obs)
    n_pista = n_devueltas = 0
    for i, ident in enumerate(identidades, start=1):
        etiqueta = str(equipos.get(i, "otro"))
        obs = sorted(
            (t, tuple(par)) for tr in ident for t, par in zip(tr.ts, tr.det_idxs)
        )
        devolver = params.variante == "sustituye" and etiqueta == "otro"
        for t_a, par in obs:
            if pista.get(par[0]) == par[1]:
                salida[(i, par[0])] = "otro"
                n_pista += 1
                continue
            if not devolver:
                continue
            cerca = [
                (p, colores[p])
                for t2, p in obs
                if abs(t2 - t_a) <= params.ventana_voto_s / 2 and p in colores
            ]
            media = color_medio_limpio(cerca, None) if cerca else None
            if media is None:
                continue
            salida[(i, par[0])] = clasificador.predict_color(media, solo_equipos=True)
            n_devueltas += 1
    logger.info(
        "Árbitro (Viterbi, %s): %d observaciones de la pista a 'otro'; %d del tercer grupo "
        "vuelven al voto por observación",
        params.variante,
        n_pista,
        n_devueltas,
    )
    return salida
