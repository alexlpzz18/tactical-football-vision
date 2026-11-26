#!/usr/bin/env python
"""Premisa de B1 (segunda opinión, 26-nov-2026): ¿el fondo fijo ve la camiseta verde oscuro?

Dos medidas, con criterio fijado antes por Alex:
1. **Vibración**: desplazamiento de la imagen en 100 fotogramas SEGUIDOS del alevín B, medido con
   correlación de fase (con ventana de Hanning) sobre una banda ESTÁTICA y con textura del fondo
   (edificios y vallas). No vale el techo de la grada: va pegado a la cámara y tiene destello del
   sol. Pasa si el máximo es < 1 px.
2. **Torso retenido**: en los recortes del mini-GT a ojo (verdes «V» y blancos «B»), qué fracción
   del pecho (12-45 % del alto, 15-85 % del ancho: la banda del clasificador) sobrevive
   - a la máscara anti-césped de producción (se borra H 35-85, S ≥ 40, V ≥ 40), y
   - a una máscara de primer plano |I − B| > umbral, con B la mediana de 40 fotogramas del mismo
     minuto (sin el propio fotograma).
   Pasa si, en los jugadores verdes, el primer plano conserva ≥ 60 % del pecho y la máscara
   anti-césped < 20 %.
Los fotogramas se leen con el ffmpeg de línea de comandos (CLAUDE.md). Solo lee: no toca producción.

Uso:
    python scripts/premisa_fondo_fijo.py --salida outputs/premisa_fondo_fijo
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.utils.video_ffmpeg import leer_frames_ffmpeg  # noqa: E402

VIDEO = R / "data/raw/alevinb_p1.mp4"
GT = R / "outputs/gt_equipos_alevinb/detecciones_120.csv"
TORSO_ALTO, TORSO_ANCHO = (0.12, 0.45), (0.15, 0.85)
BANDA_FONDO = (195, 265, 700, 1150)  # y0, y1, x0, x1: edificios y vallas del fondo


def vibracion(inicio: int, n: int = 100) -> dict:
    """Desplazamiento (px) de la banda del fondo de cada fotograma respecto al primero."""
    y0, y1, x0, x1 = BANDA_FONDO
    ref, ventana, desp = None, None, []
    for _f, img in leer_frames_ffmpeg(VIDEO, range(inicio, inicio + n)):
        g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        if ref is None:
            ref = g
            ventana = cv2.createHanningWindow(g.shape[::-1], cv2.CV_32F)
            continue
        (dx, dy), _r = cv2.phaseCorrelate(ref, g, ventana)
        desp.append(float(np.hypot(dx, dy)))
    d = np.array(desp)
    return {
        "fotogramas": n,
        "desde": inicio,
        "p50_px": round(float(np.median(d)), 3),
        "p95_px": round(float(np.percentile(d, 95)), 3),
        "max_px": round(float(d.max()), 3),
    }


def pecho(img: np.ndarray, caja) -> tuple[slice, slice]:
    x1, y1, x2, y2 = [float(v) for v in caja]
    w, h = x2 - x1, y2 - y1
    ya, yb = int(y1 + TORSO_ALTO[0] * h), int(y1 + TORSO_ALTO[1] * h)
    xa, xb = int(x1 + TORSO_ANCHO[0] * w), int(x1 + TORSO_ANCHO[1] * w)
    return slice(ya, max(yb, ya + 1)), slice(xa, max(xb, xa + 1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--umbral", type=int, nargs="+", default=[15, 25, 40])
    ap.add_argument("--fondo-n", type=int, default=40)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    gt = pd.read_csv(GT)
    gt = gt[gt.equipo_a_ojo.isin(["B", "V"])]
    res = {
        "vibracion": [
            vibracion(int(gt.frame.min())),
            vibracion(int(gt.frame.max()) - 100),
        ]
    }
    # fondo por minuto: mediana de `fondo_n` fotogramas repartidos en el minuto de cada marca
    fps = 25
    minutos = sorted({int(f // (60 * fps)) for f in gt.frame})
    filas = []
    for m in minutos:
        marcas = gt[(gt.frame // (60 * fps)) == m]
        candidatos = np.linspace(
            m * 60 * fps, (m + 1) * 60 * fps - 1, a.fondo_n
        ).astype(int)
        pedir = sorted(set(candidatos) | set(marcas.frame.astype(int)))
        imgs = dict(leer_frames_ffmpeg(VIDEO, pedir))
        for r in marcas.itertuples():
            pila = [imgs[c] for c in candidatos if abs(int(c) - int(r.frame)) > 2 * fps]
            fondo = np.median(np.stack(pila), axis=0).astype(np.uint8)
            img = imgs[int(r.frame)]
            sy, sx = pecho(img, (r.x1, r.y1, r.x2, r.y2))
            p_img, p_fondo = img[sy, sx], fondo[sy, sx]
            hsv = cv2.cvtColor(p_img, cv2.COLOR_BGR2HSV)
            h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
            cesped = (h >= 35) & (h <= 85) & (s >= 40) & (v >= 40)
            dif = np.abs(p_img.astype(int) - p_fondo.astype(int)).max(axis=2)
            fila = {
                "equipo": r.equipo_a_ojo,
                "franja": r.franja,
                "alto_px": float(r.y2 - r.y1),
                "anti_cesped_conserva": float((~cesped).mean()),
            }
            for u in a.umbral:
                fila[f"primer_plano_{u}"] = float((dif > u).mean())
            filas.append(fila)
    d = pd.DataFrame(filas)
    res["torso_retenido_mediana"] = {
        e: {
            c: round(float(g[c].median()), 3)
            for c in d.columns
            if c not in ("equipo", "franja")
        }
        for e, g in d.groupby("equipo")
    }
    res["torso_retenido_por_franja_verdes"] = {
        fr: {
            c: round(float(g[c].median()), 3)
            for c in d.columns
            if c.startswith(("anti", "primer"))
        }
        for fr, g in d[d.equipo == "V"].groupby("franja")
    }
    res["n"] = d.equipo.value_counts().to_dict()
    a.salida.mkdir(parents=True, exist_ok=True)
    d.to_csv(a.salida / "recortes.csv", index=False)
    (a.salida / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
