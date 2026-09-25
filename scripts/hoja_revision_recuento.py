#!/usr/bin/env python
"""Hoja de revisión para el GT de RECUENTO (BACKLOG 31): 1 imagen por segundo, cajas
numeradas, sin tracks.

Alex (25-sep-2026): formato A — anota por imagen los jugadores visibles SIN caja, las
cajas que no son jugador, y quién está cortado por el borde.

Ventanas (`docs/desglose_por_episodios.md`, §4): tres candidatas a minuto MALO (juego
cerca de la cámara) y una de control (pocas detecciones SIN estar cerca de la cámara).

Cada imagen sale del vídeo con `posicionar_en_frame()` (nunca `cap.set`, ver
`src/tracking_data/processor.py`), y las cajas son las del CACHÉ de detecciones —
exactamente lo que entra al tracking, no una re-detección.

Uso:
    python scripts/hoja_revision_recuento.py --salida-dir outputs/hoja_recuento
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("hoja_recuento")

# (nombre, inicio en segundos, duración) — de docs/desglose_por_episodios.md §4.
VENTANAS = [
    ("A_3-10", 3 * 60 + 10, 30, "candidata: peor bin, juego cerca de la cámara"),
    (
        "B_4-30",
        4 * 60 + 30,
        30,
        "candidata: segundo peor, pegada al GT ya anotado (5:25)",
    ),
    ("C_14-00", 14 * 60 + 0, 30, "candidata: segunda mitad, mismo patrón"),
    (
        "D_13-25_control",
        13 * 60 + 25,
        30,
        "CONTROL: pocas detecciones SIN estar cerca de la cámara",
    ),
]

VERDE = (0, 220, 0)


def dets_del_frame(cache: dict, frame_idx: int):
    """Las detecciones (en píxeles) que el caché tiene para ese frame, o ninguna."""
    entrada = cache.get(frame_idx)
    return entrada if entrada is not None else []


def dibujar(imagen: np.ndarray, dets: list) -> np.ndarray:
    """Dibuja las cajas del caché numeradas por orden de confianza descendente."""
    salida = imagen.copy()
    orden = sorted(range(len(dets)), key=lambda i: -dets[i][6])
    for n, i in enumerate(orden, start=1):
        _mx, _my, x1, y1, x2, y2, conf = dets[i]
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        cv2.rectangle(salida, (x1, y1), (x2, y2), VERDE, 2)
        etiqueta = f"{n} ({conf:.2f})"
        (tw, th), _ = cv2.getTextSize(etiqueta, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(salida, (x1, y1 - th - 6), (x1 + tw + 4, y1), VERDE, -1)
        cv2.putText(
            salida,
            etiqueta,
            (x1 + 2, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 0),
            2,
        )
    return salida


def generar_ventana(
    cap, cache: dict, fps: float, salida: Path, nombre: str, ini_s: float, dur_s: int
) -> list:
    """Una imagen por segundo de la ventana. Devuelve las rutas escritas."""
    carpeta = salida / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for s in range(dur_s):
        t = ini_s + s
        objetivo = round(t * fps)
        real = posicionar_en_frame(cap, objetivo)
        ok, frame = cap.read()
        if not ok:
            logger.warning(
                "no se pudo leer el frame %d (t=%.1fs) de %s", real, t, nombre
            )
            continue
        dets = dets_del_frame(cache, real)
        pintado = dibujar(frame, dets)
        cv2.putText(
            pintado,
            f"{nombre}  t={t // 60}:{t % 60:02d}  frame={real}  cajas={len(dets)}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 220, 0),
            2,
        )
        ruta = carpeta / f"{nombre}_s{s:02d}_frame{real}.jpg"
        cv2.imwrite(str(ruta), pintado, [cv2.IMWRITE_JPEG_QUALITY, 90])
        rutas.append(ruta)
    return rutas


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    p.add_argument(
        "--dets", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument("--salida-dir", default="outputs/hoja_recuento")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    with open(args.dets, "rb") as f:
        datos = pickle.load(f)
    cache = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
    fps = datos["fps"]

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"no se pudo abrir {args.video}")

    salida = Path(args.salida_dir)
    total = 0
    for nombre, ini_s, dur_s, motivo in VENTANAS:
        logger.info("%s (%s): t=%d-%ds", nombre, motivo, ini_s, ini_s + dur_s)
        rutas = generar_ventana(cap, cache, fps, salida, nombre, ini_s, dur_s)
        total += len(rutas)
    cap.release()

    (salida / "LEEME.txt").write_text(
        "Hoja de revisión para el GT de recuento (formato A).\n\n"
        "Por cada imagen, anota:\n"
        "  1) jugadores VISIBLES sin caja verde (cuenta y, si puedes, posición aprox.)\n"
        "  2) cajas verdes que NO son un jugador (balón, banco, marca del campo...)\n"
        "  3) quién está CORTADO por el borde de la imagen (sale a medias)\n\n"
        "Las cajas son del caché de detecciones (lo que entra al tracking), numeradas\n"
        "por confianza descendente (el número no es un id de jugador).\n\n"
        "Carpetas:\n"
        + "\n".join(f"  {n}: {motivo}" for n, _, _, motivo in VENTANAS)
        + "\n"
    )
    logger.info("%d imágenes en %s", total, salida)
    print(f"\n✓ {total} imágenes en {salida}/")


if __name__ == "__main__":
    main()
