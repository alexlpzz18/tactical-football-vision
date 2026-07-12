"""Métricas de tracking propias, calculadas sobre la asociación en metros.

Estas métricas son el núcleo transparente y testeable del banco (TrackEval
se usa además como referencia estándar para HOTA; ver trackeval_runner).

Definiciones (Ristani et al. 2016 para IDF1; CLEAR-MOT para IDSW/Frag),
con la puerta de emparejamiento por distancia en metros en vez de IoU:

- IDF1: se empareja globalmente cada identidad GT con como mucho una
  identidad predicha (húngaro maximizando frames coincidentes); IDTP son
  los frames en que una pareja emparejada coincide (dist ≤ umbral).
  IDF1 = 2·IDTP / (2·IDTP + IDFP + IDFN).
- ID switches (IDSW): veces que una identidad GT pasa a estar emparejada
  con una identidad predicha distinta de la última que tuvo.
- Fragmentaciones (Frag): veces que una identidad GT pasa de emparejada a
  no-emparejada y vuelve a emparejarse después (cortes de cobertura).
- Accuracy de equipos: por identidad predicha, su equipo GT "verdadero" es
  el voto mayoritario del team GT sobre sus frames emparejados; la accuracy
  es la fracción de identidades cuya predicción de equipo coincide.
"""

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.evaluation.asociacion import asociar_todos
from src.evaluation.modelo import PorFrame

logger = logging.getLogger(__name__)


@dataclass
class ResultadoTracking:
    """Resultado de las métricas propias de tracking."""

    idf1: float
    idtp: int
    idfp: int
    idfn: int
    id_switches: int
    fragmentaciones: int
    n_gt: int  # observaciones GT totales en los frames evaluados
    n_pred: int  # observaciones predichas totales en los frames evaluados
    recall: float  # fracción de observaciones GT emparejadas (algún pred)
    precision: float  # fracción de observaciones pred emparejadas (algún GT)


def calcular_metricas_tracking(
    gt: PorFrame,
    pred: PorFrame,
    frames: list[int],
    umbral_metros: float,
) -> ResultadoTracking:
    """Calcula IDF1, IDSW y fragmentaciones con asociación en metros."""
    frames = sorted(frames)
    pares_por_frame = asociar_todos(gt, pred, frames, umbral_metros)

    n_gt = sum(len(gt.get(f, [])) for f in frames)
    n_pred = sum(len(pred.get(f, [])) for f in frames)
    n_emparejadas = sum(len(p) for p in pares_por_frame.values())

    # --- IDF1: emparejamiento GLOBAL identidad GT ↔ identidad pred ---
    # coincidencias[g][p] = nº de frames en que g y p quedaron emparejados
    coincidencias: dict[int, Counter] = defaultdict(Counter)
    for pares in pares_por_frame.values():
        for id_gt, id_pred in pares:
            coincidencias[id_gt][id_pred] += 1

    ids_gt = sorted({o.obj_id for f in frames for o in gt.get(f, [])})
    ids_pred = sorted({o.obj_id for f in frames for o in pred.get(f, [])})
    idtp = 0
    if ids_gt and ids_pred:
        beneficio = np.zeros((len(ids_gt), len(ids_pred)))
        for i, g in enumerate(ids_gt):
            for j, p in enumerate(ids_pred):
                beneficio[i, j] = coincidencias[g][p]
        filas, cols = linear_sum_assignment(-beneficio)  # maximizar
        idtp = int(beneficio[filas, cols].sum())
    idfn = n_gt - idtp
    idfp = n_pred - idtp
    idf1 = 2 * idtp / (2 * idtp + idfp + idfn) if (n_gt + n_pred) else 0.0

    # --- IDSW y fragmentaciones, siguiendo cada identidad GT en el tiempo ---
    ultimo_pred: dict[int, int] = {}  # última identidad pred de cada GT
    emparejado_antes: dict[int, bool] = (
        {}
    )  # ¿estaba emparejado en el frame anterior visto?
    id_switches = 0
    fragmentaciones = 0
    for frame in frames:
        pares = dict(pares_por_frame[frame])  # {id_gt: id_pred}
        for obs in gt.get(frame, []):
            g = obs.obj_id
            if g in pares:
                if g in ultimo_pred and ultimo_pred[g] != pares[g]:
                    id_switches += 1
                if g in emparejado_antes and not emparejado_antes[g]:
                    fragmentaciones += 1
                ultimo_pred[g] = pares[g]
                emparejado_antes[g] = True
            else:
                emparejado_antes[g] = False

    resultado = ResultadoTracking(
        idf1=idf1,
        idtp=idtp,
        idfp=idfp,
        idfn=idfn,
        id_switches=id_switches,
        fragmentaciones=fragmentaciones,
        n_gt=n_gt,
        n_pred=n_pred,
        recall=n_emparejadas / n_gt if n_gt else 0.0,
        precision=n_emparejadas / n_pred if n_pred else 0.0,
    )
    logger.info(
        "Métricas propias: IDF1=%.3f IDSW=%d Frag=%d recall=%.3f precision=%.3f",
        resultado.idf1,
        resultado.id_switches,
        resultado.fragmentaciones,
        resultado.recall,
        resultado.precision,
    )
    return resultado


