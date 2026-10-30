#!/usr/bin/env python
"""CELDA DE COLAB: detección completa del Villaviciosa cadete A, por partes, con chequeo previo.

docs/cadete_villa_preparacion.md. **No se ejecuta en el Mac** (GPU). En Colab, con `data/` montado
y GPU, la celda de siempre (CLAUDE.md, «Receta de Colab»):

    !git fetch -q && git checkout -q <rama> && pip install -q -r requirements-colab.txt && \\
        python scripts/colab_villa_cadete.py --partes 280-2900,3380-5850 --salida /content/cadete

`--partes`: segundos del ARCHIVO de inicio-fin de cada parte (los confirma Alex con el reloj
impreso en el vídeo: archivo 0:00 = 10:55:00 del reloj impreso).

Pasos:
0. Comprobaciones antes de gastar GPU: el vídeo y la homografía existen, el vídeo es 2560×1064 a
   25 fps, las partes no se solapan.
1. CHEQUEO PREVIO de 3 frames (9 originales con `sample_every` 3) al principio de la parte 1, con
   el MISMO bucle que el modo full (`detectar_y_cachear`), leyendo la caché DEL DISCO:
   - 3 frames en la caché, con la resolución 2560×1064;
   - en cada frame, entre 10 y 40 detecciones con el pie DENTRO del campo (22 jugadores + árbitro +
     asistentes, con margen); fuera de eso algo está mal (homografía, lente o detector);
   - un vector de color por cada detección;
   - el tiempo por frame, y la estimación de la pasada entera.
   Si algo falla, se para aquí con un mensaje claro.
2. Una pasada `full` por parte (`procesar_partido.py`, subproceso), con su tramo, su caché y su
   CSV. El checkpoint (cada 500 frames) permite reanudar si Colab se cae: basta con relanzar.
"""

import argparse
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path

import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
BASE = R / "configs/processor_villa_cadete.yaml"
RESOLUCION = (2560, 1064)
FPS = 25.0
DETECCIONES_EN_CAMPO = (10, 40)
FRAMES_CHEQUEO = 9  # originales: 3 procesados con sample_every 3
# Solo para PROBAR en local (CPU, homografía provisional, vídeo en otra ruta). En Colab, vacío.
SOBRESCRIBIR: dict = {}


def leer_partes(texto: str) -> list[tuple[float, float]]:
    """'280-2900,3380-5850' → [(280, 2900), (3380, 5850)], comprobando orden y solapes."""
    partes = []
    for trozo in texto.split(","):
        ini, fin = (float(v) for v in trozo.split("-"))
        if fin <= ini:
            raise SystemExit(
                f"Parte mal escrita: {trozo} (el fin va después del inicio)"
            )
        partes.append((ini, fin))
    for (_a, b), (c, _d) in zip(partes, partes[1:]):
        if c < b:
            raise SystemExit(f"Las partes se solapan: {partes}")
    return partes


def _base() -> dict:
    cfg = yaml.safe_load(open(BASE))
    if "dispositivo" in SOBRESCRIBIR:
        cfg["deteccion"]["device"] = SOBRESCRIBIR["dispositivo"]
    for clave in ("video", "homografia"):
        if clave in SOBRESCRIBIR:
            cfg["rutas"][clave] = SOBRESCRIBIR[clave]
    return cfg


def config(
    salida: Path, nombre: str, ini_s: float, dur_s: float, max_frames=None
) -> Path:
    cfg = _base()
    cfg["modo"] = "full"
    cfg["muestreo"]["tramo"] = {"min_ini": ini_s / 60.0, "dur_seg": dur_s}
    cfg["muestreo"]["max_frames"] = max_frames
    if max_frames is not None:
        cfg["checkpoint"] = {"cada_frames": 0, "reanudar": False}
    cfg["rutas"].update(
        cache=str(salida / f"cache_{nombre}.pkl"),
        cache_colores=str(salida / f"colores_{nombre}.pkl"),
        salida_csv=str(salida / f"posiciones_{nombre}.csv"),
        salida_meta=str(salida / f"posiciones_{nombre}_meta.json"),
    )
    ruta = salida / f"config_{nombre}.yaml"
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    return ruta


