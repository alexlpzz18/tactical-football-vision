#!/usr/bin/env python
"""CELDA DE COLAB: detección completa del Alevín B, una pasada por parte, con chequeo previo.

docs/alevinb_preparacion.md. **No se ejecuta en el Mac** (GPU). El vídeo entero no cabe en Drive: se
trabaja con las partes cortadas (`scripts/cortar_partido.py`) en `data/raw/alevinb_p1.mp4` y `_p2`.
La celda de siempre (CLAUDE.md, «Receta de Colab»):

    !git fetch -q && git checkout -q <rama> && pip install -q -r requirements-colab.txt && \\
        python scripts/colab_alevinb.py --imagen <corregida|original> --salida /content/alevinb

`--imagen` es OBLIGATORIO porque es una decisión de Alex: la lente nueva NO está adoptada.
- `corregida`: como producción hoy. Corrige el fotograma y usa la homografía de Villaviciosa. Lo que
  queda a más de ~840 px del centro (las esquinas cercanas) no se ve.
- `original`: detecta sobre el fotograma sin corregir (mismo recall, docs/lente_f11.md) y lleva cada
  pie a metros con la lente nueva (`camara_alevinb.npz`). Ve todo el campo, pero su error en las
  marcas no cumple el criterio y el color sobre el original no está medido.

Pasos:
0. Antes de gastar GPU: existen las partes y la calibración; 2560×1064 a 25 fps.
1. CHEQUEO PREVIO de 3 frames con el MISMO bucle que el modo full, leyendo la caché DEL DISCO: 3
   frames, 10-40 detecciones con el pie DENTRO del campo por frame y vector de color en ≥ 90 % de
   las detecciones (en producción faltan unos pocos: recortes en el borde). Si falla, se para aquí.
2. Una pasada por parte (los lados y el fit de color son POR PASADA): detección, conversión a metros
   si toca, y `desde_cache`. El checkpoint permite relanzar si Colab se cae.
"""

import argparse
import importlib.util
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
BASE = R / "configs/processor_alevinb.yaml"
CAMARA = R / "data/calibracion_alevinb/camara_alevinb.npz"
RESOLUCION = (2560, 1064)
FPS = 25.0
DETECCIONES_EN_CAMPO = (10, 40)
FRAMES_CHEQUEO = 9  # originales: 3 procesados con sample_every 3
MIN_COLORES = 0.90
FUERA = -1000.0  # un pie que la lente no sabe convertir queda lejos del campo


def _lente():
    spec = importlib.util.spec_from_file_location("lc", R / "scripts/lente_camara.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def config(
    salida: Path, nombre: str, video: Path, imagen: str, dispositivo, max_frames=None
) -> Path:
    cfg = yaml.safe_load(open(BASE))
    cfg["modo"] = "full"
    cfg["muestreo"]["tramo"] = None
    cfg["muestreo"]["max_frames"] = max_frames
    if max_frames is not None:
        cfg["checkpoint"] = {"cada_frames": 0, "reanudar": False}
    if dispositivo:
        cfg["deteccion"]["device"] = dispositivo
    if imagen == "original":
        # sin corregir el fotograma; los metros los pone `a_metros_con_lente` después
        cfg["distorsion"] = {"k1": 0.0, "k2": 0.0}
        identidad = salida / "homografia_identidad.npy"
        np.save(identidad, np.eye(3))
        cfg["rutas"]["homografia"] = str(identidad)
    cfg["rutas"].update(
        video=str(video),
        cache=str(salida / f"cache_{nombre}.pkl"),
        cache_colores=str(salida / f"colores_{nombre}.pkl"),
        salida_csv=str(salida / f"posiciones_{nombre}.csv"),
        salida_meta=str(salida / f"posiciones_{nombre}_meta.json"),
    )
    ruta = salida / f"config_{nombre}.yaml"
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    return ruta


def a_metros_con_lente(ruta_cache: Path) -> None:
    """Reescribe (mx, my) de cada detección: pie en el ORIGINAL → metros con la lente nueva."""
    lc = _lente()
    cam = lc.cargar_camara(CAMARA)
    datos = pickle.load(open(ruta_cache, "rb"))
    for e in datos["cache"]:
        if not e["dets"]:
            continue
        pies = np.array([[(d[2] + d[4]) / 2, d[5]] for d in e["dets"]], float)
        m = cam.pixel_a_metros(pies)
        e["dets"] = [
            (*(xy if np.isfinite(xy).all() else (FUERA, FUERA)), *d[2:])
            for d, xy in zip(e["dets"], m.tolist())
        ]
    pickle.dump(datos, open(ruta_cache, "wb"))


