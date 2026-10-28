#!/usr/bin/env python
"""Diagnóstico 22-oct (e), bloque 0: invariantes de recuento por frame. Solo medición.

Criterio en `docs/diagnostico_22oct_e.md`. Filas REALES, dentro del campo; porteros en su equipo.
Las funciones `recuento_por_frame` y `arbitro_en_equipo_ventana_gt` las reutiliza el bloque 1.

Uso:
    python scripts/diag22e_invariantes.py --salida outputs/diagnostico_22oct_e
"""

import argparse
import importlib.util
import json
import pickle
import re
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
VENTANA_GT_BENJA = (9750, 10635)
BORDE_M = 2.0
PATAS = {
    "benja": dict(
        csv=R / "outputs/diagnostico_22oct_d/posiciones_hoy.csv",
        log=R / "outputs/diagnostico_22oct_d/posiciones_hoy.log",
        largo=62.0,
        ancho=40.0,
        tope=7,
    ),
    "villa": dict(
        csv=R / "outputs/diagnostico_22oct/villa/posiciones.csv",
        log=None,
        largo=100.0,
        ancho=64.0,
        tope=11,
    ),
}


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def equipo(etq) -> str:
    e = str(etq)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def dentro(filas, largo, ancho):
    return filas.x_m.between(0, largo) & filas.y_m.between(0, ancho)


def recuento_por_frame(filas, largo: float, ancho: float):
    """DataFrame frame × {A, B, otro}: filas REALES dentro del campo (porteros en su equipo)."""
    r = filas[(filas.es_real == 1) & dentro(filas, largo, ancho)]
    c = (
        r.assign(e=r.etiqueta.map(equipo))
        .groupby(["frame", "e"])
        .size()
        .unstack(fill_value=0)
    )
    for col in ("A", "B", "otro"):
        if col not in c:
            c[col] = 0
    return c[["A", "B", "otro"]].reindex(sorted(filas.frame.unique()), fill_value=0)


def invariantes(c, tope: int) -> dict:
    n = len(c)
    return {
        "frames": int(n),
        "media_A_B_otro": [round(float(c[k].mean()), 2) for k in ("A", "B", "otro")],
        "pct_A_mas_del_tope": round(100 * float((c.A > tope).mean()), 2),
        "pct_B_mas_del_tope": round(100 * float((c.B > tope).mean()), 2),
        "pct_otro_2_o_mas": round(100 * float((c.otro >= 2).mean()), 2),
    }


