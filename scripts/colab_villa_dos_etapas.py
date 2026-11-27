#!/usr/bin/env python
"""CELDA DE COLAB: re-detección del alevín A («Villaviciosa», 60 s) con detecciones DÉBILES aparte.

Opción 1 del embudo lejano (`docs/plan_opcion1_dos_etapas.md`). **No se ejecuta en el Mac** (GPU).
Es el modo full de producción (`detectar_y_cachear` con `configs/processor.yaml`, tramo 5:00-6:00,
1 de cada 3) con UN cambio, envolviendo la llamada a SAHI:

- SAHI corre con umbral 0,10 y SIN fusionar (predicciones crudas);
- las de conf ≥ 0,30 se fusionan EXACTAMENTE como en producción (GREEDYNMM, IOS 0,5): ese
  subconjunto tiene que reproducir el caché de producción (control en el Mac);
- las de 0,10-0,30 que no solapan (IOS < 0,5) con ninguna de las fuertes se fusionan entre sí y se
  AÑADEN. Llevan su confianza en el caché, así que el tracker las distingue.

Todo lo demás (lente, metros, feature de color, checkpoint, formato del caché) es el código de
producción. Interfaz de `scripts/gpu_colab.py`: `--fase deteccion --salida --videos --nombres`.

    !git fetch -q && git checkout -q alevinb-preparacion \\
        && pip install -q -r requirements-colab.txt \\
        && python scripts/colab_villa_dos_etapas.py --salida /content/villa_dos_etapas \\
           --videos /content/datos/partido.mp4 --nombres villa_conf010
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
BASE = R / "configs/processor.yaml"
CONF_FUERTE, CONF_DEBIL, IOS = 0.30, 0.10, 0.5


def ios(a, b) -> float:
    iw = max(0.0, min(a.maxx, b.maxx) - max(a.minx, b.minx))
    ih = max(0.0, min(a.maxy, b.maxy) - max(a.miny, b.miny))
    menor = min(
        (a.maxx - a.minx) * (a.maxy - a.miny), (b.maxx - b.minx) * (b.maxy - b.miny)
    )
    return iw * ih / max(menor, 1e-9)


def envolver_sahi() -> None:
    """Sustituye `sahi.predict.get_sliced_prediction` por la versión de dos etapas."""
    import sahi.predict
    from sahi.postprocess.combine import GreedyNMMPostprocess

    original = sahi.predict.get_sliced_prediction
    fusionar = GreedyNMMPostprocess(
        match_threshold=IOS, match_metric="IOS", class_agnostic=True
    )

    class Resultado:
        def __init__(self, preds):
            self.object_prediction_list = preds

    def dos_etapas(imagen, modelo, **kw):
        # crudas: NMS con umbral > 1 no suprime nada (y a 0,10 SAHI no cambia el postproceso)
        crudas = original(
            imagen,
            modelo,
            postprocess_type="NMS",
            postprocess_match_metric="IOU",
            postprocess_match_threshold=1.01,
            **kw,
        ).object_prediction_list
        fuertes = fusionar([p for p in crudas if p.score.value >= CONF_FUERTE])
        debiles = [
            p
            for p in crudas
            if CONF_DEBIL <= p.score.value < CONF_FUERTE
            and all(ios(p.bbox, f.bbox) < IOS for f in fuertes)
        ]
        return Resultado(list(fuertes) + list(fusionar(debiles)))

    sahi.predict.get_sliced_prediction = dos_etapas


def config(salida: Path, nombre: str, video: Path, dispositivo) -> dict:
    cfg = yaml.safe_load(open(BASE))
    cfg["modo"] = "full"
    cfg["deteccion"][
        "confianza"
    ] = CONF_DEBIL  # el filtro de producción deja pasar las débiles
    cfg["deteccion"]["modelo"] = str(R / "models/weights/best_v4pre.pt")
    if dispositivo:
        cfg["deteccion"]["device"] = dispositivo
    cfg["muestreo"]["tramo"] = {
        "min_ini": 5.0,
        "dur_seg": 60.0,
    }  # frames 7500-8999, como el caché
    cfg["muestreo"]["max_frames"] = None
    cfg["rutas"].update(
        video=str(video),
        cache=str(salida / f"cache_{nombre}.pkl"),
        cache_colores=str(salida / f"colores_{nombre}.pkl"),
        homografia=str(R / "data/calibracion/homografia.npy"),
    )
    return cfg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--fase", choices=["deteccion"], default="deteccion")
    ap.add_argument("--videos", required=True)
    ap.add_argument("--nombres", default="villa_conf010")
    ap.add_argument(
        "--sin-chequeo", action="store_true"
    )  # interfaz del orquestador; no se usa
    ap.add_argument("--dispositivo", default=None)
    a = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    a.salida.mkdir(parents=True, exist_ok=True)
    envolver_sahi()
    from src.tracking_data.processor import detectar_y_cachear

    for nombre, video in zip(a.nombres.split(","), a.videos.split(",")):
        t0 = time.time()
        detectar_y_cachear(config(a.salida, nombre, Path(video), a.dispositivo))
        print(
            f"✓ deteccion {nombre}: {round((time.time() - t0) / 60, 1)} min", flush=True
        )


if __name__ == "__main__":
    main()
