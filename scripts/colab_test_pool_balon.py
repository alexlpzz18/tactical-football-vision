#!/usr/bin/env python
"""Medida A del reentreno: v1 contra el candidato sobre el TEST del pool (Colab, GPU).

docs/plan_reentreno_balon.md, "Cómo medir". Las MISMAS condiciones para los dos modelos:
la detección de producción (`detectar_balon._detectar_con_esquema`, esquema mixto, la
franja derivada de la homografía) a la confianza del config (0,35), sobre los 36 frames
de test, sacados del vídeo con `posicionar_en_frame()` y avanzando con `grab()`.

Un ACIERTO es una detección cuyo centro cae a ≤ max(8 px, diagonal de la caja etiquetada)
del centro de la caja de Alex (la más cercana, si hay varias). Cualquier otra detección es
un falso positivo; en una imagen sin balón, todas.

No juzga: guarda los recuentos en un JSON y el veredicto lo da
`scripts/medir_reentreno_balon.py` (el criterio está escrito allí, una sola vez).

Uso (Colab, raíz del repo, modelos enlazados en models/weights/):
    python scripts/colab_test_pool_balon.py \\
        --test-zip "$D/pool_balon/test_yolo.zip" --manifiesto "$D/pool_balon/manifiesto.csv" \\
        --salida "$D/salidas/reentreno_balon/medida_A.json"
"""

import argparse
import json
import logging
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

RADIO_MIN_PX = 8.0
MODELOS = {
    "v1": "models/weights/best_balon_v1.pt",
    "v2": "models/weights/best_balon_v2_pegado.pt",
}


def leer_etiquetas_test(test_zip) -> dict[str, list[tuple]]:
    """{fNNNNNN: [(cx, cy, w, h) normalizados]} del export YOLO 1.1 de la tarea test."""
    salida = {}
    with zipfile.ZipFile(test_zip) as z:
        for nombre in z.namelist():
            if nombre.startswith("obj_train_data/") and nombre.endswith(".txt"):
                filas = [
                    ln.split()
                    for ln in z.read(nombre).decode().splitlines()
                    if ln.strip()
                ]
                salida[Path(nombre).stem] = [tuple(map(float, f[1:5])) for f in filas]
    return salida


def evaluar_imagen(dets, cajas_gt, ancho: int, alto: int) -> tuple[int, int]:
    """(aciertos, falsos positivos) de una imagen. dets: [(x1, y1, x2, y2, conf)]."""
    centros = [((d[0] + d[2]) / 2, (d[1] + d[3]) / 2) for d in dets]
    usadas, aciertos = set(), 0
    for cx, cy, w, h in cajas_gt:
        gx, gy = cx * ancho, cy * alto
        radio = max(RADIO_MIN_PX, float(np.hypot(w * ancho, h * alto)))
        libres = [
            (np.hypot(x - gx, y - gy), i)
            for i, (x, y) in enumerate(centros)
            if i not in usadas
        ]
        cerca = [li for li in libres if li[0] <= radio]
        if cerca:
            usadas.add(min(cerca)[1])
            aciertos += 1
    return aciertos, len(dets) - len(usadas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config", default="configs/processor_benja_balon_parte_entera.yaml"
    )
    ap.add_argument("--test-zip", required=True)
    ap.add_argument("--manifiesto", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    import cv2
    from detectar_balon import _detectar_con_esquema, _esquema_de_config
    from sahi import AutoDetectionModel
    from src.balon.franja_lejana import banda_a_trocear
    from src.tracking_data.processor import posicionar_en_frame
    from ultralytics import YOLO

    cfg = yaml.safe_load(open(args.config))
    cb = cfg["balon"]
    H = np.load(cfg["rutas"]["homografia"])
    m = pd.read_csv(args.manifiesto)
    test = m[m.split == "test"].sort_values("frame")
    etiquetas = leer_etiquetas_test(args.test_zip)
    faltan = [f for f in test.frame if f"f{int(f):06d}" not in etiquetas]
    if faltan:
        raise SystemExit(f"frames de test sin etiqueta en el export: {faltan}. PARA")

    # Los 36 frames, en orden: posicionar_en_frame para el primero y grab() para avanzar.
    cap = cv2.VideoCapture(cfg["rutas"]["video"])
    ancho, alto = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )
    frames, pos = {}, None
    for f in test.frame.astype(int):
        if pos is None or f - pos > 300:
            pos = posicionar_en_frame(cap, f)
        while pos < f:
            cap.grab()
            pos += 1
        ok, img = cap.read()
        pos += 1
        if not ok:
            raise SystemExit(f"no se pudo leer el frame {f}")
        frames[f] = img
    cap.release()

    nombre_esq, esquema = _esquema_de_config(cb)
    banda = banda_a_trocear(
        H, float(cfg["campo_m"]["largo"]), float(cfg["campo_m"]["ancho"]),
        float(cb.get("zona_min_m", 45.0)), alto, ancho,
        float(cb.get("margen_campo_m", 20.0)), float(cb.get("altura_aerea_m", 3.0)),
    )  # fmt: skip
    resultado = {"esquema": nombre_esq, "confianza": cb["confianza"], "banda": banda,
                 "radio_min_px": RADIO_MIN_PX, "por_frame": {}}  # fmt: skip
    for clave, ruta in MODELOS.items():
        if not Path(ruta).exists():
            raise SystemExit(f"no existe {ruta}: enlázalo en models/weights/. PARA")
        modelo = YOLO(ruta)
        modelo_sahi = AutoDetectionModel.from_pretrained(
            model_type="ultralytics", model_path=ruta,
            confidence_threshold=cb["confianza"], device=cfg["deteccion"]["device"],
        )  # fmt: skip
        for f, img in frames.items():
            crudas = _detectar_con_esquema(
                esquema, modelo, modelo_sahi, img, cb, ancho, alto, banda
            )
            dets = [
                d for d in crudas if d[4] >= cb["confianza"]
            ]  # lo mismo que guarda el caché
            gt = etiquetas[f"f{f:06d}"]
            ac, fp = evaluar_imagen(dets, gt, ancho, alto)
            fila = resultado["por_frame"].setdefault(str(f), {"positivo": bool(gt)})
            fila[clave] = {
                "aciertos": ac,
                "fp": fp,
                "dets": [list(map(float, d)) for d in dets],
            }
        n_ac = sum(v[clave]["aciertos"] for v in resultado["por_frame"].values())
        n_fp = sum(v[clave]["fp"] for v in resultado["por_frame"].values())
        print(
            f"{clave}: {n_ac} aciertos, {n_fp} falsos positivos en {len(frames)} imágenes"
        )
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(json.dumps(resultado, indent=1))
    print(
        f"✓ {args.salida} (el veredicto, con scripts/medir_reentreno_balon.py en el Mac)"
    )


if __name__ == "__main__":
    main()
