#!/usr/bin/env python
"""Embeddings DINOv2 de CADA detección de producción, para clasificar equipos. NECESITA GPU.

docs/plan_equipos_embeddings.md. Lo lanza `scripts/gpu_colab.py lanzar embeddings_equipos`, con la
misma interfaz que las demás celdas (`--fase deteccion --salida --videos --nombres`).

Qué cambia respecto a `generar_embeddings.py` (el de la asociación), y por qué:
- el recorte sale del fotograma TAL CUAL lo vio el detector: corregido con la lente si esa pata la
  corrige (Villaviciosa), original si no (benjamín, alevín B). Si no, la caja no cae sobre la
  persona;
- la normalización es la del PROPIO modelo (DINOv2 usa la de ImageNet; la de 0,5 de aquel script es
  la de SigLIP);
- semiprecisión en la GPU y lotes grandes: medio millón de recortes del alevín B;
- la salida va en el formato que vigila el orquestador (`cache` con los frames hechos y `completo`),
  con el nombre del caché de detecciones de origen (las claves `(frame, det)` caducan si cambia).

Para cada `--nombres X` lee `<salida>/det_X.pkl` (el caché de detecciones de producción, subido por
el orquestador) y escribe `<salida>/cache_X.pkl`.
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

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

logger = logging.getLogger("emb_equipos")
MODELO = "facebook/dinov2-base"  # Apache-2.0 (docs/licencias_apariencia.md)
LADO = 224
MARGEN = 0.15  # holgura del recorte, la de generar_embeddings.py
LOTE = 256
CHECKPOINT_FRAMES = 2000
# Lente de cada pata, la de su config de producción (configs/processor*.yaml)
DISTORSION = {"benja": (0.0, 0.0), "villa": (-1.5, 0.5), "alevinb": (0.0, 0.0)}


def distorsion_de(nombre: str) -> tuple[float, float]:
    for clave, k in DISTORSION.items():
        if clave in nombre:
            return k
    raise SystemExit(f"No sé qué lente tiene «{nombre}»: añádela a DISTORSION")


def recortar(frame, caja):
    """Recorte cuadrado con holgura, escalado al lado del modelo (RGB)."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = caja
    dx, dy = (x2 - x1) * MARGEN, (y2 - y1) * MARGEN
    x1, y1 = max(0, int(x1 - dx)), max(0, int(y1 - dy))
    x2, y2 = min(w, int(x2 + dx)), min(h, int(y2 + dy))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = cv2.resize(frame[y1:y2, x1:x2], (LADO, LADO), interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)


def _volcar(ruta: Path, datos: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(ruta.parent), suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        pickle.dump(datos, f, protocol=4)
    os.replace(tmp, ruta)


def embeber_pata(nombre: str, video: Path, salida: Path, dispositivo: str) -> None:
    import torch
    from transformers import AutoImageProcessor, AutoModel

    from src.tracking_data.processor import (
        _build_camera_matrix,
        _corregir_distorsion,
        posicionar_en_frame,
    )

    det = pickle.load(open(salida / f"det_{nombre}.pkl", "rb"))
    por_frame = {e["frame_idx"]: e["dets"] for e in det["cache"]}
    proc = AutoImageProcessor.from_pretrained(MODELO)
    media = np.array(proc.image_mean, np.float32)
    desv = np.array(proc.image_std, np.float32)
    modelo = AutoModel.from_pretrained(MODELO).eval().to(dispositivo)
    if dispositivo == "cuda":
        modelo = modelo.half()

    claves, vectores, hechos = [], [], []
    lote_img, lote_claves = [], []
    destino = salida / f"cache_{nombre}.pkl"

    def vaciar():
        if not lote_img:
            return
        x = (np.stack(lote_img).astype(np.float32) / 255.0 - media) / desv
        x = torch.from_numpy(np.transpose(x, (0, 3, 1, 2))).to(dispositivo)
        if dispositivo == "cuda":
            x = x.half()
        with torch.no_grad():
            out = modelo(pixel_values=x)
        v = (
            out.pooler_output
            if out.pooler_output is not None
            else out.last_hidden_state[:, 0]
        )
        vectores.append(v.float().cpu().numpy().astype(np.float16))
        claves.extend(lote_claves)
        lote_img.clear()
        lote_claves.clear()

    def guardar(completo: bool):
        vaciar()
        _volcar(
            destino,
            {
                "cache": [
                    {"frame_idx": f} for f in hechos
                ],  # lo que lee el orquestador
                "claves": list(claves),
                "embeddings": (
                    np.concatenate(vectores) if vectores else np.zeros((0, 768))
                ),
                "backbone": MODELO,
                "cache_origen": det.get("origen", f"det_{nombre}.pkl"),
                "completo": completo,
            },
        )

    cap = cv2.VideoCapture(str(video))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )
    K = _build_camera_matrix(w, h)
    k1, k2 = distorsion_de(nombre)
    dist = np.array([k1, k2, 0, 0, 0], np.float64)
    primero, ultimo = min(por_frame), max(por_frame)
    posicionar_en_frame(cap, primero)
    idx, t0 = primero, time.time()
    while idx <= ultimo:
        ok, frame = cap.read()
        if not ok:
            break
        if idx in por_frame:
            frame = _corregir_distorsion(frame, K, dist)
            for i, d in enumerate(por_frame[idx]):
                crop = recortar(frame, d[2:6])
                if crop is not None:
                    lote_img.append(crop)
                    lote_claves.append((idx, i))
                    if len(lote_img) >= LOTE:
                        vaciar()
            hechos.append(idx)
            if len(hechos) % CHECKPOINT_FRAMES == 0:
                guardar(False)
                logger.info(
                    "%s: %d/%d frames · %.0f ms/frame",
                    nombre, len(hechos), len(por_frame),
                    1000 * (time.time() - t0) / len(hechos),
                )  # fmt: skip
        idx += 1
    cap.release()
    guardar(True)
    logger.info("✓ %s: %d recortes embebidos", nombre, len(claves))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--imagen", default="original"
    )  # interfaz común; la lente va por pata
    ap.add_argument("--fase", choices=["deteccion"], default="deteccion")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--videos", required=True)
    ap.add_argument("--nombres", required=True)
    ap.add_argument("--sin-chequeo", action="store_true")
    ap.add_argument("--dispositivo", default=None)
    a = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    import torch

    dispositivo = a.dispositivo or ("cuda" if torch.cuda.is_available() else "cpu")
    for nombre, video in zip(a.nombres.split(","), a.videos.split(",")):
        t0 = time.time()
        embeber_pata(nombre, Path(video), a.salida, dispositivo)
        print(
            f"✓ deteccion {nombre}: {round((time.time() - t0) / 60, 1)} min", flush=True
        )


if __name__ == "__main__":
    main()