def comprobar_entradas() -> None:
    cfg = _base()
    video, homografia = R / cfg["rutas"]["video"], R / cfg["rutas"]["homografia"]
    faltan = [str(p) for p in (video, homografia) if not p.exists()]
    if faltan:
        raise SystemExit(
            f"Faltan {faltan}. El vídeo se copia de Drive a esa ruta; la homografía sale de "
            "outputs/calibrar_villa_cadete.html (los clics de Alex)."
        )
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    s = json.loads(salida)["streams"][0]
    num, den = (int(v) for v in s["r_frame_rate"].split("/"))
    if (s["width"], s["height"]) != RESOLUCION or abs(num / den - FPS) > 0.01:
        raise SystemExit(
            f"El vídeo no es el esperado: {s} (se esperaba {RESOLUCION} a {FPS} fps)"
        )


def chequeo_previo(salida: Path, parte1: tuple[float, float]) -> dict:
    from src.tracking_data.processor import detectar_y_cachear

    ruta = config(salida, "chequeo", parte1[0], parte1[1] - parte1[0], FRAMES_CHEQUEO)
    t0 = time.time()
    detectar_y_cachear(yaml.safe_load(open(ruta)))
    segundos = time.time() - t0
    datos = pickle.load(open(salida / "cache_chequeo.pkl", "rb"))
    colores = pickle.load(open(salida / "colores_chequeo.pkl", "rb"))
    cfg = _base()
    largo, ancho = cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]
    problemas = []
    if len(datos["cache"]) != 3:
        problemas.append(f"{len(datos['cache'])} frames en la caché (se esperaban 3)")
    if tuple(datos["wh"]) != RESOLUCION:
        problemas.append(f"resolución {datos['wh']} (se esperaba {RESOLUCION})")
    en_campo = []
    for e in datos["cache"]:
        n = sum(1 for d in e["dets"] if 0 <= d[0] <= largo and 0 <= d[1] <= ancho)
        en_campo.append(n)
        if not DETECCIONES_EN_CAMPO[0] <= n <= DETECCIONES_EN_CAMPO[1]:
            problemas.append(
                f"frame {e['frame_idx']}: {n} detecciones con el pie en el campo "
                f"(se esperaban {DETECCIONES_EN_CAMPO}): ¿homografía, lente o detector?"
            )
    n_dets = sum(len(e["dets"]) for e in datos["cache"])
    n_col = len(colores) if hasattr(colores, "__len__") else -1
    if n_col != n_dets:
        problemas.append(f"{n_col} vectores de color para {n_dets} detecciones")
    if problemas:
        raise SystemExit(
            "CHEQUEO PREVIO FALLIDO, no se lanza la pasada larga:\n- "
            + "\n- ".join(problemas)
        )
    return {
        "frames": len(datos["cache"]),
        "detecciones_en_campo": en_campo,
        "segundos_por_frame_procesado": round(segundos / 3, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--partes", required=True, help="segundos del archivo: 280-2900,3380-5850"
    )
    ap.add_argument("--salida", required=True)
    ap.add_argument("--solo-chequeo", action="store_true")
    # solo para probar en local; en Colab no se pasan
    ap.add_argument("--dispositivo", default=None)
    ap.add_argument("--video", default=None)
    ap.add_argument("--homografia", default=None)
    args = ap.parse_args()
    for clave in ("dispositivo", "video", "homografia"):
        if getattr(args, clave):
            SOBRESCRIBIR[clave] = getattr(args, clave)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    partes = leer_partes(args.partes)
    comprobar_entradas()
    previo = chequeo_previo(salida, partes[0])
    total_frames = sum((b - a) * FPS / 3 for a, b in partes)
    # cota SUPERIOR: el tiempo del chequeo incluye cargar el modelo y posicionarse en el vídeo
    previo["estimacion_horas_cota_superior"] = round(
        total_frames * previo["segundos_por_frame_procesado"] / 3600, 1
    )
    print(f"✓ chequeo previo: {previo}", flush=True)
    if args.solo_chequeo:
        return
    resultados = {"chequeo_previo": previo, "partes": {}}
    for n, (a, b) in enumerate(partes, start=1):
        ruta = config(salida, f"parte{n}", a, b - a)
        t0 = time.time()
        subprocess.run(
            [
                sys.executable,
                str(R / "scripts/procesar_partido.py"),
                "--config",
                str(ruta),
            ],
            check=True,
        )
        resultados["partes"][f"parte{n}"] = {
            "archivo_s": [a, b],
            "minutos_gpu": round((time.time() - t0) / 60, 1),
            "csv": str(salida / f"posiciones_parte{n}.csv"),
        }
        print(f"✓ parte {n}: {resultados['partes'][f'parte{n}']}", flush=True)
    (salida / "resumen.json").write_text(
        json.dumps(resultados, indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
