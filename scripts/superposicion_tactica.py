#!/usr/bin/env python
"""Prototipo: superposición TÁCTICA sobre el vídeo real (tarea 4 de la noche).

Sobre el propio vídeo, para cada equipo:
- el **contorno** del bloque (envolvente convexa de sus jugadores de campo, sin porteros);
- sus **líneas de defensa, medio y ataque**, promediadas en 3 s, dibujadas a lo ancho del campo;
- la **distancia entre líneas en metros**.
Todo se calcula en METROS (el CSV de posiciones) y se proyecta a la imagen con la homografía
inversa.
Sin números de identidad: lo que se ve es el bloque, no las fichas.

Las líneas, en cada fotograma: los jugadores de campo del equipo se ordenan por profundidad desde SU
portería y se parten en tres grupos con el corte 1D óptimo (el que hace mínima la dispersión dentro
de cada grupo). La profundidad de una línea es la media de su grupo; luego se promedia en ± 1,5 s.

Qué portería defiende cada equipo se deduce de dónde está su portero en el tramo.

Uso:
    python scripts/superposicion_tactica.py \\
        --csv outputs/literatura/banco/benja20/posiciones_actual.csv \\
        --video data/raw/benja_gredos_p1_20min.mp4 \\
        --homografia data/calibracion_benja/homografia_benja.npy \\
        --desde 840 --hasta 870 --salida outputs/literatura/superposicion/benja_14m00s.mp4
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.utils.video_ffmpeg import leer_frames_ffmpeg, tamano_video  # noqa: E402

EQUIPO = {"A": "A", "B": "B", "portero_A": "A", "portero_B": "B"}
NOMBRE_LINEA = ("def", "med", "ata")


def cortes_1d(valores: np.ndarray, k: int = 3) -> list[np.ndarray]:
    """Parte valores ordenados en k grupos seguidos con mínima suma de varianzas (DP exacta)."""
    v = np.sort(np.asarray(valores, float))
    n = len(v)
    if n < k:
        return [v[i : i + 1] for i in range(n)]  # noqa: E203
    coste = np.full((k + 1, n + 1), np.inf)
    corte = np.zeros((k + 1, n + 1), dtype=int)
    coste[0, 0] = 0.0

    def sse(a, b):
        s = v[a:b]
        return float(((s - s.mean()) ** 2).sum())

    for g in range(1, k + 1):
        for fin in range(g, n + 1):
            for ini in range(g - 1, fin):
                c = coste[g - 1, ini] + sse(ini, fin)
                if c < coste[g, fin]:
                    coste[g, fin], corte[g, fin] = c, ini
    grupos, fin = [], n
    for g in range(k, 0, -1):
        ini = corte[g, fin]
        grupos.append(v[ini:fin])
        fin = ini
    return grupos[::-1]


def lineas_del_frame(
    xy: np.ndarray, hacia_x_creciente: bool
) -> list[tuple[float, float, float]]:
    """[(profundidad x, y_min, y_max)] de defensa, medio y ataque, en metros de campo."""
    if len(xy) < 3:
        return []
    prof = xy[:, 0] if hacia_x_creciente else -xy[:, 0]
    orden = np.argsort(prof)
    grupos = cortes_1d(prof[orden], 3)
    salida, k = [], 0
    for g in grupos:
        miembros = xy[orden[k : k + len(g)]]  # noqa: E203
        k += len(g)
        salida.append(
            (float(miembros[:, 0].mean()), miembros[:, 1].min(), miembros[:, 1].max())
        )
    return salida


def a_pixeles(Hi: np.ndarray, xy) -> np.ndarray:
    p = np.column_stack([np.asarray(xy, float), np.ones(len(xy))]) @ Hi.T
    return (p[:, :2] / p[:, 2:3]).astype(np.int32)


def color_bgr(hexa: str) -> tuple[int, int, int]:
    h = hexa.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--homografia", type=Path, required=True)
    ap.add_argument("--desde", type=float, required=True)
    ap.add_argument("--hasta", type=float, required=True)
    ap.add_argument("--largo", type=float, default=62.0)
    ap.add_argument("--ancho", type=float, default=40.0)
    ap.add_argument("--ventana-s", type=float, default=3.0)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()

    df = pd.read_csv(a.csv)
    meta = a.csv.with_name(
        a.csv.name.replace("posiciones_", "meta_").replace(".csv", ".json")
    )
    colores = (
        json.loads(meta.read_text()).get("colores_equipo", {}) if meta.exists() else {}
    ) or {"A": "#3b82f6", "B": "#ef4444"}
    tramo = df[
        (df.tiempo_s >= a.desde - a.ventana_s) & (df.tiempo_s <= a.hasta + a.ventana_s)
    ]
    tramo = tramo[
        tramo.x_m.between(0, a.largo)
        & tramo.y_m.between(0, a.ancho)
        & tramo.etiqueta.isin(EQUIPO)
    ]
    # ¿qué portería defiende cada equipo? la de su portero (o, si no hay, la de su bloque)
    defiende_x0 = {}
    for e in ("A", "B"):
        p = tramo[tramo.etiqueta == f"portero_{e}"]
        ref = p.x_m.mean() if len(p) else tramo[tramo.etiqueta == e].x_m.mean()
        defiende_x0[e] = bool(ref < a.largo / 2)
    campo = tramo[tramo.etiqueta.isin(["A", "B"])]
    # líneas por frame del CSV y luego promediadas en la ventana
    por_frame = {}
    for (f, e), g in campo.groupby(["frame", "etiqueta"]):
        lin = lineas_del_frame(g[["x_m", "y_m"]].to_numpy(), defiende_x0[e])
        if len(lin) == 3:
            por_frame[(int(f), e)] = (float(g.tiempo_s.iloc[0]), lin)

    def lineas_suaves(t: float, e: str):
        sel = [
            lin
            for (f, ee), (tt, lin) in por_frame.items()
            if ee == e and abs(tt - t) <= a.ventana_s / 2
        ]
        if not sel:
            return None
        arr = np.array(sel)  # (n, 3, 3)
        return arr.mean(axis=0)

    H = np.load(a.homografia)
    Hi = np.linalg.inv(H)
    ancho_v, alto_v = tamano_video(a.video)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    escala = 1280 / ancho_v
    fuera = (int(ancho_v * escala) // 2 * 2, int(alto_v * escala) // 2 * 2)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s",
         f"{fuera[0]}x{fuera[1]}", "-r", str(a.fps), "-i", "-", "-c:v", "libx264", "-preset",
         "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(a.salida)],
        stdin=subprocess.PIPE,
    )  # fmt: skip
    frames_csv = np.array(sorted(campo.frame.unique()))
    ini, fin = int(round(a.desde * a.fps)), int(round(a.hasta * a.fps))
    capturas = {ini + (fin - ini) * k // 4 for k in (1, 2, 3)}
    for f, img in leer_frames_ffmpeg(a.video, range(ini, fin)):
        # posiciones del frame del CSV más cercano (el caché va 1 de cada 3)
        fc = int(frames_csv[np.argmin(np.abs(frames_csv - f))])
        capa = img.copy()
        t = f / a.fps
        textos = []
        for e in ("A", "B"):
            col = color_bgr(colores.get(e, "#ffffff"))
            g = campo[(campo.frame == fc) & (campo.etiqueta == e)]
            pts = g[["x_m", "y_m"]].to_numpy()
            if len(pts) >= 3:
                casco = cv2.convexHull(a_pixeles(Hi, pts).reshape(-1, 1, 2))
                cv2.fillPoly(capa, [casco], col)
                cv2.polylines(img, [casco], True, col, 2, cv2.LINE_AA)
            lin = lineas_suaves(t, e)
            if lin is None:
                continue
            for k, (x, y0, y1) in enumerate(lin):
                seg = a_pixeles(
                    Hi, [[x, max(0.0, y0 - 1.0)], [x, min(a.ancho, y1 + 1.0)]]
                )
                cv2.line(img, tuple(seg[0]), tuple(seg[1]), col, 3, cv2.LINE_AA)
            d1, d2 = abs(lin[1][0] - lin[0][0]), abs(lin[2][0] - lin[1][0])
            textos.append((e, col, d1, d2, abs(lin[2][0] - lin[0][0])))
        img = cv2.addWeighted(capa, 0.18, img, 0.82, 0)
        for n_, (e, col, d1, d2, total) in enumerate(textos):
            txt = f"{e}: def-med {d1:.1f} m · med-ata {d2:.1f} m · largo del bloque {total:.1f} m"
            txt = txt.replace(".", ",").replace("·", "|")
            y = 40 + 34 * n_
            cv2.putText(
                img,
                txt,
                (24, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 0, 0),
                5,
                cv2.LINE_AA,
            )
            cv2.putText(
                img, txt, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2, cv2.LINE_AA
            )
        s = int(t)
        cv2.putText(img, f"{s // 60}:{s % 60:02d} (reloj del archivo)", (24, alto_v - 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)  # fmt: skip
        pequeno = cv2.resize(img, fuera, interpolation=cv2.INTER_AREA)
        ff.stdin.write(pequeno.tobytes())
        if f in capturas:
            cv2.imwrite(
                str(a.salida.with_name(f"{a.salida.stem}_{s // 60}m{s % 60:02d}s.jpg")),
                pequeno,
            )
    ff.stdin.close()
    ff.wait()
    print(f"✓ {a.salida} ({(fin - ini) / a.fps:.0f} s)")


if __name__ == "__main__":
    main()
