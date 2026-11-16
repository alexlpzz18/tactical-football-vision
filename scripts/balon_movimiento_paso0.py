#!/usr/bin/env python
"""H5, paso 0 (docs/registro_mision.md): ¿se ve el balón como MOVIMIENTO en una cámara fija?

Premisa a comprobar antes de construir nada. El detector de apariencia ve el balón en el 9 % de los
fotogramas del alevín B (mide 2-4 px en casi todo el campo). Con cámara fija, un balón en juego es
una mancha pequeña que cambia de sitio entre fotogramas.

Medida: en fotogramas donde el detector SÍ ve el balón (una candidata que no es una marca fija),
se calcula la diferencia de tres fotogramas (f−2, f, f+2: lo que cambia respecto al anterior Y al
siguiente, así no queda el «fantasma» de donde estaba antes) y se buscan manchas pequeñas.
- ¿hay una mancha a ≤ `--radio` px del balón conocido?
- ¿cuántas manchas candidatas hay por fotograma, en total y fuera de las cajas de personas?

Criterio (escrito antes): el balón conocido aparece en ≥ 80 % y hay ≤ 20 candidatas por fotograma
fuera de las personas. ⚠️ Sesgo conocido: «donde el detector lo ve» es donde el balón es más grande
(cajas de ~8 px). Por eso se informa también por tamaño de caja y por velocidad del balón.

Uso:
    python scripts/balon_movimiento_paso0.py --hasta 900 --muestras 200
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.utils.video_ffmpeg import leer_frames_ffmpeg  # noqa: E402

DATOS = R / "data/tracking_alevinb"
CELDA_PX, FIJA_SEGUNDOS = 8, 20  # las de visor_alevinb.py


def celdas_fijas(cache: list) -> set:
    segundos: dict = {}
    for e in cache:
        for d in e["dets"]:
            c = (int((d[2] + d[4]) / 2 // CELDA_PX), int((d[3] + d[5]) / 2 // CELDA_PX))
            segundos.setdefault(c, set()).add(int(e["t"]))
    return {c for c, ss in segundos.items() if len(ss) >= FIJA_SEGUNDOS}


def manchas(antes, ahora, despues, umbral: int, area_max: int):
    """Centros y áreas de las manchas pequeñas que cambian respecto a antes Y a después."""
    a = cv2.absdiff(ahora, antes).max(axis=2)
    b = cv2.absdiff(ahora, despues).max(axis=2)
    mov = (np.minimum(a, b) > umbral).astype(np.uint8)
    n, _et, stats, centros = cv2.connectedComponentsWithStats(mov, connectivity=8)
    ok = (stats[1:, cv2.CC_STAT_AREA] >= 2) & (stats[1:, cv2.CC_STAT_AREA] <= area_max)
    return centros[1:][ok], stats[1:, cv2.CC_STAT_AREA][ok]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, default=R / "data/raw/alevinb_p1.mp4")
    ap.add_argument("--balon", type=Path, default=DATOS / "cache_alevinb_p1_balon.pkl")
    ap.add_argument("--personas", type=Path, default=DATOS / "cache_alevinb_p1.pkl")
    ap.add_argument("--hasta", type=float, default=900.0)
    ap.add_argument("--muestras", type=int, default=200)
    ap.add_argument("--conf", type=float, default=0.5)
    ap.add_argument(
        "--separacion", type=int, default=2, help="fotogramas entre f y f±k"
    )
    ap.add_argument("--umbrales", type=int, nargs="+", default=[12, 20, 30])
    ap.add_argument("--area-max", type=int, default=150)
    ap.add_argument("--radio", type=float, default=6.0)
    ap.add_argument(
        "--salida", type=Path, default=R / "outputs/balon_movimiento/paso0.json"
    )
    a = ap.parse_args()

    balon = pickle.load(open(a.balon, "rb"))["cache"]
    fijas = celdas_fijas(balon)
    personas = {
        e["frame_idx"]: np.array([d[2:6] for d in e["dets"]], dtype=float).reshape(
            -1, 4
        )
        for e in pickle.load(open(a.personas, "rb"))["cache"]
    }
    por_frame = {e["frame_idx"]: e for e in balon}
    conocidos = []
    for e in balon:
        if e["t"] > a.hasta or e["frame_idx"] not in personas:
            continue
        buenas = [
            d
            for d in e["dets"]
            if d[6] >= a.conf
            and (int((d[2] + d[4]) / 2 // CELDA_PX), int((d[3] + d[5]) / 2 // CELDA_PX))
            not in fijas
        ]
        if len(buenas) == 1:
            d = buenas[0]
            conocidos.append(
                (e["frame_idx"], (d[2] + d[4]) / 2, (d[3] + d[5]) / 2, d[4] - d[2])
            )
    rng = np.random.default_rng(0)
    elegidos = sorted(
        (
            conocidos[i]
            for i in rng.choice(len(conocidos), min(a.muestras, len(conocidos)), False)
        ),
        key=lambda c: c[0],
    )
    k = a.separacion
    pedir = sorted({f + s for f, *_ in elegidos for s in (-k, 0, k) if f + s >= 0})
    imagenes = {}
    filas = {u: [] for u in a.umbrales}
    pendientes = {f: (cx, cy, lado) for f, cx, cy, lado in elegidos}
    for f, img in leer_frames_ffmpeg(a.video, pedir):
        imagenes[f] = img
        listo = f - k
        if listo in pendientes and listo - k in imagenes:
            cx, cy, lado = pendientes[listo]
            # velocidad del balón en px por fotograma, con la detección vecina (si la hay)
            vel = None
            for otro in (listo + 2, listo - 2):
                v = por_frame.get(otro)
                if v and v["dets"]:
                    d2 = min(v["dets"], key=lambda d: abs((d[2] + d[4]) / 2 - cx))
                    paso = (
                        np.hypot((d2[2] + d2[4]) / 2 - cx, (d2[3] + d2[5]) / 2 - cy) / 2
                    )
                    if paso < 40:
                        vel = float(paso)
                        break
            cajas = personas[listo]
            for u in a.umbrales:
                centros, areas = manchas(
                    imagenes[listo - k],
                    imagenes[listo],
                    imagenes[listo + k],
                    u,
                    a.area_max,
                )
                if len(centros):
                    dist = np.hypot(centros[:, 0] - cx, centros[:, 1] - cy)
                    en_persona = (
                        (centros[:, None, 0] >= cajas[None, :, 0] - 3)
                        & (centros[:, None, 0] <= cajas[None, :, 2] + 3)
                        & (centros[:, None, 1] >= cajas[None, :, 1] - 3)
                        & (centros[:, None, 1] <= cajas[None, :, 3] + 3)
                    ).any(axis=1)
                    es_balon = dist <= a.radio
                    filas[u].append(
                        (
                            bool(es_balon.any()),
                            len(centros),
                            int((~en_persona & ~es_balon).sum()),
                            float(lado),
                            vel,
                        )
                    )
                else:
                    filas[u].append((False, 0, 0, float(lado), vel))
            for viejo in [g for g in imagenes if g < listo - k]:
                del imagenes[viejo]
    res = {"fotogramas": len(elegidos), "conocidos_disponibles": len(conocidos)}
    for u, fs in filas.items():
        visto = np.array([f[0] for f in fs])
        vel = np.array([np.nan if f[4] is None else f[4] for f in fs])
        lado = np.array([f[3] for f in fs])
        res[f"umbral_{u}"] = {
            "balon_conocido_con_mancha_pct": round(100 * float(visto.mean()), 1),
            "…si_se_mueve_mas_de_1px_por_frame_pct": (
                round(100 * float(visto[vel > 1].mean()), 1)
                if (vel > 1).any()
                else None
            ),
            "…si_esta_quieto_pct": (
                round(100 * float(visto[vel <= 1].mean()), 1)
                if (vel <= 1).any()
                else None
            ),
            "…caja_menor_de_8px_pct": (
                round(100 * float(visto[lado < 8].mean()), 1)
                if (lado < 8).any()
                else None
            ),
            "manchas_por_frame_p50_p90": [
                float(np.percentile([f[1] for f in fs], q)) for q in (50, 90)
            ],
            "candidatas_fuera_de_personas_p50_p90": [
                float(np.percentile([f[2] for f in fs], q)) for q in (50, 90)
            ],
        }
    res["con_velocidad"] = int(np.isfinite(vel).sum())
    res["se_mueven"] = int((vel > 1).sum())
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
