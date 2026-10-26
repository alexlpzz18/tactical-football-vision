#!/usr/bin/env python
"""CELDA DE COLAB: la puntuación de chaleco dentro de la pasada de detección (modo `full`, GPU).

docs/diagnostico_23oct_f.md, bloque 1. **No se ejecuta en el Mac**: hace falta la GPU y, sobre
todo, el decodificador de Colab. En local se probó todo lo que no es SAHI con el ffmpeg CLI y salió
idéntico al 100 %, pero eso es el mismo código sobre los mismos píxeles. Lo que puede romperse es
que `cv2.VideoCapture` en Linux (FFmpeg) dé píxeles distintos de los del ffmpeg CLI.

En Colab, desde la raíz del repo, con `data/` montado y GPU:

    !python scripts/colab_chaleco_full.py --salida /content/chaleco_full

⚠️ 25-oct: la primera ejecución reventó al final de la pasada A con «arbitro.viterbi está
ENCENDIDO… y no hay puntuación de chaleco». La causa era ESTA celda: el config A quitaba la banda
pero dejaba la pista encendida (F7), y `procesar_partido` corre `desde_cache` tras detectar
(docs/diagnostico_25oct_chaleco_colab.md). Ahora A apaga la pista con su propio YAML de equipos y,
antes de las pasadas largas, un CHEQUEO PREVIO de 3 frames comprueba que la caché sale con la
clave `chaleco`.

Pasos, sobre el tramo de 60 s del minuto 5 del benjamín:
0. Chequeo previo (3 frames, con banda): la caché tiene que llevar una puntuación de chaleco por
   detección; si no, se para aquí con un mensaje claro, sin gastar la pasada larga.
1. Modo `full` SIN banda (`chaleco_banda: null`) y con la PISTA APAGADA (`arbitro.viterbi.activo:
   false`), cronometrado → caché A.
2. Modo `full` CON banda → caché B, que lleva la clave `chaleco`.
   - Mismo modelo y mismas cajas: A y B tienen que tener las MISMAS detecciones.
3. La pasada aparte (`scripts/cache_chaleco.py`, ffmpeg CLI) sobre las cajas de B → caché C.
4. Criterios:
   (1) B["chaleco"] contra C: ≥ 99 % de las detecciones a ± 0,005;
   (2) la pista Viterbi de `desde_cache` con B (sin `rutas.cache_chaleco`) contra la de B + C:
       ≥ 99,9 % de los frames iguales;
   (3) coste: (ms/frame de B − ms/frame de A) / ms/frame de A < 5 %.
       ⚠️ El ruido de la GPU entre dos pasadas puede ser del orden del efecto; se informa también
       el tiempo del chaleco medido DENTRO del bucle.
"""

import argparse
import json
import pickle
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
BASE = R / "configs/processor_benja_parte_entera.yaml"
TRAMO = {"min_ini": 5.0, "dur_seg": 60}


def config(
    salida: Path, nombre: str, con_banda: bool, max_frames: int | None = None
) -> Path:
    """Config del modo full para la pasada `nombre`.

    Sin banda, la pista del árbitro se APAGA con un YAML de equipos propio: un F7 con la pista
    encendida y sin banda es incoherente (no habría puntuación) y el processor lo rechaza antes de
    detectar (`comprobar_chaleco_antes_de_detectar`).
    """
    cfg = yaml.safe_load(open(BASE))
    cfg["modo"] = "full"
    cfg["muestreo"]["tramo"] = dict(TRAMO)
    cfg["muestreo"]["max_frames"] = max_frames
    cfg["checkpoint"] = {"cada_frames": 0, "reanudar": False}
    if not con_banda:
        cfg["deteccion"]["chaleco_banda"] = None
        equipos = yaml.safe_load(open(R / cfg["config_equipos"]))
        equipos.setdefault("arbitro", {}).setdefault("viterbi", {})["activo"] = False
        ruta_eq = salida / f"equipos_{nombre}_sin_pista.yaml"
        ruta_eq.write_text(yaml.safe_dump(equipos, allow_unicode=True))
        cfg["config_equipos"] = str(ruta_eq)
    cfg["rutas"].pop("cache_chaleco", None)
    cfg["rutas"].update(
        cache=str(salida / f"cache_{nombre}.pkl"),
        cache_colores=str(salida / f"colores_{nombre}.pkl"),
        salida_csv=str(salida / f"pos_{nombre}.csv"),
        salida_meta=str(salida / f"pos_{nombre}_meta.json"),
    )
    ruta = salida / f"config_{nombre}.yaml"
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    return ruta


