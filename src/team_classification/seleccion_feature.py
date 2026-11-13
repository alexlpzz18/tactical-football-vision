"""Elegir en CADA partido con qué feature se deciden los equipos, sin etiquetas.

docs/plan_equipos_consistencia.md. No hay un peso de brillo que sirva a todos los partidos: en el
alevín B (verde oscuro contra blanco, 21-29 px, neblina) el TONO del verde casi no se distingue del
blanco y lo que separa es el BRILLO; en el benjamín el brillo mete ruido y empeora
(docs/plan_equipos_medias.md). Una medida interna de «buena partición» (la silueta) elige AL REVÉS
en dos de tres patas (docs/plan_equipos_seleccion_automatica.md): premia grupos compactos, no
grupos acertados.

Lo que sí funciona es una ley FÍSICA: **una persona no cambia de equipo**. Para cada feature
candidata se agrupan en dos las medias de 1,5 s de las observaciones dentro del campo, y se mira
si la misma persona cae en el mismo grupo en dos ventanas distintas. Para estar seguros de que es
la misma persona, solo cuentan tramos AISLADOS (nadie a menos de `aislamiento_m` en ningún
fotograma, así que no hay cruce donde la identidad pueda saltar). Y para no premiar una partición
que separe «cerca contra lejos» o «sol contra sombra», las dos ventanas tienen que estar a
profundidades distintas (`min_dprof_m`): esa partición cambiaría de grupo ahí; la de equipos, no.

La puntuación es la kappa de Cohen sobre esas parejas (acuerdo corregido por el azar, para que un
reparto 95/5 no puntúe alto solo por ser desequilibrado).

Medido antes de construir (premisa, los tres partidos):
    benjamín (20 min)  H 0,975 · V 0,954  → H  (lo correcto)
    Villaviciosa       H 0,968 · V 0,841  → H  (lo correcto)
    alevín B           H 0,608 · V 0,749  → V  (lo correcto)
Sin la condición de profundidad, el benjamín saldría al revés (V 0,984 · H 0,954).
"""

import logging

import numpy as np
from sklearn.cluster import KMeans

from src.team_classification.color_classifier import (
    ParametrosClasificadorColor,
    _feature_trabajo,
)

logger = logging.getLogger(__name__)


def _kappa(a: np.ndarray, b: np.ndarray) -> float:
    """Kappa de Cohen entre dos vectores de etiquetas 0/1 (acuerdo corregido por azar)."""
    acuerdo = float(np.mean(a == b))
    p1 = float(np.mean(np.concatenate([a, b]) == 1))
    azar = p1**2 + (1 - p1) ** 2
    return (acuerdo - azar) / (1 - azar) if azar < 1 else float("nan")