def comprobar_entradas(videos: list[Path], imagen: str) -> None:
    faltan = [str(p) for p in videos if not p.exists()]
    if imagen == "original" and not CAMARA.exists():
        faltan.append(str(CAMARA))
    if faltan:
        raise SystemExit(
            f"Faltan {faltan}. Las partes salen de scripts/cortar_partido.py."
        )
    for v in videos:
        salida = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate", "-of", "json", str(v)],
            capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip
        s = json.loads(salida)["streams"][0]
        num, den = (int(x) for x in s["r_frame_rate"].split("/"))
        if (s["width"], s["height"]) != RESOLUCION or abs(num / den - FPS) > 0.01:
            raise SystemExit(
                f"{v} no es el esperado: {s} (se esperaba {RESOLUCION} a {FPS} fps)"
            )


def chequeo_previo(salida: Path, video: Path, imagen: str, dispositivo) -> dict:
    from src.tracking_data.processor import detectar_y_cachear

    ruta = config(salida, "chequeo", video, imagen, dispositivo, FRAMES_CHEQUEO)
    t0 = time.time()
    detectar_y_cachear(yaml.safe_load(open(ruta)))
    segundos = time.time() - t0
    if imagen == "original":
        a_metros_con_lente(salida / "cache_chequeo.pkl")
    datos = pickle.load(open(salida / "cache_chequeo.pkl", "rb"))
    colores = pickle.load(open(salida / "colores_chequeo.pkl", "rb"))
    cfg = yaml.safe_load(open(BASE))
    largo, ancho = cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]
    problemas, en_campo = [], []
    if len(datos["cache"]) != 3:
        problemas.append(f"{len(datos['cache'])} frames en la caché (se esperaban 3)")
    if tuple(datos["wh"]) != RESOLUCION:
        problemas.append(f"resolución {datos['wh']} (se esperaba {RESOLUCION})")
    for e in datos["cache"]:
        n = sum(1 for d in e["dets"] if 0 <= d[0] <= largo and 0 <= d[1] <= ancho)
        en_campo.append(n)
        if not DETECCIONES_EN_CAMPO[0] <= n <= DETECCIONES_EN_CAMPO[1]:
            problemas.append(
                f"frame {e['frame_idx']}: {n} detecciones con el pie en el campo "
                f"(se esperaban {DETECCIONES_EN_CAMPO}): ¿calibración, lente o detector?"
            )
    n_dets = sum(len(e["dets"]) for e in datos["cache"])
    if len(colores) < MIN_COLORES * n_dets:
        problemas.append(f"{len(colores)} vectores de color para {n_dets} detecciones")
    if problemas:
        raise SystemExit(
            "CHEQUEO PREVIO FALLIDO, no se lanza la pasada:\n- "
            + "\n- ".join(problemas)
        )
    return {
        "frames": len(datos["cache"]),
        "detecciones_en_campo": en_campo,
        "colores_para_detecciones": [len(colores), n_dets],
        "segundos_por_frame_cota_superior": round(segundos / 3, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--imagen", choices=["corregida", "original"], required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--solo-chequeo", action="store_true")
    # solo para probar en local; en Colab no se pasan
    ap.add_argument("--dispositivo", default=None)
    ap.add_argument("--videos", default=None, help="rutas separadas por comas")
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    videos = (
        [Path(v) for v in a.videos.split(",")]
        if a.videos
        else [R / "data/raw/alevinb_p1.mp4", R / "data/raw/alevinb_p2.mp4"]
    )
    comprobar_entradas(videos, a.imagen)
    previo = chequeo_previo(a.salida, videos[0], a.imagen, a.dispositivo)
    print(f"✓ chequeo previo: {previo}", flush=True)
    if a.solo_chequeo:
        return
    from src.tracking_data.processor import detectar_y_cachear, procesar_desde_cache

    resultados = {"imagen": a.imagen, "chequeo_previo": previo, "partes": {}}
    for n, video in enumerate(videos, start=1):
        ruta = config(a.salida, f"parte{n}", video, a.imagen, a.dispositivo)
        cfg = yaml.safe_load(open(ruta))
        t0 = time.time()
        detectar_y_cachear(cfg)
        if a.imagen == "original":
            a_metros_con_lente(a.salida / f"cache_parte{n}.pkl")
        cfg["modo"] = "desde_cache"
        procesar_desde_cache(cfg)
        resultados["partes"][f"parte{n}"] = {
            "video": str(video),
            "minutos": round((time.time() - t0) / 60, 1),
            "csv": str(a.salida / f"posiciones_parte{n}.csv"),
        }
        print(f"✓ parte {n}: {resultados['partes'][f'parte{n}']}", flush=True)
    (a.salida / "resumen.json").write_text(
        json.dumps(resultados, indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
