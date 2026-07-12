"""Integración con TrackEval (estándar académico) para HOTA/IDF1/IDSW.

EL TRUCO DE LAS CAJAS SINTÉTICAS
--------------------------------
TrackEval asocia GT↔predicción por IoU de cajas, pero nuestro banco vive en
metros. Solución: convertimos cada objeto (GT proyectado y predicciones) en
una caja sintética de LxL "metros" centrada en su posición de campo, y
escribimos archivos en formato MOTChallenge donde las "coordenadas de
píxel" son en realidad metros. Así el IoU interno de TrackEval opera como
una medida de cercanía métrica y obtenemos HOTA/IDF1/IDSW estándar sin
modificar la librería.

Equivalencia IoU↔distancia (para interpretar resultados): dos cajas LxL
cuyos centros distan d (a lo largo de un eje) tienen IoU = (L-d)/(L+d).
Con L=2 m, el umbral IoU=0.5 que usan CLEAR e Identity equivale a d ≈ 0.67 m
— una puerta MÁS ESTRICTA que nuestro umbral de 2.0 m de las métricas
propias. HOTA promedia umbrales de IoU 0.05..0.95, así que degrada
suavemente con la distancia en vez de cortar en seco. Por eso el informe
final muestra ambas familias de métricas.
"""

import configparser
import logging
from pathlib import Path

from src.evaluation.modelo import PorFrame

logger = logging.getLogger(__name__)

# Nombres fijos de la estructura de carpetas que espera TrackEval
_BENCHMARK = "TLENS"
_SPLIT = "train"
_SECUENCIA = "TLENS-01"
_TRACKER = "tactical_lens"


def exportar_motchallenge(
    gt: PorFrame,
    pred: PorFrame,
    frames: list[int],
    directorio: str | Path,
    lado_caja: float,
) -> dict:
    """Escribe GT y predicciones en formato MOTChallenge con cajas sintéticas.

    Args:
        gt, pred: observaciones por frame (formato común, posiciones en metros).
        frames: frames globales a evaluar (los comunes GT∩caché).
        directorio: carpeta raíz donde crear la estructura de TrackEval.
        lado_caja: lado L de la caja sintética LxL en metros.

    Returns:
        dict con las rutas creadas ('gt_folder', 'trackers_folder').
    """
    directorio = Path(directorio)
    frames = sorted(frames)
    # MOTChallenge exige frames 1..N consecutivos → remapeamos
    frame_a_mot = {f: i + 1 for i, f in enumerate(frames)}

    carpeta_gt = directorio / "gt" / "mot_challenge"
    carpeta_seq = carpeta_gt / f"{_BENCHMARK}-{_SPLIT}" / _SECUENCIA
    carpeta_trackers = directorio / "trackers" / "mot_challenge"
    carpeta_datos_tracker = (
        carpeta_trackers / f"{_BENCHMARK}-{_SPLIT}" / _TRACKER / "data"
    )
    carpeta_seq.joinpath("gt").mkdir(parents=True, exist_ok=True)
    carpeta_datos_tracker.mkdir(parents=True, exist_ok=True)

    # seqmap: lista de secuencias a evaluar
    carpeta_seqmaps = carpeta_gt / "seqmaps"
    carpeta_seqmaps.mkdir(parents=True, exist_ok=True)
    (carpeta_seqmaps / f"{_BENCHMARK}-{_SPLIT}.txt").write_text(f"name\n{_SECUENCIA}\n")

    # seqinfo.ini (imWidth/imHeight son nominales: aquí "píxeles" = metros)
    seqinfo = configparser.ConfigParser()
    seqinfo["Sequence"] = {
        "name": _SECUENCIA,
        "seqLength": str(len(frames)),
        "imWidth": "110",
        "imHeight": "75",
        "frameRate": "2",
        "imDir": "img1",
        "imExt": ".jpg",
    }
    with open(carpeta_seq / "seqinfo.ini", "w") as f:
        seqinfo.write(f)

    mitad = lado_caja / 2.0

    def _lineas(por_frame: PorFrame, es_gt: bool) -> list[str]:
        lineas = []
        for frame in frames:
            for obs in por_frame.get(frame, []):
                x, y = obs.pos
                # frame, id, left, top, width, height, conf, ...
                if es_gt:
                    # clase 1 = pedestrian (la única que evalúa MotChallenge2DBox)
                    sufijo = "1,1,1"
                else:
                    sufijo = "1,-1,-1,-1"
                lineas.append(
                    f"{frame_a_mot[frame]},{obs.obj_id + 1},"
                    f"{x - mitad:.4f},{y - mitad:.4f},"
                    f"{lado_caja:.4f},{lado_caja:.4f},{sufijo}\n"
                )
        return lineas

    with open(carpeta_seq / "gt" / "gt.txt", "w") as f:
        f.writelines(_lineas(gt, es_gt=True))
    with open(carpeta_datos_tracker / f"{_SECUENCIA}.txt", "w") as f:
        f.writelines(_lineas(pred, es_gt=False))

    return {"gt_folder": carpeta_gt, "trackers_folder": carpeta_trackers}


