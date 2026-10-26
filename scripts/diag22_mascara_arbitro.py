#!/usr/bin/env python
"""Diagnóstico 22-oct, bloque 2: ¿ve la feature de color el torso del árbitro? Solo medición.

Criterio en `docs/diagnostico_22oct.md`. En PÍXELES del vídeo: centro del torso de las cajas que el
proxy marca como árbitro y de cajas vacías de césped (20 frames por minuto, minutos 0-19).
- 2a: fracción que SOBREVIVE a la máscara anti-césped de la feature (se borra H 35-85, S≥40, V≥40).
- 2b: lo mismo con una máscara POR POSICIÓN: un píxel sobrevive si cae fuera del rectángulo
  (H, S, V) p1-p99 del césped de cajas vacías del MISMO frame.

Uso:
    python scripts/diag22_mascara_arbitro.py --pasada outputs/arbitro_obs \\
        --salida outputs/diagnostico_22oct
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
FPS = 29.97002997002997
MASCARA_FEATURE = {"h": (35, 85), "s_min": 40, "v_min": 40}  # lo que la feature BORRA
CRITERIO = {"min_arbitro": 0.30, "max_cesped": 0.05}


def sobrevive_feature(px: np.ndarray) -> np.ndarray:
    m = MASCARA_FEATURE
    borra = (px[:, 0] >= m["h"][0]) & (px[:, 0] <= m["h"][1])
    borra &= (px[:, 1] >= m["s_min"]) & (px[:, 2] >= m["v_min"])
    return ~borra


def sobrevive_posicion(px: np.ndarray, cesped_frame: np.ndarray) -> np.ndarray:
    """Fuera del rectángulo p1-p99 del césped del mismo frame en algún canal."""
    lo = np.percentile(cesped_frame, 1, axis=0)
    hi = np.percentile(cesped_frame, 99, axis=0)
    dentro = np.all((px >= lo) & (px <= hi), axis=1)
    return ~dentro


def _frames(video, objetivo, decodificador):
    """(frame, imagen BGR) de los frames pedidos, con el decodificador elegido."""
    if decodificador == "ffmpeg":
        from src.utils.video_ffmpeg import leer_frames_ffmpeg

        yield from leer_frames_ffmpeg(video, objetivo)
        return
    import cv2

    from src.tracking_data.processor import posicionar_en_frame

    cap = cv2.VideoCapture(str(video))
    actual = posicionar_en_frame(cap, 0)
    for f in sorted(objetivo):
        while actual < f:
            cap.grab()
            actual += 1
        ok, img = cap.read()
        actual += 1
        if not ok:
            raise RuntimeError(f"no se pudo leer el frame {f}")
        yield f, img
    cap.release()


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> None:
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pasada", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument(
        "--decodificador",
        choices=["ffmpeg", "cv2"],
        default="ffmpeg",
        help="ffmpeg de línea de comandos = los píxeles de producción. 'cv2' solo para "
        "reproducir la medida del 22-oct, que en el Mac salió de AVFoundation "
        "(docs/diagnostico_22oct_c.md, bloque 0)",
    )
    args = ap.parse_args()
    pasada, salida = Path(args.pasada), Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(CONFIG))
    pu, am = _mod("puerta_chaleco_cesped"), _mod("arbitro_medicion")
    filas = pd.read_csv(pasada / "posiciones.csv")
    reales = filas[filas.es_real == 1]
    capt = pickle.load(open(pasada / "cajas.pkl", "rb"))
    crudo = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    W = am.masa_de_ventana(
        reales, crudo, pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    )
    zb = (W.x_m >= am.ZONA_PORTERO_B_X) & ((W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY)
    W["proxy"] = (W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")
    proxy = set(zip(W[W.proxy].frame, W[W.proxy].id_jugador))
    H = np.load(R / cfg["rutas"]["homografia"])
    fr_cache = np.array(sorted(capt["cache_filtrado"]))
    objetivo = sorted(
        {
            int(fr_cache[np.argmin(np.abs(fr_cache - (m * 60 + k * 3) * FPS))])
            for m in range(20)
            for k in range(20)
        }
    )
    porf = {f: g for f, g in reales.groupby("frame")}

    def a_metros(u, v):
        p = H @ np.array([u, v, 1.0])
        return p[0] / p[2], p[1] / p[2]

    tot = {"arb_feat": [0, 0], "ces_feat": [0, 0], "arb_pos": [0, 0], "ces_pos": [0, 0]}
    for f, img in _frames(R / cfg["rutas"]["video"], objetivo, args.decodificador):
        dets = [tuple(d[2:6]) for d in capt["cache_filtrado"].get(f, [])]
        cesped = []
        for x1, y1, x2, y2 in dets[:4]:
            an = x2 - x1
            for dx in pu.CRITERIO["desplazamientos_caja_vacia"]:
                c = (x1 + dx * an, y1, x2 + dx * an, y2)
                if (
                    c[0] < 0
                    or c[2] >= img.shape[1]
                    or any(pu._solapan(c, b) for b in dets)
                ):
                    continue
                xm, ym = a_metros((c[0] + c[2]) / 2, c[3])
                if 0 <= xm <= 62 and 0 <= ym <= 40:
                    cesped.append(pu.recorte_centro(img, [int(round(v)) for v in c]))
        cesped = [c for c in cesped if len(c)]
        g = porf.get(f)
        arb = []
        if g is not None:
            for r in g.itertuples():
                d = capt["obs"].get((int(r.id_jugador), f))
                if d is not None and (f, int(r.id_jugador)) in proxy:
                    arb.append(pu.recorte_centro(img, [int(round(v)) for v in dets[d]]))
        arb = [a for a in arb if len(a)]
        if not cesped:
            continue
        ces = np.vstack(cesped).astype(float)
        tot["ces_feat"][0] += int(sobrevive_feature(ces).sum())
        tot["ces_feat"][1] += len(ces)
        # el césped por posición se mide contra el rectángulo de OTRAS cajas del frame (sin fuga)
        if len(cesped) >= 2:
            for k in range(len(cesped)):
                resto = np.vstack([c for j, c in enumerate(cesped) if j != k]).astype(
                    float
                )
                s = sobrevive_posicion(cesped[k].astype(float), resto)
                tot["ces_pos"][0] += int(s.sum())
                tot["ces_pos"][1] += len(s)
        for a in arb:
            a = a.astype(float)
            tot["arb_feat"][0] += int(sobrevive_feature(a).sum())
            tot["arb_feat"][1] += len(a)
            tot["arb_pos"][0] += int(sobrevive_posicion(a, ces).sum())
            tot["arb_pos"][1] += len(a)
    frac = {k: (v[0] / v[1] if v[1] else None) for k, v in tot.items()}
    res = {
        "decodificador": args.decodificador,
        "pixeles": {k: v[1] for k, v in tot.items()},
        "fraccion_que_sobrevive": frac,
        "criterio": CRITERIO,
        "feature_discrimina": bool(
            frac["arb_feat"] is not None
            and frac["arb_feat"] >= 0.30
            and frac["ces_feat"] <= 0.05
        ),
        "posicion_discrimina": bool(
            frac["arb_pos"] is not None
            and frac["arb_pos"] >= 0.30
            and frac["ces_pos"] <= 0.05
        ),
    }
    (salida / "bloque2.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
