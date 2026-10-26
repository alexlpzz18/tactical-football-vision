"""Métricas de ASOCIACIÓN desde un CSV de posiciones: IDF1 y fragmentación por persona.

docs/diagnostico_23oct_a.md, bloque 1. Para evaluar la asociación sin que engañe la PUREZA: la
pureza de una identidad premia partirla (un trozo corto es más puro por construcción), y eso
escondió durante dos días que el corte en cruces doblaba las identidades. IDF1 castiga las dos
cosas a la vez (mezclar y partir), y la fragmentación dice cuántas identidades del sistema necesita,
de media, cada persona del GT.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from src.evaluation.modelo import Observacion, PorFrame


def pred_desde_csv(filas, solo_reales: bool = True) -> PorFrame:
    """{frame: [Observacion]} con las filas del CSV (id_jugador como identidad)."""
    r = filas[filas.es_real == 1] if solo_reales else filas
    out: PorFrame = {}
    for f, ident, x, y in zip(r.frame, r.id_jugador, r.x_m, r.y_m):
        out.setdefault(int(f), []).append(
            Observacion(
                obj_id=int(ident), pos=np.array([x, y]), team=None, label="player"
            )
        )
    return out


def fragmentacion_por_persona(
    gt: PorFrame, pred: PorFrame, frames, umbral: float
) -> dict:
    """Identidades del sistema casadas con cada persona del GT (casado 1-a-1 por frame).

    Returns:
        {"media": identidades por persona, "mediana": ..., "por_persona": {obj_id: n}}.
    """
    from src.evaluation.asociacion import asociar_todos

    pares = asociar_todos(gt, pred, sorted(frames), umbral)
    ids: dict[int, set[int]] = defaultdict(set)
    for lista in pares.values():
        for id_gt, id_pred in lista:
            ids[id_gt].add(id_pred)
    n = {g: len(s) for g, s in ids.items()}
    vals = np.array(list(n.values())) if n else np.array([0])
    return {
        "media": float(vals.mean()),
        "mediana": float(np.median(vals)),
        "por_persona": n,
    }


def asociacion_desde_csv(filas, gt: PorFrame, umbral: float = 2.0) -> dict:
    """IDF1 (Ristani, con la asociación en metros del banco) y fragmentación por persona."""
    from src.evaluation.metricas import calcular_metricas_tracking

    pred = pred_desde_csv(filas)
    frames = sorted(set(gt) & set(pred))
    gt_jug = {f: [o for o in gt[f] if o.label != "referee"] for f in frames}
    res = calcular_metricas_tracking(gt_jug, pred, frames, umbral)
    frag = fragmentacion_por_persona(gt_jug, pred, frames, umbral)
    return {
        "IDF1": round(float(res.idf1), 4),
        "IDSW": int(res.id_switches),
        "identidades_por_persona_media": round(frag["media"], 2),
        "identidades_por_persona_mediana": frag["mediana"],
    }
