#!/usr/bin/env python
"""Diagnóstico 26-oct: los entornos. Criterios en `docs/diagnostico_26oct_entornos.md`.

- `chaleco`: con las cajas de la caché de Colab (`cache_B.pkl`, que lleva su puntuación de
  chaleco), recalcula la puntuación en el Mac con el ffmpeg CLI y compara puntuación y pista.
- `tracks`: corre `desde_cache` del benjamín y deja el CSV, para comparar dos entornos (supervision
  0.25.1 en un venv aparte contra 0.28.0 en el del Mac). `comparar` mide IDF1 y fragmentación de
  los dos CSV contra el GT.

Uso:
    python scripts/diag26_entornos.py chaleco --colab DIR_CHALECO_FULL --salida DIR
    python scripts/diag26_entornos.py tracks --etiqueta mac --salida DIR      # en cada entorno
    python scripts/diag26_entornos.py comparar --salida DIR
"""

import argparse
import json
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIGS = {
    "parte_entera": R / "configs/processor_benja_parte_entera.yaml",
    "60s": R / "configs/processor_benja.yaml",
}


def _pasada(cfg: dict) -> tuple[Path, dict]:
    """`desde_cache` capturando la pista del árbitro."""
    import src.team_classification.arbitro_viterbi as av
    from src.tracking_data.processor import procesar_desde_cache

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
    return Path(cfg["rutas"]["salida_csv"]), captura.get("pista") or {}


def chaleco(colab: Path, salida: Path) -> dict:
    from src.team_classification.chaleco import puntuaciones_del_frame
    from src.tracking_data.processor import (
        _build_camera_matrix,
        _corregir_distorsion,
        banda_chaleco,
    )
    from src.utils.video_ffmpeg import leer_frames_ffmpeg, tamano_video

    # copia local: leer de Google Drive frame a frame es lento y puede dar ficheros a medias
    for n in ("cache_B.pkl", "colores_B.pkl", "config_B.yaml"):
        shutil.copy(colab / n, salida / n)
    datos = pickle.load(open(salida / "cache_B.pkl", "rb"))
    cfg_colab = yaml.safe_load(open(salida / "config_B.yaml"))
    banda = banda_chaleco(cfg_colab)
    video = R / "data/raw/benja_gredos_p1_20min.mp4"
    w, h = tamano_video(video)
    K = _build_camera_matrix(w, h)
    dist = np.array(
        [cfg_colab["distorsion"]["k1"], cfg_colab["distorsion"]["k2"], 0, 0, 0], float
    )
    dets = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
    mac = {}
    for f, img in leer_frames_ffmpeg(video, [f for f in dets if dets[f]]):
        mac.update(
            puntuaciones_del_frame(
                _corregir_distorsion(img, K, dist), f, dets[f], banda
            )
        )
    pickle.dump(mac, open(salida / "chaleco_mac.pkl", "wb"))
    colab_p = datos["chaleco"]
    claves = sorted(set(mac) | set(colab_p))
    dif = np.array([abs(mac.get(k, -1.0) - colab_p.get(k, -1.0)) for k in claves])
    peores = sorted(zip(dif, claves), reverse=True)[:5]

    # la pista del árbitro con las mismas cajas: puntuación de Colab (clave de la caché) contra
    # la del Mac (rutas.cache_chaleco manda sobre la clave)
    cfg = yaml.safe_load(open(CONFIGS["parte_entera"]))
    cfg["modo"] = "desde_cache"
    cfg["muestreo"]["tramo"] = cfg_colab["muestreo"]["tramo"]
    cfg["rutas"].update(
        cache=str(salida / "cache_B.pkl"), cache_colores=str(salida / "colores_B.pkl")
    )
    pistas = {}
    for nombre, ruta_ch in (("colab", None), ("mac", salida / "chaleco_mac.pkl")):
        c = json.loads(json.dumps(cfg))
        c["rutas"].pop("cache_chaleco", None)
        if ruta_ch is not None:
            c["rutas"]["cache_chaleco"] = str(ruta_ch)
        c["rutas"]["salida_csv"] = str(salida / f"pos_{nombre}.csv")
        c["rutas"]["salida_meta"] = str(salida / f"pos_{nombre}_meta.json")
        _csv, pistas[nombre] = _pasada(c)
    frames = set(pistas["colab"]) | set(pistas["mac"])
    iguales = sum(pistas["colab"].get(f) == pistas["mac"].get(f) for f in frames)
    ffmpeg = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True
    ).stdout
    res = {
        "ffmpeg_mac": ffmpeg.splitlines()[0] if ffmpeg else None,
        "detecciones": len(claves),
        "solo_en_colab": len(set(colab_p) - set(mac)),
        "solo_en_mac": len(set(mac) - set(colab_p)),
        "dentro_de_0_01_pct": round(100 * float(np.mean(dif <= 0.01)), 3),
        "identicas_pct": round(100 * float(np.mean(dif == 0)), 3),
        "dif_max": round(float(dif.max()), 4),
        "dif_p99": round(float(np.quantile(dif, 0.99)), 4),
        "peores": [[round(float(d), 4), list(k)] for d, k in peores],
        "pista_frames_colab_mac": [len(pistas["colab"]), len(pistas["mac"])],
        "pista_identica_pct": round(100 * iguales / max(len(frames), 1), 3),
        "csv_identico": (salida / "pos_colab.csv").read_bytes()
        == (salida / "pos_mac.csv").read_bytes(),
    }
    res["criterio"] = {
        "puntuacion_+-0,01_>=99%": res["dentro_de_0_01_pct"] >= 99.0,
        "pista_>=99,9%": res["pista_identica_pct"] >= 99.9,
    }
    return res