def chequeo_previo(salida: Path, cfg_a: Path, cfg_b: Path) -> dict:
    """ANTES de las pasadas largas: configs coherentes y 3 frames de B con la clave `chaleco`.

    Corre `detectar_y_cachear` (el MISMO bucle que el modo full) sobre 9 frames originales (3 con
    `sample_every` 3) y lee la caché DEL DISCO, que es lo que leerá `desde_cache`.
    """
    from src.tracking_data.processor import (
        comprobar_chaleco_antes_de_detectar,
        detectar_y_cachear,
    )

    for ruta in (cfg_a, cfg_b):
        comprobar_chaleco_antes_de_detectar(yaml.safe_load(open(ruta)))
    ruta = config(salida, "chequeo", True, max_frames=9)
    detectar_y_cachear(yaml.safe_load(open(ruta)))
    datos = pickle.load(open(salida / "cache_chequeo.pkl", "rb"))
    dets = {(e["frame_idx"], j) for e in datos["cache"] for j in range(len(e["dets"]))}
    chaleco = datos.get("chaleco")
    if chaleco is None or set(chaleco) != dets:
        motivo = "sin clave `chaleco`" if chaleco is None else "claves distintas"
        raise SystemExit(
            "CHEQUEO PREVIO FALLIDO: la pasada de detección de 3 frames NO deja la puntuación de "
            f"chaleco en la caché ({motivo}; {len(dets)} detecciones). No se lanza la pasada "
            "larga. Mira "
            "docs/diagnostico_25oct_chaleco_colab.md."
        )
    return {
        "frames": len(datos["cache"]),
        "detecciones": len(dets),
        "puntuaciones": len(chaleco),
    }


