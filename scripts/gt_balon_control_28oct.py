#!/usr/bin/env python
"""Mini-hoja de CONTROL del balón inventado: ~10 frames de cada tramo que vio Alex.

docs/diagnostico_28oct_c.md, punto 2. Mismo formato y mismas teclas que `gt_balon_rapido.py`, en
OTRA página con OTRA clave del navegador, para no mezclarse con las marcas de la hoja de 200.

Uso:
    python scripts/gt_balon_control_28oct.py generar
    # abrir outputs/gt_balon_control/index.html, marcar y «Descargar CSV»
    python scripts/gt_balon_control_28oct.py leer ~/Downloads/respuestas_gt_balon_control.csv
"""

import argparse
import csv
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/gt_balon_control"
GT = R / "data/annotations/gt_balon_benja/gt_balon_control.csv"
FPS = 29.97002997002997
TRAMOS = {"14:46-14:48": (886.0, 888.5), "15:12-15:15": (912.0, 915.5)}  # archivo, s
POR_TRAMO = 10


def _gbr():
    spec = importlib.util.spec_from_file_location(
        "gbr", R / "scripts/gt_balon_rapido.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def generar() -> None:
    import cv2

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    gbr = _gbr()
    gv_spec = importlib.util.spec_from_file_location(
        "gv", R / "scripts/generar_video_detecciones.py"
    )
    gv = importlib.util.module_from_spec(gv_spec)
    gv_spec.loader.exec_module(gv)
    activo = gv.balon_activo(
        gbr.CACHE_BALON,
        R / "outputs/diagnostico_26oct_b/posiciones_main.csv",
        gbr.CAMPO,
    )
    todas = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(open(gbr.CACHE_BALON, "rb"))["cache"]
    }
    filas = []
    for nombre, (t0, t1) in TRAMOS.items():
        fs = [f for f in sorted(todas) if t0 * FPS <= f <= t1 * FPS]
        for f in [fs[int(i)] for i in np.linspace(0, len(fs) - 1, POR_TRAMO)]:
            sel = activo.get(f)
            eleg = [float(v) for v in sel[0][2:6]] if sel is not None else None
            filas.append(
                {
                    "frame": int(f),
                    "zona": nombre,
                    "elegida": eleg,
                    "otras": [
                        [float(v) for v in d[2:6]]
                        for d in todas.get(f, [])
                        if eleg is None or [float(v) for v in d[2:6]] != eleg
                    ],
                    "relojes": gbr.relojes(int(f)),
                }
            )
    (SALIDA / "img").mkdir(parents=True, exist_ok=True)
    for f, img in leer_frames_ffmpeg(gbr.VIDEO, [r["frame"] for r in filas]):
        cv2.imwrite(str(SALIDA / f"img/f{f}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    (SALIDA / "frames.json").write_text(json.dumps({"filas": filas}, indent=1))
    pagina = (
        gbr.PAGINA.replace("__FILAS__", json.dumps(filas))
        .replace('"gt_balon_rapido_23oct_f"', '"gt_balon_control_28oct"')
        .replace('"respuestas_gt_balon.csv"', '"respuestas_gt_balon_control.csv"')
        .replace(
            "<title>GT rápido del balón</title>",
            "<title>Control: balón inventado</title>",
        )
    )
    assert (
        '"gt_balon_control_28oct"' in pagina
        and "respuestas_gt_balon_control.csv" in pagina
    )
    (SALIDA / "index.html").write_text(pagina)
    print(
        f"✓ {len(filas)} frames ({POR_TRAMO} por tramo) · abre {SALIDA / 'index.html'}"
    )


def leer(ruta: Path) -> None:
    filas = list(csv.DictReader(open(ruta)))
    GT.parent.mkdir(parents=True, exist_ok=True)
    with open(GT, "w", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["frame", "zona", "respuesta", "x_px", "y_px"]
        )
        w.writeheader()
        w.writerows(filas)
    print(f"✓ {len(filas)} respuestas → {GT}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["generar", "leer"])
    ap.add_argument("csv", nargs="?")
    args = ap.parse_args()
    generar() if args.accion == "generar" else leer(Path(args.csv))


if __name__ == "__main__":
    main()