def proxy_arbitro(filas_hoy, dets):
    """Detecciones (frame, k) del árbitro según el proxy de píxeles de hoy (fijado, 22-oct b)."""
    import yaml

    am = _mod("arbitro_medicion")
    cfg = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
    W = am.masa_de_ventana(
        filas_hoy[filas_hoy.es_real == 1],
        dets,
        pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb")),
    )
    zb = (W.x_m >= am.ZONA_PORTERO_B_X) & ((W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY)
    W = W[(W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")]
    return set(zip(W.frame, W.k))


def con_caja(filas, dets):
    """Filas reales con el índice de la detección cruda MÁS CERCANA a su posición (el proxy).

    ⚠️ NO sirve para elegir la caja que se dibuja en una hoja: en un cruce la posición suavizada
    cae más cerca del OTRO (docs/auditoria_hojas.md). Para eso, `hoja_otro_v3.con_caja_de_la_fila`.
    """
    b3 = _mod("diag22b_bloque3_medir")
    r = filas[filas.es_real == 1].copy()
    r["k"] = b3.caja_cruda_mas_cercana(r, dets)
    return r


def arbitro_en_equipo_ventana_gt(filas_k, det_arbitro) -> dict:
    """% de frames de la ventana del GT (con fila de árbitro) en que esa fila es A/B."""
    v = filas_k[filas_k.frame.between(*VENTANA_GT_BENJA)]
    a = v[[(f, k) in det_arbitro for f, k in zip(v.frame, v.k)]]
    por_frame = a.groupby("frame").etiqueta.agg(
        lambda s: bool(s.map(equipo).isin(["A", "B"]).any())
    )
    return {
        "frames_con_fila_de_arbitro": int(len(por_frame)),
        "frames_con_el_arbitro_en_un_equipo": int(por_frame.sum()),
        "pct": round(100 * float(por_frame.mean()), 1) if len(por_frame) else None,
    }


def ids_guarda(log: Path) -> list[int]:
    for linea in log.read_text().splitlines():
        if "TERCER GRUPO" in linea or linea.startswith("Tercer grupo"):
            ids = [int(x) for x in re.findall(r"(\d+) \(\d+ obs en", linea)]
            if ids:
                return ids
    return []


def desglose_benja(filas, filas_k, det_arbitro, ids_g, largo, ancho) -> dict:
    import pandas as pd

    r = filas_k[dentro(filas_k, largo, ancho)]
    otro = r[r.etiqueta == "otro"].copy()
    todo_otro = (
        filas[filas.es_real == 1]
        .groupby("id_jugador")
        .etiqueta.agg(lambda s: bool((s == "otro").all()))
    )
    otro["fuente"] = np.where(
        otro.id_jugador.isin(ids_g),
        "identidad_de_la_guarda",
        np.where(
            otro.id_jugador.map(todo_otro).fillna(False),
            "identidad_otro_que_la_guarda_no_cuenta",
            "observacion_suelta_de_identidad_AB",
        ),
    )
    borde = (
        np.minimum.reduce([otro.x_m, largo - otro.x_m, otro.y_m, ancho - otro.y_m])
        <= BORDE_M
    )
    arb = np.array([(f, k) in det_arbitro for f, k in zip(otro.frame, otro.k)])
    otro["tipo"] = np.where(arb, "arbitro", np.where(borde, "borde", "interior"))
    n_frames = filas.frame.nunique()
    g = otro.groupby("frame")
    dos = g.size()[g.size() >= 2].index
    sub = otro[otro.frame.isin(dos)]

    def tipo_frame(s):
        t = sorted(s)
        n_arb = t.count("arbitro")
        if n_arb >= 2:
            return "arbitro+arbitro"
        if n_arb == 1:
            return "arbitro+" + "+".join(sorted(set(x for x in t if x != "arbitro")))
        return "sin_arbitro(" + "+".join(sorted(set(t))) + ")"

    def fuente_frame(s):
        if (s == "identidad_de_la_guarda").sum() >= 2:
            return "visible_a_la_guarda(>=2 identidades suyas)"
        if (s == "observacion_suelta_de_identidad_AB").any():
            return "con_observacion_suelta_de_identidad_AB"
        return "con_identidad_otro_que_la_guarda_no_cuenta"

    tipos = sub.groupby("frame").tipo.agg(tipo_frame).value_counts()
    fuentes = sub.groupby("frame").fuente.agg(fuente_frame).value_counts()
    return {
        "frames_otro_2_o_mas_reales": int(len(dos)),
        "pct_de_los_frames": round(100 * len(dos) / n_frames, 2),
        "tipo_de_frame": {k: int(v) for k, v in tipos.items()},
        "fuente_de_frame": {k: int(v) for k, v in fuentes.items()},
        "filas_otro_por_tipo": otro.tipo.value_counts().to_dict(),
        "filas_otro_por_fuente": otro.fuente.value_counts().to_dict(),
        "_pd": pd.__name__,
    }


def villa_ventana_gt(filas) -> dict:
    """Filas `otro` reales en la ventana del GT casadas (1-a-1, 2 m) con el árbitro / un jugador."""
    from scipy.optimize import linear_sum_assignment

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/ground_truth_tracking/annotations.xml"),
        np.load(R / "data/calibracion/homografia.npy"),
        7500,
        15,
    )
    r = filas[filas.es_real == 1]
    porf = {f: g for f, g in r.groupby("frame")}
    cuenta = {"arbitro_gt": 0, "jugador_gt": 0, "sin_casar": 0}
    for f, obs in gt.items():
        g = porf.get(f)
        if g is None:
            continue
        P = np.array([o.pos for o in obs])
        xy = g[["x_m", "y_m"]].to_numpy()
        coste = np.hypot(xy[None, :, 0] - P[:, None, 0], xy[None, :, 1] - P[:, None, 1])
        coste = np.where(coste > 2.0, 1e6, coste)
        casada = {
            int(j): obs[i].label
            for i, j in zip(*linear_sum_assignment(coste))
            if coste[i, j] < 1e6
        }
        for j, e in enumerate(g.etiqueta.to_numpy()):
            if e != "otro":
                continue
            lab = casada.get(j)
            cuenta[
                (
                    "sin_casar"
                    if lab is None
                    else ("arbitro_gt" if lab == "referee" else "jugador_gt")
                )
            ] += 1
    return cuenta


def main() -> None:
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    res = {}
    for nombre, p in PATAS.items():
        filas = pd.read_csv(p["csv"])
        c = recuento_por_frame(filas, p["largo"], p["ancho"])
        res[nombre] = {"invariantes": invariantes(c, p["tope"])}
        if nombre == "benja":
            cfg = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
            dets = {
                e["frame_idx"]: e["dets"]
                for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
            }
            det_arb = proxy_arbitro(filas, dets)
            fk = con_caja(filas, dets)
            ids_g = ids_guarda(p["log"])
            d = desglose_benja(filas, fk, det_arb, ids_g, p["largo"], p["ancho"])
            d.pop("_pd")
            # reconciliación 12,6 % (todas las filas) → 4,3 % (guarda)
            todas = filas[
                dentro(filas, p["largo"], p["ancho"]) & (filas.etiqueta == "otro")
            ]
            pct_todas = 100 * float(
                (
                    todas.groupby("frame")
                    .size()
                    .reindex(filas.frame.unique(), fill_value=0)
                    >= 2
                ).mean()
            )
            res[nombre]["reconciliacion"] = {
                "todas_las_filas_pct": round(pct_todas, 2),
                "solo_reales_pct": d["pct_de_los_frames"],
                "ids_de_la_guarda": ids_g,
                "frames_reales_otro_2_por_fuente": d["fuente_de_frame"],
            }
            res[nombre]["desglose_otro_2"] = d
            res[nombre]["arbitro_en_equipo_ventana_gt"] = arbitro_en_equipo_ventana_gt(
                fk, det_arb
            )
            v = c[(c.index >= VENTANA_GT_BENJA[0]) & (c.index <= VENTANA_GT_BENJA[1])]
            res[nombre]["ventana_gt_frames_sin_otro_pct"] = round(
                100 * float((v.otro == 0).mean()), 1
            )
        else:
            res[nombre]["ventana_gt_otro"] = villa_ventana_gt(filas)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "bloque0.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
