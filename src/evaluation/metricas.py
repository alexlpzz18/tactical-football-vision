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

from src.evaluation.asociacion import Umbral, asociar_todos
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
    umbral_metros: Umbral,
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
    umbral_metros: Umbral,
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


@dataclass
class ResultadoCobertura:
    """Cobertura colectiva: la métrica de PRODUCTO del informe.

    % de posiciones GT (con equipo) cubiertas por una predicción emparejada
    cuyo equipo coincide, frame a frame. Un switch de identidad DENTRO del
    mismo equipo no penaliza (el informe colectivo agrega por equipo, no
    por jugador): solo importa que la posición esté y esté bien asignada.
    """

    cobertura: float  # global, sobre posiciones GT con equipo
    n_posiciones_gt: int
    permutado: bool  # mapeo A↔B aplicado a las predicciones
    por_grupo: dict[str, float]  # cobertura por grupo de equipo ('A', 'B')


def _grupo_equipo(team: str | None) -> str | None:
    """Grupo de equipo a efectos del informe: el portero cuenta con su equipo."""
    if team in ("A", "portero_A"):
        return "A"
    if team in ("B", "portero_B"):
        return "B"
    return None


def cobertura_colectiva(
    gt: PorFrame,
    pred: PorFrame,
    frames: list[int],
    umbral_metros: Umbral,
) -> ResultadoCobertura:
    """Calcula la cobertura colectiva (ver ResultadoCobertura).

    El emparejamiento GT↔pred es el mismo posicional del banco (húngaro +
    umbral); el equipo se compara a nivel de GRUPO (A/B, porteros incluidos
    en su equipo). Las etiquetas A/B del clasificador son arbitrarias: se
    prueba el mapeo directo y el permutado y se reporta el mejor.
    """
    from src.evaluation.asociacion import asociar_frame

    frames = sorted(frames)
    # (grupo_gt, grupo_pred_directo) por cada posición GT con equipo
    resultados_por_obs: list[tuple[str, str | None]] = []
    for frame in frames:
        obs_gt = gt.get(frame, [])
        obs_pred = pred.get(frame, [])
        pares = dict(asociar_frame(obs_gt, obs_pred, umbral_metros))
        for idx_gt, obs in enumerate(obs_gt):
            grupo_gt = _grupo_equipo(obs.team)
            if grupo_gt is None:  # el árbitro no cuenta para el informe
                continue
            grupo_pred = None
            if idx_gt in pares:
                grupo_pred = _grupo_equipo(obs_pred[pares[idx_gt]].team)
            resultados_por_obs.append((grupo_gt, grupo_pred))

    def _cobertura(mapa: dict[str, str]) -> tuple[float, dict[str, float]]:
        aciertos_grupo: Counter = Counter()
        total_grupo: Counter = Counter()
        for grupo_gt, grupo_pred in resultados_por_obs:
            total_grupo[grupo_gt] += 1
            if grupo_pred is not None and mapa.get(grupo_pred, grupo_pred) == grupo_gt:
                aciertos_grupo[grupo_gt] += 1
        total = sum(total_grupo.values())
        global_ = sum(aciertos_grupo.values()) / total if total else 0.0
        por_grupo = {g: aciertos_grupo[g] / total_grupo[g] for g in sorted(total_grupo)}
        return global_, por_grupo

    directo = _cobertura({"A": "A", "B": "B"})
    invertido = _cobertura({"A": "B", "B": "A"})
    permutado = invertido[0] > directo[0]
    cobertura, por_grupo = invertido if permutado else directo

    resultado = ResultadoCobertura(
        cobertura=cobertura,
        n_posiciones_gt=len(resultados_por_obs),
        permutado=permutado,
        por_grupo=por_grupo,
    )
    logger.info(
        "Cobertura colectiva: %.3f sobre %d posiciones GT (%s)",
        resultado.cobertura,
        resultado.n_posiciones_gt,
        por_grupo,
    )
    return resultado


@dataclass
class ResultadoConcurrencia:
    """Identidades SIMULTÁNEAS por frame: predichas vs las reales del GT.

    Es el número que grita el replay y que ninguna métrica clásica mira:
    IDF1/HOTA/cobertura pueden ser razonables con el doble de fichas en
    pantalla, porque penalizan por posición emparejada, no por exceso de
    identidades vivas a la vez. Si el pipeline dibuja 44 círculos para 23
    personas, el producto es inservible aunque las métricas aguanten.

    Nota: se cuentan las identidades con OBSERVACIÓN en el frame (lo que
    el replay dibuja), no las "activas" entre su primer y último frame.
    """

    mediana_pred: float
    p90_pred: float
    max_pred: int
    mediana_gt: float
    p90_gt: float
    exceso_mediana: float  # mediana_pred - mediana_gt (0 = perfecto)


