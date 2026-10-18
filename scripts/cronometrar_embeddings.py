#!/usr/bin/env python
"""Cronometra el paso de embeddings. NECESITA GPU.

Es el pendiente que bloquea llevar el perfil del v4 a producción: todo lo
dicho hasta ahora sobre su coste son FLOPs estimados, no un cronómetro, y
sin el número real no se puede saber el margen.

Mide por separado lo que cuesta cada cosa, que es lo que permite decidir:

- **decodificar** el vídeo (coste fijo, se paga igual con o sin embeddings)
- **recortar** y preparar los tensores
- **inferir** el backbone

Uso (Colab con GPU):
    python scripts/cronometrar_embeddings.py \\
        --config configs/processor_benja_emb.yaml --video /content/benja.mp4
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

logger = logging.getLogger("crono")
MINUTOS_PARTIDO = 90.0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--backbone", default="google/siglip-base-patch16-224")
    p.add_argument("--lote", type=int, default=64)
    p.add_argument("--max-recortes", type=int, default=4000)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    import torch
    from transformers import AutoModel

    cfg = yaml.safe_load(open(args.config))
    datos = cargar_cache(cfg["rutas"]["cache"])
    cache = datos["cache"]
    por_frame = {e["frame_idx"]: e["dets"] for e in cache}
    frames = sorted(por_frame)

    modelo = AutoModel.from_pretrained(args.backbone).eval().cuda()
    if hasattr(modelo, "vision_model"):
        modelo = modelo.vision_model

    cap = cv2.VideoCapture(args.video)
    posicionar_en_frame(cap, frames[0])
    t_dec = t_rec = t_inf = 0.0
    lote, n = [], 0
    idx = frames[0]

    def vaciar():
        nonlocal t_inf, lote
        if not lote:
            return
        x = np.stack(lote).astype(np.float32) / 255.0
        x = np.transpose((x - 0.5) / 0.5, (0, 3, 1, 2))
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            modelo(pixel_values=torch.from_numpy(x).cuda())
        torch.cuda.synchronize()
        t_inf += time.perf_counter() - t0
        lote = []

    while n < args.max_recortes and idx <= frames[-1]:
        t0 = time.perf_counter()
        ok, fr = cap.read()
        t_dec += time.perf_counter() - t0
        if not ok:
            break
        for d in por_frame.get(idx, []):
            t0 = time.perf_counter()
            x1, y1, x2, y2 = (int(v) for v in d[2:6])
            ya, xa = max(0, y1), max(0, x1)
            crop = fr[ya:y2, xa:x2]
            if crop.size:
                lote.append(
                    cv2.cvtColor(cv2.resize(crop, (224, 224)), cv2.COLOR_BGR2RGB)
                )
                n += 1
            t_rec += time.perf_counter() - t0
            if len(lote) >= args.lote:
                vaciar()
        idx += 1
    vaciar()
    cap.release()

    n_frames = idx - frames[0]
    fps = datos["fps"]
    seg_tramo = n_frames / fps
    escala = MINUTOS_PARTIDO * 60 / max(seg_tramo, 1e-9)

    print(f"\n{n} recortes de {n_frames} fotogramas ({seg_tramo:.1f} s de vídeo)\n")
    cab = f"{'paso':<28}{'segundos':>10}{'ms/recorte':>13}{'min por partido':>18}"
    print(cab)
    print("-" * len(cab))
    for nombre, t in (
        ("decodificar (coste fijo)", t_dec),
        ("recortar + preparar", t_rec),
        (f"inferir {args.backbone.split('/')[-1]}", t_inf),
    ):
        print(f"{nombre:<28}{t:>10.1f}{1000*t/max(n,1):>13.2f}" f"{t*escala/60:>18.1f}")
    print("-" * len(cab))
    total = t_dec + t_rec + t_inf
    print(
        f"{'TOTAL':<28}{total:>10.1f}{1000*total/max(n,1):>13.2f}{total*escala/60:>18.1f}"
    )
    print(
        f"\n  El embedding AÑADE {(t_rec+t_inf)*escala/60:.1f} min por partido\n"
        f"  sobre los {t_dec*escala/60:.1f} min de decodificación, que se pagan igual."
    )


if __name__ == "__main__":
    main()
