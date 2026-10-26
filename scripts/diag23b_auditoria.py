#!/usr/bin/env python
"""Diagnóstico 23-oct (b), bloque 3: auditoría visual de la mejor variante.

- `paneles`: 20 frames con B > 7 (semilla 0), con TODAS las cajas reales del frame dibujadas con su
  etiqueta e identidad, para decir qué es la fila de más.
- `render`: vídeo con etiquetas + pizarra del tramo 10:00-10:45 del archivo (11:33-12:18 del
  reproductor de Alex), con hoy y con la variante.

Uso:
    python scripts/diag23b_auditoria.py paneles --csv VARIANTE.csv --salida DIR
    python scripts/diag23b_auditoria.py render --csv-hoy HOY.csv --csv-variante VAR.csv --salida DIR
"""

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
FPS = 29.97002997002997
COLOR = {  # BGR
    "A": (235, 187, 183),
    "B": (6, 45, 235),
    "portero_A": (255, 255, 0),
    "portero_B": (0, 140, 255),
    "otro": (0, 255, 255),
    "staff": (150, 150, 150),
}
TRAMO_S = (600.0, 645.0)


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def relojes(frame: int) -> str:
    t = frame / FPS
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int(r // 60)}:{r % 60:04.1f} repr"


def paneles(csv: Path, salida: Path) -> None:
    import cv2
    import pandas as pd

    from src.tracking.cache_io import cargar_cache
    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    inv = _mod("diag22e_invariantes")
    cfg = yaml.safe_load(open(CONFIG))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    filas = pd.read_csv(csv)
    c = inv.recuento_por_frame(filas, 62.0, 40.0)
    con_b = sorted(int(f) for f in c.index[c.B > 7])
    rng = np.random.default_rng(0)
    elegidos = sorted(
        int(x) for x in rng.choice(con_b, min(20, len(con_b)), replace=False)
    )
    fk = inv.con_caja(filas[filas.frame.isin(elegidos)], dets)
    carpeta = salida / "paneles_B_mas_de_7"
    carpeta.mkdir(parents=True, exist_ok=True)
    lista = []
    for f, img in leer_frames_ffmpeg(R / cfg["rutas"]["video"], elegidos):
        g = fk[fk.frame == f]
        for r in g.itertuples():
            x1, y1, x2, y2 = (int(round(v)) for v in dets[f][int(r.k)][2:6])
            col = COLOR.get(str(r.etiqueta), (255, 255, 255))
            grosor = 3 if str(r.etiqueta) in ("B", "portero_B") else 1
            cv2.rectangle(img, (x1, y1), (x2, y2), col, grosor)
            cv2.putText(
                img,
                f"{r.etiqueta} #{int(r.id_jugador)}",
                (x1, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                col,
                1,
            )
        n_b = int(c.loc[f, "B"])
        cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(
            img,
            f"f{f}  {relojes(f)}  B en el campo: {n_b}  (B en grueso)",
            (8, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )
        nombre = f"f{f}.jpg"
        cv2.imwrite(str(carpeta / nombre), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        lista.append({"frame": f, "relojes": relojes(f), "B": n_b, "panel": nombre})
    (carpeta / "paneles.json").write_text(
        json.dumps(lista, indent=1, ensure_ascii=False)
    )
    print(json.dumps(lista, indent=1, ensure_ascii=False))


def render(csv_hoy: Path, csv_var: Path, salida: Path) -> None:
    import pandas as pd

    salida.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(CONFIG))
    cfg["muestreo"]["tramo"] = {
        "min_ini": TRAMO_S[0] / 60,
        "dur_seg": TRAMO_S[1] - TRAMO_S[0],
    }
    ruta_cfg = salida / "config_tramo_10m.yaml"
    ruta_cfg.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    py = sys.executable
    for nombre, csv in (("hoy", csv_hoy), ("variante", csv_var)):
        tramo = pd.read_csv(csv)
        tramo = tramo[tramo.tiempo_s.between(*TRAMO_S)]
        csv_tramo = salida / f"tramo_10m_{nombre}.csv"
        tramo.to_csv(csv_tramo, index=False)
        subprocess.run(
            [
                py,
                str(R / "scripts/generar_video_detecciones.py"),
                "--config",
                str(ruta_cfg),
                "--csv",
                str(csv_tramo),
                "--salida",
                str(salida / f"video_10m_{nombre}.mp4"),
            ],
            check=True,
        )
        subprocess.run(
            [
                py,
                str(R / "scripts/generar_replay.py"),
                "--csv",
                str(csv_tramo),
                "--salida",
                str(salida / f"pizarra_10m_{nombre}.html"),
                "--config-campo",
                str(R / "configs/campo_benja.yaml"),
                "--titulo",
                f"10:00-10:45 (archivo) · {nombre}",
            ],
            check=True,
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="accion", required=True)
    a = sub.add_parser("paneles")
    a.add_argument("--csv", required=True)
    a.add_argument("--salida", required=True)
    b = sub.add_parser("render")
    b.add_argument("--csv-hoy", required=True)
    b.add_argument("--csv-variante", required=True)
    b.add_argument("--salida", required=True)
    args = ap.parse_args()
    if args.accion == "paneles":
        paneles(Path(args.csv), Path(args.salida))
    else:
        render(Path(args.csv_hoy), Path(args.csv_variante), Path(args.salida))


if __name__ == "__main__":
    main()