def evaluar_con_trackeval(
    gt: PorFrame,
    pred: PorFrame,
    frames: list[int],
    directorio_trabajo: str | Path,
    lado_caja: float,
) -> dict:
    """Exporta a MOTChallenge y corre TrackEval (HOTA + CLEAR + Identity).

    Returns:
        dict plano con las métricas principales: HOTA, DetA, AssA, IDF1,
        IDSW (CLEAR), Frag (CLEAR), MOTA.

    Raises:
        ImportError: si trackeval no está instalado.
    """
    import trackeval  # import local: dependencia opcional del banco

    rutas = exportar_motchallenge(gt, pred, frames, directorio_trabajo, lado_caja)

    config_eval = trackeval.Evaluator.get_default_eval_config()
    config_eval.update(
        {
            "PRINT_RESULTS": False,
            "PRINT_CONFIG": False,
            "TIME_PROGRESS": False,
            "LOG_ON_ERROR": None,
            "OUTPUT_SUMMARY": False,
            "OUTPUT_DETAILED": False,
            "PLOT_CURVES": False,
        }
    )
    config_dataset = trackeval.datasets.MotChallenge2DBox.get_default_dataset_config()
    config_dataset.update(
        {
            "GT_FOLDER": str(rutas["gt_folder"]),
            "TRACKERS_FOLDER": str(rutas["trackers_folder"]),
            "BENCHMARK": _BENCHMARK,
            "SPLIT_TO_EVAL": _SPLIT,
            "TRACKERS_TO_EVAL": [_TRACKER],
            "DO_PREPROC": False,  # sin zonas de distractores: evaluamos todo
            "PRINT_CONFIG": False,
        }
    )
    evaluador = trackeval.Evaluator(config_eval)
    dataset = trackeval.datasets.MotChallenge2DBox(config_dataset)
    metricas = [
        trackeval.metrics.HOTA({"PRINT_CONFIG": False}),
        trackeval.metrics.CLEAR({"PRINT_CONFIG": False}),
        trackeval.metrics.Identity({"PRINT_CONFIG": False}),
    ]
    resultados, _ = evaluador.evaluate([dataset], metricas)

    res = resultados["MotChallenge2DBox"][_TRACKER][_SECUENCIA]["pedestrian"]
    plano = {
        # HOTA es un array por umbral de IoU (0.05..0.95): se reporta la media
        "HOTA": float(res["HOTA"]["HOTA"].mean()),
        "DetA": float(res["HOTA"]["DetA"].mean()),
        "AssA": float(res["HOTA"]["AssA"].mean()),
        "IDF1": float(res["Identity"]["IDF1"]),
        "IDSW": int(res["CLEAR"]["IDSW"]),
        "Frag": int(res["CLEAR"]["Frag"]),
        "MOTA": float(res["CLEAR"]["MOTA"]),
    }
    logger.info("TrackEval: %s", plano)
    return plano
