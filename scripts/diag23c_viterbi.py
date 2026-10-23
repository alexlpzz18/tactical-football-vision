#!/usr/bin/env python
"""Diagnóstico 23-oct (c), bloque 1: el árbitro como seguimiento de un único objeto (Viterbi).

Criterio en `docs/diagnostico_23oct_c.md`. Necesita las cachés de chaleco de
`scripts/cache_chaleco.py` en `--salida` (`cache_chaleco_benja_p1.pkl`, `_benja60_v3.pkl`,
`_benja60_v4.pkl`).

Uso:
    python scripts/diag23c_viterbi.py modelo --salida outputs/diagnostico_23oct_c
    python scripts/diag23c_viterbi.py medir --salida outputs/diagnostico_23oct_c
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
sys.path.insert(0, str(R / "scripts"))
BINS = [0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 1.0001]
MODELO = R / "configs/arbitro_viterbi_benja.json"
CONFIGS = {
    "benja": (
        R / "configs/processor_benja_parte_entera.yaml",
        "cache_chaleco_benja_p1.pkl",
    ),
    "benja60_v3": (R / "configs/processor_benja.yaml", "cache_chaleco_benja60_v3.pkl"),
    "benja60_v4": (
        R / "configs/processor_benja_v4.yaml",
        "cache_chaleco_benja60_v4.pkl",
    ),
}
HOY = R / "outputs/diagnostico_22oct_d/posiciones_hoy.csv"


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def modelo(salida: Path) -> dict:
    """log LR por bins, con la verdad del árbitro del 23-oct (a) en la ventana del GT."""
    import pandas as pd
    from scipy.optimize import linear_sum_assignment

    from src.team_classification.arbitro_viterbi import estimar_modelo
    from src.tracking.cache_io import cargar_cache

    inv, col = _mod("diag22e_invariantes"), _mod("diag22g_color")
    cfg = yaml.safe_load(open(CONFIGS["benja"][0]))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    chaleco = pickle.load(open(salida / CONFIGS["benja"][1], "rb"))
    fk = inv.con_caja(pd.read_csv(HOY), dets)
    gt = col.gt_de("benja")
    arb, jug = [], []
    for f, obs in gt.items():  # la MISMA verdad que diag23a_chaleco.py
        g = fk[fk.frame == f]
        if not len(g):
            continue
        D = np.array([dets[f][k][:2] for k in g.k])
        P = np.array([o.pos for o in obs])
        coste = np.hypot(D[None, :, 0] - P[:, None, 0], D[None, :, 1] - P[:, None, 1])
        for i, j in zip(*linear_sum_assignment(np.where(coste > 1.0, 1e6, coste))):
            if coste[i, j] <= 1.0:
                jug.append(chaleco.get((f, int(g.k.iloc[j])), 0.0))
        for j, (x, y) in enumerate(D):
            if (
                np.min(np.hypot(P[:, 0] - x, P[:, 1] - y)) > 3.0
                and 2 <= x <= 60
                and 2 <= y <= 38
            ):
                arb.append(chaleco.get((f, int(g.k.iloc[j])), 0.0))
    m = estimar_modelo(np.array(arb), np.array(jug), BINS)
    MODELO.write_text(json.dumps(m, indent=1))
    return m


def pasada(nombre: str, pata: str, salida: Path, vit: dict | None):
    """CSV + la pista capturada + el caché filtrado del tracker."""
    import src.team_classification.arbitro_viterbi as av
    import src.team_classification.pipeline_equipos as pe
    from src.tracking_data.processor import procesar_desde_cache

    config, chal = CONFIGS[pata]
    cfg = yaml.safe_load(open(config))
    cfg["modo"] = "desde_cache"
    csv = salida / f"viterbi_{pata}_{nombre}.csv"
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(salida / f"viterbi_{pata}_{nombre}_meta.json")
    cfg["rutas"]["cache_chaleco"] = str(salida / chal)
    captura = {}
    original_cfg, original_pista = pe.cargar_config_equipos, av.pista_del_arbitro

    def con_flag(ruta):
        ce = original_cfg(ruta)
        if vit is not None:
            ce.setdefault("arbitro", {})["viterbi"] = {
                "activo": True,
                "modelo_emision": str(MODELO),
                **vit,
            }
        return ce

    def espia(cache, chaleco, mod, params, dims):
        p = original_pista(cache, chaleco, mod, params, dims)
        captura.update(pista=p, cache=cache, chaleco=chaleco, modelo=mod)
        return p

    pe.cargar_config_equipos, av.pista_del_arbitro = con_flag, espia
    try:
        procesar_desde_cache(cfg)
    finally:
        pe.cargar_config_equipos, av.pista_del_arbitro = original_cfg, original_pista
    return csv, captura


def metricas_pista(captura, chaleco_real=None) -> dict:
    """Cobertura, velocidad y cuánto de la pista tiene chaleco (con la emisión REAL)."""
    from src.team_classification.arbitro_viterbi import log_lr

    pista, cache = captura["pista"], captura["cache"]
    dets = {e["frame_idx"]: e["dets"] for e in cache}
    t_de = {e["frame_idx"]: e["t"] for e in cache}
    fs = sorted(pista)
    pos = np.array([dets[f][pista[f]][:2] for f in fs])
    t = np.array([t_de[f] for f in fs])
    v = (
        np.hypot(*np.diff(pos, axis=0).T) / np.maximum(np.diff(t), 1e-6)
        if len(fs) > 1
        else []
    )
    ch = chaleco_real if chaleco_real is not None else captura["chaleco"]
    llr = log_lr(np.array([ch.get((f, pista[f]), 0.0) for f in fs]), captura["modelo"])
    return {
        "cobertura_pct": round(100 * len(fs) / max(len(cache), 1), 1),
        "pasos_mas_de_9_m_s_pct": (
            round(100 * float(np.mean(np.asarray(v) > 9.0)), 2) if len(v) else None
        ),
        "pista_con_chaleco_pct_(llr_real>0)": round(100 * float(np.mean(llr > 0)), 1),
    }


def cambios_a_otro(hoy, nueva):
    cols = ["frame", "x_m", "y_m"]
    a = hoy[hoy.es_real == 1][cols + ["etiqueta", "id_jugador"]]
    b = nueva[nueva.es_real == 1][cols + ["etiqueta"]]
    j = a.merge(b, on=cols, suffixes=("_hoy", "_nueva"))
    eq = j.etiqueta_hoy.astype(str).str.replace("portero_", "").isin(["A", "B"])
    return j[eq & (j.etiqueta_nueva == "otro")]


def hojas(salida, captura, csv, dets_crudos, video):
    """Las dos hojas de revisión: detecciones de la pista y filas que pasan de equipo a otro."""
    import pandas as pd

    hoja, inv = _mod("hoja_otro_v3"), _mod("diag22e_invariantes")
    filt = {e["frame_idx"]: e["dets"] for e in captura["cache"]}
    rng = np.random.default_rng(0)

    def k_crudo(f, d):
        B = np.array([x[2:6] for x in dets_crudos[f]], float)
        return int(np.argmin(np.abs(B - np.asarray(d[2:6], float)).sum(axis=1)))

    fs = sorted(captura["pista"])
    elegidos = sorted(rng.choice(fs, min(60, len(fs)), replace=False))
    filas = pd.DataFrame(
        [
            {
                "frame": int(f),
                "k": k_crudo(f, filt[f][captura["pista"][f]]),
                "x_m": filt[f][captura["pista"][f]][0],
                "y_m": filt[f][captura["pista"][f]][1],
            }
            for f in elegidos
        ]
    )
    n1 = hoja.escribir_hoja("arbitro_viterbi", filas, dets_crudos, video, lambda r: {})
    cambian = cambios_a_otro(pd.read_csv(HOY), pd.read_csv(csv))
    cambian = inv.con_caja(
        pd.read_csv(csv).merge(
            cambian[["frame", "x_m", "y_m"]], on=["frame", "x_m", "y_m"]
        ),
        dets_crudos,
    )
    elegidas = cambian.sample(n=min(60, len(cambian)), random_state=0)
    n2 = hoja.escribir_hoja(
        "viterbi_a_otro",
        elegidas.sort_values("frame"),
        dets_crudos,
        video,
        lambda r: {"id": int(r.id_jugador)},
    )
    return {
        "hoja_arbitro_viterbi": n1,
        "hoja_viterbi_a_otro": n2,
        "filas_A_B_a_otro": len(cambian),
    }


def medir(salida: Path) -> dict:
    import pandas as pd

    from src.tracking.cache_io import cargar_cache

    inv, b3, fe, col = (
        _mod(n)
        for n in (
            "diag22e_invariantes",
            "diag22b_bloque3_medir",
            "foto_de_estado",
            "diag22g_color",
        )
    )
    res = {}
    cfg = yaml.safe_load(open(CONFIGS["benja"][0]))
    dets_crudos = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    gt = col.gt_de("benja")
    variantes = {
        "hoy": None,
        "v1_sustituye": {"variante": "sustituye"},
        "v2_anade": {"variante": "anade"},
        "control_permutado_v1": {
            "variante": "sustituye",
            "control_permutar_semilla": 0,
        },
    }
    capt = {}
    for nombre, vit in variantes.items():
        csv, captura = pasada(nombre, "benja", salida, vit)
        filas = pd.read_csv(csv)
        foto = fe.medir(str(csv), gt, None, 62.0, 40.0)
        m = {
            "B_mas_de_7_pct": inv.invariantes(
                inv.recuento_por_frame(filas, 62.0, 40.0), 7
            )["pct_B_mas_del_tope"],
            "equipo_equivocado_pct": b3.error_equipo(csv),
            "centroide_m": round(float(foto["centroide"]), 3),
            "filas_A_B_a_otro": len(cambios_a_otro(pd.read_csv(HOY), filas)),
        }
        if vit is not None:
            capt[nombre] = (csv, captura)
            real = (
                capt["v1_sustituye"][1]["chaleco"] if "v1_sustituye" in capt else None
            )
            m.update(metricas_pista(captura, real))
        res[nombre] = m
    res["hojas_v1"] = hojas(
        salida,
        capt["v1_sustituye"][1],
        capt["v1_sustituye"][0],
        dets_crudos,
        R / cfg["rutas"]["video"],
    )
    # control (ii): las dos cachés de 60 s
    for pata in ("benja60_v3", "benja60_v4"):
        res[pata] = {}
        for nombre, vit in (
            ("hoy", None),
            ("v1_sustituye", {"variante": "sustituye"}),
            ("v2_anade", {"variante": "anade"}),
        ):
            csv, captura = pasada(nombre, pata, salida, vit)
            filas = pd.read_csv(csv)
            res[pata][nombre] = {
                "B_mas_de_7_pct": inv.invariantes(
                    inv.recuento_por_frame(filas, 62.0, 40.0), 7
                )["pct_B_mas_del_tope"],
                "equipo_equivocado_pct": b3.error_equipo(csv),
                **(metricas_pista(captura) if vit else {}),
            }
    h = res["hoy"]
    for v in ("v1_sustituye", "v2_anade"):
        m = res[v]
        res[f"criterio_{v}"] = {
            "B_mas_de_7_<=20": m["B_mas_de_7_pct"] <= 20.0,
            "velocidad_>9_<=1%": m["pasos_mas_de_9_m_s_pct"] is not None
            and m["pasos_mas_de_9_m_s_pct"] <= 1.0,
            "cobertura_>=80%": m["cobertura_pct"] >= 80.0,
            "error_<=1,5": m["equipo_equivocado_pct"] <= 1.5,
            "centroide_<=hoy": m["centroide_m"] <= h["centroide_m"],
            "auditoria_20_frames_y_hoja_de_jugadores": "a ojo, en el informe",
        }
    pr, pp = res["v1_sustituye"], res["control_permutado_v1"]
    res["control_i_pierde_al_arbitro"] = (
        pp["pista_con_chaleco_pct_(llr_real>0)"]
        < pr["pista_con_chaleco_pct_(llr_real>0)"] / 2
    )
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["modelo", "medir"])
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    res = modelo(salida) if args.accion == "modelo" else medir(salida)
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / f"bloque1_{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
