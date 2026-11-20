#!/usr/bin/env python
"""Método 4 de docs/plan_literatura.md: recortes extra en la franja LEJANA del F11.

Producción en Villaviciosa: SAHI 2×4 recortes + imagen completa sobre el fotograma con la lente
corregida. Un recorte de 640×532 px se pasa a la red a 640: casi no amplía (×1,0-1,2), y un jugador
lejano de 15-20 px sigue siendo de 15-20 px para la red. Aquí se AÑADEN recortes pequeños solo en
la banda de la imagen que ve el tercio lejano del campo (calculada con la homografía), que la red
amplía ×2-×3. Todas las predicciones se fusionan con el mismo postproceso de SAHI (GREEDYNMM, IOS
0,5).

Mide en los frames del GT del alevín A («Villaviciosa», 60 frames):
- recall por tamaño de la caja del GT (< 20 px, 20-30, ≥ 30) y por franja;
- detecciones dentro del campo que no casan con nadie del GT (falsos positivos por frame);
- inferencias de la red por frame (coste).

**Control del instrumento**: la variante «produccion» tiene que reproducir las cajas del caché de
producción en esos frames (se informa el % de cajas reproducidas, IoU ≥ 0,9).

Corre en la CPU con `~/.venvs/detector-cpu` (60 frames) o en GPU con `--dispositivo cuda`.

Uso:
    ~/.venvs/detector-cpu/bin/python scripts/lit_franjas_lejanas.py \\
        --salida outputs/literatura/franjas
    (con --chequeo 3 para probar 3 frames)
"""

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import cv2
import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.utils.video_ffmpeg import leer_frames_ffmpeg  # noqa: E402

VIDEO = R / "data/raw/partido.mp4"
MODELO = R / "models/weights/best_v4pre.pt"
CACHE = R / "data/tracking/cache_detecciones_v4pre.pkl"
GT = R / "data/annotations/ground_truth_tracking/annotations.xml"
HOMOGRAFIA = R / "data/calibracion/homografia.npy"
OFFSET, PASO = 7500, 15
K1, K2 = -1.5, 0.5
LARGO, ANCHO = 105.0, 68.0
CONF, MAX_AREA = 0.3, 0.05


def banda_lejana(H: np.ndarray, w: int, h: int, desde_frac: float) -> tuple[int, int]:
    """Filas de la imagen (y0, y1) que ven el campo a partir de `desde_frac` del ancho (lejos)."""
    Hi = np.linalg.inv(H)
    ys = []
    for x in np.linspace(0, LARGO, 30):
        for y in (desde_frac * ANCHO, ANCHO + 3.0):
            p = Hi @ np.array([x, y, 1.0])
            p = p[:2] / p[2]
            if 0 <= p[0] < w:
                ys.append(p[1])
    y0, y1 = int(max(0, min(ys) - 40)), int(min(h, max(ys) + 40))
    return min(y0, y1), max(y0, y1)


