#!/usr/bin/env python
"""Cachés de balón de la parte entera a VARIOS umbrales en UNA pasada de GPU (Colab).

Para medir el COSTE de bajar la confianza del detector en el partido entero
(docs/colab_balon_umbral_bajo.md, celda 2), no solo el beneficio en 9 frames.

⚠️ Por qué no vale "detectar a 0,05 y quedarse con lo que pase de 0,35":

1. SAHI cambia SOLO el postproceso a NMS/IOU cuando la confianza del modelo
   es < 0,1 ("Switching postprocess type/metric to NMS/IOU since confidence is
   low"); producción usa GREEDYNMM/IOS.
2. Aun forzando GREEDYNMM, la fusión depende del umbral: una caja débil
   fusionada con una fuerte le AGRANDA la geometría (se queda la unión).
3. La deduplicación del esquema mixto (`_solapan`) tira una caja de la franja
   si se solapa con una del frame entero, aunque esa sea débil.

Así que se guarda lo de ANTES de cualquier fusión (frame entero a 0,05 y las
predicciones de la franja SIN postproceso, con un postproceso identidad
registrado en SAHI), y para CADA umbral de la rejilla se aplica la cadena de
producción tal cual: filtro de confianza → GREEDYNMM/IOS de SAHI (la misma
clase y los mismos defaults) → deduplicación del mixto → proyección. Inferir
una vez y fusionar siete veces.

CONTROL dentro de la pasada: en los primeros `--frames-control` frames se
corre además el camino de producción literal (`_detectar_con_esquema` a la
confianza del config) y se exige que salga idéntico al reconstruido a ese
umbral. Si no, el script PARA: la reconstrucción no sería producción.

Uso (Colab, desde la raíz del repo):
    python scripts/colab_cache_balon_umbrales.py \\
        --config configs/processor_benja_balon_parte_entera.yaml \\
        --salida /content/drive/MyDrive/tactical-football-vision-data/salidas/umbral_bajo
"""

import argparse
import logging
import os
import pickle
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

logger = logging.getLogger("cache_umbrales")

UMBRALES = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35)


def combinar_mixto(entero, franja_fusionada, solapan):
    """La deduplicación del esquema mixto, igual que `_detectar_con_esquema`.

    Primero todo el frame entero; una caja de la franja solo entra si no se
    solapa con ninguna de las que ya hay.
    """
    cajas = list(entero)
    for caja in franja_fusionada:
        if not any(solapan(caja[:4], c[:4]) for c in cajas):
            cajas.append(caja)
    return cajas


