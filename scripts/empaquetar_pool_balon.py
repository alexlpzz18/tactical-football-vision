#!/usr/bin/env python
"""Empaqueta el pool del balón pegado al pie para entrenar en Colab (YOLO, JPEG alta calidad).

Solo train (102) y validación (15): **el test no entra**. Va aparte y se usa solo para
medir el criterio. Las etiquetas salen del export de CVAT (YOLO 1.1); una imagen sin caja
es un negativo (txt vacío). La repetición ×3 del pool NO se hace aquí, con copias que
triplicarían lo que se sube a Drive: la hace la celda de entrenamiento con enlaces
simbólicos (docs/colab_reentreno_balon.md).

Estructura del zip:
    images/{train,val}/fNNNNNN.jpg
    labels/{train,val}/fNNNNNN.txt

Uso:
    python scripts/empaquetar_pool_balon.py
"""

import argparse
import sys
import zipfile
from pathlib import Path

import cv2
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contar_etiquetado_pool import leer_export_yolo  # noqa: E402

CALIDAD_JPEG = 95


def empaquetar(
    pool: Path, train_zip: Path, salida: Path, calidad: int = CALIDAD_JPEG
) -> dict:
    manifiesto = pd.read_csv(pool / "manifiesto.csv")
    etiquetas = leer_export_yolo(train_zip)  # la tarea train de CVAT trae train + val
    cuenta = {"train": 0, "val": 0, "positivos": 0}
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_STORED) as z:  # JPEG ya va comprimido
        for r in manifiesto.itertuples():
            if r.split not in ("train", "val"):
                continue  # el TEST no entra en el paquete de entrenamiento
            nombre = f"f{int(r.frame):06d}"
            if nombre not in etiquetas:
                raise SystemExit(
                    f"{nombre} ({r.split}) no está en el export de CVAT: PARA"
                )
            img = cv2.imread(str(pool / "train" / "images" / f"{nombre}.png"))
            if img is None:
                raise SystemExit(f"no se pudo leer {nombre}.png")
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, calidad])
            z.writestr(f"images/{r.split}/{nombre}.jpg", buf.tobytes())
            cajas = etiquetas[nombre]
            z.writestr(
                f"labels/{r.split}/{nombre}.txt",
                "\n".join(cajas) + ("\n" if cajas else ""),
            )
            cuenta[r.split] += 1
            cuenta["positivos"] += int(bool(cajas))
    return cuenta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool", default="outputs/pool_balon_pegado")
    ap.add_argument(
        "--train-zip", default="outputs/pool_balon_pegado/etiquetado/train_yolo.zip"
    )
    ap.add_argument(
        "--salida", default="outputs/pool_balon_pegado/paquete_pool_yolo.zip"
    )
    a = ap.parse_args()
    c = empaquetar(Path(a.pool), Path(a.train_zip), Path(a.salida))
    mb = Path(a.salida).stat().st_size / 1e6
    print(
        f"✓ {a.salida}: {c['train']} train + {c['val']} val ({c['positivos']} con balón), "
        f"JPEG calidad {CALIDAD_JPEG} · {mb:.1f} MB"
    )


if __name__ == "__main__":
    main()