def detectar(img, modelo, filas, cols, solape, extra):
    """Predicciones SAHI de producción + (opcional) recortes extra en la banda. Da (dets, n)."""
    from sahi.postprocess.combine import GreedyNMMPostprocess
    from sahi.predict import get_prediction, get_sliced_prediction

    h, w = img.shape[:2]
    res = get_sliced_prediction(
        img,
        modelo,
        slice_height=h // filas,
        slice_width=w // cols,
        overlap_height_ratio=solape,
        overlap_width_ratio=solape,
        verbose=0,
    )
    preds = list(res.object_prediction_list)
    inferencias = filas * cols + 1
    if extra:
        y0, y1, ancho_tile = extra
        paso = int(ancho_tile * (1 - solape))
        for x0 in range(0, w - ancho_tile + paso, paso):
            x0 = min(x0, w - ancho_tile)
            tile = img[y0:y1, x0 : x0 + ancho_tile]  # noqa: E203
            r = get_prediction(
                tile, modelo, shift_amount=[x0, y0], full_shape=[h, w], verbose=0
            )
            # ⚠️ get_prediction devuelve las cajas en coordenadas del RECORTE: hay que desplazarlas
            # al fotograma (sin esto caían en la esquina superior izquierda y la variante no medía
            # nada; cazado el 20-nov porque las tres variantes daban cifras idénticas)
            preds += [
                q.get_shifted_object_prediction() for q in r.object_prediction_list
            ]
            inferencias += 1
    # El MISMO postproceso para todas las variantes (también para la de producción): fusionar otra
    # vez lo ya fusionado no es neutro, y aplicarlo solo a las franjas falseaba sus falsos
    # positivos.
    preds = GreedyNMMPostprocess(
        match_threshold=0.5, match_metric="IOS", class_agnostic=True
    )(preds)
    dets = []
    for p in preds:
        b = p.bbox
        if (
            p.score.value < CONF
            or (b.maxx - b.minx) * (b.maxy - b.miny) > MAX_AREA * w * h
        ):
            continue
        dets.append((b.minx, b.miny, b.maxx, b.maxy, p.score.value))
    return dets, inferencias


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--chequeo", type=int, default=0, help="solo N frames (prueba)")
    ap.add_argument("--dispositivo", default="cpu")
    ap.add_argument(
        "--desde-frac", type=float, default=0.6, help="lejos = y ≥ esto × ancho"
    )
    ap.add_argument("--anchos-tile", type=int, nargs="+", default=[320, 240])
    a = ap.parse_args()
    from sahi import AutoDetectionModel

    from src.evaluation.gt_parser import parsear_cvat

    modelo = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(MODELO),
        confidence_threshold=CONF,
        device=a.dispositivo,
    )
    H = np.load(HOMOGRAFIA)
    tracks = parsear_cvat(GT)
    gt = {}
    for tr in tracks:
        for c in tr.cajas:
            gt.setdefault(OFFSET + PASO * c.frame_local, []).append(
                (c.xtl, c.ytl, c.xbr, c.ybr)
            )
    frames = sorted(gt)[: a.chequeo] if a.chequeo else sorted(gt)
    prod = {e["frame_idx"]: e["dets"] for e in pickle.load(open(CACHE, "rb"))["cache"]}
    w, h = 2560, 1064
    Kc = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    dist = np.array([K1, K2, 0, 0, 0], dtype=np.float64)
    y0, y1 = banda_lejana(H, w, h, a.desde_frac)
    variantes = {"produccion": None} | {
        f"franja_{t}px": (y0, y1, t) for t in a.anchos_tile
    }
    resultados = {v: [] for v in variantes}
    t0 = time.time()
    for f, img in leer_frames_ffmpeg(VIDEO, frames):
        img = cv2.undistort(img, Kc, dist)
        for v, extra in variantes.items():
            dets, n_inf = detectar(img, modelo, 2, 4, 0.2, extra)
            resultados[v].append((f, dets, n_inf))
        print(f"frame {f} · {time.time() - t0:.0f} s", flush=True)

    def proy(x, y):
        p = H @ np.array([x, y, 1.0])
        return p[:2] / p[2]

    from scipy.optimize import linear_sum_assignment

    salida = {"banda_px": [y0, y1], "frames": len(frames)}
    for v, filas in resultados.items():
        por_tam = {"<20": [0, 0], "20-30": [0, 0], ">=30": [0, 0]}
        fp, inf, reproducidas, total_prod = 0, 0, 0, 0
        for f, dets, n_inf in filas:
            inf += n_inf
            g = np.array(gt[f], float)
            dd = np.array([d[:4] for d in dets], float).reshape(-1, 4)
            # casado 1-a-1 por distancia entre centros, aceptado si el centro de la detección cae
            # dentro de la caja del GT ampliada un 20 % (las cajas del detector son más altas)
            cg = (g[:, :2] + g[:, 2:]) / 2
            cd = (dd[:, :2] + dd[:, 2:]) / 2
            dist_c = (
                np.linalg.norm(cg[:, None] - cd[None], axis=2)
                if len(dd)
                else np.zeros((len(g), 0))
            )
            ok = np.zeros_like(dist_c, dtype=bool)
            for i in range(len(g)):
                mw, mh = 0.2 * (g[i, 2] - g[i, 0]), 0.2 * (g[i, 3] - g[i, 1])
                ok[i] = (
                    (cd[:, 0] >= g[i, 0] - mw)
                    & (cd[:, 0] <= g[i, 2] + mw)
                    & (cd[:, 1] >= g[i, 1] - mh)
                    & (cd[:, 1] <= g[i, 3] + mh)
                )
            casa_g, casa_d = set(), set()
            if len(dd):
                i_, j_ = linear_sum_assignment(np.where(ok, dist_c, 1e6))
                for i, j in zip(i_, j_):
                    if ok[i, j]:
                        casa_g.add(i)
                        casa_d.add(j)
            for i in range(len(g)):
                alto = g[i, 3] - g[i, 1]
                k = "<20" if alto < 20 else ("20-30" if alto < 30 else ">=30")
                por_tam[k][1] += 1
                por_tam[k][0] += i in casa_g
            for j in range(len(dd)):
                if j in casa_d:
                    continue
                mx, my = proy((dd[j, 0] + dd[j, 2]) / 2, dd[j, 3])
                if 0 <= mx <= LARGO and 0 <= my <= ANCHO:
                    fp += 1
            if v == "produccion":
                cp = np.array([d[2:6] for d in prod.get(f, [])], float).reshape(-1, 4)
                total_prod += len(cp)
                # el criterio de control ya validado (docs/diagnostico_28oct_c.md): IoU ≥ 0,9
                for c in cp:
                    if not len(dd):
                        continue
                    x1 = np.maximum(dd[:, 0], c[0])
                    y1 = np.maximum(dd[:, 1], c[1])
                    x2 = np.minimum(dd[:, 2], c[2])
                    y2 = np.minimum(dd[:, 3], c[3])
                    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
                    union = (
                        (dd[:, 2] - dd[:, 0]) * (dd[:, 3] - dd[:, 1])
                        + (c[2] - c[0]) * (c[3] - c[1])
                        - inter
                    )
                    if (inter / union).max() >= 0.9:
                        reproducidas += 1
        salida[v] = {
            "recall_por_alto_px": {
                k: round(100 * x[0] / max(x[1], 1), 1) for k, x in por_tam.items()
            },
            "personas_gt_por_alto": {k: x[1] for k, x in por_tam.items()},
            "falsos_positivos_en_campo_por_frame": round(fp / len(filas), 2),
            "inferencias_por_frame": round(inf / len(filas), 1),
        }
        if v == "produccion":
            salida[v]["control_cajas_de_produccion_reproducidas_pct"] = round(
                100 * reproducidas / max(total_prod, 1), 1
            )
    a.salida.mkdir(parents=True, exist_ok=True)
    nombre = "chequeo.json" if a.chequeo else "resultado.json"
    (a.salida / nombre).write_text(json.dumps(salida, indent=1, ensure_ascii=False))
    print(json.dumps(salida, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
