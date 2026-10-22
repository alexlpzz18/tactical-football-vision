#!/usr/bin/env python
"""Diagnóstico 22-oct (b), bloque 3: caché de color «v3» (máscara por posición) del benjamín.

SIN detector: las cajas son las de la caché de producción. Se relee el vídeo y, con el MISMO recorte
que el modo `full` (`processor.py`), se calcula:
- la v1 de siempre (CONTROL: tiene que reproducir la caché de producción);
- la v3: la misma feature con `rango_cesped` del frame (`mascara_posicion.rango_cesped_del_frame`).

Uso:
    python scripts/diag22b_feature_v3.py --salida outputs/diagnostico_22oct_b
"""

import argparse
import json
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))


def main() -> None:
    import yaml

    from src.team_classification.color_classifier import extraer_color_torso
    from src.team_classification.mascara_posicion import rango_cesped_del_frame
    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import project_point

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
    H = np.load(R / cfg["rutas"]["homografia"])
    dims = (cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"])
    cache = cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    prod = pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))

    v3, difs, sin_rango, n = {}, [], 0, 0
    # ⚠️ El vídeo se decodifica con FFMPEG (como en Colab), NO con cv2.VideoCapture: en
    # macOS OpenCV usa AVFoundation y da píxeles distintos (el control no reproducía la
    # caché: mediana 0,23 de distancia). Con ffmpeg sale idéntico (comprobado en 2 frames).
    w, h = 1920, 1080
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(R / cfg["rutas"]["video"]),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-",
        ],
        stdout=subprocess.PIPE,
    )
    actual = 0
    for e in cache:
        f = e["frame_idx"]
        while actual < f:
            proc.stdout.read(w * h * 3)
            actual += 1
        buf = proc.stdout.read(w * h * 3)
        actual += 1
        if len(buf) < w * h * 3:
            raise RuntimeError(f"no se pudo leer el frame {f}")
        frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3).copy()
        dets = e["dets"]
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
    proc.stdout.close()
    proc.kill()
    difs = np.array(difs)
    control = {
        "cajas": n,
        "comparadas_con_produccion": int(len(difs)),
        "frac_identicas_1e-6": float((difs < 1e-6).mean()),
        "dif_p99": float(np.percentile(difs, 99)),
        "frames_sin_rango_de_cesped": int(sin_rango),
        "frames": len(cache),
    }
    pickle.dump(v3, open(salida / "cache_colores_v3.pkl", "wb"))
    (salida / "feature_v3_control.json").write_text(json.dumps(control, indent=1))
    print(json.dumps(control, indent=1))


if __name__ == "__main__":
    main()
