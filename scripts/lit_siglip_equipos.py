#!/usr/bin/env python
"""Método 5 de docs/plan_literatura.md: equipos con SigLIP → UMAP 3D → K-means de 2 grupos.

Es el método de `roboflow/sports` (MIT), con dos cambios dichos: el recorte es el CENTRO del
jugador (torso: 15-60 % del alto y 20-80 % del ancho de la caja), y se ajusta solo con detecciones
dentro del campo (lo aprendido el 12-nov: banquillos y público hacían un tercer grupo).

Necesita torch y transformers: se corre con el entorno del detector (`~/.venvs/detector-cpu`, numpy
1.26), no con el del proyecto. Para ventanas de 60 s basta la CPU; para un partido entero, GPU
(`--dispositivo cuda`, misma interfaz).

Salida (`--salida`, un .npz): las claves (frame, det) de las detecciones etiquetadas, el embedding
SigLIP, la etiqueta 0/1 del K-means y si se usó para ajustar. La evaluación contra el GT se hace
después en el entorno del proyecto (`scripts/lit_evaluar_equipos.py`).

Uso:
    ~/.venvs/detector-cpu/bin/python scripts/lit_siglip_equipos.py \\
        --cache data/tracking/cache_detecciones_v4pre.pkl --video data/raw/partido.mp4 \\
        --k1 -1.5 --k2 0.5 --largo 105 --ancho 68 --salida outputs/literatura/siglip_villa.npz
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

MODELO = "google/siglip-base-patch16-224"  # Apache-2.0
TORSO_ALTO = (0.15, 0.60)
TORSO_ANCHO = (0.20, 0.80)


def recorte_torso(frame: np.ndarray, caja) -> np.ndarray | None:
    x1, y1, x2, y2 = [float(v) for v in caja]
    w, h = x2 - x1, y2 - y1
    a, b = int(x1 + TORSO_ANCHO[0] * w), int(y1 + TORSO_ALTO[0] * h)
    c, d = int(np.ceil(x1 + TORSO_ANCHO[1] * w)), int(np.ceil(y1 + TORSO_ALTO[1] * h))
    a, b = max(a, 0), max(b, 0)
    c, d = min(c, frame.shape[1]), min(d, frame.shape[0])
    if c - a < 2 or d - b < 2:
        return None
    return cv2.cvtColor(frame[b:d, a:c], cv2.COLOR_BGR2RGB)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--k1", type=float, default=0.0)
    ap.add_argument("--k2", type=float, default=0.0)
    ap.add_argument("--largo", type=float, required=True)
    ap.add_argument("--ancho", type=float, required=True)
    ap.add_argument("--desde-s", type=float, default=None)
    ap.add_argument("--hasta-s", type=float, default=None)
    ap.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="como mucho tantos frames, repartidos",
    )
    ap.add_argument(
        "--extra", type=Path, default=None, help="CSV frame,x1,y1,x2,y2 a incluir"
    )
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--dispositivo", default="cpu")
    ap.add_argument("--lote", type=int, default=64)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()

    import torch
    import umap
    from sklearn.cluster import KMeans
    from transformers import AutoImageProcessor, SiglipVisionModel

    datos = pickle.load(open(a.cache, "rb"))
    cache = [
        e
        for e in datos["cache"]
        if (a.desde_s is None or e["t"] >= a.desde_s)
        and (a.hasta_s is None or e["t"] <= a.hasta_s)
    ]
    extra = {}
    if a.extra:
        import csv

        for fila in csv.DictReader(open(a.extra)):
            extra.setdefault(int(fila["frame"]), []).append(
                tuple(float(fila[k]) for k in ("x1", "y1", "x2", "y2"))
            )
    if a.max_frames and len(cache) > a.max_frames:
        idx = np.linspace(0, len(cache) - 1, a.max_frames).round().astype(int)
        elegidos = {cache[i]["frame_idx"] for i in idx} | set(extra)
        cache = [e for e in cache if e["frame_idx"] in elegidos]
    por_frame = {e["frame_idx"]: e for e in cache}

    proc = AutoImageProcessor.from_pretrained(MODELO)
    modelo = SiglipVisionModel.from_pretrained(MODELO).eval().to(a.dispositivo)
    w, h = datos["wh"]
    K = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    dist = np.array([a.k1, a.k2, 0, 0, 0], dtype=np.float64)

    claves, dentro, vectores, lote, lote_claves = [], [], [], [], []

    def vaciar():
        if not lote:
            return
        with torch.no_grad():
            x = proc(images=lote, return_tensors="pt")["pixel_values"].to(a.dispositivo)
            v = modelo(pixel_values=x).pooler_output.float().cpu().numpy()
        vectores.append(v / np.linalg.norm(v, axis=1, keepdims=True))
        claves.extend(lote_claves)
        lote.clear()
        lote_claves.clear()

    t0 = time.time()
    for n, (f, img) in enumerate(leer_frames_ffmpeg(a.video, sorted(por_frame))):
        if a.k1 or a.k2:
            img = cv2.undistort(img, K, dist)
        for j, d in enumerate(por_frame[f]["dets"]):
            if d[6] < a.conf:
                continue
            crop = recorte_torso(img, d[2:6])
            if crop is None:
                continue
            lote.append(crop)
            lote_claves.append((f, j))
            dentro.append(bool(0 <= d[0] <= a.largo and 0 <= d[1] <= a.ancho))
            if len(lote) >= a.lote:
                vaciar()
        if n % 100 == 0:
            print(f"{n}/{len(por_frame)} frames · {time.time() - t0:.0f} s", flush=True)
    vaciar()
    emb = np.concatenate(vectores)
    dentro = np.array(dentro)
    # UMAP 3D + K-means de 2, ajustados con lo de DENTRO del campo y aplicados a todo
    red = umap.UMAP(n_components=3, random_state=a.semilla).fit(emb[dentro])
    km = KMeans(n_clusters=2, n_init=10, random_state=a.semilla).fit(red.embedding_)
    etiquetas = km.predict(red.transform(emb))
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        a.salida,
        claves=np.array(claves),
        etiqueta=etiquetas,
        dentro=dentro,
        embedding=emb.astype(np.float16),
        modelo=MODELO,
        cache=str(a.cache),
    )
    print(
        f"✓ {a.salida}: {len(claves)} recortes, grupos {np.bincount(etiquetas).tolist()}, "
        f"{time.time() - t0:.0f} s"
    )


if __name__ == "__main__":
    main()
