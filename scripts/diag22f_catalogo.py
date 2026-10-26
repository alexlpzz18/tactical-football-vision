#!/usr/bin/env python
"""Diagnóstico 22-oct (f), bloque B: el segundo «otro», y el catálogo que requiere identidad.

Criterio en `docs/diagnostico_22oct_f.md`.
- B1: quién es el «otro» extra (ventana del GT y, si no hay casos, el partido entero sin GT).
- X: la fracción mínima por trozo, fijada con la distribución de los tracklets ANTES de medir B3.
- B3: el flag `arbitro.catalogo_requiere_identidad` encendido, y el control permutado.

Uso:
    python scripts/diag22f_catalogo.py --salida outputs/diagnostico_22oct_f
"""

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
HOY = R / "outputs/diagnostico_22oct_d/posiciones_hoy.csv"
VENTANA_S, MIN_OBS_TROZO = 1.5, 10


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def correr(salida_csv: Path, cfg_req: dict | None, espiar: bool = False):
    """`desde_cache` del benjamín con el flag; con `espiar`, captura la entrada del catálogo."""
    import yaml

    import src.team_classification.pipeline_equipos as pe
    from src.tracking_data.processor import procesar_desde_cache

    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(salida_csv)
    cfg["rutas"]["salida_meta"] = str(salida_csv.with_suffix(".meta.json"))
    original_cfg = pe.cargar_config_equipos
    original_obs = pe.etiquetar_por_observacion
    captura = {}
    if cfg_req is not None:

        def con_flag(ruta):
            ce = original_cfg(ruta)
            ce.setdefault("arbitro", {})["catalogo_requiere_identidad"] = cfg_req
            return ce

        pe.cargar_config_equipos = con_flag
    if espiar:

        def espia(*a, **k):
            captura["args"] = a
            return original_obs(*a, **k)

        pe.etiquetar_por_observacion = espia
    c3 = _mod("diag22c_v3")
    cap = c3._Captura()
    raiz = logging.getLogger()
    nivel = raiz.level
    raiz.addHandler(cap)
    raiz.setLevel(logging.INFO)
    try:
        procesar_desde_cache(cfg)
    finally:
        pe.cargar_config_equipos = original_cfg
        pe.etiquetar_por_observacion = original_obs
        raiz.removeHandler(cap)
        raiz.setLevel(nivel)
    return captura, cap.mensajes


def disparos(identidades, equipos, colores, clasificador):
    """{(identidad, k_tracklet): [(dispara, arquetipos, det, pos)]}, con la ventana del catálogo."""
    from src.team_classification.arbitro import (
        ARQUETIPOS,
        arquetipos_activos,
        brillo_medio,
        tono_dominante,
    )
    from src.team_classification.pipeline_equipos import color_medio_limpio

    pr = clasificador._prototipos
    activos = arquetipos_activos([pr.a, pr.b], ARQUETIPOS)
    out: dict[tuple[int, int], list] = {}
    for i, ident in enumerate(identidades, start=1):
        if str(equipos.get(i, "otro")) not in ("A", "B"):
            continue
        obs = sorted(
            (
                (t, tuple(par), k, np.asarray(pos))
                for k, tr in enumerate(ident)
                for t, par, pos in zip(tr.ts, tr.det_idxs, tr.pos)
            ),
            key=lambda o: o[0],
        )
        for t_a, par, k, pos in obs:
            cerca = [
                (p, colores[p])
                for t2, p, _k, _p in obs
                if abs(t2 - t_a) <= VENTANA_S / 2 and p in colores
            ]
            if not cerca:
                continue
            media = color_medio_limpio(cerca, None)
            if media is None:
                continue
            tono = tono_dominante(media)
            nombres = (
                [
                    a.nombre
                    for a in activos
                    if a.contiene(tono[0], tono[1], brillo_medio(media))
                ]
                if tono is not None
                else []
            )
            out.setdefault((i, k), []).append((bool(nombres), nombres, par, pos))
    return out