def tracks(etiqueta: str, salida: Path) -> dict:
    import supervision

    res = {"supervision": supervision.__version__}
    for nombre, ruta in CONFIGS.items():
        cfg = yaml.safe_load(open(ruta))
        cfg["modo"] = "desde_cache"
        cfg["rutas"]["salida_csv"] = str(salida / f"tracks_{etiqueta}_{nombre}.csv")
        cfg["rutas"]["salida_meta"] = str(
            salida / f"tracks_{etiqueta}_{nombre}_meta.json"
        )
        csv, _p = _pasada(cfg)
        res[nombre] = str(csv)
    return res


def comparar(salida: Path) -> dict:
    import pandas as pd

    from src.evaluation.asociacion_desde_csv import asociacion_desde_csv
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"),
        np.load(R / "data/calibracion_benja/homografia_benja.npy"),
        9750,
        15,
    )
    res = {}
    for nombre in CONFIGS:
        m = {}
        csvs = {}
        for et in ("mac", "sv0251"):
            csvs[et] = salida / f"tracks_{et}_{nombre}.csv"
            m[et] = asociacion_desde_csv(pd.read_csv(csvs[et]), gt)
        a, b = pd.read_csv(csvs["mac"]), pd.read_csv(csvs["sv0251"])
        k = ["frame", "id_jugador"]
        j = a.merge(b, on=k, how="outer", suffixes=("_mac", "_sv"), indicator=True)
        distintas = j[
            (j["_merge"] != "both")
            | (j.etiqueta_mac != j.etiqueta_sv)
            | (j.x_m_mac != j.x_m_sv)
            | (j.y_m_mac != j.y_m_sv)
        ]
        d_idf1 = 100 * (m["sv0251"]["IDF1"] - m["mac"]["IDF1"])
        d_frag = (
            m["sv0251"]["identidades_por_persona_media"]
            - m["mac"]["identidades_por_persona_media"]
        )
        res[nombre] = {
            "mac_sv0280": m["mac"],
            "venv_sv0251": m["sv0251"],
            "csv_identico_bytes": csvs["mac"].read_bytes()
            == csvs["sv0251"].read_bytes(),
            "filas_mac_sv": [len(a), len(b)],
            "filas_distintas": int(len(distintas)),
            "identidades_mac_sv": [
                int(a.id_jugador.nunique()),
                int(b.id_jugador.nunique()),
            ],
            "dif_IDF1_puntos": round(d_idf1, 2),
            "dif_identidades_por_persona": round(d_frag, 2),
            "equivalentes": abs(d_idf1) <= 0.5 and abs(d_frag) <= 0.2,
        }
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["chaleco", "tracks", "comparar"])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--colab", default=None)
    ap.add_argument("--etiqueta", default="mac")
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    if args.accion == "chaleco":
        res = chaleco(Path(args.colab), salida)
    elif args.accion == "tracks":
        res = tracks(args.etiqueta, salida)
    else:
        res = comparar(salida)
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (
        salida
        / f"{args.accion}_{args.etiqueta if args.accion == 'tracks' else 'res'}.json"
    ).write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
