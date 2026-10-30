#!/usr/bin/env python
"""Corta las partes de un partido SIN recomprimir y comprueba que no cambia nada.

docs/alevinb_preparacion.md. `ffmpeg -c copy` solo puede empezar en un fotograma clave, así que se
corta en el MÁS CERCANO al inicio pedido y se informa el desplazamiento. Sin audio.

Comprobación: con el lector común (`src/utils/video_ffmpeg.leer_frames_ffmpeg`, ffmpeg CLI), los
frames del corte tienen que ser IDÉNTICOS bit a bit a los del original. Primero se busca qué frame
del original es el frame 0 del corte (igualdad exacta en ± 40 frames) y luego se comparan frames
repartidos por todo el corte. Se comparan HUELLAS y no imágenes: un frame ocupa 8 MB.

Uso (tiempos del ARCHIVO, m:ss o h:mm:ss):
    python scripts/cortar_partido.py cortar --video V.mp4 --nombre alevinb \\
        --partes 6:49-47:18,59:08-1:40:05
    python scripts/cortar_partido.py comprobar --video V.mp4 --nombre alevinb
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
COMPROBAR = (0, 1, 2, 25, 250, 2500, 25000, 50000)  # frames del corte que se comparan
BUSQUEDA = 40
VENTANA_CLAVE_S = 12.0


def a_segundos(texto: str) -> float:
    """'6:49' → 409.0; '1:40:05' → 6005.0."""
    s = 0.0
    for trozo in texto.split(":"):
        s = s * 60 + float(trozo)
    return s


def leer_partes(texto: str) -> list[tuple[float, float]]:
    partes = []
    for trozo in texto.split(","):
        ini, fin = (a_segundos(v) for v in trozo.split("-"))
        if fin <= ini:
            raise SystemExit(
                f"Parte mal escrita: {trozo} (el fin va después del inicio)"
            )
        partes.append((ini, fin))
    for (_a, b), (c, _d) in zip(partes, partes[1:]):
        if c < b:
            raise SystemExit(f"Las partes se solapan: {partes}")
    return partes


def clave_mas_cercana(claves: list[float], t: float) -> float:
    return min(claves, key=lambda c: abs(c - t))


def fotogramas_clave(video: Path, t: float) -> list[float]:
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-read_intervals", f"{max(0.0, t - VENTANA_CLAVE_S)}%{t + VENTANA_CLAVE_S}",
         "-skip_frame", "nokey", "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    claves = [float(x.strip(",")) for x in salida.split() if x.strip(",")]
    if not claves:
        raise SystemExit(f"Sin fotogramas clave cerca de {t} s")
    return claves


def _sondear(ruta: Path) -> dict:
    return json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
             "-show_entries", "stream=nb_read_packets,r_frame_rate:format=duration",
             "-of", "json", str(ruta)],
            capture_output=True, text=True, check=True,
        ).stdout
    )  # fmt: skip


def ruta_parte(salida: Path, nombre: str, n: int) -> Path:
    return salida / f"{nombre}_p{n}.mp4"


def cortar(video: Path, nombre: str, partes: list, salida: Path) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    res = {"original": str(video), "original_bytes": video.stat().st_size, "partes": {}}
    for n, (ini, fin) in enumerate(partes, start=1):
        clave = clave_mas_cercana(fotogramas_clave(video, ini), ini)
        ruta = ruta_parte(salida, nombre, n)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{clave:.3f}", "-i", str(video),
             "-t", f"{fin - clave:.3f}", "-map", "0:v:0", "-c", "copy",
             "-avoid_negative_ts", "make_zero", str(ruta)],
            check=True,
        )  # fmt: skip
        s = _sondear(ruta)
        res["partes"][f"p{n}"] = {
            "pedido_s": [ini, fin],
            "clave_s": clave,
            "desplazamiento_inicio_s": round(clave - ini, 3),
            "bytes": ruta.stat().st_size,
            "duracion_s": float(s["format"]["duration"]),
            "frames": int(s["streams"][0]["nb_read_packets"]),
        }
    (salida / f"{nombre}_cortes.json").write_text(json.dumps(res, indent=1))
    return res


def _huella(img: np.ndarray) -> str:
    """Dos huellas iguales = frames idénticos bit a bit."""
    return hashlib.sha256(img.tobytes()).hexdigest()


def comprobar(video: Path, nombre: str, salida: Path) -> dict:
    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    cortes = json.loads((salida / f"{nombre}_cortes.json").read_text())
    s0 = _sondear(video)["streams"][0]["r_frame_rate"].split("/")
    fps = float(s0[0]) / float(s0[1])
    res = {}
    for clave_p, p in cortes["partes"].items():
        n = int(clave_p[1:])
        pedir = [k for k in COMPROBAR if k < p["frames"]]
        aprox = int(round(p["clave_s"] * fps))
        h_corte = {
            f: _huella(i)
            for f, i in leer_frames_ffmpeg(ruta_parte(salida, nombre, n), pedir)
        }
        pedidos = [aprox + k + d for k in pedir for d in range(-BUSQUEDA, BUSQUEDA + 1)]
        h_orig = {f: _huella(i) for f, i in leer_frames_ffmpeg(video, pedidos)}
        candidatos = [
            f
            for f in range(aprox - BUSQUEDA, aprox + BUSQUEDA + 1)
            if h_orig[f] == h_corte[0]
        ]
        if len(candidatos) != 1:
            res[clave_p] = {"frame0_candidatos": candidatos, "todos_identicos": False}
            continue
        k0 = candidatos[0]
        iguales = {k: h_orig[k0 + k] == h_corte[k] for k in pedir}
        res[clave_p] = {
            "frame0_es_el_frame_del_original": k0,
            "t_original_s": round(k0 / fps, 3),
            "frames_identicos": iguales,
            "todos_identicos": all(iguales.values()),
        }
    (salida / f"{nombre}_comprobacion.json").write_text(json.dumps(res, indent=1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["cortar", "comprobar"])
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--partes", default=None)
    ap.add_argument("--salida", type=Path, default=R / "data/raw")
    a = ap.parse_args()
    if a.accion == "cortar":
        if not a.partes:
            raise SystemExit("cortar necesita --partes")
        out = cortar(a.video, a.nombre, leer_partes(a.partes), a.salida)
    else:
        out = comprobar(a.video, a.nombre, a.salida)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
