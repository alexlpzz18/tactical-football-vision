#!/usr/bin/env python
"""Banco de evaluación de tracking: mide el pipeline actual contra el GT.

Flujo:
  1. Carga caché de detecciones, ground truth (CVAT) y homografía.
  2. Corre el pipeline validado (Etapa A + cosido v2). Si existe el caché
     de colores usa el veto de color; si no, cose solo por movimiento.
  3. Alinea GT y caché (frames comunes) y verifica el offset empíricamente.
  4. Calcula métricas propias (asociación en metros, umbral configurable)
     y métricas estándar con TrackEval (truco de cajas sintéticas).
  5. Imprime la tabla de resultados → el BASELINE contra el que se medirá
     cada mejora de la Tarea 3.

Uso:
    python scripts/evaluar_tracking.py [--config configs/evaluation.yaml]
"""

import argparse
import logging
import pickle
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

# Permite ejecutar el script desde la raíz del repo sin instalar el paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.adaptador import identidades_a_por_frame  # noqa: E402
from src.evaluation.alineacion import (  # noqa: E402
    distancia_media_gt_cache,
    frames_comunes,
)
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.evaluation.metricas import (  # noqa: E402
    accuracy_equipos,
    calcular_metricas_tracking,
)
from src.evaluation.trackeval_runner import evaluar_con_trackeval  # noqa: E402
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.field_tracker import (  # noqa: E402
    ConservativeTracker,
    ParametrosEtapaA,
)
from src.tracking.stitcher import ParametrosCosido, TrackletStitcher  # noqa: E402

logger = logging.getLogger("evaluar_tracking")