def concurrencia_por_frame(
    gt: PorFrame,
    pred: PorFrame,
    frames: list[int],
) -> ResultadoConcurrencia:
    """Mediana/p90/máximo de identidades simultáneas (predichas y GT)."""
    n_pred = np.array([len(pred.get(frame, [])) for frame in frames], dtype=float)
    n_gt = np.array([len(gt.get(frame, [])) for frame in frames], dtype=float)
    resultado = ResultadoConcurrencia(
        mediana_pred=float(np.median(n_pred)) if len(n_pred) else 0.0,
        p90_pred=float(np.percentile(n_pred, 90)) if len(n_pred) else 0.0,
        max_pred=int(n_pred.max()) if len(n_pred) else 0,
        mediana_gt=float(np.median(n_gt)) if len(n_gt) else 0.0,
        p90_gt=float(np.percentile(n_gt, 90)) if len(n_gt) else 0.0,
        exceso_mediana=(
            float(np.median(n_pred) - np.median(n_gt)) if len(n_pred) else 0.0
        ),
    )
    logger.info(
        "Concurrencia por frame: pred mediana=%.0f p90=%.0f (GT mediana=%.0f)",
        resultado.mediana_pred,
        resultado.p90_pred,
        resultado.mediana_gt,
    )
    return resultado


@dataclass
class ResumenEquipos:
    """Resumen de la clasificación de equipos con mapeo A↔B óptimo.

    Las etiquetas A/B del clasificador son arbitrarias (clustering sin
    supervisión): se elige la correspondencia con las del GT que maximiza
    los aciertos sobre jugadores de campo, y se informa si hubo que
    permutar.
    """

    accuracy_campo: float | None  # sobre identidades con GT mayoritario A o B
    n_campo: int  # identidades de campo evaluadas
    permutado: bool  # True si el mapeo óptimo fue A↔B
    confusion: dict[str, Counter]  # {equipo_gt: Counter(equipo_pred mapeado)}
    # Porteros (regla posicional, etiquetas ancladas al lado del campo:
    # NO se permutan con A↔B)
    accuracy_porteros: float | None = None
    n_porteros: int = 0


def resumen_equipos(
    detalle: dict[int, tuple[str | None, str | None]],
) -> ResumenEquipos:
    """Calcula accuracy de campo y confusión a partir del detalle por identidad.

    Args:
        detalle: salida de accuracy_equipos().detalle:
            {id_identidad: (equipo_predicho, equipo_gt_mayoritario)}.
    """
    con_prediccion = [(pred, gt) for pred, gt in detalle.values() if pred is not None]

    def _aciertos_campo(mapa: dict[str, str]) -> tuple[int, int]:
        aciertos = total = 0
        for pred, gt in con_prediccion:
            if gt in ("A", "B"):
                total += 1
                if mapa.get(pred, pred) == gt:
                    aciertos += 1
        return aciertos, total

    directo = _aciertos_campo({"A": "A", "B": "B"})
    invertido = _aciertos_campo({"A": "B", "B": "A"})
    permutado = invertido[0] > directo[0]
    aciertos, n_campo = invertido if permutado else directo
    mapa = {"A": "B", "B": "A"} if permutado else {"A": "A", "B": "B"}

    confusion: dict[str, Counter] = defaultdict(Counter)
    for pred, gt in con_prediccion:
        confusion[gt][mapa.get(pred, pred)] += 1

    # Porteros: la regla posicional ancla la etiqueta al lado del campo,
    # así que se compara directa (sin permutación A↔B)
    porteros = [
        (pred, gt) for pred, gt in con_prediccion if gt in ("portero_A", "portero_B")
    ]
    aciertos_porteros = sum(1 for pred, gt in porteros if pred == gt)

    return ResumenEquipos(
        accuracy_campo=aciertos / n_campo if n_campo else None,
        n_campo=n_campo,
        permutado=permutado,
        confusion=dict(confusion),
        accuracy_porteros=aciertos_porteros / len(porteros) if porteros else None,
        n_porteros=len(porteros),
    )
