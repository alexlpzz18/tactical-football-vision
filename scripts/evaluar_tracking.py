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

from src.evaluation.adaptador import (  # noqa: E402
    identidades_a_por_frame,
    trayectorias_a_por_frame,
)
from src.evaluation.alineacion import (  # noqa: E402
    distancia_media_gt_cache,
    frames_comunes,
)
from src.evaluation.asociacion import UmbralProfundidad  # noqa: E402
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
from src.tracking.interpolacion import interpolar_identidades  # noqa: E402
from src.tracking.stitcher import (  # noqa: E402
    ParametrosCosido,
    TrackletStitcher,
    filtrar_identidades_cortas,
    fusionar_identidad,
)

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
    parser.add_argument(
        "--interpolar",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forzar interpolación de huecos on/off (por defecto: lo que diga la config)",
    )
    parser.add_argument(
        "--rescatar-cortos",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forzar rescate de tracklets cortos on/off (por defecto: config)",
    )
    parser.add_argument(
        "--segunda-pasada",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forzar segunda pasada de cosido on/off (por defecto: config)",
    )
    parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Usar el caché de colores si existe (--no-color: solo movimiento)",
    )
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
    # Tarea 3b: con rescate de cortos, la Etapa A no filtra (min_frames=1)
    # y el filtro de calidad se aplica tras el cosido, a nivel de identidad.
    cfg_rescate = cfg_tracking.get("rescate_cortos", {})
    rescatar = (
        args.rescatar_cortos
        if args.rescatar_cortos is not None
        else cfg_rescate.get("activo", False)
    )
    params_etapa_a = dict(cfg_tracking["etapa_a"])
    if rescatar:
        params_etapa_a["min_frames"] = 1
    tracker = ConservativeTracker(ParametrosEtapaA.desde_dict(params_etapa_a))
    tracklets = tracker.procesar(datos["cache"], datos["fps"], datos["sample"])

    if args.color:
        color_medio = cargar_colores_opcional(
            Path(cfg["rutas"]["cache_colores"]), tracklets
        )
    else:
        logger.info("Color desactivado por --no-color: cosido solo por movimiento.")
        color_medio = None
    stitcher = TrackletStitcher(ParametrosCosido.desde_dict(cfg_tracking["cosido"]))
    identidades = stitcher.coser(tracklets, color_medio)
    if rescatar:
        identidades = filtrar_identidades_cortas(
            identidades, cfg_rescate["min_frames_identidad"]
        )

    # Tarea 3c: segunda pasada de cosido sobre identidades fusionadas
    cfg_p2 = cfg_tracking.get("segunda_pasada", {})
    segunda = (
        args.segunda_pasada
        if args.segunda_pasada is not None
        else cfg_p2.get("activa", False)
    )
    if segunda:
        params_p2 = {k: v for k, v in cfg_p2.items() if k != "activa"}
        stitcher_p2 = TrackletStitcher(ParametrosCosido.desde_dict(params_p2))
        super_tracklets = [fusionar_identidad(ident) for ident in identidades]
        identidades = stitcher_p2.coser(super_tracklets)

    # Tarea 3a: interpolación de huecos dentro de identidades (opcional)
    cfg_interp = cfg_tracking.get("interpolacion", {})
    interpolar = (
        args.interpolar
        if args.interpolar is not None
        else cfg_interp.get("activa", False)
    )
    if interpolar:
        frames_ts = [(e["frame_idx"], e["t"]) for e in datos["cache"]]
        trayectorias = interpolar_identidades(
            identidades, frames_ts, cfg_interp["max_hueco"]
        )
        pred = trayectorias_a_por_frame(trayectorias)
    else:
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
    # Umbral OFICIAL: dependiente de la profundidad. El fijo se mantiene
    # como referencia comparable con evaluaciones antiguas.
    umbral_fijo = cfg["asociacion"]["umbral_metros"]
    umbral_prof = UmbralProfundidad.desde_dict(cfg["asociacion"]["umbral_profundidad"])
    propias_prof = calcular_metricas_tracking(gt, pred, comunes, umbral_prof)
    propias_fijo = calcular_metricas_tracking(gt, pred, comunes, umbral_fijo)
    equipos = accuracy_equipos(gt, pred, comunes, umbral_prof)

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
    print(f"Interpolación de huecos: {'ACTIVA' if interpolar else 'off'}")
    print(f"Rescate de tracklets cortos: {'ACTIVO' if rescatar else 'off'}")
    print(f"Segunda pasada de cosido: {'ACTIVA' if segunda else 'off'}")
    print(f"Identidades GT: {len(tracks_gt)} (22 players + 1 referee)")
    print(
        f"Sanidad alineación: dist. media GT→det más cercana = {dist_alineacion:.2f} m"
    )
    print("-" * ancho)
    print(
        "MÉTRICAS PROPIAS — umbral por PROFUNDIDAD (OFICIAL): "
        f"clip({umbral_prof.base} + {umbral_prof.por_metro}·my, "
        f"{umbral_prof.minimo}, {umbral_prof.maximo}) m"
    )
    print(
        f"  IDF1:            {propias_prof.idf1:.3f}   (IDTP={propias_prof.idtp}, "
        f"IDFP={propias_prof.idfp}, IDFN={propias_prof.idfn})"
    )
    print(f"  ID switches:     {propias_prof.id_switches}")
    print(f"  Fragmentaciones: {propias_prof.fragmentaciones}")
    print(
        f"  Recall/frame:    {propias_prof.recall:.3f}   ({propias_prof.n_gt} obs GT)"
    )
    print(
        f"  Precision/frame: {propias_prof.precision:.3f}   "
        f"({propias_prof.n_pred} obs pred)"
    )
    print("-" * ancho)
    print(f"MÉTRICAS PROPIAS — umbral FIJO {umbral_fijo:.1f} m (referencia)")
    print(f"  IDF1:            {propias_fijo.idf1:.3f}")
    print(f"  ID switches:     {propias_fijo.id_switches}")
    print(f"  Fragmentaciones: {propias_fijo.fragmentaciones}")
    print(f"  Recall/frame:    {propias_fijo.recall:.3f}")
    print(f"  Precision/frame: {propias_fijo.precision:.3f}")
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
