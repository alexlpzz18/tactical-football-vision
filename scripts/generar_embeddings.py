#!/usr/bin/env python
"""Genera el caché de embeddings de apariencia para un tramo. NECESITA GPU.

Se corre en Colab; en este Mac no hay GPU (ver CLAUDE.md). Produce un
fichero con la MISMA clave que el caché de colores —`(frame_idx,
det_idx)`— para que sea un consumidor más del mismo índice y no haya que
tocar el formato de las detecciones.

Aviso que ya costó una medición: `det_idx` es la POSICIÓN de la detección
dentro de su frame. Si se regenera el caché de detecciones, este caché
caduca entero. Por eso se guarda junto al embedding el nombre del caché
de origen y el del backbone: sin esos dos datos, un caché de embeddings
no se puede validar.

Uso (en Colab, con GPU):
    python scripts/generar_embeddings.py \\
        --cache data/tracking/cache_detecciones_v4.pkl \\
        --video data/raw/villaviciosa.mp4 \\
        --backbone timm/resnet50.a1_in1k \\
        --salida data/tracking/emb_villa_resnet50.pkl
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("embeddings")

# Los tres candidatos, todos Apache-2.0 (docs/licencias_apariencia.md).
BACKBONES = {
    "siglip": "google/siglip-base-patch16-224",
    "dinov2": "facebook/dinov2-base",
    "resnet50": "timm/resnet50.a1_in1k",
}
MARGEN = 0.15  # holgura del recorte; sin ella se cortan hombros y pies


def recortar(frame, caja, lado=224):
    """Recorte cuadrado del jugador, escalado al tamaño del backbone."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = caja
    dx, dy = (x2 - x1) * MARGEN, (y2 - y1) * MARGEN
    x1 = max(0, int(x1 - dx))
    y1 = max(0, int(y1 - dy))
    x2 = min(w, int(x2 + dx))
    y2 = min(h, int(y2 + dy))
    if x2 <= x1 or y2 <= y1:
        return None
    return cv2.resize(frame[y1:y2, x1:x2], (lado, lado), interpolation=cv2.INTER_CUBIC)


def iterar_recortes(ruta_video, cache):
    """(clave, alto_original_px, recorte) recorriendo el vídeo UNA vez.

    Se decodifica en orden y se sacan todos los recortes de cada frame de
    golpe. Saltar por el vídeo por cada detección multiplicaría el tiempo
    por cien, y además `cap.set` no es de fiar (ver posicionar_en_frame).
    """
    por_frame = {e["frame_idx"]: e["dets"] for e in cache}
    if not por_frame:
        return
    cap = cv2.VideoCapture(str(ruta_video))
    if not cap.isOpened():
        raise FileNotFoundError(f"No se puede abrir {ruta_video}")
    primero, ultimo = min(por_frame), max(por_frame)
    posicionar_en_frame(cap, primero)
    idx = primero
    while idx <= ultimo:
        ok, frame = cap.read()
        if not ok:
            break
        for i, det in enumerate(por_frame.get(idx, [])):
            caja = det[2:6]
            crop = recortar(frame, caja)
            if crop is not None:
                yield (idx, i), float(caja[3] - caja[1]), crop
        idx += 1
    cap.release()


def cargar_backbone(nombre, dispositivo):
    """Devuelve (funcion_de_embedding, dimensiones)."""
    import torch

    if nombre.startswith("timm/"):
        import timm

        modelo = timm.create_model(
            nombre.split("/", 1)[1], pretrained=True, num_classes=0
        )
        modelo.eval().to(dispositivo)
        cfg = timm.data.resolve_data_config({}, model=modelo)
        media = np.array(cfg["mean"], dtype=np.float32)
        desv = np.array(cfg["std"], dtype=np.float32)

        def embeber(lote):
            x = torch.from_numpy(lote).to(dispositivo)
            with torch.no_grad():
                return modelo(x).float().cpu().numpy()

        return embeber, media, desv, modelo.num_features

    from transformers import AutoModel

    modelo = AutoModel.from_pretrained(nombre).eval().to(dispositivo)
    if hasattr(modelo, "vision_model"):
        modelo = modelo.vision_model
    media = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    desv = np.array([0.5, 0.5, 0.5], dtype=np.float32)

    def embeber(lote):
        x = torch.from_numpy(lote).to(dispositivo)
        with torch.no_grad():
            salida = modelo(pixel_values=x)
        # pooler cuando existe; si no, media de los tokens
        v = getattr(salida, "pooler_output", None)
        if v is None:
            v = salida.last_hidden_state.mean(axis=1)
        return v.float().cpu().numpy()

    return embeber, media, desv, modelo.config.hidden_size


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--backbone", required=True, help="clave corta o id de HF")
    p.add_argument("--salida", required=True)
    p.add_argument("--lote", type=int, default=64)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    import torch

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    if dispositivo == "cpu":
        logger.warning("⚠ Sin GPU: esto va a tardar muchísimo (ver CLAUDE.md)")

    nombre = BACKBONES.get(args.backbone, args.backbone)
    embeber, media, desv, dims = cargar_backbone(nombre, dispositivo)
    logger.info("Backbone %s → %d dims, en %s", nombre, dims, dispositivo)

    claves, alturas, vectores = [], [], []
    lote_img, lote_claves, lote_alt = [], [], []

    def vaciar():
        if not lote_img:
            return
        x = np.stack(lote_img).astype(np.float32) / 255.0
        x = (x - media) / desv
        x = np.transpose(x, (0, 3, 1, 2))
        vectores.append(embeber(x).astype(np.float16))
        claves.extend(lote_claves)
        alturas.extend(lote_alt)
        lote_img.clear()
        lote_claves.clear()
        lote_alt.clear()

    for clave, alto, crop in iterar_recortes(
        args.video, cargar_cache(args.cache)["cache"]
    ):
        lote_img.append(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        lote_claves.append(clave)
        lote_alt.append(alto)
        if len(lote_img) >= args.lote:
            vaciar()
            if len(claves) % 2000 < args.lote:
                logger.info("  %d recortes embebidos...", len(claves))
    vaciar()

    matriz = np.concatenate(vectores) if vectores else np.zeros((0, dims), np.float16)
    datos = {
        "claves": claves,
        "embeddings": matriz,
        # La ALTURA en píxeles de cada caja: el benchmark se estratifica
        # por tamaño de recorte y sin esto habría que recalcularla.
        "alturas_px": np.array(alturas, dtype=np.float32),
        # Sin estos dos campos el caché no se puede validar más adelante.
        "backbone": nombre,
        "cache_origen": Path(args.cache).name,
        "dims": int(matriz.shape[1]) if len(matriz) else dims,
    }
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    with open(args.salida, "wb") as f:
        pickle.dump(datos, f, protocol=4)
    mb = Path(args.salida).stat().st_size / 1e6
    logger.info(
        "✓ %s — %d recortes × %d dims (%.1f MB)",
        args.salida,
        len(claves),
        datos["dims"],
        mb,
    )


if __name__ == "__main__":
    main()
