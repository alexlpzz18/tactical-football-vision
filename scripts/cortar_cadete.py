#!/usr/bin/env python
"""Corta las dos partes del cadete de Villaviciosa SIN recomprimir y comprueba que no cambia nada.

docs/cadete_villa_preparacion.md. El vídeo entero (3,66 GB) no cabe en Drive; las partes sí.

- Partes en TIEMPO DEL ARCHIVO (confirmadas con los saques de centro): 1ª 6:49-47:18, 2ª
  59:08-1:40:05.
- `ffmpeg -c copy` solo puede empezar en un fotograma clave (aquí, cada 2 s exactos, en x,032 s).
  Se corta en el fotograma clave MÁS CERCANO al inicio pedido y se dice el desplazamiento.
- Comprobación: con el lector común (`src/utils/video_ffmpeg.leer_frames_ffmpeg`, ffmpeg CLI) los
  frames del corte tienen que ser IDÉNTICOS bit a bit a los del original. Primero se busca qué
  frame del original es el frame 0 del corte (igualdad exacta en ± 40 frames) y luego se comparan
  frames repartidos por todo el corte.

Uso:
    python scripts/cortar_cadete.py cortar
    python scripts/cortar_cadete.py comprobar
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
ORIGINAL = Path("/Users/alexlpzz/Desktop/Partidos /CadeteA_Techniteam.mp4")
FPS = 25.0
PARTES = {  # tiempo del archivo pedido por Alex (s) y fotograma clave elegido
    "p1": {"pedido": (409.0, 2838.0), "clave": 408.032},
    "p2": {"pedido": (3548.0, 6005.0), "clave": 3548.032},
}
SALIDA = R / "data/raw"
COMPROBAR = [0, 1, 2, 25, 250, 2500, 25000, 50000]  # frames del corte que se comparan
BUSQUEDA = 40


def ruta(parte: str) -> Path:
    return SALIDA / f"cadete_villa_{parte}.mp4"


def cortar() -> dict:
    res = {"original_bytes": ORIGINAL.stat().st_size}
    for parte, p in PARTES.items():
        ini, fin = p["clave"], p["pedido"][1]
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{ini:.3f}", "-i", str(ORIGINAL),
             "-t", f"{fin - ini:.3f}", "-map", "0:v:0", "-c", "copy",
             "-avoid_negative_ts", "make_zero", str(ruta(parte))],
            check=True,
        )  # fmt: skip
        sonda = json.loads(
            subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                 "-show_entries",
                 "stream=nb_read_packets,width,height,r_frame_rate:format=duration",
                 "-of", "json", str(ruta(parte))],
                capture_output=True, text=True, check=True,
            ).stdout
        )  # fmt: skip
        res[parte] = {
            "bytes": ruta(parte).stat().st_size,
            "duracion_s": float(sonda["format"]["duration"]),
            "frames": int(sonda["streams"][0]["nb_read_packets"]),
            "desplazamiento_inicio_s": round(ini - p["pedido"][0], 3),
        }
    (SALIDA / "cadete_villa_cortes.json").write_text(json.dumps(res, indent=1))
    return res


def _huella(img: np.ndarray) -> str:
    """Huella del frame decodificado: dos huellas iguales = frames idénticos bit a bit."""
    return hashlib.sha256(img.tobytes()).hexdigest()


def comprobar() -> dict:
    """Una sola pasada por el original, guardando HUELLAS y no imágenes (8 MB por frame)."""
    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    res = {}
    for parte, p in PARTES.items():
        aprox = int(round(p["clave"] * FPS))
        cortes = {f: _huella(i) for f, i in leer_frames_ffmpeg(ruta(parte), COMPROBAR)}
        pedidos = [
            aprox + k + d for k in COMPROBAR for d in range(-BUSQUEDA, BUSQUEDA + 1)
        ]
        originales = {f: _huella(i) for f, i in leer_frames_ffmpeg(ORIGINAL, pedidos)}
        # qué frame del original es el frame 0 del corte (igualdad EXACTA)
        candidatos = [
            f
            for f in range(aprox - BUSQUEDA, aprox + BUSQUEDA + 1)
            if originales[f] == cortes[0]
        ]
        if len(candidatos) != 1:
            res[parte] = {"frame0_candidatos": candidatos, "todos_identicos": False}
            continue
        k0 = candidatos[0]
        iguales = {k: originales[k0 + k] == cortes[k] for k in COMPROBAR}
        res[parte] = {
            "frame0_es_el_frame_del_original": k0,
            "t_original_s": round(k0 / FPS, 3),
            "frames_identicos": iguales,
            "todos_identicos": all(iguales.values()),
        }
    (SALIDA / "cadete_villa_comprobacion.json").write_text(json.dumps(res, indent=1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["cortar", "comprobar"])
    args = ap.parse_args()
    print(
        json.dumps({"cortar": cortar, "comprobar": comprobar}[args.accion](), indent=1)
    )


if __name__ == "__main__":
    main()
