#!/usr/bin/env python
"""Diagnóstico 23-oct (f), bloque 1: el chaleco dentro de la pasada de detección.

Criterio en `docs/diagnostico_23oct_f.md`. Sin GPU: reproduce la parte del bucle de
`detectar_y_cachear` que va DESPUÉS de SAHI (`processor.features_del_frame`), con las cajas de la
caché de producción y los fotogramas del ffmpeg CLI, y compara:

1. su puntuación de chaleco con la de la pasada aparte (`cache_chaleco_benja_p1.pkl`);
2. su feature de color con la caché de colores (comprueba que el fotograma es el mismo);
3. la pista Viterbi y el CSV de `desde_cache` alimentados con la caché de detección «con chaleco»
   (y SIN `rutas.cache_chaleco`) contra la variante 2 del 23-oct (d);
4. el tiempo del chaleco por frame contra el de la feature de color y contra 95 ms/frame de GPU.

Uso:
    python scripts/diag23f_chaleco.py --salida outputs/diagnostico_23oct_f
"""

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
CHALECO_APARTE = R / "data/tracking_benja/cache_chaleco_benja_p1.pkl"
REF_D = (
    R / "outputs/diagnostico_23oct_d"
)  # variante 2 del 23-oct (d): CSV y pista capturada
MS_POR_FRAME_GPU = 95.0  # T4, benjamín (docs/plan_ablacion_1a1.md)


def reproducir(cfg: dict) -> dict:
    """La parte del bucle del modo full que va después de SAHI, frame a frame."""
    from src.team_classification.color_classifier import extraer_color_torso
    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import (
        _build_camera_matrix,
        _corregir_distorsion,
        banda_chaleco,
        features_del_frame,
    )
    from src.utils.video_ffmpeg import leer_frames_ffmpeg, tamano_video

    datos = cargar_cache(R / cfg["rutas"]["cache"])
    dets = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
    video = R / cfg["rutas"]["video"]
    w, h = tamano_video(video)
    K = _build_camera_matrix(w, h)
    dist = np.array([cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], float)
    banda = banda_chaleco(cfg)
    colores, chaleco = {}, {}
    t_color = t_ambos = 0.0
    n = 0
    for f, img in leer_frames_ffmpeg(video, [f for f in dets if dets[f]]):
        img = _corregir_distorsion(img, K, dist)
        t0 = time.perf_counter()
        c_solo, _ = features_del_frame(img, f, dets[f], extraer_color_torso)
        t1 = time.perf_counter()
        c, ch = features_del_frame(img, f, dets[f], extraer_color_torso, banda=banda)
        t2 = time.perf_counter()
        t_color += t1 - t0
        t_ambos += t2 - t1
        colores.update(c)
        chaleco.update(ch)
        n += 1
    return {
        "datos": datos,
        "colores": colores,
        "chaleco": chaleco,
        "frames": n,
        "ms_color": 1000 * t_color / max(n, 1),
        "ms_color_y_chaleco": 1000 * t_ambos / max(n, 1),
    }


def comparar_puntuaciones(nuevo: dict, aparte: dict) -> dict:
    claves = set(nuevo) | set(aparte)
    dif = np.array([abs(nuevo.get(k, -1.0) - aparte.get(k, -1.0)) for k in claves])
    return {
        "detecciones": len(claves),
        "en_las_dos": len(set(nuevo) & set(aparte)),
        "identicas_mas_menos_0_005_pct": round(100 * float(np.mean(dif <= 0.005)), 3),
        "identicas_exactas_pct": round(100 * float(np.mean(dif == 0)), 3),
        "dif_max": round(float(dif.max()), 4),
    }


def comparar_colores(nuevo: dict, cache_ruta: Path) -> dict:
    prod = pickle.load(open(cache_ruta, "rb"))
    comunes = set(nuevo) & set(prod)
    iguales = sum(np.array_equal(nuevo[k], prod[k]) for k in comunes)
    return {
        "features_nuevas": len(nuevo),
        "features_produccion": len(prod),
        "comunes": len(comunes),
        "identicas_pct": round(100 * iguales / max(len(comunes), 1), 3),
    }


def pista_con_cache_de_deteccion(rep: dict, salida: Path) -> dict:
    """`desde_cache` con la caché de detección «con chaleco» y SIN rutas.cache_chaleco."""
    import src.team_classification.arbitro_viterbi as av
    from src.tracking_data.processor import procesar_desde_cache

    ruta_det = salida / "cache_deteccion_con_chaleco.pkl"
    pickle.dump({**rep["datos"], "chaleco": rep["chaleco"]}, open(ruta_det, "wb"))
    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["cache"] = str(ruta_det)
    cfg["rutas"].pop("cache_chaleco", None)
    csv = salida / "v2_desde_cache_de_deteccion.csv"
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(salida / "v2_desde_cache_de_deteccion_meta.json")
    captura = {}
    original = av.pista_del_arbitro

    def espia(cache, chaleco, mod, params, dims):
        p = original(cache, chaleco, mod, params, dims)
        captura["pista"] = p
        return p

    av.pista_del_arbitro = espia
    try:
        procesar_desde_cache(cfg)
    finally:
        av.pista_del_arbitro = original
    ref = pickle.load(open(REF_D / "captura_v2_anade.pkl", "rb"))["pista"]
    nueva = captura["pista"]
    todos = set(ref) | set(nueva)
    iguales = sum(ref.get(f) == nueva.get(f) for f in todos)
    ruta_det.unlink()  # 9 MB de copia: no se deja en outputs
    return {
        "frames_pista_ref_nueva": [len(ref), len(nueva)],
        "pista_identica_pct": round(100 * iguales / max(len(todos), 1), 3),
        "csv_identico_a_v2_del_23oct_d": csv.read_bytes()
        == (REF_D / "v2_anade.csv").read_bytes(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(CONFIG))
    rep = reproducir(cfg)
    ms_chaleco = rep["ms_color_y_chaleco"] - rep["ms_color"]
    res = {
        "1_puntuacion_contra_la_pasada_aparte": comparar_puntuaciones(
            rep["chaleco"], pickle.load(open(CHALECO_APARTE, "rb"))
        ),
        "control_feature_de_color_contra_produccion": comparar_colores(
            rep["colores"], R / cfg["rutas"]["cache_colores"]
        ),
        "2_pista": pista_con_cache_de_deteccion(rep, salida),
        "3_coste": {
            "frames": rep["frames"],
            "ms_por_frame_color_cpu": round(rep["ms_color"], 2),
            "ms_por_frame_color_y_chaleco_cpu": round(rep["ms_color_y_chaleco"], 2),
            "ms_por_frame_chaleco_cpu": round(ms_chaleco, 2),
            "pct_de_95_ms_de_gpu": round(100 * ms_chaleco / MS_POR_FRAME_GPU, 2),
            "tamano_mb_en_la_cache": round(len(pickle.dumps(rep["chaleco"])) / 1e6, 2),
        },
    }
    p1 = res["1_puntuacion_contra_la_pasada_aparte"]["identicas_mas_menos_0_005_pct"]
    res["criterios"] = {
        "1_>=99%": p1 >= 99.0,
        "2_pista_>=99,9%": res["2_pista"]["pista_identica_pct"] >= 99.9,
        "3_coste_<5%": res["3_coste"]["pct_de_95_ms_de_gpu"] < 5.0,
        "nota": "en local: mismo código y mismo decodificador; la prueba de verdad es Colab",
    }
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / "bloque1_chaleco.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