def main() -> None:
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    inv, b3 = _mod("diag22e_invariantes"), _mod("diag22b_bloque3_medir")
    cfg = yaml.safe_load(open(CONFIG))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    hoy = pd.read_csv(HOY)
    det_arb = inv.proxy_arbitro(hoy, dets)
    hoy_k = inv.con_caja(hoy, dets)
    res = {}

    # ── B1 ──
    c = inv.recuento_por_frame(hoy, 62.0, 40.0)
    v = c[(c.index >= inv.VENTANA_GT_BENJA[0]) & (c.index <= inv.VENTANA_GT_BENJA[1])]
    res["B1_ventana_gt_frames_otro_2_o_mas_reales"] = int((v.otro >= 2).sum())

    # ── captura de la entrada del catálogo (pasada de HOY, flag apagado) ──
    captura, mensajes = correr(salida / "catalogo_off.csv", None, espiar=True)
    res["flag_apagado_identico_a_hoy"] = (
        salida / "catalogo_off.csv"
    ).read_bytes() == HOY.read_bytes()
    identidades, equipos, colores, clasificador = captura["args"][:4]
    D = disparos(identidades, equipos, colores, clasificador)
    n_disp = sum(d[0] for lista in D.values() for d in lista)
    linea = [m for m in mensajes if m.startswith("Etiqueta por observación")]
    res["control_disparos_recontados"] = n_disp
    res["control_log_de_produccion"] = linea[0] if linea else None

    # B1 en el partido entero: en los frames con ≥ 2 `otro` reales dentro del campo, las filas
    # `otro` que NO son del árbitro (proxy). Cada fila se casa con su detección cruda (k) y el
    # arquetipo se busca por la posición de ESA detección (las del CSV están suavizadas).
    r = hoy_k[inv.dentro(hoy_k, 62.0, 40.0) & (hoy_k.etiqueta == "otro")]
    dos = r.groupby("frame").size()
    r = r[r.frame.isin(dos[dos >= 2].index)]
    no_arb = r[[(f, k) not in det_arb for f, k in zip(r.frame, r.k)]]
    por_id = no_arb.id_jugador.value_counts()
    acum = por_id.cumsum() / por_id.sum()
    maj = (
        hoy[hoy.es_real == 1]
        .groupby("id_jugador")
        .etiqueta.agg(lambda s: s.mode().iloc[0])
    )
    ids_g = inv.ids_guarda(R / "outputs/diagnostico_22oct_d/posiciones_hoy.log")
    arq_de = {}
    for (_i, _k), lista in D.items():
        for disp, nombres, par, pos in lista:
            arq_de[(par[0], round(float(pos[0]), 2), round(float(pos[1]), 2))] = (
                "+".join(nombres) if disp else "no_dispara"
            )
    arq = []
    for f, k, i in zip(no_arb.frame, no_arb.k, no_arb.id_jugador):
        d = dets[f][k]
        clave = (f, round(float(d[0]), 2), round(float(d[1]), 2))
        arq.append(
            arq_de.get(
                clave, "identidad_del_tercer_grupo" if i in ids_g else "identidad_otro"
            )
        )
    res["B1_partido_frames_otro_2"] = {
        "frames": int((dos >= 2).sum()),
        "filas_otro_no_arbitro_en_esos_frames": int(len(no_arb)),
        "identidades": int(por_id.size),
        "identidades_para_el_50_y_80_pct": [
            int((acum < 0.5).sum() + 1),
            int((acum < 0.8).sum() + 1),
        ],
        "top10": [
            {
                "id": int(i),
                "filas": int(n),
                "etiqueta_mayoritaria": str(maj.get(i, "?")),
                "del_tercer_grupo": int(i) in ids_g,
            }
            for i, n in por_id.head(10).items()
        ],
        "origen": pd.Series(arq).value_counts().to_dict(),
    }

    # ── X: fracción que dispara por trozo, árbitro contra los demás ──
    proxy_pos = {
        (f, round(float(dets[f][k][0]), 2), round(float(dets[f][k][1]), 2))
        for f, k in det_arb
    }
    trozos = []
    for (i, k), lista in D.items():
        if len(lista) < MIN_OBS_TROZO:
            continue
        fr_disp = float(np.mean([d[0] for d in lista]))
        fr_arb = float(
            np.mean(
                [
                    (par[0], round(float(pos[0]), 2), round(float(pos[1]), 2))
                    in proxy_pos
                    for _d, _n, par, pos in lista
                ]
            )
        )
        trozos.append((fr_disp, fr_arb, len(lista)))
    T = np.array(trozos)
    arb, no = T[T[:, 1] > 0.5], T[T[:, 1] < 0.1]
    p10_arb = float(np.percentile(arb[:, 0], 10)) if len(arb) else None
    p90_no = float(np.percentile(no[:, 0], 90)) if len(no) else None
    if p10_arb is not None and p90_no is not None and p10_arb > p90_no:
        X, regla = (p10_arb + p90_no) / 2, "punto medio (no se solapan)"
    else:
        cand = np.round(np.arange(0.05, 1.0001, 0.05), 2)
        malas = [
            float(arb[arb[:, 0] < x, 2].sum() + no[no[:, 0] >= x, 2].sum())
            for x in cand
        ]
        X, regla = (
            float(cand[int(np.argmin(malas))]),
            "mínimo de filas mal repartidas (se solapan)",
        )
    frac_id = {
        i: float(np.mean([d[0] for (ii, _k), l in D.items() if ii == i for d in l]))
        for i in {ii for ii, _k in D}
    }
    res["X"] = {
        "trozos_arbitro_y_demas": [int(len(arb)), int(len(no))],
        "p10_arbitro": p10_arb,
        "p90_demas": p90_no,
        "X": round(X, 3),
        "regla": regla,
        "identidades_que_disparan_en_mayoria": int(
            sum(v >= 0.5 for v in frac_id.values())
        ),
    }

    # ── B3: flag encendido con X, y el control permutado ──
    def metricas(csv: Path) -> dict:
        f = pd.read_csv(csv)
        return {
            "frames_otro_2_o_mas_reales_pct": inv.invariantes(
                inv.recuento_por_frame(f, 62.0, 40.0), 7
            )["pct_otro_2_o_mas"],
            "equipo_equivocado_pct": b3.error_equipo(csv),
            "arbitro_en_equipo_ventana_gt": inv.arbitro_en_equipo_ventana_gt(
                inv.con_caja(f, dets), det_arb
            ),
        }

    res["B3"] = {"hoy": metricas(HOY)}
    for nombre, semilla in (("regla", None), ("control_permutado", 0)):
        cfg_req = {"activo": True, "frac_identidad": 0.5, "frac_trozo": round(X, 3)}
        if semilla is not None:
            cfg_req["control_permutar_semilla"] = semilla
        csv = salida / f"catalogo_{nombre}.csv"
        _c, msgs = correr(csv, cfg_req)
        res["B3"][nombre] = metricas(csv)
        res["B3"][nombre]["log"] = [
            m for m in msgs if m.startswith("Catálogo que requiere")
        ]
    n, ctl = res["B3"]["regla"], res["B3"]["control_permutado"]
    res["B3"]["criterio"] = {
        "otro_2_<=6": n["frames_otro_2_o_mas_reales_pct"] <= 6.0,
        "error_<=1,5": n["equipo_equivocado_pct"] <= 1.5,
        "arbitro_<=53,5": n["arbitro_en_equipo_ventana_gt"]["pct"] <= 53.5,
        "control_arbitro_10_puntos_peor": ctl["arbitro_en_equipo_ventana_gt"]["pct"]
        >= n["arbitro_en_equipo_ventana_gt"]["pct"] + 10,
    }
    res["B3"]["criterio"]["cumple"] = all(
        v
        for k, v in res["B3"]["criterio"].items()
        if k != "control_arbitro_10_puntos_peor"
    )
    (salida / "bloqueB.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
