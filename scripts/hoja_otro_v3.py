#!/usr/bin/env python
"""Hoja de revisión `otro_v3`: 60 recortes de lo que la feature v3 manda a `otro` sin ser árbitro.

docs/diagnostico_22oct_d.md, bloque 1b. De las 3.889 filas no-árbitro (por el proxy de detección)
que pasan de A/B (hoy) a `otro` (v3), se apartan las de identidades que HOY son mayoritariamente
árbitro y, del RESTO, se eligen 60 al azar (semilla 0). Un recorte por imagen, con la caja marcada,
y la identidad y la etiqueta OCULTAS (para no sesgar a quien marca). La clave queda aparte, en
`clave_otro_v3.csv`, para cruzarla después.

Los fotogramas salen del ffmpeg de línea de comandos (CLAUDE.md: medir color nunca con cv2
en el Mac).

Uso:
    python scripts/hoja_otro_v3.py --pasadas outputs/diagnostico_22oct_c
    # y después, para marcar:
    python scripts/revision_equipos.py html --ventana otro_v3
"""

import argparse
import importlib.util
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
HOJA = R / "outputs/hoja_equipos"
VENTANA = "otro_v3"
N_RECORTES, SEMILLA = 60, 0
FPS = 29.97002997002997
DESFASE_REPRODUCTOR_S = 93
LADO_RECORTE_PX = 200  # alrededor del centro de la caja, en píxeles del vídeo
ESCALA = 3  # el recorte se amplía ×3 para verlo


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def reloj(segundos: float) -> str:
    return f"{int(segundos // 60)}:{segundos % 60:04.1f}"


def main() -> None:
    import cv2
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache
    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pasadas", required=True)
    args = ap.parse_args()
    pas = Path(args.pasadas)
    cfg = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }

    c3, b3, am = (
        _mod("diag22c_v3"),
        _mod("diag22b_bloque3_medir"),
        _mod("arbitro_medicion"),
    )
    base = pd.read_csv(pas / "posiciones_hoy.csv")
    v3 = pd.read_csv(pas / "posiciones_v3.csv")
    W = am.masa_de_ventana(
        base[base.es_real == 1],
        dets,
        pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb")),
    )
    zb = (W.x_m >= am.ZONA_PORTERO_B_X) & ((W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY)
    W = W[(W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")]
    mov, _nv = c3.filas_movidas(base, v3, dets, set(zip(W.frame, W.k)), b3)
    resto = mov[mov.clase != "arbitro_por_identidad"]
    n_arb = int((mov.clase == "arbitro_por_identidad").sum())
    print(f"movidas {len(mov)}: de identidades árbitro hoy {n_arb}, resto {len(resto)}")
    elegidas = resto.sample(
        n=min(N_RECORTES, len(resto)), random_state=SEMILLA
    ).sort_values("frame")

    carpeta = HOJA / VENTANA
    carpeta.mkdir(parents=True, exist_ok=True)
    por_frame = {}
    for r in elegidas.itertuples():
        por_frame.setdefault(int(r.frame), []).append(r)
    cajas, clave, n = [], [], 0
    for f, img in leer_frames_ffmpeg(R / cfg["rutas"]["video"], por_frame):
        alto_img, ancho_img = img.shape[:2]
        for r in por_frame[f]:
            x1, y1, x2, y2 = (float(v) for v in dets[f][int(r.k)][2:6])
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            ox = int(np.clip(cx - LADO_RECORTE_PX / 2, 0, ancho_img - LADO_RECORTE_PX))
            oy = int(np.clip(cy - LADO_RECORTE_PX / 2, 0, alto_img - LADO_RECORTE_PX))
            filas = slice(oy, oy + LADO_RECORTE_PX)
            columnas = slice(ox, ox + LADO_RECORTE_PX)
            rec = img[filas, columnas]
            rec = cv2.resize(
                rec, None, fx=ESCALA, fy=ESCALA, interpolation=cv2.INTER_NEAREST
            )
            t = f / FPS
            nombre = f"{n:02d}_{reloj(t).replace(':', '-')}.jpg"
            cv2.imwrite(str(carpeta / nombre), rec, [cv2.IMWRITE_JPEG_QUALITY, 95])
            caja = {
                "ventana": VENTANA,
                "imagen": nombre,
                "frame": f,
                "reloj_archivo": reloj(t),
                "reloj_reproductor": reloj(t + DESFASE_REPRODUCTOR_S),
                "caja": 0,
                "id_jugador": "",  # OCULTA a propósito
                "etiqueta": "?",  # OCULTA a propósito
                "x1": int((x1 - ox) * ESCALA),
                "y1": int((y1 - oy) * ESCALA),
                "x2": int((x2 - ox) * ESCALA),
                "y2": int((y2 - oy) * ESCALA),
                "x_m": round(float(r.x_m), 2),
                "y_m": round(float(r.y_m), 2),
            }
            cajas.append(caja)
            clave.append(
                {
                    "imagen": nombre,
                    "frame": f,
                    "k": int(r.k),
                    "id_hoy": int(r.id_jugador),
                    "etiqueta_hoy": r.etiqueta,
                    "id_v3": int(r.id_jugador_v3),
                    "clase": r.clase,
                    "mecanismo": r.mecanismo,
                }
            )
            n += 1
    pd.DataFrame(cajas).to_csv(HOJA / f"cajas_{VENTANA}.csv", index=False)
    pd.DataFrame(clave).to_csv(HOJA / f"clave_{VENTANA}.csv", index=False)
    print(f"✓ {n} recortes en {carpeta}; cajas en cajas_{VENTANA}.csv; clave aparte")


if __name__ == "__main__":
    main()
