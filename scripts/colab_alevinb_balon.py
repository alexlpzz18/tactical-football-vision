#!/usr/bin/env python
"""Caché de BALÓN del Alevín B en GPU (Colab), con la misma interfaz que `colab_alevinb.py`.

docs/alevinb_balon.md. Lo lanza `scripts/gpu_colab.py lanzar alevinb_balon`; envuelve a
`scripts/detectar_balon.py` (el de producción, con su checkpoint y su firma) con un config propio.

Decisiones, cada una con su razón:
- **Imagen ORIGINAL** (como los jugadores, decisión de Alex del 5-nov): sin corregir la lente y con
  homografía identidad, así que (mx, my) del caché quedan en PÍXELES del original. Los metros se
  ponen después en el Mac con la lente (`camara_alevinb.npz`), igual que con los jugadores.
- **Esquema `sahi` 3×5 sobre toda la imagen**, no el `mixto` de producción: el mixto trocea una
  franja que se deriva de la homografía, y aquí no hay homografía. Y en esta cámara el balón mide
  2-4 px en casi todo el campo (calculado con la lente), justo donde SAHI es el único que puede.
  Prueba en CPU sobre 30 fotogramas: SAHI con candidatas en 11, frame entero en 4.
- **1 de cada 2 fotogramas** (`sample_every: 2`), el muestreo del balón en producción.

Interfaz (la que espera el orquestador):
    python scripts/colab_alevinb_balon.py --imagen original --fase deteccion \\
        --salida /content/salida --videos /content/datos/alevinb_p1_balon.mp4 \\
        --nombres alevinb_p1_balon
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
BASE = R / "configs/processor_alevinb.yaml"
BALON = R / "configs/balon_alevinb.yaml"


def config(
    salida: Path, nombre: str, video: Path, dispositivo: str | None, max_frames=None
) -> Path:
    cfg = yaml.safe_load(open(BASE))
    cfg["balon"] = yaml.safe_load(open(BALON))["balon"]
    cfg["modo"] = "full"
    cfg["muestreo"]["tramo"] = None
    cfg["muestreo"]["max_frames"] = max_frames
    cfg["checkpoint"] = {"cada_frames": 500, "reanudar": True}
    if dispositivo:
        cfg["deteccion"]["device"] = dispositivo
    # imagen original: sin corregir el fotograma y con homografía identidad (metros en el Mac)
    cfg["distorsion"] = {"k1": 0.0, "k2": 0.0}
    identidad = salida / "homografia_identidad.npy"
    np.save(identidad, np.eye(3))
    cfg["rutas"].update(
        video=str(video),
        homografia=str(identidad),
        cache_balon=str(salida / f"cache_{nombre}.pkl"),
    )
    ruta = salida / f"config_{nombre}.yaml"
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    return ruta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--imagen", choices=["original"], required=True)
    ap.add_argument("--fase", choices=["deteccion"], default="deteccion")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--videos", required=True)
    ap.add_argument("--nombres", required=True)
    ap.add_argument(
        "--sin-chequeo", action="store_true"
    )  # interfaz común; aquí no hay chequeo
    # solo para probar en local; en Colab no se pasan
    ap.add_argument("--dispositivo", default=None)
    ap.add_argument("--max-frames", type=int, default=None)
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    for nombre, video in zip(a.nombres.split(","), a.videos.split(",")):
        t0 = time.time()
        ruta = config(a.salida, nombre, Path(video), a.dispositivo, a.max_frames)
        subprocess.run(
            [
                sys.executable,
                str(R / "scripts/detectar_balon.py"),
                "--config",
                str(ruta),
            ],
            check=True,
            cwd=R,
        )
        print(
            f"✓ deteccion {nombre}: {round((time.time() - t0) / 60, 1)} min", flush=True
        )


if __name__ == "__main__":
    main()
