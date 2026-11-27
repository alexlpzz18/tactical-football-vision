#!/usr/bin/env python
"""Etapa E1 del embudo del tercio lejano: ¿las personas que el caché no tiene salen en SAHI con
umbral bajo, o antes de la fusión GREEDYNMM?

Para cada persona del GT del alevín A que `embudo_tercio_lejano.py` marcó como `E1_detector` en el
tercio lejano, se repite la detección de producción (best_v4pre, lente corregida, SAHI 2×4 con
solape 0,2 + imagen entera) con umbral 0,05 y se guardan las predicciones ANTES y DESPUÉS de la
fusión (GREEDYNMM, IOS 0,5). Cada persona se clasifica en la primera etapa en la que aparece:
  - «fusion»: hay una predicción con conf ≥ 0,3 antes de fusionar que la fusión se come;
  - «umbral_0.2» / «umbral_0.1» / «umbral_0.05»: solo aparece con conf por debajo de 0,3;
  - «area»: aparece pero el filtro de área la quita (no debería en jugadores lejanos);
  - «no_sale»: no sale ni con 0,05.
El casado con la caja del GT es el mismo del embudo (centro dentro de la caja ±20 %, 1-a-1).

⚠️ En CPU la detección reproduce el 83 % de las cajas de producción (`lit_franjas_lejanas.py`): las
cifras son una DIRECCIÓN, no un número exacto. Se informa también del control: de las personas que
el caché SÍ tiene, cuántas reproduce esta pasada a conf ≥ 0,3 después de fusionar.

Uso:
    ~/.venvs/detector-cpu/bin/python scripts/embudo_detector_lejano.py \\
        --salida outputs/embudo_tercio_lejano
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

from embudo_tercio_lejano import GT, OFFSET, PASO, casar_cajas  # noqa: E402
from src.utils.video_ffmpeg import leer_frames_ffmpeg  # noqa: E402

VIDEO = R / "data/raw/partido.mp4"
MODELO = R / "models/weights/best_v4pre.pt"
K1, K2, CONF_PROD, MAX_AREA = -1.5, 0.5, 0.3, 0.05


def predicciones(img, modelo):
    """(antes, después) de la fusión: listas de (x1, y1, x2, y2, conf, area_ok)."""
    from sahi.postprocess.combine import GreedyNMMPostprocess
    from sahi.predict import get_sliced_prediction

    h, w = img.shape[:2]
    res = get_sliced_prediction(
        img,
        modelo,
        slice_height=h // 2,
        slice_width=w // 4,
        overlap_height_ratio=0.2,
        overlap_width_ratio=0.2,
        postprocess_type="NMM",
        postprocess_match_threshold=1.01,  # no fusiona nada: así salen las crudas
        verbose=0,
    )
    crudas = list(res.object_prediction_list)
    fusion = GreedyNMMPostprocess(
        match_threshold=0.5, match_metric="IOS", class_agnostic=True
    )(crudas)

    def a_tupla(ps):
        out = []
        for p in ps:
            b = p.bbox
            area_ok = (b.maxx - b.minx) * (b.maxy - b.miny) <= MAX_AREA * w * h
            out.append((b.minx, b.miny, b.maxx, b.maxy, p.score.value, area_ok))
        return out

    return a_tupla(crudas), a_tupla(fusion)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--dispositivo", default="cpu")
    a = ap.parse_args()
    from sahi import AutoDetectionModel

    from src.evaluation.desglose_error import EQUIPOS, equipo_de_etiqueta
    from src.evaluation.gt_parser import parsear_cvat

    emb = pd.read_csv(a.salida / "embudo.csv")
    lejos = emb[emb.tercio == 2]
    frames = sorted(set(lejos[lejos.etapa == "E1_detector"].frame))
    gt = {}
    for tr in parsear_cvat(GT):
        for c in tr.cajas:
            if equipo_de_etiqueta(c.team if c.team is not None else tr.team) in EQUIPOS:
                gt.setdefault(OFFSET + PASO * c.frame_local, []).append(
                    (c.xtl, c.ytl, c.xbr, c.ybr)
                )
    modelo = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(MODELO),
        confidence_threshold=0.05,
        device=a.dispositivo,
    )
    w, h = 2560, 1064
    Kc = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    dist = np.array([K1, K2, 0, 0, 0], dtype=np.float64)
    clases, control = Counter(), Counter()
    guardadas = {}
    t0 = time.time()
    for f, img in leer_frames_ffmpeg(VIDEO, frames):
        img = cv2.undistort(img, Kc, dist)
        crudas, fusion = predicciones(img, modelo)
        guardadas[f] = (crudas, fusion)
        g = np.array(gt[f], float)
        # orden del GT de este frame = el del embudo (mismo parser, mismo orden)
        etapas = emb[emb.frame == f].reset_index(drop=True)
        assert len(etapas) == len(g), f"frame {f}: el orden del GT no coincide"

        def casa(lista, conf_min, con_area=True):
            sel = [p for p in lista if p[4] >= conf_min and (p[5] or not con_area)]
            dd = np.array([p[:4] for p in sel], float).reshape(-1, 4)
            return casar_cajas(g, dd)

        prod = casa(fusion, CONF_PROD)
        for i, r in etapas.iterrows():
            if r.tercio != 2:
                continue
            if r.etapa != "E1_detector":
                control["cache_si"] += 1
                control["reproducida"] += i in prod
                continue
            if i in prod:
                clases["sale_en_cpu_y_no_en_cache"] += 1
            elif i in casa(crudas, CONF_PROD):
                clases["fusion"] += 1
            elif i in casa(fusion, CONF_PROD, con_area=False):
                clases["area"] += 1
            elif i in casa(fusion, 0.2) or i in casa(crudas, 0.2):
                clases["umbral_0.2"] += 1
            elif i in casa(fusion, 0.1) or i in casa(crudas, 0.1):
                clases["umbral_0.1"] += 1
            elif i in casa(crudas, 0.05):
                clases["umbral_0.05"] += 1
            else:
                clases["no_sale"] += 1
        print(f"frame {f} · {time.time() - t0:.0f} s · {dict(clases)}", flush=True)
    n = sum(clases.values())
    res = {
        "personas_E1_lejanas": n,
        "clases": dict(clases),
        "clases_pct": {k: round(100 * v / n, 1) for k, v in clases.items()},
        "control_reproducidas_pct": round(
            100 * control["reproducida"] / max(control["cache_si"], 1), 1
        ),
    }
    print(json.dumps(res, indent=1, ensure_ascii=False))
    import pickle

    # las predicciones (crudas y fusionadas) para medir falsos positivos por umbral sin repetir SAHI
    pickle.dump(guardadas, open(a.salida / "predicciones_lejano.pkl", "wb"))
    (a.salida / "detector_lejano.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
