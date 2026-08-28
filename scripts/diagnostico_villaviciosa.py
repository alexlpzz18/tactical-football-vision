#!/usr/bin/env python
"""¿Por qué Villaviciosa está veinte veces peor que el benjamín?

23,6 % de observaciones con el equipo equivocado contra 1,2 %, y este mes
no la ha movido nada. Antes de invertir allí, el diagnóstico que ordenó el
benjamín, y la pregunta de fondo de Alex: **¿es el ESCENARIO o es el
SISTEMA?**

  - Si es el escenario (jugadores más pequeños, equipaciones que separan
    peor, campo más grande), hay un techo y hay que aceptarlo.
  - Si es el sistema, hay margen.

Se mide lo mismo en las DOS patas, con el mismo código, para que la
comparación signifique algo.

Uso:
    python scripts/diagnostico_villaviciosa.py
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

logger = logging.getLogger("diag_villa")
RADIO = 2.0


def eq_base(e):
    e = str(e)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def analizar(nombre, cfg_proc, ruta_gt, offset, ruta_eq=None):
    import pickle

    import yaml

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.team_classification.color_classifier import _solo_hs
    from src.team_classification.pipeline_equipos import (
        cargar_config_equipos,
        entrenar_clasificador,
    )
    from src.tracking.cache_io import cargar_cache
    from src.tracking.filtro_confianza import filtrar_por_confianza

    cfg = yaml.safe_load(open(cfg_proc))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    cfg_eq = cargar_config_equipos(ruta_eq or cfg.get("config_equipos"))
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    cache, colores = filtrar_por_confianza(
        datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    H = np.load(cfg["rutas"]["homografia"])
    gt = gt_a_por_frame(parsear_cvat(ruta_gt), H, offset, 15)

    clf = entrenar_clasificador(colores, cfg_eq, cache)
    pr = clf._prototipos
    A, B = _solo_hs(pr.a), _solo_hs(pr.b)
    sep = float(np.linalg.norm(A - B))

    # ── EL ESCENARIO: tamaño de los recortes y separación de color ───
    altos, dist_prop = [], []
    por_frame = {e["frame_idx"]: e for e in cache}
    for f, obs in gt.items():
        e = por_frame.get(f)
        if not e:
            continue
        for o in obs:
            d = [np.hypot(dd[0] - o.pos[0], dd[1] - o.pos[1]) for dd in e["dets"]]
            if not d or min(d) > RADIO:
                continue
            i = int(np.argmin(d))
            dd = e["dets"][i]
            altos.append(dd[5] - dd[3])
            ft = colores.get((f, i))
            if ft is not None:
                x = _solo_hs(ft)
                dist_prop.append(
                    min(np.linalg.norm(x - A), np.linalg.norm(x - B)) / sep
                )

    return {
        "nombre": nombre,
        "sep_ab": sep,
        "alto_px": float(np.median(altos)) if altos else float("nan"),
        "alto_p10": float(np.quantile(altos, 0.1)) if altos else float("nan"),
        "dist_med": float(np.median(dist_prop)) if dist_prop else float("nan"),
        "dist_p90": float(np.quantile(dist_prop, 0.9)) if dist_prop else float("nan"),
        "n": len(altos),
        "cfg": cfg,
        "cfg_tr": cfg_tr,
        "cfg_eq": cfg_eq,
        "cache": cache,
        "colores": colores,
        "datos": datos,
        "gt": gt,
        "clf": clf,
    }


def descomponer(est, csv):
    """El 23,6 %: ¿contaminación, clasificador o intrusos?"""
    from src.tracking.perfiles import correr_perfil

    ids = correr_perfil(
        est["cache"],
        est["datos"]["fps"],
        est["datos"]["sample"],
        est["cfg_tr"],
        perfil="bytetrack",
        colores=est["colores"],
        clasificador=est["clf"],
        cfg_equipos=est["cfg_eq"],
    )
    gt = est["gt"]
    por_frame = {e["frame_idx"]: e for e in est["cache"]}
    # dueño del GT de cada observación, por POSICIÓN
    dueno = {}
    for f, obs in gt.items():
        e = por_frame.get(f)
        if not e:
            continue
        for i, dd in enumerate(e["dets"]):
            d = [np.hypot(dd[0] - o.pos[0], dd[1] - o.pos[1]) for o in obs]
            if d and min(d) <= RADIO:
                o = obs[int(np.argmin(d))]
                dueno[(f, i)] = (o.obj_id, eq_base(o.team))

    df = pd.read_csv(csv)
    df = df[df.es_real == 1].copy()
    df["eqb"] = df.etiqueta.map(eq_base)
    etq_de = {}
    for _, r in df.iterrows():
        etq_de.setdefault(int(r.frame), []).append((r.x_m, r.y_m, r.eqb))

    puras = mixtas = 0
    mal_en_puras = mal_en_mixtas = obs_puras = obs_mixtas = 0
    for k, ident in enumerate(ids, start=1):
        pares = [tuple(p) for tr in ident for p in tr.det_idxs]
        gs = [dueno[p] for p in pares if p in dueno]
        if not gs:
            continue
        personas = Counter(g[0] for g in gs)
        es_pura = len(personas) == 1
        puras += es_pura
        mixtas += not es_pura
        # etiqueta del sistema en cada observación, por posición
        for p in pares:
            if p not in dueno:
                continue
            e = por_frame.get(p[0])
            dd = e["dets"][p[1]]
            filas = etq_de.get(p[0], [])
            if not filas:
                continue
            j = min(
                range(len(filas)),
                key=lambda z: (filas[z][0] - dd[0]) ** 2 + (filas[z][1] - dd[1]) ** 2,
            )
            sis = filas[j][2]
            if sis not in ("A", "B"):
                continue
            real = dueno[p][1]
            if es_pura:
                obs_puras += 1
                mal_en_puras += sis != real
            else:
                obs_mixtas += 1
                mal_en_mixtas += sis != real
    return {
        "identidades": len(ids),
        "puras": puras,
        "mixtas": mixtas,
        "obs_puras": obs_puras,
        "mal_puras": mal_en_puras,
        "obs_mixtas": obs_mixtas,
        "mal_mixtas": mal_en_mixtas,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    patas = [
        (
            "benjamín (F7)",
            "configs/processor_benja_parte_entera.yaml",
            "data/annotations/gt_benja/annotations.xml",
            9750,
            None,
            "data/tracking_benja/posiciones_benja_p1_v2.csv",
        ),
        (
            "Villaviciosa (F11)",
            "configs/processor.yaml",
            "data/annotations/ground_truth_tracking/annotations.xml",
            7500,
            "configs/team_classification.yaml",
            "data/tracking/posiciones_v4pre_hoy.csv",
        ),
    ]
    ests = []
    print("\n¿ES EL ESCENARIO? — lo mismo medido en las dos patas")
    print(
        f"  {'pata':<22}{'alto px':>9}{'p10':>7}{'sep A-B':>10}"
        f"{'dist/sep':>10}{'p90':>8}{'n':>7}"
    )
    for nombre, cfgp, gt, off, eq, _csv in patas:
        e = analizar(nombre, cfgp, gt, off, eq)
        ests.append(e)
        print(
            f"  {nombre:<22}{e['alto_px']:>9.0f}{e['alto_p10']:>7.0f}"
            f"{e['sep_ab']:>10.3f}{e['dist_med']:>10.2f}{e['dist_p90']:>8.2f}"
            f"{e['n']:>7}"
        )
    print("\n  alto px = altura de la caja del jugador (el tamaño del recorte)")
    print("  dist/sep = a qué distancia está un jugador de su prototipo, en")
    print("             unidades de la separación entre los dos equipos.")
    print("             Cuanto MAYOR, peor separan las equipaciones.")

    print("\n¿O ES EL SISTEMA? — el 23,6 % descompuesto")
    print(
        f"  {'pata':<22}{'ident.':>8}{'mixtas':>9}{'mal en PURAS':>15}"
        f"{'mal en MIXTAS':>16}"
    )
    for e, (nombre, _c, _g, _o, _eq, csv) in zip(ests, patas):
        d = descomponer(e, csv)
        pm = 100 * d["mal_puras"] / max(d["obs_puras"], 1)
        mm = 100 * d["mal_mixtas"] / max(d["obs_mixtas"], 1)
        print(
            f"  {nombre:<22}{d['identidades']:>8}"
            f"{100*d['mixtas']/max(d['puras']+d['mixtas'],1):>8.0f}%"
            f"{pm:>13.1f}% {mm:>14.1f}%"
        )
    print("\n  'mal en PURAS' es el clasificador fallando sobre identidades que")
    print("  contienen a UNA sola persona: ahí no hay excusa de contaminación.")


if __name__ == "__main__":
    main()
