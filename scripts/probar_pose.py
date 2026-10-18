#!/usr/bin/env python
"""¿Detecta RTMPose los tobillos en NUESTROS recortes? NECESITA GPU.

El anclaje por pose promete bajar el error de profundidad de ~58 cm
(caja) a ~11 cm (media de tobillos). El riesgo que hay que medir ANTES de
integrarlo es concreto: la pose se estima sobre el recorte, y en la banda
lejana el recorte mide 13-20 px. Puede fallar justo donde más falta hace.

Este script no integra nada: solo responde **en qué porcentaje encuentra
tobillos, por franja de tamaño y de profundidad**, y cuánto tarda.

Aviso de licencia (regla de Alex: nada AGPL, nada NC):
- `rtmlib` es **Apache-2.0** y no arrastra mmcv/mmpose.
- Pero **la licencia de los PESOS no está declarada** y salen de "7
  datasets" sin especificar. Vale para EXPERIMENTAR y decidir si el
  enfoque funciona; **antes de producción hay que resolverlo o
  reentrenar**.

Uso (Colab con GPU):
    python scripts/probar_pose.py --config configs/processor_benja_emb.yaml \\
        --video /content/benja.mp4 --max-recortes 3000
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("pose")

# COCO-17: 15 = tobillo izquierdo, 16 = tobillo derecho
TOBILLO_IZQ, TOBILLO_DER = 15, 16
FRANJAS_PX = [
    ("<20 px", 0, 20),
    ("20-30 px", 20, 30),
    ("30-45 px", 30, 45),
    (">45 px", 45, 1e9),
]
FRANJAS_M = [("10-20 m", 10, 20), ("20-30 m", 20, 30), ("30+ m", 30, 1e9)]
MARGEN = 0.15


def franja(v, franjas):
    for nombre, lo, hi in franjas:
        if lo <= v < hi:
            return nombre
    return franjas[-1][0]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--max-recortes", type=int, default=3000)
    p.add_argument("--umbral-kp", type=float, default=0.3)
    p.add_argument("--lote", type=int, default=32)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from rtmlib import RTMPose

    cfg = yaml.safe_load(open(args.config))
    datos = cargar_cache(cfg["rutas"]["cache"])
    cache = datos["cache"]

    modelo = RTMPose(
        onnx_model="https://download.openmmlab.com/mmpose/v1/projects/"
        "rtmposev1/onnx_sdk/rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.zip",
        model_input_size=(192, 256),
        backend="onnxruntime",
        device="cuda",
    )
    logger.info("RTMPose cargado (rtmpose-m, body7, 256x192)")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"No se puede abrir {args.video}")
    frames = sorted(e["frame_idx"] for e in cache)
    posicionar_en_frame(cap, frames[0])
    por_frame = {e["frame_idx"]: e["dets"] for e in cache}

    resultados = []
    t_pose = 0.0
    idx, hechos = frames[0], 0
    while hechos < args.max_recortes and idx <= frames[-1]:
        ok, fr = cap.read()
        if not ok:
            break
        dets = por_frame.get(idx, [])
        if dets:
            cajas, metas = [], []
            for d in dets:
                x1, y1, x2, y2 = d[2:6]
                dx, dy = (x2 - x1) * MARGEN, (y2 - y1) * MARGEN
                cajas.append([x1 - dx, y1 - dy, x2 + dx, y2 + dy])
                metas.append({"alto": y2 - y1, "y_m": d[1], "pie_caja": y2})
            t0 = time.perf_counter()
            kps, scores = modelo(fr, bboxes=np.array(cajas))
            t_pose += time.perf_counter() - t0
            for k, s, m in zip(kps, scores, metas):
                ok_i = float(s[TOBILLO_IZQ]) >= args.umbral_kp
                ok_d = float(s[TOBILLO_DER]) >= args.umbral_kp
                pie_pose = None
                if ok_i or ok_d:
                    ys = [
                        k[j][1]
                        for j, o in ((TOBILLO_IZQ, ok_i), (TOBILLO_DER, ok_d))
                        if o
                    ]
                    pie_pose = float(np.mean(ys))
                resultados.append(
                    {
                        **m,
                        "ok": ok_i or ok_d,
                        "los_dos": ok_i and ok_d,
                        "pie_pose": pie_pose,
                    }
                )
                hechos += 1
        idx += 1
    cap.release()

    import pandas as pd

    r = pd.DataFrame(resultados)
    print(f"\n{len(r)} recortes evaluados · umbral de keypoint {args.umbral_kp}\n")
    for nombre, franjas, col in (
        ("POR TAMAÑO DEL RECORTE", FRANJAS_PX, "alto"),
        ("POR PROFUNDIDAD", FRANJAS_M, "y_m"),
    ):
        print(f"── {nombre} ──")
        cab = (
            f"{'franja':<12}{'n':>7}{'≥1 tobillo':>13}{'los dos':>10}{'desfase px':>13}"
        )
        print(cab)
        print("-" * len(cab))
        r["_f"] = r[col].map(lambda v: franja(v, franjas))
        for f_nombre, _lo, _hi in franjas:
            s = r[r._f == f_nombre]
            if not len(s):
                continue
            con = s[s.pie_pose.notna()]
            desf = (con.pie_pose - con.pie_caja).median() if len(con) else float("nan")
            print(
                f"{f_nombre:<12}{len(s):>7}{s.ok.mean():>12.0%}{s.los_dos.mean():>10.0%}"
                + (f"{desf:>13.1f}" if desf == desf else f"{'—':>13}")
            )
        print()

    print(
        f"⏱  POSE: {t_pose:.1f} s para {len(r)} recortes "
        f"= {1000*t_pose/max(len(r),1):.2f} ms/recorte"
    )
    n_partido = 903600
    print(
        f"   extrapolado a un partido de 90 min ({n_partido:,} recortes): "
        f"{t_pose/max(len(r),1)*n_partido/60:.0f} min de GPU"
    )
    print(
        "\n'desfase px' = cuánto más ABAJO cae el tobillo que el borde de la\n"
        "caja. Si es positivo y consistente, confirma que la caja se queda\n"
        "corta y que el anclaje por pose tiene algo que corregir."
    )


if __name__ == "__main__":
    main()