def cargar_colores_opcional(ruta: Path, identidades_tracklets) -> dict | None:
    """Carga el caché de colores si existe y lo agrega por tracklet.

    El pickle tiene formato {(frame_idx, det_idx): feature np.array(256)}.
    Devuelve {tracklet.id: feature media} o None si el archivo no existe.
    """
    if not ruta.exists():
        logger.info("Sin caché de colores (%s): cosido SOLO por movimiento.", ruta)
        return None
    with open(ruta, "rb") as f:
        features = pickle.load(f)
    color_medio = {}
    for tracklet in identidades_tracklets:
        feats = [features[par] for par in tracklet.det_idxs if par in features]
        if feats:
            color_medio[tracklet.id] = np.mean(feats, axis=0)
    logger.info(
        "Caché de colores cargado: feature media para %d/%d tracklets.",
        len(color_medio),
        len(identidades_tracklets),
    )
    return color_medio


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/evaluation.yaml")
    parser.add_argument("--config-tracking", default="configs/tracking.yaml")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    with open(args.config_tracking) as f:
        cfg_tracking = yaml.safe_load(f)

    # ------------------------------------------------------------------ datos
    datos = cargar_cache(cfg["rutas"]["cache"])
    homografia = np.load(cfg["rutas"]["homografia"])
    tracks_gt = parsear_cvat(cfg["rutas"]["ground_truth"])

    gt = gt_a_por_frame(
        tracks_gt,
        homografia,
        frame_offset=cfg["alineacion"]["frame_offset"],
        paso_gt=cfg["alineacion"]["paso_gt"],
    )

    # --------------------------------------------------------------- pipeline
    tracker = ConservativeTracker(ParametrosEtapaA.desde_dict(cfg_tracking["etapa_a"]))
    tracklets = tracker.procesar(datos["cache"], datos["fps"], datos["sample"])

    color_medio = cargar_colores_opcional(
        Path(cfg["rutas"]["cache_colores"]), tracklets
    )
    stitcher = TrackletStitcher(ParametrosCosido.desde_dict(cfg_tracking["cosido"]))
    identidades = stitcher.coser(tracklets, color_medio)

    pred = identidades_a_por_frame(identidades)

    # ------------------------------------------------------------- alineación
    frames_cache = [e["frame_idx"] for e in datos["cache"]]
    comunes = frames_comunes(gt, frames_cache)
    dets_por_frame = {
        e["frame_idx"]: np.array([(d[0], d[1]) for d in e["dets"]])
        for e in datos["cache"]
    }
    dist_alineacion = distancia_media_gt_cache(gt, dets_por_frame, comunes)
    if dist_alineacion > 3.0:
        logger.warning(
            "Distancia media GT↔detecciones sospechosamente alta (%.2f m): "
            "revisa frame_offset/paso_gt en %s",
            dist_alineacion,
            args.config,
        )

    # --------------------------------------------------------------- métricas
    umbral = cfg["asociacion"]["umbral_metros"]
    propias = calcular_metricas_tracking(gt, pred, comunes, umbral)
    equipos = accuracy_equipos(gt, pred, comunes, umbral)

    with tempfile.TemporaryDirectory(prefix="trackeval_") as tmp:
        estandar = evaluar_con_trackeval(
            gt, pred, comunes, tmp, lado_caja=cfg["trackeval"]["lado_caja_sintetica"]
        )

    # ------------------------------------------------- distribución de equipos
    votos_por_equipo = defaultdict(int)
    for _, equipo_gt in equipos.detalle.values():
        votos_por_equipo[equipo_gt] += 1

    # ------------------------------------------------------------------ tabla
    ancho = 66
    print("\n" + "=" * ancho)
    print("BASELINE DE TRACKING — pipeline actual (Etapa A + cosido v2)")
    print("=" * ancho)
    print(f"Tramo: min 5-6 | frames evaluados: {len(comunes)} (GT∩caché)")
    print(
        f"Tracklets Etapa A: {len(tracklets)} | identidades cosidas: "
        f"{len(identidades)} ({'con color' if color_medio else 'solo movimiento'})"
    )
    print(f"Identidades GT: {len(tracks_gt)} (22 players + 1 referee)")
    print(
        f"Sanidad alineación: dist. media GT→det más cercana = {dist_alineacion:.2f} m"
    )
    print("-" * ancho)
    print(f"MÉTRICAS PROPIAS (asociación en metros, umbral {umbral:.1f} m)")
    print(
        f"  IDF1:            {propias.idf1:.3f}   (IDTP={propias.idtp}, "
        f"IDFP={propias.idfp}, IDFN={propias.idfn})"
    )
    print(f"  ID switches:     {propias.id_switches}")
    print(f"  Fragmentaciones: {propias.fragmentaciones}")
    print(f"  Recall/frame:    {propias.recall:.3f}   ({propias.n_gt} obs GT)")
    print(f"  Precision/frame: {propias.precision:.3f}   ({propias.n_pred} obs pred)")
    print("-" * ancho)
    lado = cfg["trackeval"]["lado_caja_sintetica"]
    print(
        f"TRACKEVAL (cajas sintéticas {lado:.0f}x{lado:.0f} m; "
        f"IoU 0.5 ≈ {lado / 3:.2f} m)"
    )
    print(
        f"  HOTA:  {estandar['HOTA']:.3f}   (DetA={estandar['DetA']:.3f}, "
        f"AssA={estandar['AssA']:.3f})"
    )
    print(f"  IDF1:  {estandar['IDF1']:.3f}")
    print(f"  IDSW:  {estandar['IDSW']}")
    print(f"  Frag:  {estandar['Frag']}")
    print(f"  MOTA:  {estandar['MOTA']:.3f}")
    print("-" * ancho)
    if equipos.accuracy is not None:
        print(
            f"EQUIPOS: accuracy = {equipos.accuracy:.3f} "
            f"({equipos.n_identidades_evaluadas} identidades)"
        )
    else:
        print("EQUIPOS: N/A (clasificador de equipos aún no conectado al pipeline)")
        print(f"  Identidades pred con equipo GT mayoritario: {dict(votos_por_equipo)}")
    print("=" * ancho + "\n")


if __name__ == "__main__":
    main()
