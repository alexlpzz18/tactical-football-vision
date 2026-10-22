#!/usr/bin/env python
"""Caché de color «v3» (máscara por posición) para cualquier partido, desde su caché de detección.

SIN detector: las cajas son las de la caché de producción. Se relee el vídeo con el ffmpeg de línea
de comandos y, con el MISMO recorte y la MISMA corrección de distorsión que el modo `full`
(`processor.py`), se calcula:
- la v1 de siempre (CONTROL: tiene que reproducir la caché de producción);
- la v3: la misma feature con `rango_cesped` del frame (`mascara_posicion.rango_cesped_del_frame`).

Nació en el diagnóstico 22-oct (b), bloque 3 (benjamín); el 22-oct (d), bloque 2, lo generalizó por
config para Villaviciosa (`scripts/colab_v3_villa.py`).

Uso:
    python scripts/diag22b_feature_v3.py --salida outputs/diagnostico_22oct_b
    python scripts/diag22b_feature_v3.py --config configs/processor.yaml --salida DIR
    python scripts/diag22b_feature_v3.py --salida DIR --max-frames 100   # prueba rápida
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG_BENJA = R / "configs/processor_benja_parte_entera.yaml"


def _ruta(p) -> Path:
    p = Path(p)
    return p if p.is_absolute() else R / p


def calcular_v1_v3(config: Path, max_frames: int | None = None) -> tuple[dict, dict]:
    """(caché v3 {(frame, k): feature}, control de la v1 contra la caché de producción)."""
    import yaml

    from src.team_classification.color_classifier import extraer_color_torso
    from src.team_classification.mascara_posicion import rango_cesped_del_frame
    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import (
        _build_camera_matrix,
        _corregir_distorsion,
        project_point,
    )
    from src.utils.video_ffmpeg import leer_frames_ffmpeg, tamano_video

    cfg = yaml.safe_load(open(config))
    H = np.load(_ruta(cfg["rutas"]["homografia"]))
    dims = (cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"])
    cache = cargar_cache(_ruta(cfg["rutas"]["cache"]))["cache"]
    if max_frames:
        cache = cache[:max_frames]
    prod = pickle.load(open(_ruta(cfg["rutas"]["cache_colores"]), "rb"))
    video = _ruta(cfg["rutas"]["video"])
    # La MISMA corrección de distorsión que el modo `full` (en el benjamín k1=k2=0 y es la
    # identidad; en Villaviciosa no).
    w, h = tamano_video(video)
    K = _build_camera_matrix(w, h)
    dist_lente = np.array(
        [cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], dtype=np.float64
    )

    dets_de = {e["frame_idx"]: e["dets"] for e in cache}
    v3, difs, sin_rango, n = {}, [], 0, 0
    # ⚠️ ffmpeg CLI, NO cv2.VideoCapture: en macOS OpenCV decodifica con AVFoundation y no
    # reproduce la caché (0,27 % de features idénticas; con ffmpeg, el 100 %).
    for f, frame in leer_frames_ffmpeg(video, dets_de):
        frame = _corregir_distorsion(frame, K, dist_lente)
        dets = dets_de[f]
        rango = rango_cesped_del_frame(
            frame, [d[2:6] for d in dets], lambda u, v: project_point(u, v, H), dims
        )
        sin_rango += rango is None
        for k, d in enumerate(dets):
            x1, y1, x2, y2 = (int(v) for v in d[2:6])
            y1, x1 = max(y1, 0), max(x1, 0)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            n += 1
            f1 = extraer_color_torso(crop)
            if (f, k) in prod:
                difs.append(float(np.linalg.norm(f1 - prod[(f, k)])))
            f3 = (
                extraer_color_torso(crop, rango_cesped=rango)
                if rango is not None
                else f1
            )
            if f3.sum() > 0:
                v3[(f, k)] = f3
    difs = np.array(difs)
    control = {
        "config": str(config),
        "cajas": n,
        "comparadas_con_produccion": int(len(difs)),
        "frac_identicas_1e-6": float((difs < 1e-6).mean()) if len(difs) else None,
        "dif_p99": float(np.percentile(difs, 99)) if len(difs) else None,
        "frames_sin_rango_de_cesped": int(sin_rango),
        "frames": len(cache),
    }
    return v3, control


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--config", default=str(CONFIG_BENJA))
    ap.add_argument("--max-frames", type=int, default=None)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    v3, control = calcular_v1_v3(Path(args.config), args.max_frames)
    pickle.dump(v3, open(salida / "cache_colores_v3.pkl", "wb"))
    (salida / "feature_v3_control.json").write_text(json.dumps(control, indent=1))
    print(json.dumps(control, indent=1))


if __name__ == "__main__":
    main()
