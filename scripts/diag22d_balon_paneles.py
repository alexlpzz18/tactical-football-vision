#!/usr/bin/env python
"""Diagnóstico 22-oct (d), bloque 3a-3b: por qué los 604 son «aéreos», y 24 paneles para mirarlos.

Criterio en `docs/diagnostico_22oct_d.md`.
- 3a: de los frames con el balón elegido a > 3 m fuera del campo, cuántos están entre las
  detecciones de SUELO (tras plausibilidad) y cuántos son vuelos readmitidos.
- 3b: 12 frames detrás del fondo (x > 65) y 12 laterales (y < −3 o y > 43), semilla 0. Panel: el
  fotograma entero reducido con la caja marcada, el zoom de la caja y la pizarra de `main`.

Uso:
    python scripts/diag22d_balon_paneles.py \\
        --base-main outputs/diagnostico_22oct_b/balon_base_main.csv \\
        --salida outputs/diagnostico_22oct_d
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
CSV_JUGADORES = R / "outputs/arbitro_obs/posiciones.csv"
CAMPO = R / "configs/campo_benja.yaml"
FPS = 29.97002997002997
N_POR_LADO, SEMILLA = 12, 0


def relojes(frame: int) -> str:
    t = frame / FPS
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int(r // 60)}:{r % 60:04.1f} repr"


def main() -> None:
    import cv2
    import pandas as pd

    from src.balon.carga import cargar_detecciones_limpias
    from src.balon.tracking_balon import _fuera_del_campo_m
    from src.campo_modelo import cargar_modelo
    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-main", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    (salida / "paneles_balon").mkdir(parents=True, exist_ok=True)

    spec = importlib.util.spec_from_file_location(
        "gv", R / "scripts/generar_video_detecciones.py"
    )
    gv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gv)
    sel = gv.balon_activo(CACHE_BALON, CSV_JUGADORES, CAMPO)  # = main (flag apagado)
    modelo = cargar_modelo(config=CAMPO)
    suelo, _t, _m = cargar_detecciones_limpias(CACHE_BALON, modelo)

    fuera = {
        f: (d, a)
        for f, (d, a) in sel.items()
        if _fuera_del_campo_m(d[0], d[1], (62.0, 40.0)) > 3.0
    }
    en_suelo = sum(
        any(np.allclose(s[:2], d[:2]) and s[6] == d[6] for s in suelo.get(f, []))
        for f, (d, _a) in fuera.items()
    )
    res = {
        "3a": {
            "frames_con_el_elegido_a_mas_de_3m": len(fuera),
            "de_ellos_entre_las_detecciones_de_suelo": int(en_suelo),
            "de_ellos_vuelos_readmitidos": len(fuera) - int(en_suelo),
            "marcados_aereos": int(sum(a for _d, a in fuera.values())),
        }
    }

    traseros = sorted(f for f, (d, _a) in fuera.items() if d[0] > 65.0)
    laterales = sorted(f for f, (d, _a) in fuera.items() if d[1] < -3.0 or d[1] > 43.0)
    rng = np.random.default_rng(SEMILLA)
    elegidos = {
        "trasero": sorted(
            int(x) for x in rng.choice(traseros, N_POR_LADO, replace=False)
        ),
        "lateral": sorted(
            int(x) for x in rng.choice(laterales, N_POR_LADO, replace=False)
        ),
    }
    res["3b_disponibles"] = {"trasero": len(traseros), "lateral": len(laterales)}
    piz = pd.read_csv(args.base_main)
    piz = piz[piz.etiqueta.astype(str).str.startswith("balon")]
    jug = pd.read_csv(CSV_JUGADORES)
    jug = jug[jug.etiqueta.isin(["A", "B", "portero_A", "portero_B", "otro"])]
    fr_j = np.array(sorted(jug.frame.unique()))
    lado_de = {f: lado for lado, fs in elegidos.items() for f in fs}
    paneles = []
    for f, img in leer_frames_ffmpeg(R / "data/raw/benja_gredos_p1_20min.mp4", lado_de):
        det, aer = sel[f]
        x1, y1, x2, y2 = (int(round(v)) for v in det[2:6])
        entero = img.copy()
        cv2.rectangle(entero, (x1 - 12, y1 - 12), (x2 + 12, y2 + 12), (0, 255, 255), 3)
        entero = cv2.resize(entero, (960, 540))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        ox = int(np.clip(cx - 120, 0, img.shape[1] - 240))
        oy = int(np.clip(cy - 90, 0, img.shape[0] - 180))
        zoom = img[slice(oy, oy + 180), slice(ox, ox + 240)].copy()
        cv2.rectangle(
            zoom,
            (x1 - ox - 3, y1 - oy - 3),
            (x2 - ox + 3, y2 - oy + 3),
            (0, 255, 255),
            1,
        )
        zoom = cv2.resize(zoom, (720, 540), interpolation=cv2.INTER_NEAREST)
        # pizarra 62x40 m a 6 px/m con 10 m de margen alrededor
        pz = np.full((540, 480, 3), (40, 110, 40), np.uint8)

        def a_px(x, y):
            return int((x + 10) * 6), int((y + 10) * 6)

        cv2.rectangle(pz, a_px(0, 0), a_px(62, 40), (255, 255, 255), 1)
        fj = fr_j[np.argmin(np.abs(fr_j - f))]
        for r in jug[jug.frame == fj].itertuples():
            cv2.circle(pz, a_px(r.x_m, r.y_m), 3, (200, 200, 200), -1)
        bx, by = det[0], det[1]
        cv2.circle(
            pz, a_px(np.clip(bx, -9, 71), np.clip(by, -9, 79)), 6, (0, 255, 255), 2
        )
        for r in piz[piz.frame == f].itertuples():
            cv2.circle(pz, a_px(r.x_m, r.y_m), 4, (0, 0, 255), -1)
        panel = np.hstack([entero, zoom, pz])
        cab = (
            f"{lado_de[f]} f{f} {relojes(f)}  balon proyectado ({bx:.0f}, {by:.0f}) m  "
            f"aereo={aer}  amarillo=caja/proyeccion  rojo=pizarra main"
        )
        panel = cv2.copyMakeBorder(panel, 30, 0, 0, 0, cv2.BORDER_CONSTANT)
        cv2.putText(
            panel, cab, (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1
        )
        nombre = f"{lado_de[f]}_{f}.jpg"
        cv2.imwrite(str(salida / "paneles_balon" / nombre), panel)
        paneles.append(
            {
                "lado": lado_de[f],
                "frame": f,
                "relojes": relojes(f),
                "x_m": round(float(bx), 1),
                "y_m": round(float(by), 1),
                "panel": nombre,
            }
        )
    res["3b_paneles"] = paneles
    (salida / "bloque3ab.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