def correr_full(ruta_cfg: Path) -> dict:
    t0 = time.time()
    p = subprocess.run(
        [
            sys.executable,
            str(R / "scripts/procesar_partido.py"),
            "--config",
            str(ruta_cfg),
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        print(p.stdout[-3000:], p.stderr[-3000:])
        raise SystemExit(f"falló el modo full con {ruta_cfg}")
    ms = [float(x) for x in re.findall(r"([\d.]+) ms/frame", p.stdout + p.stderr)]
    return {
        "segundos": round(time.time() - t0, 1),
        "ms_por_frame_log": ms[-1] if ms else None,
    }


def pista(
    cfg_ruta: Path, salida: Path, nombre: str, cache_chaleco: Path | None
) -> dict:
    import src.team_classification.arbitro_viterbi as av
    from src.tracking_data.processor import procesar_desde_cache

    cfg = yaml.safe_load(open(cfg_ruta))
    cfg["modo"] = "desde_cache"
    if cache_chaleco is not None:
        cfg["rutas"]["cache_chaleco"] = str(cache_chaleco)
    cfg["rutas"]["salida_csv"] = str(salida / f"pos_{nombre}.csv")
    captura = {}
    original = av.pista_del_arbitro

    def espia(*a):
        captura["pista"] = original(*a)
        return captura["pista"]

    av.pista_del_arbitro = espia
    try:
        procesar_desde_cache(cfg)
    finally:
        av.pista_del_arbitro = original
    return captura["pista"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg_a, cfg_b = config(salida, "A", False), config(salida, "B", True)
    previo = chequeo_previo(salida, cfg_a, cfg_b)
    print(f"✓ chequeo previo: {previo}")
    t_a, t_b = correr_full(cfg_a), correr_full(cfg_b)
    A = pickle.load(open(salida / "cache_A.pkl", "rb"))
    B = pickle.load(open(salida / "cache_B.pkl", "rb"))
    mismas_cajas = [e["dets"] for e in A["cache"]] == [e["dets"] for e in B["cache"]]
    # (3') el tiempo del chaleco DENTRO del bucle, sobre los mismos fotogramas
    from src.team_classification.chaleco import puntuaciones_del_frame
    from src.tracking_data.processor import banda_chaleco

    # 3. la pasada aparte (ffmpeg CLI) sobre las cajas de B
    ruta_c = salida / "chaleco_aparte_C.pkl"
    subprocess.run(
        [
            sys.executable,
            str(R / "scripts/cache_chaleco.py"),
            "--config",
            str(cfg_b),
            "--salida",
            str(ruta_c),
        ],
        check=True,
    )
    C = pickle.load(open(ruta_c, "rb"))
    nuevo = B.get("chaleco") or {}
    claves = set(nuevo) | set(C)
    dif = np.array([abs(nuevo.get(k, -1.0) - C.get(k, -1.0)) for k in claves])
    p_b = pista(cfg_b, salida, "pista_B", None)
    p_bc = pista(cfg_b, salida, "pista_BC", ruta_c)
    frames = set(p_b) | set(p_bc)
    iguales = sum(p_b.get(f) == p_bc.get(f) for f in frames)
    # cronómetro del chaleco solo, sobre un fotograma real repetido
    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    cfg = yaml.safe_load(open(cfg_b))
    f0 = next(e for e in B["cache"] if e["dets"])
    _f, img = next(leer_frames_ffmpeg(R / cfg["rutas"]["video"], [f0["frame_idx"]]))
    t0 = time.perf_counter()
    for _ in range(200):
        puntuaciones_del_frame(img, f0["frame_idx"], f0["dets"], banda_chaleco(cfg))
    ms_chaleco = 1000 * (time.perf_counter() - t0) / 200
    ms_a = t_a["ms_por_frame_log"] or 1000 * t_a["segundos"] / max(len(A["cache"]), 1)
    ms_b = t_b["ms_por_frame_log"] or 1000 * t_b["segundos"] / max(len(B["cache"]), 1)
    res = {
        "chequeo_previo": previo,
        "frames": len(B["cache"]),
        "mismas_cajas_A_y_B": mismas_cajas,
        "1_chaleco_dentro_contra_aparte": {
            "detecciones": len(claves),
            "identicas_mas_menos_0_005_pct": round(
                100 * float(np.mean(dif <= 0.005)), 3
            ),
            "dif_max": round(float(dif.max()), 4) if len(dif) else None,
        },
        "2_pista_identica_pct": round(100 * iguales / max(len(frames), 1), 3),
        "3_coste": {
            "A_sin_banda": t_a,
            "B_con_banda": t_b,
            "pct_B_sobre_A": round(100 * (ms_b - ms_a) / ms_a, 2),
            "ms_chaleco_por_frame_en_el_bucle": round(ms_chaleco, 3),
            "pct_chaleco_sobre_A": round(100 * ms_chaleco / ms_a, 2),
        },
    }
    res["criterios"] = {
        "1_>=99%": res["1_chaleco_dentro_contra_aparte"][
            "identicas_mas_menos_0_005_pct"
        ]
        >= 99,
        "2_>=99,9%": res["2_pista_identica_pct"] >= 99.9,
        "3_<5%_(chaleco_en_el_bucle)": res["3_coste"]["pct_chaleco_sobre_A"] < 5,
    }
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / "chaleco_full.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