def ventanas_aisladas(
    identidades,
    colores: dict,
    cache: list[dict],
    dentro,
    profundidad_de,
    aislamiento_m: float,
    ventana_s: float,
    hueco_max_s: float,
    minimo: int = 3,
) -> tuple[list[np.ndarray], list[tuple]]:
    """Medias de ventana para el agrupado y ventanas de tramos aislados para las parejas.

    Devuelve `(medias, aisladas)`:
    - `medias`: feature media de cada ventana fija de `ventana_s` de cada identidad, con lo que
      está dentro del campo (la población que se agrupa);
    - `aisladas`: `(tramo, t_centro, profundidad_media, feature_media)` de las ventanas de tramos
      continuos (huecos ≤ `hueco_max_s`) en los que la persona está dentro del campo y sin nadie a
      menos de `aislamiento_m`. `tramo` numera el tramo: dos ventanas con el mismo número son la
      misma persona.
    """
    pos = {}
    aislado = {}
    for e in cache:
        xy = np.array([d[:2] for d in e["dets"]], dtype=float).reshape(-1, 2)
        if len(xy) > 1:
            dist = np.linalg.norm(xy[:, None] - xy[None], axis=2)
            np.fill_diagonal(dist, np.inf)
            vecino = dist.min(axis=1)
        else:
            vecino = np.full(len(xy), np.inf)
        for j in range(len(xy)):
            pos[(e["frame_idx"], j)] = (xy[j, 0], xy[j, 1])
            aislado[(e["frame_idx"], j)] = bool(vecino[j] >= aislamiento_m)

    medias, aisladas = [], []
    n_tramo = 0

    def agrupar(obs):
        grupos = {}
        t0 = obs[0][0]
        for t, par in obs:
            grupos.setdefault(int((t - t0) // ventana_s), []).append((t, par))
        return [g for g in grupos.values() if len(g) >= minimo]

    for identidad in identidades:
        obs = sorted(
            (float(t), tuple(par))
            for tracklet in identidad
            for t, par in zip(tracklet.ts, tracklet.det_idxs)
            if tuple(par) in colores and tuple(par) in pos
        )
        de_dentro = [(t, p) for t, p in obs if dentro(pos[p])]
        if de_dentro:
            for g in agrupar(de_dentro):
                medias.append(np.mean([colores[p] for _, p in g], axis=0))
        tramo: list = []
        for t, p in obs + [(np.inf, None)]:  # centinela para cerrar el último tramo
            ok = p is not None and aislado[p] and dentro(pos[p])
            if ok and tramo and t - tramo[-1][0] <= hueco_max_s:
                tramo.append((t, p))
                continue
            if len(tramo) >= minimo:
                for g in agrupar(tramo):
                    aisladas.append(
                        (
                            n_tramo,
                            float(np.mean([t_ for t_, _ in g])),
                            float(np.mean([profundidad_de(pos[p_]) for _, p_ in g])),
                            np.mean([colores[p_] for _, p_ in g], axis=0),
                        )
                    )
                n_tramo += 1
            tramo = [(t, p)] if ok else []
    return medias, aisladas


def parejas(aisladas: list[tuple], max_dt_s: float, min_dprof_m: float) -> list:
    """Parejas (i, j) de ventanas del MISMO tramo, cercanas en tiempo y lejanas en profundidad."""
    salida = []
    for i in range(len(aisladas)):
        for j in range(i + 1, len(aisladas)):
            if aisladas[j][0] != aisladas[i][0]:
                break
            if (
                abs(aisladas[j][1] - aisladas[i][1]) <= max_dt_s
                and abs(aisladas[j][2] - aisladas[i][2]) >= min_dprof_m
            ):
                salida.append((i, j))
    return salida


def consistencia(
    medias: list[np.ndarray],
    aisladas: list[tuple],
    pares: list,
    params: ParametrosClasificadorColor,
    semilla: int = 0,
    max_ajuste: int = 20000,
) -> float:
    """Kappa de las parejas con la partición en dos de la feature `params`."""
    rng = np.random.default_rng(semilla)
    X = np.array([_feature_trabajo(f, params) for f in medias])
    if len(X) > max_ajuste:
        X = X[rng.choice(len(X), max_ajuste, replace=False)]
    km = KMeans(n_clusters=2, n_init=10, random_state=semilla).fit(X)
    etiqueta = km.predict(np.array([_feature_trabajo(a[3], params) for a in aisladas]))
    i, j = np.array(pares).T
    return _kappa(etiqueta[i], etiqueta[j])


def elegir_feature(
    identidades,
    colores: dict,
    cache: list[dict],
    cfg_equipos: dict,
    dentro,
    profundidad_de,
) -> tuple[dict, dict]:
    """`(cfg_equipos para este partido, informe)` según `entrenamiento.seleccion_automatica`.

    Si la alternativa (por defecto, brillo y pantalón con medias por ventana y k 2) supera a la base
    en kappa por `margen_kappa`, se aplican sus cambios; si no, o si hay menos de `min_parejas`
    parejas (sin señal), se queda la config tal cual. Nunca rompe: ante la duda, la base.
    """
    import copy

    cfg_sel = (cfg_equipos.get("entrenamiento") or {}).get("seleccion_automatica") or {}
    alternativa = dict(
        cfg_sel.get(
            "alternativa",
            {
                "medias_por_ventana_s": 1.5,
                "peso_v_pecho": 1.0,
                "peso_pantalon": 1.0,
                "k_clusters": 2,
            },
        )
    )
    medias, aisladas = ventanas_aisladas(
        identidades,
        colores,
        cache,
        dentro,
        profundidad_de,
        aislamiento_m=float(cfg_sel.get("aislamiento_m", 2.0)),
        ventana_s=float(cfg_sel.get("ventana_s", 1.5)),
        hueco_max_s=float(cfg_sel.get("hueco_max_s", 0.5)),
    )
    pares = parejas(
        aisladas,
        max_dt_s=float(cfg_sel.get("max_dt_s", 6.0)),
        min_dprof_m=float(cfg_sel.get("min_dprof_m", 6.0)),
    )
    informe = {"parejas": len(pares), "eleccion": "base"}
    if len(pares) < int(cfg_sel.get("min_parejas", 100)) or len(medias) < 10:
        logger.info(
            "Selección automática de feature: %d parejas (< mínimo), se queda la base",
            len(pares),
        )
        return cfg_equipos, informe

    base_params = ParametrosClasificadorColor.desde_dict(
        cfg_equipos.get("clasificador_color", {}) or {}
    )
    alt_params = ParametrosClasificadorColor.desde_dict(
        {
            **(cfg_equipos.get("clasificador_color", {}) or {}),
            **{
                k: v
                for k, v in alternativa.items()
                if k in ("peso_v_pecho", "peso_pantalon")
            },
        }
    )
    informe["kappa_base"] = round(consistencia(medias, aisladas, pares, base_params), 3)
    informe["kappa_alternativa"] = round(
        consistencia(medias, aisladas, pares, alt_params), 3
    )
    margen = float(cfg_sel.get("margen_kappa", 0.05))
    if informe["kappa_alternativa"] >= informe["kappa_base"] + margen:
        informe["eleccion"] = "alternativa"
        cfg_equipos = copy.deepcopy(cfg_equipos)
        ent = cfg_equipos.setdefault("entrenamiento", {})
        if "medias_por_ventana_s" in alternativa:
            ent["medias_por_ventana_s"] = alternativa["medias_por_ventana_s"]
        cc = cfg_equipos.setdefault("clasificador_color", {})
        for k, v in alternativa.items():
            if k != "medias_por_ventana_s":
                cc[k] = v
    logger.info(
        "Selección automática de feature: %d parejas · kappa base %.3f · alternativa %.3f → %s",
        len(pares),
        informe["kappa_base"],
        informe["kappa_alternativa"],
        informe["eleccion"],
    )
    return cfg_equipos, informe
