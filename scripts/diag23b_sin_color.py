#!/usr/bin/env python
"""Diagnóstico 23-oct (b), bloque 2: corte en cruces SIN color, contra hoy y contra el control.

Criterio en `docs/diagnostico_23oct_b.md`. Pipeline entero `desde_cache`: las dos patas (hoy, sin
color, y cortes al AZAR como control) y las dos cachés de 60 s del benjamín (control ii).

Uso:
    python scripts/diag23b_sin_color.py --salida outputs/diagnostico_23oct_b
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))
FLAG = "corte_cruces_sin_color"
PARAMS = {
    "iou_solape": 0.1,
    "dist_max_m": 1.5,
    "crecimiento_m_s": 3.0,
    "hueco_max_s": 2.5,
}


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> None:
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    col, inv, b0 = (
        _mod("diag22g_color"),
        _mod("diag22e_invariantes"),
        _mod("diag23b_bloque0"),
    )
    prod, b3 = _mod("diag23a_b2_producto"), _mod("diag22b_bloque3_medir")
    cfg = yaml.safe_load(open(col.CONFIGS["benja"]))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    hoy_b = pd.read_csv(R / "outputs/diagnostico_22oct_d/posiciones_hoy.csv")
    ctx = {
        "benja": {
            "gt": col.gt_de("benja"),
            "dets": dets,
            "det_arb": inv.proxy_arbitro(hoy_b, dets),
        },
        "villa": {"gt": col.gt_de("villa")},
    }
    variantes = {
        "hoy": None,
        "sin_color": PARAMS,
        "cortes_al_azar": {**PARAMS, "control_cortes_aleatorios_semilla": 0},
    }
    res = {}
    for pata in ("benja", "villa"):
        res[pata] = {}
        for nombre, pc in variantes.items():
            _c, _d, csv = col.variante(pata, salida, pc, flag=FLAG, nombre=nombre)
            m = prod.medir(pata, csv, ctx[pata])
            m.update(b0.huecos_pct(pd.read_csv(csv)))
            res[pata][nombre] = m
    # control (ii): las dos cachés de 60 s del benjamín
    for pata in ("benja60_v3", "benja60_v4"):
        res[pata] = {}
        for nombre, pc in (("hoy", None), ("sin_color", PARAMS)):
            _c, _d, csv = col.variante(pata, salida, pc, flag=FLAG, nombre=nombre)
            filas = pd.read_csv(csv)
            c = inv.recuento_por_frame(filas, 62.0, 40.0)
            v = c[(c.index >= 9750) & (c.index <= 10635)]
            res[pata][nombre] = {
                "frames_ventana_gt_sin_otro_pct": round(
                    100 * float((v.otro == 0).mean()), 1
                ),
                "equipo_equivocado_pct": b3.error_equipo(csv),
            }
    hb, sb, ab = (res["benja"][k] for k in ("hoy", "sin_color", "cortes_al_azar"))
    sv = res["villa"]["sin_color"]
    crit = {
        "benja_arbitro_<=10": sb["arbitro_en_equipo_ventana_gt_pct"] <= 10.0,
        "benja_error_<=1,5": sb["equipo_equivocado_pct"] <= 1.5,
        "benja_centroide_<=hoy": sb["centroide_m"] <= hb["centroide_m"],
        "benja_B_mas_de_7_<=20": sb["B_mas_del_tope_pct"] <= 20.0,
        "benja_huecos_<=hoy+0,5": sb["huecos_pct"] <= hb["huecos_pct"] + 0.5,
        "benja_IDF1_>=hoy-0,02": sb["IDF1"] >= hb["IDF1"] - 0.02,
        "villa_A_mas_de_11_<=56,6": sv["A_mas_del_tope_pct"] <= 54.6 + 2,
        "villa_centroide_<=4,47": sv["centroide_m"] <= 4.37 + 0.10,
        "villa_IDF1_>=0,422": sv["IDF1"] >= 0.442 - 0.02,
        "villa_error_<=24,1": sv["equipo_equivocado_pct"] <= 23.6 + 0.5,
    }
    crit["cumple"] = all(crit.values())
    d3 = [res["benja60_v3"][k] for k in ("hoy", "sin_color")]
    d4 = [res["benja60_v4"][k] for k in ("hoy", "sin_color")]
    res["criterio"] = crit
    res["controles"] = {
        "i_al_azar_arbitro_pct": ab["arbitro_en_equipo_ventana_gt_pct"],
        "i_la_posicion_del_corte_importa_(azar_>=_real+15)": ab[
            "arbitro_en_equipo_ventana_gt_pct"
        ]
        >= sb["arbitro_en_equipo_ventana_gt_pct"] + 15,
        "ii_v3_v4_sin_otro_cambio": [
            round(
                d3[1]["frames_ventana_gt_sin_otro_pct"]
                - d3[0]["frames_ventana_gt_sin_otro_pct"],
                1,
            ),
            round(
                d4[1]["frames_ventana_gt_sin_otro_pct"]
                - d4[0]["frames_ventana_gt_sin_otro_pct"],
                1,
            ),
        ],
        "ii_v3_v4_error_cambio": [
            round(d3[1]["equipo_equivocado_pct"] - d3[0]["equipo_equivocado_pct"], 2),
            round(d4[1]["equipo_equivocado_pct"] - d4[0]["equipo_equivocado_pct"], 2),
        ],
    }
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / "bloque2.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
