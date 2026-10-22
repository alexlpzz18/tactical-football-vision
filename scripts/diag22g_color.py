#!/usr/bin/env python
"""Diagnóstico 22-oct (g), bloque B: asociación de ByteTrack con término de color.

Criterio en `docs/diagnostico_22oct_g.md`. Sin vídeo: las features de color ya están cacheadas.
- `calibrar`: el umbral relativo (p99 de d / sep entre la pista y una detección limpia de la
  MISMA persona), sobre la salida de ByteTrack de HOY en el benjamín.
- `medir`: hoy contra el flag `tracking.coste_color` encendido (y el control permutado), en la
  parte entera del benjamín, en Villaviciosa y en las dos cachés de 60 s del benjamín (v3, v4).

Uso:
    python scripts/diag22g_color.py calibrar --salida outputs/diagnostico_22oct_g
    python scripts/diag22g_color.py medir --salida outputs/diagnostico_22oct_g --umbral X
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIGS = {
    "benja": R / "configs/processor_benja_parte_entera.yaml",
    "villa": R / "configs/processor.yaml",
    "benja60_v3": R / "configs/processor_benja.yaml",
    "benja60_v4": R / "configs/processor_benja_v4.yaml",
}
GT = {
    "benja": (
        "data/annotations/gt_benja/annotations.xml",
        "data/calibracion_benja/homografia_benja.npy",
        9750,
    ),
    "villa": (
        "data/annotations/ground_truth_tracking/annotations.xml",
        "data/calibracion/homografia.npy",
        7500,
    ),
}
PARAMS_BASE = {"lambda_rel": 0.5, "alfa": 0.2, "iou_solape": 0.1}


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def gt_de(pata: str):
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    g, h, off = GT["villa" if pata == "villa" else "benja"]
    return gt_a_por_frame(parsear_cvat(R / g), np.load(R / h), off, 15)


def separacion(config: Path) -> float:
    from src.team_classification.pipeline_equipos import (
        cargar_config_equipos,
        entrenar_clasificador,
    )
    from src.tracking.cache_io import cargar_cache

    cfg = yaml.safe_load(open(config))
    ce = cargar_config_equipos(
        cfg.get("config_equipos", "configs/team_classification.yaml")
    )
    datos = cargar_cache(R / cfg["rutas"]["cache"])
    col = pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    pr = entrenar_clasificador(col, ce, datos["cache"])._prototipos
    return float(np.linalg.norm(pr.a - pr.b))


def calibrar(salida: Path) -> dict:
    from src.team_classification.color_classifier import _solo_hs
    from src.tracking.asociacion_bytetrack import _iou_maximo

    dp = _mod("diag22f_pureza")
    captura, datos = dp.capturar(CONFIGS["benja"], salida / "calibrar_benja.csv")
    gt = gt_de("benja")
    _obs, persona = dp.casar_etapa("bytetrack", captura["bytetrack"], None, gt)
    cfg = yaml.safe_load(open(CONFIGS["benja"]))
    col = pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    sep = separacion(CONFIGS["benja"])
    dets_de = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
    iou_de: dict[int, np.ndarray] = {}
    misma, otra = [], []
    for i, ident in enumerate(captura["bytetrack"]):
        obs = sorted((int(p[0]), int(p[1])) for tr in ident for p in tr.det_idxs)
        modelo, previa = None, None
        for f, j in obs:
            if f not in iou_de:
                iou_de[f] = _iou_maximo(np.array([d[2:6] for d in dets_de[f]], float))
            limpia = iou_de[f][j] <= PARAMS_BASE["iou_solape"] and (f, j) in col
            feat = _solo_hs(col[(f, j)]) if (f, j) in col else None
            if (
                limpia
                and modelo is not None
                and (i, f) in persona
                and previa is not None
            ):
                d = float(np.linalg.norm(modelo - feat)) / sep
                (misma if persona[(i, f)] == persona[(i, previa)] else otra).append(d)
            if (i, f) in persona:
                previa = f
            if limpia:
                w = PARAMS_BASE["alfa"] * (1 - float(iou_de[f][j]))
                modelo = feat if modelo is None else (1 - w) * modelo + w * feat
    misma, otra = np.array(misma), np.array(otra)
    return {
        "separacion_A_B": round(sep, 4),
        "pares_misma_persona": int(len(misma)),
        "pares_otra_persona": int(len(otra)),
        "d_sep_misma_p50_p90_p99": [
            round(float(x), 3) for x in np.percentile(misma, [50, 90, 99])
        ],
        "d_sep_otra_p10_p50": (
            [round(float(x), 3) for x in np.percentile(otra, [10, 50])]
            if len(otra)
            else None
        ),
        "umbral_rel": round(float(np.percentile(misma, 99)), 3),
    }


def variante(pata: str, salida: Path, params_color: dict | None, por_obs: bool = True):
    """(captura, csv) de una pasada con el término de color dado (None = hoy)."""
    import src.team_classification.pipeline_equipos as pe

    dp = _mod("diag22f_pureza")
    nombre = (
        "hoy"
        if params_color is None
        else (
            "permutado"
            if params_color.get("control_permutar_semilla") is not None
            else "color"
        )
    )
    csv = salida / f"color_{pata}_{nombre}{'' if por_obs else '_sin_por_obs'}.csv"

    def ajustar(cfg):
        if params_color is None:
            return
        trk = yaml.safe_load(open(R / cfg["config_tracking"]))
        trk["coste_color"] = {"activo": True, **params_color}
        ruta = salida / f"tracking_{pata}_{nombre}.yaml"
        ruta.write_text(yaml.safe_dump(trk, allow_unicode=True))
        cfg["config_tracking"] = str(ruta)

    original = pe.etiquetar_por_observacion
    if not por_obs:
        pe.etiquetar_por_observacion = lambda *a, **k: {}
    try:
        captura, datos = dp.capturar(CONFIGS[pata], csv, ajustar)
    finally:
        pe.etiquetar_por_observacion = original
    return captura, datos, csv


def impureza(pata, captura) -> float:
    dp = _mod("diag22f_pureza")
    gt = gt_de(pata)
    _o, persona = dp.casar_etapa(
        "postproceso", captura["cosido"], captura["postproceso"], gt
    )
    por_id: dict[int, list[int]] = {}
    for (i, _f), p in persona.items():
        por_id.setdefault(i, []).append(p)
    tot = sum(len(v) for v in por_id.values())
    maj = sum(max(np.unique(v, return_counts=True)[1]) for v in por_id.values())
    return round(100 * (1 - maj / tot), 2)


def medir(salida: Path, umbral: float) -> dict:
    import pandas as pd

    b3, inv = _mod("diag22b_bloque3_medir"), _mod("diag22e_invariantes")
    res = {"umbral_rel": umbral}
    params = {**PARAMS_BASE, "umbral_rel": umbral}
    variantes = {
        "hoy": None,
        "color": params,
        "permutado": {**params, "control_permutar_semilla": 0},
    }
    for pata in ("benja", "villa", "benja60_v3", "benja60_v4"):
        res[pata] = {}
        for nombre, pc in variantes.items():
            if pata != "benja" and nombre == "permutado":
                continue
            captura, datos, csv = variante(pata, salida, pc)
            n_dets = sum(len(e["dets"]) for e in datos["cache"])
            asignadas = sum(
                len(tr.det_idxs) for ident in captura["bytetrack"] for tr in ident
            )
            m = {
                "impureza_csv": impureza(pata, captura),
                "identidades_bytetrack": len(captura["bytetrack"]),
                "identidades_finales": len(captura["cosido"]),
                "asignacion_pct": round(100 * asignadas / n_dets, 2),
            }
            if pata == "benja":
                filas = pd.read_csv(csv)
                inv_ = inv.invariantes(inv.recuento_por_frame(filas, 62.0, 40.0), 7)
                m["otro_2_pct"] = inv_["pct_otro_2_o_mas"]
                m["B_mas_de_7_pct"] = inv_["pct_B_mas_del_tope"]
                _c, _d, csv_sin = variante(pata, salida, pc, por_obs=False)
                m["error_equipo_por_identidad_pct"] = b3.error_equipo(csv_sin)
            res[pata][nombre] = m
    h, c = res["benja"]["hoy"], res["benja"]["color"]
    hv, cv = res["villa"]["hoy"], res["villa"]["color"]
    crit = {
        "impureza_benja_<=14": c["impureza_csv"] <= 14.0,
        "impureza_villa_<=11": cv["impureza_csv"] <= 11.0,
        "error_por_identidad_<=6": c["error_equipo_por_identidad_pct"] <= 6.0,
        "asignacion_benja_>=97": c["asignacion_pct"] >= 97.0,
        "asignacion_villa_>=93": cv["asignacion_pct"] >= 93.0,
        "identidades_<=+20%": c["identidades_finales"] <= 1.2 * h["identidades_finales"]
        and cv["identidades_finales"] <= 1.2 * hv["identidades_finales"],
        "otro_2_<=8": c["otro_2_pct"] <= 8.0,
        "B_mas_de_7_<=20": c["B_mas_de_7_pct"] <= 20.0,
    }
    crit["cumple"] = all(crit.values())
    d3 = (
        res["benja60_v3"]["color"]["impureza_csv"]
        - res["benja60_v3"]["hoy"]["impureza_csv"]
    )
    d4 = (
        res["benja60_v4"]["color"]["impureza_csv"]
        - res["benja60_v4"]["hoy"]["impureza_csv"]
    )
    controles = {
        "i_permutado_no_mejora_(>=_hoy-1)": res["benja"]["permutado"]["impureza_csv"]
        >= h["impureza_csv"] - 1.0,
        "ii_cambio_de_impureza_v3_v4": [round(d3, 2), round(d4, 2)],
        "ii_mismo_signo": (d3 < 0) == (d4 < 0),
    }
    res["criterio"] = crit
    res["controles"] = controles
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["calibrar", "medir"])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--umbral", type=float, default=None)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    if args.accion == "calibrar":
        res = calibrar(salida)
        nombre = "bloqueB_calibracion.json"
    else:
        res = medir(salida, args.umbral)
        nombre = "bloqueB.json"
    # los criterios salen como numpy.bool_ / numpy.float64: se pasan a tipos de Python
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / nombre).write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
