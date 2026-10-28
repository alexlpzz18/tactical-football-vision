#!/usr/bin/env python
"""Diagnóstico 28-oct (c), punto 3a: ¿la caja fundida existe ya en el detector o la crea la fusión?

Vuelve a detectar en CPU (venv con numpy 1.26: torch no arranca con numpy 2 en el Mac) unos frames
concretos, con el detector de producción (`best_v4pre.pt`) y dos postprocesos de SAHI:
- PRODUCCIÓN: el de por defecto de sahi 0.12.1 (GREEDYNMM, IOS, 0,5), el que usa `processor.py`;
- SIN FUSIÓN: NMS por IoU con umbral 0,99 (solo junta duplicados casi exactos).

Control: con el de producción, las cajas tienen que reproducir las del caché (≥ 95 % casadas a
IoU ≥ 0,9). Correr con el python del venv:

    VENV/bin/python scripts/diag28c_caja_fundida.py --salida outputs/diagnostico_28oct_c
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
MODELO = R / "models/weights/best_v4pre.pt"
FPS = 29.97002997002997
# frames donde las dos personas del cruce comparten UNA detección del caché (14:40, 14:44, 15:06)
FRAMES = {
    "14:40 (A683 tras B708)": [26376, 26382],
    "14:44 (B708 tras A683)": [26487, 26490],
    "15:06 (A708 con B525)": [27150, 27156],
}
POSTPROCESOS = {
    "produccion": dict(
        postprocess_type="GREEDYNMM",
        postprocess_match_metric="IOS",
        postprocess_match_threshold=0.5,
    ),
    "sin_fusion": dict(
        postprocess_type="NMS",
        postprocess_match_metric="IOU",
        postprocess_match_threshold=0.99,
    ),
}


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def main() -> None:
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(CONFIG))
    det = cfg["deteccion"]
    modelo = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(MODELO),
        confidence_threshold=det["confianza"],
        device="cpu",
    )
    cache = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(open(R / cfg["rutas"]["cache"], "rb"))["cache"]
    }
    todos = sorted(f for fs in FRAMES.values() for f in fs)
    res = {"frames": {}}
    for f, img in leer_frames_ffmpeg(R / cfg["rutas"]["video"], todos):
        h, w = img.shape[:2]
        salidas = {}
        for nombre, pp in POSTPROCESOS.items():
            r = get_sliced_prediction(
                img,
                modelo,
                slice_height=h // det["sahi"]["filas"],
                slice_width=w // det["sahi"]["columnas"],
                overlap_height_ratio=det["sahi"]["solape"],
                overlap_width_ratio=det["sahi"]["solape"],
                verbose=0,
                **pp,
            )
            cajas = []
            for p in r.object_prediction_list:
                b = p.bbox
                if p.score.value < det["confianza"]:
                    continue
                if (b.maxx - b.minx) * (b.maxy - b.miny) > det["max_area_caja"] * w * h:
                    continue
                cajas.append([b.minx, b.miny, b.maxx, b.maxy, float(p.score.value)])
            salidas[nombre] = cajas
        # control: producción en CPU contra el caché
        cach = [list(d[2:7]) for d in cache[f]]
        casadas = sum(
            any(iou(c, p) >= 0.9 for p in salidas["produccion"]) for c in cach
        )
        res["frames"][f] = {
            "cajas_cache": len(cach),
            "cajas_cpu_produccion": len(salidas["produccion"]),
            "cajas_cpu_sin_fusion": len(salidas["sin_fusion"]),
            "cache_casadas_con_cpu_produccion": f"{casadas}/{len(cach)}",
            "cajas": salidas,
        }
        print(
            f,
            res["frames"][f]["cache_casadas_con_cpu_produccion"],
            len(salidas["produccion"]),
            len(salidas["sin_fusion"]),
            flush=True,
        )
    (salida / "caja_fundida_cajas.json").write_text(json.dumps(res, indent=1))
    pickle.dump(res, open(salida / "caja_fundida.pkl", "wb"))


if __name__ == "__main__":
    main()
