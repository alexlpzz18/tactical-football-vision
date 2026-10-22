"""Leer frames del vídeo con el ffmpeg de LÍNEA DE COMANDOS (los mismos píxeles que producción).

⚠️ Para medir COLOR, nunca `cv2.VideoCapture` en el Mac. En macOS OpenCV decodifica con
AVFoundation, que da píxeles distintos de los de FFmpeg (el que usa Colab al generar las cachés):
una feature recalculada así coincidió con la caché de producción en el 0,27 % de las cajas, y con
este lector en el 100 % (`docs/diagnostico_22oct_b.md`, bloque 3). `cv2.CAP_FFMPEG` no abre el
vídeo en este Mac, por eso se usa el binario `ffmpeg` por una tubería.

El vídeo se lee SECUENCIALMENTE desde el frame 0 (sin buscar con `-ss`), así que el índice de frame
es exactamente el del caché: no hay ambigüedad de búsqueda como con `cap.set`.
"""

import json
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np


def tamano_video(ruta: str | Path) -> tuple[int, int]:
    """(ancho, alto) en píxeles, leído con ffprobe."""
    salida = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(ruta),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    s = json.loads(salida)["streams"][0]
    return int(s["width"]), int(s["height"])


def leer_frames_ffmpeg(
    ruta: str | Path, frames: Iterable[int]
) -> Iterator[tuple[int, np.ndarray]]:
    """Genera (frame_idx, imagen BGR) para cada frame pedido, en orden creciente.

    Decodifica todo hasta el último frame pedido y descarta el resto: leer 20 min de 1080p cuesta
    unos 2,5 min en este Mac (medido: 30 s de vídeo en 3,4 s).

    Raises:
        RuntimeError: si el vídeo se acaba antes de un frame pedido.
    """
    pedidos = sorted(set(int(f) for f in frames))
    if not pedidos:
        return
    ancho, alto = tamano_video(ruta)
    tam = ancho * alto * 3
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(ruta),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-",
        ],
        stdout=subprocess.PIPE,
    )
    try:
        actual = 0
        for f in pedidos:
            while actual < f:
                if len(proc.stdout.read(tam)) < tam:
                    raise RuntimeError(f"el vídeo se acabó antes del frame {f}")
                actual += 1
            buf = proc.stdout.read(tam)
            actual += 1
            if len(buf) < tam:
                raise RuntimeError(f"no se pudo leer el frame {f}")
            yield f, np.frombuffer(buf, np.uint8).reshape(alto, ancho, 3).copy()
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()
