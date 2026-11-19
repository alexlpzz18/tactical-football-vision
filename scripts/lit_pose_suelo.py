#!/usr/bin/env python
"""Método 3 de docs/plan_literatura.md: puntos clave de cada detección con RTMPose.

Corre RTMPose-m (rtmlib + onnxruntime; código Apache-2.0) sobre cada caja del caché, en el
fotograma tal como lo vio el detector (con la lente corregida si la pata la corrige). Guarda los 17
puntos COCO (x, y en píxeles de ese fotograma, y su confianza) por detección. El punto de suelo y su
evaluación se calculan después, en el entorno del proyecto (`scripts/lit_evaluar_pose.py`).

⚠️ Pesos: los de rtmlib por defecto están entrenados en «body7» (siete conjuntos públicos de pose).
Para COMPARAR vale; para el producto habría que revisar las licencias de esos conjuntos o usar un
modelo entrenado solo en COCO.

Necesita onnxruntime: se corre con `~/.venvs/detector-cpu` (CPU para ventanas de 60 s; un partido
entero, mejor en GPU con `--dispositivo cuda` y onnxruntime-gpu).

Uso:
    ~/.venvs/detector-cpu/bin/python scripts/lit_pose_suelo.py \\
        --cache data/tracking/cache_detecciones_v4pre.pkl --video data/raw/partido.mp4 \\
        --k1 -1.5 --k2 0.5 --salida outputs/literatura/pose/villa.npz
"""

import argparse
import pickle
import sys
import time
from pathlib import Path

import cv2
import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.utils.video_ffmpeg import leer_frames_ffmpeg  # noqa: E402

MODELO = (
    "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
    "rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.zip"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--k1", type=float, default=0.0)
    ap.add_argument("--k2", type=float, default=0.0)
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--dispositivo", default="cpu")
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    from rtmlib import RTMPose

    pose = RTMPose(MODELO, model_input_size=(192, 256), device=a.dispositivo)
    datos = pickle.load(open(a.cache, "rb"))
    cache = datos["cache"]
    if a.max_frames:
        cache = cache[: a.max_frames]
    por_frame = {e["frame_idx"]: e for e in cache}
    w, h = datos["wh"]
    K = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    dist = np.array([a.k1, a.k2, 0, 0, 0], dtype=np.float64)
    claves, puntos = [], []
    t0 = time.time()
    for n, (f, img) in enumerate(leer_frames_ffmpeg(a.video, sorted(por_frame))):
        if a.k1 or a.k2:
            img = cv2.undistort(img, K, dist)
        dets = [(j, d) for j, d in enumerate(por_frame[f]["dets"]) if d[6] >= a.conf]
        if not dets:
            continue
        kps, scores = pose(img, bboxes=[list(map(float, d[2:6])) for _j, d in dets])
        for (j, _d), k, s in zip(dets, kps, scores):
            claves.append((f, j))
            puntos.append(np.column_stack([k, s]).astype(np.float32))
        if n % 100 == 0:
            print(f"{n}/{len(por_frame)} frames · {time.time() - t0:.0f} s", flush=True)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        a.salida,
        claves=np.array(claves),
        puntos=np.array(puntos),
        modelo=MODELO,
        cache=str(a.cache),
    )
    print(f"✓ {a.salida}: {len(claves)} detecciones, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