@dataclass
class ResultadoEquipos:
    """Resultado de la evaluación de clasificación de equipos."""

    accuracy: float | None  # None si no hay predicciones de equipo
    n_identidades_evaluadas: int
    # {id_identidad_pred: (equipo_predicho, equipo_gt_mayoritario)}
    detalle: dict[int, tuple[str | None, str | None]]


def accuracy_equipos(
    gt: PorFrame,
    pred: PorFrame,
    frames: list[int],
    umbral_metros: float,
) -> ResultadoEquipos:
    """Accuracy de equipos por identidad predicha (voto mayoritario del GT).

    Para cada identidad predicha, el equipo GT mayoritario sobre sus frames
    emparejados define su equipo "verdadero". Si la identidad no trae
    predicción de equipo (clasificador aún no conectado), se registra el
    detalle pero no puntúa; con 0 identidades puntuables, accuracy = None.
    """
    frames = sorted(frames)
    pares_por_frame = asociar_todos(gt, pred, frames, umbral_metros)

    # Voto de equipo GT por identidad pred + equipo predicho declarado
    votos: dict[int, Counter] = defaultdict(Counter)
    equipo_predicho: dict[int, str | None] = {}
    teams_gt = {}  # {(frame, id_gt): team}
    for frame in frames:
        for obs in gt.get(frame, []):
            teams_gt[(frame, obs.obj_id)] = obs.team
        for obs in pred.get(frame, []):
            equipo_predicho.setdefault(obs.obj_id, obs.team)
    for frame, pares in pares_por_frame.items():
        for id_gt, id_pred in pares:
            team = teams_gt.get((frame, id_gt))
            if team is not None:  # el árbitro no vota
                votos[id_pred][team] += 1

    detalle = {}
    aciertos = 0
    evaluables = 0
    for id_pred, contador in sorted(votos.items()):
        equipo_gt = contador.most_common(1)[0][0]
        declarado = equipo_predicho.get(id_pred)
        detalle[id_pred] = (declarado, equipo_gt)
        if declarado is not None:
            evaluables += 1
            if declarado == equipo_gt:
                aciertos += 1

    accuracy = aciertos / evaluables if evaluables else None
    logger.info(
        "Equipos: accuracy=%s sobre %d identidades con predicción (%d con voto GT)",
        f"{accuracy:.3f}" if accuracy is not None else "N/A",
        evaluables,
        len(votos),
    )
    return ResultadoEquipos(
        accuracy=accuracy,
        n_identidades_evaluadas=evaluables,
        detalle=detalle,
    )
