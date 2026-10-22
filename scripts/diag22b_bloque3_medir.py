#!/usr/bin/env python
"""Diagnóstico 22-oct (b), bloque 3: producción con la caché de color v3 contra la de hoy.

Criterios en `docs/diagnostico_22oct_b.md`. El ÁRBITRO se fija ANTES, como las DETECCIONES
(frame, caja cruda) que hoy marca el proxy de píxeles: el proxy se calcula sobre la feature que se
cambia, así que no puede usarse para juzgar la nueva.

Uso:
    python scripts/diag22b_bloque3_medir.py --v3 outputs/diagnostico_22oct_b/cache_colores_v3.pkl \\
        --base outputs/arbitro_obs/posiciones.csv --salida outputs/diagnostico_22oct_b
"""

import argparse
import importlib.util
import json
import pickle
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
MIN_OBS = 40


def caja_cruda_mas_cercana(filas, dets_crudas) -> list[int]:
    """El índice de la detección cruda más cercana a cada fila (el método del proxy)."""
    return [
        int(
            np.argmin(
                [
                    (x[0] - r.x_m) ** 2 + (x[1] - r.y_m) ** 2
                    for x in dets_crudas[r.frame]
                ]
            )
        )
        for r in filas.itertuples()
    ]


def metricas_arbitro(csv, dets_crudas, det_arbitro: set) -> dict:
    reales = csv[csv.es_real == 1].copy()
    reales["k"] = caja_cruda_mas_cercana(reales, dets_crudas)
    reales["arb"] = [(f, k) in det_arbitro for f, k in zip(reales.frame, reales.k)]
    a = reales[reales.arb]
    por_id = reales.groupby("id_jugador").agg(n=("arb", "size"), frac=("arb", "mean"))
    return {
        "detecciones_de_arbitro_con_fila": int(len(a)),
        "en_un_equipo_pct": float(100 * a.etiqueta.isin(["A", "B"]).mean()),
        "por_etiqueta": a.etiqueta.value_counts().to_dict(),
        "identidades_de_arbitro": int(
            ((por_id.n >= MIN_OBS) & (por_id.frac > 0.5)).sum()
        ),
    }


def error_equipo(csv_ruta: Path) -> float:
    salida = subprocess.run(
        [
            sys.executable,
            str(R / "scripts/comparar_escalas.py"),
            "--csv",
            f"x={csv_ruta}",
            "--dets-colores",
            "",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return float(
        re.search(r"EQUIPO EQUIVOCADO, jugadores: \d+ \(([\d.]+) %\)", salida).group(1)
    )


def main() -> None:
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import procesar_desde_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v3", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)

    # 1. producción con la caché v3 (solo cambia la ruta de la caché de color)
    csv_v3 = salida / "posiciones_v3.csv"
    if not csv_v3.exists():
        cfg = yaml.safe_load(open(CONFIG))
        cfg["modo"] = "desde_cache"
        cfg["rutas"]["cache_colores"] = str(Path(args.v3).resolve())
        cfg["rutas"]["salida_csv"] = str(csv_v3)
        cfg["rutas"]["salida_meta"] = str(salida / "posiciones_v3_meta.json")
        procesar_desde_cache(cfg)

    # 2. el árbitro, fijado con el proxy de HOY (feature v1)
    cfg = yaml.safe_load(open(CONFIG))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    spec = importlib.util.spec_from_file_location(
        "am", R / "scripts/arbitro_medicion.py"
    )
    am = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(am)
    base = pd.read_csv(args.base)
    W = am.masa_de_ventana(
        base[base.es_real == 1],
        dets,
        pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb")),
    )
    zb = (W.x_m >= am.ZONA_PORTERO_B_X) & ((W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY)
    W = W[(W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")]
    det_arbitro = set(zip(W.frame, W.k))

    v3 = pd.read_csv(csv_v3)
    res = {
        "detecciones_de_arbitro_fijadas": len(det_arbitro),
        "hoy": {
            **metricas_arbitro(base, dets, det_arbitro),
            "error_equipo_jugadores_pct": error_equipo(Path(args.base)),
        },
        "v3": {
            **metricas_arbitro(v3, dets, det_arbitro),
            "error_equipo_jugadores_pct": error_equipo(csv_v3),
        },
    }
    h, n = res["hoy"], res["v3"]
    res["criterios"] = {
        "i_error_equipo_no_sube_mas_de_0_3": n["error_equipo_jugadores_pct"]
        <= h["error_equipo_jugadores_pct"] + 0.3,
        "ii_arbitro_en_equipo_a_20_o_menos": n["en_un_equipo_pct"] <= 20.0,
        "iii_identidades_de_arbitro_bajan": n["identidades_de_arbitro"]
        < h["identidades_de_arbitro"],
        "iv_villaviciosa_no_cambia": "NO MEDIBLE (no hay vídeo de Villaviciosa en local)",
    }
    (salida / "bloque3.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
