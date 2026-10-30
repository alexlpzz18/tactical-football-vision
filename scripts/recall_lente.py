#!/usr/bin/env python
"""Recall por zona del detector: imagen ORIGINAL frente a CORREGIDA. Criterios en docs/lente_f11.md.

100 frames del GT de Villaviciosa. Corregida: la caché de producción. Original: el mismo detector
y los mismos parámetros, en CPU, sobre el frame sin corregir. El GT está en píxeles de la corregida
y se lleva al original con el polinomio de `cv2.undistort`.

Uso:
    VENV/bin/python scripts/recall_lente.py detectar   # venv numpy 1.26 (CPU); reanuda solo
    python scripts/recall_lente.py medir
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/lente_f11"
CONFIG = R / "configs/processor.yaml"
VIDEO = R / "data/raw/partido.mp4"
MODELO = R / "models/weights/best_v4pre.pt"
CACHE = R / "data/tracking/cache_detecciones_v4pre.pkl"
GT = R / "data/annotations/ground_truth_tracking/annotations.xml"
H_ACTUAL = R / "data/calibracion/homografia.npy"
OFFSET, PASO = 7500, 15
FRAMES_CONTROL = (7500, 8250, 8985)
MAX_PERDIDA_PUNTOS = 2.0  # criterio: en ninguna zona pierde más que esto
CORTES_VILLA = (0.635, 0.877)  # terciles de m/px de docs/diagnostico_23oct_e.md
N_BOOT = 2000


def _lente():
    spec = importlib.util.spec_from_file_location("lc", R / "scripts/lente_camara.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def _detectar_un_frame(img, modelo, det, get_sliced_prediction) -> list:
    """SAHI con los parámetros de producción (por defecto de sahi: GREEDYNMM, IOS, 0,5)."""
    h, w = img.shape[:2]
    r = get_sliced_prediction(
        img,
        modelo,
        slice_height=h // det["sahi"]["filas"],
        slice_width=w // det["sahi"]["columnas"],
        overlap_height_ratio=det["sahi"]["solape"],
        overlap_width_ratio=det["sahi"]["solape"],
        verbose=0,
    )
    cajas = []
    for p in r.object_prediction_list:
        b = p.bbox
        if p.score.value < det["confianza"]:
            continue
        if (b.maxx - b.minx) * (b.maxy - b.miny) > det["max_area_caja"] * w * h:
            continue
        cajas.append([b.minx, b.miny, b.maxx, b.maxy, float(p.score.value)])
    return cajas


def detectar() -> dict:
    import cv2
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / "detecciones_original.json"
    hechos = json.load(open(ruta)) if ruta.exists() else {"original": {}, "control": {}}
    cfg = yaml.safe_load(open(CONFIG))
    det = cfg["deteccion"]
    modelo = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(MODELO),
        confidence_threshold=det["confianza"],
        device="cpu",
    )
    cache = {e["frame_idx"]: e["dets"] for e in pickle.load(open(CACHE, "rb"))["cache"]}
    frames = [OFFSET + PASO * k for k in range(100)]
    pendientes = [f for f in frames if str(f) not in hechos["original"]]
    k1, k2 = cfg["distorsion"]["k1"], cfg["distorsion"]["k2"]
    if not pendientes:
        return {"frames": len(hechos["original"]), "control": hechos["control"]}
    for f, img in leer_frames_ffmpeg(VIDEO, pendientes):
        hechos["original"][str(f)] = _detectar_un_frame(
            img, modelo, det, get_sliced_prediction
        )
        if f in FRAMES_CONTROL:
            h, w = img.shape[:2]
            K = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], float)
            corr = cv2.undistort(img, K, np.array([k1, k2, 0, 0, 0], float))
            cajas = _detectar_un_frame(corr, modelo, det, get_sliced_prediction)
            en_cache = [list(d[2:6]) for d in cache[f]]
            casadas = sum(any(iou(c, p) >= 0.9 for p in cajas) for c in en_cache)
            hechos["control"][str(f)] = f"{casadas}/{len(en_cache)}"
            print("control", f, hechos["control"][str(f)], flush=True)
        json.dump(hechos, open(ruta, "w"))
        print(f, len(hechos["original"][str(f)]), flush=True)
    return {"frames": len(hechos["original"]), "control": hechos["control"]}


def casar_centro(G: np.ndarray, D: np.ndarray) -> list:
    """Pares 1-a-1: el centro de la caja del GT cae dentro de la detección (diagnostico_23oct_e)."""
    if not len(G) or not len(D):
        return []
    cx, cy = (G[:, 0] + G[:, 2]) / 2, (G[:, 1] + G[:, 3]) / 2
    valido = (
        (cx[:, None] >= D[None, :, 0])
        & (cx[:, None] <= D[None, :, 2])
        & (cy[:, None] >= D[None, :, 1])
        & (cy[:, None] <= D[None, :, 3])
    )
    dcx, dcy = (D[:, 0] + D[:, 2]) / 2, (D[:, 1] + D[:, 3]) / 2
    coste = np.where(
        valido, np.hypot(cx[:, None] - dcx[None, :], cy[:, None] - dcy[None, :]), 1e6
    )
    filas, cols = linear_sum_assignment(coste)
    return [(int(i), int(j)) for i, j in zip(filas, cols) if valido[i, j]]


def medir() -> dict:
    from src.evaluation.gt_parser import parsear_cvat

    lc = _lente()
    H = np.load(H_ACTUAL)
    hechos = json.load(open(SALIDA / "detecciones_original.json"))
    cache = {e["frame_idx"]: e["dets"] for e in pickle.load(open(CACHE, "rb"))["cache"]}
    por_frame: dict[int, list] = {}
    for t in parsear_cvat(GT):
        if t.label != "player":
            continue
        for c in t.cajas:
            por_frame.setdefault(OFFSET + PASO * c.frame_local, []).append(c)

    def m_por_px(u, v):
        a = H @ np.array([u, v, 1.0])
        b = H @ np.array([u, v + 1.0, 1.0])
        return float(np.linalg.norm(b[:2] / b[2] - a[:2] / a[2]))

    filas, fuera_de_la_corregida = [], []
    radio_pliegue = 840.0
    centro = np.array([1280.0, 532.0])
    for f, obs in sorted(por_frame.items()):
        if str(f) not in hechos["original"]:
            continue
        Gc = np.array([[c.xtl, c.ytl, c.xbr, c.ybr] for c in obs], float)
        # el GT al original: los cuatro lados de cada caja por el polinomio; su caja envolvente
        Go = []
        for x0, y0, x1, y1 in Gc:
            esq = np.array(
                [[x0, y0], [x1, y0], [x0, y1], [x1, y1], [(x0 + x1) / 2, y1]], float
            )
            q = lc.corregida_a_original(esq)
            Go.append([q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()])
        Go = np.array(Go)
        Dc = np.array([d[2:6] for d in cache.get(f, [])], float).reshape(-1, 4)
        Do = np.array([d[:4] for d in hechos["original"][str(f)]], float).reshape(-1, 4)
        pc, po = dict(casar_centro(Gc, Dc)), dict(casar_centro(Go, Do))
        for i, g in enumerate(Gc):
            filas.append(
                {
                    "frame": f,
                    "m_px": m_por_px((g[0] + g[2]) / 2, g[3]),
                    "corregida": i in pc,
                    "original": i in po,
                    "alto_corregida": g[3] - g[1],
                    "alto_original": Go[i, 3] - Go[i, 1],
                }
            )
        if len(Do):
            pies = np.column_stack([(Do[:, 0] + Do[:, 2]) / 2, Do[:, 3]])
            fuera_de_la_corregida.append(
                int((np.hypot(*(pies - centro).T) > radio_pliegue).sum())
            )

    def zona(m):
        return (
            "cerca"
            if m <= CORTES_VILLA[0]
            else ("media" if m <= CORTES_VILLA[1] else "lejos")
        )

    rng = np.random.default_rng(0)
    res = {"frames": len({x["frame"] for x in filas}), "zonas": {}}
    for z in ("cerca", "media", "lejos", "total"):
        sel = [x for x in filas if z == "total" or zona(x["m_px"]) == z]
        fr = sorted({x["frame"] for x in sel})
        idx = {f: [x for x in sel if x["frame"] == f] for f in fr}
        a = {f: (sum(x["corregida"] for x in v), sum(x["original"] for x in v), len(v))
             for f, v in idx.items()}  # fmt: skip
        boots = []
        for _ in range(N_BOOT):
            m = [a[fr[k]] for k in rng.integers(0, len(fr), len(fr))]
            c, o, n = map(sum, zip(*m))
            boots.append(100 * (o - c) / n)
        n = len(sel)
        rc = 100 * sum(x["corregida"] for x in sel) / n
        ro = 100 * sum(x["original"] for x in sel) / n
        res["zonas"][z] = {
            "gt": n,
            "recall_corregida_pct": round(rc, 1),
            "recall_original_pct": round(ro, 1),
            "diferencia_puntos": round(ro - rc, 1),
            "ic95_diferencia": [
                round(float(q), 1) for q in np.quantile(boots, [0.025, 0.975])
            ],
            "alto_mediano_corregida_px": round(
                float(np.median([x["alto_corregida"] for x in sel])), 1
            ),
            "alto_mediano_original_px": round(
                float(np.median([x["alto_original"] for x in sel])), 1
            ),
        }
    res["control_cpu_contra_cache"] = hechos["control"]
    res["detecciones_por_frame_fuera_de_la_corregida_mediana"] = (
        float(np.median(fuera_de_la_corregida)) if fuera_de_la_corregida else None
    )
    peor = min(
        res["zonas"][z]["diferencia_puntos"] for z in ("cerca", "media", "lejos")
    )
    res["criterio_ninguna_zona_pierde_mas_de_2"] = bool(peor >= -MAX_PERDIDA_PUNTOS)
    json.dump(res, open(SALIDA / "recall.json", "w"), indent=1, ensure_ascii=False)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["detectar", "medir"])
    a = ap.parse_args()
    print(
        json.dumps(
            {"detectar": detectar, "medir": medir}[a.accion](),
            indent=1,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
