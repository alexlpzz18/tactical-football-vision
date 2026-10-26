#!/usr/bin/env python
"""Diagnóstico 23-oct (a), bloque 1: B2 (`tracking.corte_cruces`) en métricas de PRODUCTO.

Criterio en `docs/diagnostico_23oct_a.md`. Pipeline entero `desde_cache`, las dos patas: hoy (flag
apagado), B2 y B2 con el color permutado (control). Solo filas reales.

Uso:
    python scripts/diag23a_b2_producto.py --salida outputs/diagnostico_23oct_a
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))
DIM = {"benja": (62.0, 40.0, 7), "villa": (100.0, 64.0, 11)}


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def equipo(e) -> str:
    e = str(e)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def portero_acierta(filas, gt, mapa_de) -> dict:
    """% de las filas casadas con un portero del GT etiquetadas `portero_` de SU lado."""
    from scipy.optimize import linear_sum_assignment

    r = filas[filas.es_real == 1]
    porf = {f: g for f, g in r.groupby("frame")}
    bien = total = 0
    for f, obs in gt.items():
        g = porf.get(f)
        if g is None:
            continue
        P = np.array([o.pos for o in obs])
        xy = g[["x_m", "y_m"]].to_numpy()
        coste = np.hypot(xy[None, :, 0] - P[:, None, 0], xy[None, :, 1] - P[:, None, 1])
        coste = np.where(coste > 2.0, 1e6, coste)
        etq = g.etiqueta.astype(str).to_numpy()
        for i, j in zip(*linear_sum_assignment(coste)):
            t = str(obs[i].team)
            if coste[i, j] >= 1e6 or not t.startswith("portero_"):
                continue
            total += 1
            e = etq[j]
            bien += e.startswith("portero_") and mapa_de(e[-1]) == t[-1]
    return {"filas": total, "pct_bien": round(100 * bien / max(total, 1), 1)}


def mapa_equipos(filas, gt):
    """A/B del sistema → A/B del GT (son arbitrarias): el emparejamiento que más acierta."""
    from scipy.optimize import linear_sum_assignment

    r = filas[filas.es_real == 1]
    porf = {f: g for f, g in r.groupby("frame")}
    directo = cruzado = 0
    for f, obs in gt.items():
        g = porf.get(f)
        gente = [
            o for o in obs if o.label != "referee" and equipo(o.team) in ("A", "B")
        ]
        if g is None or not gente:
            continue
        P = np.array([o.pos for o in gente])
        xy = g[["x_m", "y_m"]].to_numpy()
        coste = np.hypot(xy[None, :, 0] - P[:, None, 0], xy[None, :, 1] - P[:, None, 1])
        coste = np.where(coste > 2.0, 1e6, coste)
        etq = g.etiqueta.map(equipo).to_numpy()
        for i, j in zip(*linear_sum_assignment(coste)):
            if coste[i, j] < 1e6 and etq[j] in ("A", "B"):
                directo += etq[j] == equipo(gente[i].team)
                cruzado += etq[j] != equipo(gente[i].team)
    if directo >= cruzado:
        return lambda s: s
    return lambda s: {"A": "B", "B": "A"}.get(s, s)


def huecos(filas) -> dict:
    """Metros de recorrido interpolado y huecos > 2,5 s sin posición dentro de una identidad."""
    metros, n_huecos, seg = 0.0, 0, 0.0
    for _i, g in filas.sort_values("tiempo_s").groupby("id_jugador"):
        x, y = g.x_m.to_numpy(), g.y_m.to_numpy()
        t, real = g.tiempo_s.to_numpy(), g.es_real.to_numpy()
        if len(g) < 2:
            continue
        paso = np.hypot(np.diff(x), np.diff(y))
        metros += float(paso[real[1:] == 0].sum())
        dt = np.diff(t)
        n_huecos += int((dt > 2.5).sum())
        seg += float(dt[dt > 2.5].sum())
    return {
        "metros_interpolados": round(metros, 1),
        "huecos_mayores_2_5s": n_huecos,
        "segundos_en_esos_huecos": round(seg, 1),
    }


def medir(pata, csv, contexto) -> dict:
    import pandas as pd

    from src.evaluation.asociacion_desde_csv import asociacion_desde_csv

    fe, inv, b3, cv = (
        _mod(n)
        for n in (
            "foto_de_estado",
            "diag22e_invariantes",
            "diag22b_bloque3_medir",
            "colab_v3_villa",
        )
    )
    largo, ancho, tope = DIM[pata]
    filas = pd.read_csv(csv)
    gt = contexto["gt"]
    foto = fe.medir(str(csv), gt, None, largo, ancho)
    inv_ = inv.invariantes(inv.recuento_por_frame(filas, largo, ancho), tope)
    mapa = mapa_equipos(filas, gt)
    m = {
        "centroide_m": round(float(foto["centroide"]), 3),
        "anchura_m": round(float(foto["anchura"]), 3),
        "ocupacion_error_pct": round(float(foto["ocupacion"]), 2),
        "otro_2_pct": inv_["pct_otro_2_o_mas"],
        "A_mas_del_tope_pct": inv_["pct_A_mas_del_tope"],
        "B_mas_del_tope_pct": inv_["pct_B_mas_del_tope"],
        "portero": portero_acierta(filas, gt, mapa),
        **huecos(filas),
        **asociacion_desde_csv(filas, gt),
    }
    if pata == "benja":
        m["equipo_equivocado_pct"] = b3.error_equipo(csv)
        m["arbitro_en_equipo_ventana_gt_pct"] = inv.arbitro_en_equipo_ventana_gt(
            inv.con_caja(filas, contexto["dets"]), contexto["det_arb"]
        )["pct"]
    else:
        mv = cv.metricas(csv, gt, largo, ancho)
        m["equipo_equivocado_pct"] = round(mv["equipo_equivocado_pct"], 2)
        a = cv.arbitro_en_equipo(filas[filas.es_real == 1], gt)
        m["arbitro_en_equipo_pct"] = round(a["pct_de_las_casadas"], 2)
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
    col, inv = _mod("diag22g_color"), _mod("diag22e_invariantes")
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
    params = dict(col.PARAMS_CRUCES)
    variantes = {
        "hoy": None,
        "b2": params,
        "b2_permutado": {**params, "control_permutar_semilla": 0},
    }
    res = {}
    for pata in ("benja", "villa"):
        res[pata] = {}
        for nombre, pc in variantes.items():
            _cap, _datos, csv = col.variante(pata, salida, pc, flag="corte_cruces")
            res[pata][nombre] = medir(pata, csv, ctx[pata])
    hb, bb, pb = (res["benja"][k] for k in ("hoy", "b2", "b2_permutado"))
    hv, bv, pv = (res["villa"][k] for k in ("hoy", "b2", "b2_permutado"))
    crit = {
        "error_benja_<=hoy+0,3": bb["equipo_equivocado_pct"]
        <= hb["equipo_equivocado_pct"] + 0.3,
        "error_villa_<=hoy+0,3": bv["equipo_equivocado_pct"]
        <= hv["equipo_equivocado_pct"] + 0.3,
        "arbitro_benja_<=35": bb["arbitro_en_equipo_ventana_gt_pct"] <= 35.0,
        "arbitro_villa_<=5,3": bv["arbitro_en_equipo_pct"] <= 5.3,
        "otro_2_benja_<=12,2": bb["otro_2_pct"] <= 12.2,
        "B_mas_de_7_benja_<=20": bb["B_mas_del_tope_pct"] <= 20.0,
        "A_mas_de_11_villa_<=hoy": bv["A_mas_del_tope_pct"] <= hv["A_mas_del_tope_pct"],
        "centroide_<=hoy+0,05": bb["centroide_m"] <= hb["centroide_m"] + 0.05
        and bv["centroide_m"] <= hv["centroide_m"] + 0.05,
        "anchura_<=hoy+0,05": bb["anchura_m"] <= hb["anchura_m"] + 0.05
        and bv["anchura_m"] <= hv["anchura_m"] + 0.05,
        "ocupacion_no_peor_0,5": bb["ocupacion_error_pct"]
        <= hb["ocupacion_error_pct"] + 0.5
        and bv["ocupacion_error_pct"] <= hv["ocupacion_error_pct"] + 0.5,
        "portero_no_peor_2_puntos": bb["portero"]["pct_bien"]
        >= hb["portero"]["pct_bien"] - 2
        and bv["portero"]["pct_bien"] >= hv["portero"]["pct_bien"] - 2,
    }
    crit["cumple"] = all(crit.values())
    res["criterio"] = crit
    res["control_color_real_gana"] = {
        "error_benja": bb["equipo_equivocado_pct"] < pb["equipo_equivocado_pct"],
        "arbitro_benja": bb["arbitro_en_equipo_ventana_gt_pct"]
        < pb["arbitro_en_equipo_ventana_gt_pct"],
        "error_villa": bv["equipo_equivocado_pct"] < pv["equipo_equivocado_pct"],
        "arbitro_villa": bv["arbitro_en_equipo_pct"] < pv["arbitro_en_equipo_pct"],
    }
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / "bloque1.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