def _volcar(ruta: Path, objeto) -> None:
    """Escritura atómica: un corte a mitad no deja un pickle roto."""
    fd, tmp = tempfile.mkstemp(dir=str(ruta.parent), suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        pickle.dump(objeto, fh)
    os.replace(tmp, ruta)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config", default="configs/processor_benja_balon_parte_entera.yaml"
    )
    p.add_argument("--salida", required=True)
    p.add_argument("--frames-control", type=int, default=300)
    p.add_argument("--cada", type=int, default=500, help="checkpoint cada N frames")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    import sahi.predict as sp
    from sahi import AutoDetectionModel
    from sahi.postprocess.combine import GreedyNMMPostprocess
    from sahi.predict import get_sliced_prediction
    from ultralytics import YOLO

    from detectar_balon import (
        _detectar_con_esquema,
        _detectar_frame_entero,
        _esquema_de_config,
        _solapan,
        iter_frames,
        project_point,
    )
    from src.balon.franja_lejana import banda_a_trocear
    from src.tracking_data.processor import _rango_de_frames

    cfg = yaml.safe_load(open(args.config))
    cb = cfg["balon"]
    nombre, esquema = _esquema_de_config(cb)
    if nombre != "mixto":
        raise SystemExit(
            f"Esquema {nombre!r}: este script reproduce el 'mixto' de producción"
        )
    if esquema.get("postprocess_match_metric") or esquema.get(
        "postprocess_match_threshold"
    ):
        raise SystemExit(
            "El config fuerza un postproceso: aquí se reproducen los DEFAULTS"
        )
    conf_prod = float(cb["confianza"])
    if min(UMBRALES) > conf_prod or conf_prod not in UMBRALES:
        raise SystemExit(
            f"La confianza de producción ({conf_prod}) tiene que estar en la rejilla"
        )
    H = np.load(cfg["rutas"]["homografia"])

    # Postproceso IDENTIDAD: mismas rebanadas, misma inferencia, sin fusionar.
    class _SinFusion:
        def __init__(self, **_kw):
            pass

        def __call__(self, preds):
            return preds

    sp.POSTPROCESS_NAME_TO_CLASS["SIN_FUSION"] = _SinFusion
    # La fusión de producción: la MISMA clase y los mismos defaults de SAHI
    # (get_sliced_prediction: GREEDYNMM, IOS, 0,5, no agnóstica de clase).
    fusion = GreedyNMMPostprocess(
        match_threshold=0.5, match_metric="IOS", class_agnostic=False
    )

    cap = cv2.VideoCapture(cfg["rutas"]["video"])
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    y0, y1 = banda_a_trocear(
        H,
        float(cfg["campo_m"]["largo"]),
        float(cfg["campo_m"]["ancho"]),
        float(cb.get("zona_min_m", 45.0)),
        h,
        w,
        float(cb.get("margen_campo_m", 20.0)),
        float(cb.get("altura_aerea_m", 3.0)),
    )
    y0, y1 = max(0, y0), min(h, y1)
    logger.info("franja troceada y %d-%d", y0, y1)

    modelo = YOLO(cb["modelo"])

    def modelo_sahi(conf):
        return AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=cb["modelo"],
            confidence_threshold=conf,
            device=cfg["deteccion"]["device"],
        )

    sahi_bajo, sahi_prod = modelo_sahi(min(UMBRALES)), modelo_sahi(conf_prod)

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    ruta_ck = salida / "checkpoint_umbrales.pkl"
    caches = {u: [] for u in UMBRALES}
    hechos = set()
    if ruta_ck.exists():
        ck = pickle.load(open(ruta_ck, "rb"))
        caches, hechos = ck["caches"], set(ck["hechos"])
        logger.info("Reanudando: %d frames ya hechos", len(hechos))

    sample = int(cb["sample_every"])
    frame_ini, frame_fin = _rango_de_frames(cfg["muestreo"], fps)
    n_control = n = 0
    t0 = time.time()
    for frame_idx, frame in iter_frames(cap, frame_ini, frame_fin, sample, total):
        if frame_idx in hechos:
            continue
        entero = _detectar_frame_entero(modelo, frame, min(UMBRALES), cb["imgsz"])
        franja_img = frame[y0:y1]
        r = get_sliced_prediction(
            franja_img,
            sahi_bajo,
            slice_height=y1 - y0,  # filas=1, como `_detectar_con_esquema`
            slice_width=w // esquema["columnas"],
            overlap_height_ratio=esquema["solape"],
            overlap_width_ratio=esquema["solape"],
            postprocess_type="SIN_FUSION",
            force_postprocess_type=True,
            verbose=0,
        )
        crudas_franja = list(r.object_prediction_list)
        for u in UMBRALES:
            preds = [q for q in crudas_franja if q.score.value >= u]
            if len(preds) > 1:  # SAHI solo fusiona si hay más de una
                preds = fusion(preds)
            franja_u = [
                (
                    q.bbox.minx,
                    q.bbox.miny + y0,
                    q.bbox.maxx,
                    q.bbox.maxy + y0,
                    q.score.value,
                )
                for q in preds
            ]
            entero_u = [c for c in entero if c[4] >= u]
            dets = []
            for x1, yy1, x2, yy2, conf in combinar_mixto(entero_u, franja_u, _solapan):
                if conf < u:
                    continue
                mx, my = project_point((x1 + x2) / 2.0, yy2, H)
                dets.append((mx, my, x1, yy1, x2, yy2, conf))
            caches[u].append(
                {"frame_idx": frame_idx, "t": frame_idx / fps, "dets": dets}
            )

        # CONTROL: el camino de producción literal tiene que dar lo mismo.
        if n_control < args.frames_control:
            prod = _detectar_con_esquema(
                esquema, modelo, sahi_prod, frame, cb, w, h, (y0, y1)
            )
            prod = sorted(
                tuple(round(float(v), 2) for v in c) for c in prod if c[4] >= conf_prod
            )
            mio = sorted(
                tuple(round(float(v), 2) for v in d[2:])
                for d in caches[conf_prod][-1]["dets"]
            )
            if prod != mio:
                raise SystemExit(
                    f"CONTROL FALLA en el frame {frame_idx}:\n  producción {prod}\n"
                    f"  reconstruido {mio}\nLa reconstrucción NO es producción: no sigas."
                )
            n_control += 1
            if n_control == args.frames_control:
                logger.info("CONTROL OK: %d frames idénticos a producción", n_control)

        hechos.add(frame_idx)
        n += 1
        if args.cada and n % args.cada == 0:
            _volcar(ruta_ck, {"caches": caches, "hechos": sorted(hechos)})
            logger.info(
                "%d frames · %.1f min · checkpoint",
                len(hechos),
                (time.time() - t0) / 60,
            )

    for u in UMBRALES:
        datos = {
            "cache": sorted(caches[u], key=lambda e: e["frame_idx"]),
            "fps": fps,
            "sample": sample,
            "wh": (w, h),
            "umbral": u,
            "control_frames": n_control,
        }
        _volcar(salida / f"cache_balon_p1_conf{int(round(u * 100)):03d}.pkl", datos)
    logger.info(
        "✓ %d cachés (%s) en %s · control %d frames OK",
        len(UMBRALES),
        ", ".join(str(u) for u in UMBRALES),
        salida,
        n_control,
    )


if __name__ == "__main__":
    main()
