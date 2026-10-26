#!/usr/bin/env python
"""Diagnóstico 22-oct (f), bloque C: Villaviciosa, solo con la caché (sin vídeo).

Criterio en `docs/diagnostico_22oct_f.md`.
- C1: el 23,6 % de equipo equivocado por persona del GT y por prototipo; qué es el prototipo A.
- C2: el tope por identidad con 5 semillas de control; y la etiqueta por observación, re-medida.
- C3: por qué A > 11 en el 54,6 % de los frames.

Uso:
    python scripts/diag22f_villa.py --salida outputs/diagnostico_22oct_f
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor.yaml"
HOY = R / "outputs/diagnostico_22oct/villa/posiciones.csv"
GT = R / "data/annotations/ground_truth_tracking/annotations.xml"
H_GT = R / "data/calibracion/homografia.npy"
RADIO = 2.0


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def equipo(e) -> str:
    e = str(e)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def casar_todas(filas, gt):
    """[(frame, fila, persona GT)] casado 1-a-1 a 2 m con TODAS las personas del GT."""
    from scipy.optimize import linear_sum_assignment

    porf = {f: g for f, g in filas.groupby("frame")}
    out = []
    for f, obs in gt.items():
        g = porf.get(f)
        if g is None:
            continue
        P = np.array([o.pos for o in obs])
        xy = g[["x_m", "y_m"]].to_numpy()
        coste = np.hypot(xy[None, :, 0] - P[:, None, 0], xy[None, :, 1] - P[:, None, 1])
        coste = np.where(coste > RADIO, 1e6, coste)
        for i, j in zip(*linear_sum_assignment(coste)):
            if coste[i, j] < 1e6:
                out.append((f, g.iloc[j], obs[i]))
    return out


def main() -> None:
    import pandas as pd
    import yaml

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.team_classification.color_classifier import _solo_hs, color_dominante
    from src.team_classification.pipeline_equipos import (
        cargar_config_equipos,
        entrenar_clasificador,
    )
    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import procesar_desde_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    b3 = _mod("diag22b_bloque3_medir")
    cv = _mod("colab_v3_villa")
    cfg = yaml.safe_load(open(CONFIG))
    ce = cargar_config_equipos(
        cfg.get("config_equipos", "configs/team_classification.yaml")
    )
    datos = cargar_cache(R / cfg["rutas"]["cache"])
    dets = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
    colores = pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    clas = entrenar_clasificador(colores, ce, datos["cache"])
    pr = clas._prototipos
    gt = gt_a_por_frame(parsear_cvat(GT), np.load(H_GT), 7500, 15)
    hoy = pd.read_csv(HOY)
    reales = hoy[hoy.es_real == 1].copy()
    reales["k"] = b3.caja_cruda_mas_cercana(reales, dets)
    res = {}

    # ── C1 ──
    cas = casar_todas(reales, gt)
    jug = [
        (f, r, o)
        for f, r, o in cas
        if o.label != "referee" and equipo(o.team) in ("A", "B")
    ]
    directo = sum(equipo(r.etiqueta) == equipo(o.team) for _f, r, o in jug)
    cruzado = sum(
        {"A": "B", "B": "A"}.get(equipo(r.etiqueta)) == equipo(o.team)
        for _f, r, o in jug
    )
    mapa = (
        (lambda s: s)
        if directo >= cruzado
        else (lambda s: {"A": "B", "B": "A"}.get(s, s))
    )
    filas = []
    for f, r, o in jug:
        sis = equipo(r.etiqueta)
        if sis not in ("A", "B"):
            continue
        filas.append(
            {
                "persona": int(o.obj_id),
                "equipo_gt": equipo(o.team),
                "sistema_en_terminos_del_gt": mapa(sis),
                "feat": colores.get((f, int(r.k))),
            }
        )
    P = pd.DataFrame(filas)
    P["mal"] = P.equipo_gt != P.sistema_en_terminos_del_gt
    # qué prototipo es «el del equipo» de cada GT: el que el sistema le da más veces
    proto_de = {
        eq: g.sistema_en_terminos_del_gt.mode().iloc[0]
        for eq, g in P.groupby("equipo_gt")
    }
    por_persona = []
    for pid, g in P.groupby("persona"):
        feats = [x for x in g.feat if x is not None]
        m = _solo_hs(np.mean(feats, axis=0)) if feats else None
        eq = g.equipo_gt.iloc[0]
        d = (
            {
                "a_prototipo_A": round(float(np.linalg.norm(m - pr.a)), 3),
                "a_prototipo_B": round(float(np.linalg.norm(m - pr.b)), 3),
            }
            if m is not None
            else {}
        )
        por_persona.append(
            {
                "persona": int(pid),
                "equipo_gt": eq,
                "casadas": int(len(g)),
                "mal": int(g.mal.sum()),
                "pct_mal": round(100 * float(g.mal.mean()), 1),
                **d,
                "color_dominante_rgb": (
                    list(color_dominante(m)) if m is not None else None
                ),
            }
        )
    por_persona.sort(key=lambda x: -x["mal"])
    tot_mal = sum(x["mal"] for x in por_persona)
    acum = np.cumsum([x["mal"] for x in por_persona]) / max(tot_mal, 1)
    # prototipo A: qué recortes (casados con el GT) caen más cerca de él
    comp = {"arbitro": 0, "equipo_gt_A": 0, "equipo_gt_B": 0}
    feats_grupo = {"arbitro": [], "equipo_gt_A": [], "equipo_gt_B": []}
    for f, r, o in cas:
        x = colores.get((f, int(r.k)))
        if x is None:
            continue
        grupo = "arbitro" if o.label == "referee" else f"equipo_gt_{equipo(o.team)}"
        if grupo not in comp:
            continue
        feats_grupo[grupo].append(x)
        hs = _solo_hs(x)
        cand = {
            "A": pr.a,
            "B": pr.b,
            **({"otro": pr.otro} if pr.otro is not None else {}),
        }
        if min(cand, key=lambda c: np.linalg.norm(hs - cand[c])) == "A":
            comp[grupo] += 1
    n_a = sum(comp.values())
    res["C1"] = {
        "emparejamiento": "directo" if directo >= cruzado else "cruzado",
        "equipo_equivocado": f"{int(P.mal.sum())} de {len(P)} ({100 * P.mal.mean():.1f} %)",
        "prototipo_del_sistema_para_cada_equipo_gt": proto_de,
        "personas_con_errores": int(sum(x["mal"] > 0 for x in por_persona)),
        "personas_para_el_50_y_80_pct_de_los_errores": [
            int((acum < 0.5).sum() + 1),
            int((acum < 0.8).sum() + 1),
        ],
        "por_persona": por_persona,
        "colores_de_los_prototipos": clas.colores_equipos(),
        "color_dominante_rgb_de_cada_grupo_gt": {
            k: list(color_dominante(_solo_hs(np.mean(v, axis=0)))) if v else None
            for k, v in feats_grupo.items()
        },
        "recortes_casados_mas_cerca_del_prototipo_A": {
            k: f"{v} ({100 * v / max(n_a, 1):.0f} %)" for k, v in comp.items()
        },
        "color_real_en_pixeles": "NO MEDIDO: sin el vídeo de Villaviciosa en local",
    }

    # ── C2: tope por identidad con 5 semillas de control; etiqueta por observación ──
    def pasada(nombre, ajustar):
        c = yaml.safe_load(open(CONFIG))
        c["modo"] = "desde_cache"
        ajustar(c)
        csv = salida / f"villa_{nombre}.csv"
        c["rutas"]["salida_csv"] = str(csv)
        c["rutas"]["salida_meta"] = str(salida / f"villa_{nombre}_meta.json")
        procesar_desde_cache(c)
        m = cv.metricas(csv, gt, 100.0, 64.0)
        return {
            "equipo_equivocado_pct": round(m["equipo_equivocado_pct"], 2),
            "arbitro_en_equipo_pct": m["arbitro_en_equipo_gt"]["pct_de_las_casadas"],
            "cobertura_pct": round(m["cobertura"]["pct"], 2),
        }

    def tope(semilla):
        def f(c):
            c["equipos"]["tope_cardinalidad"]["activo"] = True
            if semilla is not None:
                c["equipos"]["tope_cardinalidad"]["control_permutar_semilla"] = semilla

        return f

    res["C2"] = {"tope_real": pasada("tope_real", tope(None))}
    res["C2"]["tope_permutado"] = {
        s: pasada(f"tope_perm{s}", tope(s)) for s in range(5)
    }

    import src.team_classification.pipeline_equipos as pe

    original = pe.cargar_config_equipos
    for nombre, catalogo in (("por_obs", False), ("por_obs_catalogo", True)):

        def con_obs(ruta, catalogo=catalogo):
            e = original(ruta)
            e.setdefault("agregacion", {})["por_observacion"] = {
                "activo": True,
                "ventana_s": 1.5,
                "forzar_ab": True,
                "catalogo_arbitral": catalogo,
            }
            return e

        pe.cargar_config_equipos = con_obs
        try:
            res["C2"][nombre] = pasada(nombre, lambda c: None)
        finally:
            pe.cargar_config_equipos = original
    res["C2"]["hoy"] = pasada("hoy_check", lambda c: None)

    # ── C3: qué son las filas A ──
    dentro = reales[reales.x_m.between(0, 100) & reales.y_m.between(0, 64)]
    cas_d = casar_todas(dentro, gt)
    casada_de = {(f, r.name): o for f, r, o in cas_d}
    tipos = {}
    por_frame = []
    for f in gt:
        g = dentro[dentro.frame == f]
        a = g[g.etiqueta.map(equipo) == "A"]
        cuenta = {
            "jugador_del_equipo_gt_del_A": 0,
            "jugador_del_otro_equipo": 0,
            "arbitro": 0,
            "sin_casar": 0,
        }
        for idx in a.index:
            o = casada_de.get((f, idx))
            if o is None:
                t = "sin_casar"
            elif o.label == "referee":
                t = "arbitro"
            elif mapa(equipo(o.team)) == "A":
                t = "jugador_del_equipo_gt_del_A"
            else:
                t = "jugador_del_otro_equipo"
            cuenta[t] += 1
        gte = pd.Series(
            [equipo(o.team) for o in gt[f] if o.label != "referee"]
        ).value_counts()
        por_frame.append(
            {
                **cuenta,
                "filas_A": len(a),
                "personas_gt_A": int(gte.get("A", 0)),
                "personas_gt_B": int(gte.get("B", 0)),
            }
        )
        for k, v in cuenta.items():
            tipos[k] = tipos.get(k, 0) + v
    F = pd.DataFrame(por_frame)
    res["C3"] = {
        "frames_gt": int(len(F)),
        "media_filas_A": round(float(F.filas_A.mean()), 2),
        "media_personas_gt_por_equipo_A_B": [
            round(float(F.personas_gt_A.mean()), 2),
            round(float(F.personas_gt_B.mean()), 2),
        ],
        "filas_A_por_tipo_media_por_frame": {
            k: round(v / len(F), 2) for k, v in tipos.items()
        },
        "frames_con_A_mas_de_11": int((F.filas_A > 11).sum()),
    }
    (salida / "bloqueC.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
