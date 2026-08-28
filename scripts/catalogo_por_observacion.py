#!/usr/bin/env python
"""¿Paga aplicar el catálogo arbitral POR OBSERVACIÓN en vez de por identidad?

El catálogo juzga la MEDIA DE LA IDENTIDAD, y eso lo rompe una identidad
contaminada: el id 292 del benjamín mezcla al árbitro con jugadores
naranjas, y con 3.187 recortes no dispara. **No es cantidad, es pureza.**

Este banco mide las tres cosas que Alex exige antes de adoptar nada:

  1. Contra el GT: cuántas observaciones del árbitro se cazan, y **cuántos
     jugadores se sacrifican** — que es lo que tumbó los tres intentos
     anteriores (8 jugadores por cada árbitro).
  2. El RECUENTO por equipo, que es lo que un entrenador ve en tres
     segundos. Hoy: A 62 % de frames correctos, B 13 %, los dos 8 %.
  3. Que no rompa nada aguas abajo: la identidad contaminada queda
     partida en dos etiquetas DENTRO de la misma identidad, y hay que
     comprobar que el portero, la exclusividad del árbitro y el conteo
     por identidad lo aguantan.

⚠️ El GT del benjamín NO anota al árbitro (14 tracks, todos `player`), así
que "observaciones del árbitro" se identifica por ELIMINACIÓN: filas del
sistema dentro del campo que no casan con ninguna persona del GT. Es el
mismo criterio con el que se encontró al id 292.

Uso:
    python scripts/catalogo_por_observacion.py
"""

import argparse
import copy
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("catalogo_obs")
RADIO_M = 2.0


def equipo_de(etq):
    e = str(etq)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def correr(cfg_eq, cache, colores, datos, cfg_tr):
    from src.team_classification.pipeline_equipos import (
        clasificar_identidades,
        entrenar_clasificador,
        etiquetar_por_observacion,
    )
    from src.tracking.perfiles import correr_perfil

    clf = entrenar_clasificador(colores, cfg_eq, cache)
    ids = correr_perfil(
        cache,
        datos["fps"],
        datos["sample"],
        cfg_tr,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=cfg_eq,
    )
    equipos = clasificar_identidades(ids, colores, clf, cfg_eq)
    por_obs = etiquetar_por_observacion(ids, equipos, colores, clf, cfg_eq)
    return ids, equipos, por_obs


def tabla(ids, equipos, por_obs, gt, radio=RADIO_M):
    """Filas {frame, equipo} con la etiqueta EFECTIVA de cada observación."""
    filas = []
    for k, ident in enumerate(ids, start=1):
        base = str(equipos.get(k, "otro"))
        for tr in ident:
            for pos, par in zip(tr.pos, tr.det_idxs):
                etq = por_obs.get((k, par[0]), base)
                filas.append((par[0], k, float(pos[0]), float(pos[1]), etq))
    df = pd.DataFrame(filas, columns=["frame", "id", "x", "y", "etiqueta"])
    df["eqs"] = df.etiqueta.map(equipo_de)
    return df[df.frame.isin(gt)]


def medir(df, gt):
    """(recuento correcto, árbitros cazados, jugadores sacrificados)."""
    ok_a = ok_b = ok_2 = 0
    cazados = sacrificados = intrusos = gt_total = 0
    for f in sorted(set(df.frame) & set(gt)):
        sub = df[df.frame == f]
        gente = [o for o in gt[f] if equipo_de(o.team) in ("A", "B")]
        n_gt = Counter(equipo_de(o.team) for o in gente)
        n_s = Counter(sub[sub.eqs.isin(["A", "B"])].eqs)
        ok_a += n_s["A"] == n_gt["A"]
        ok_b += n_s["B"] == n_gt["B"]
        ok_2 += (n_s["A"] == n_gt["A"]) and (n_s["B"] == n_gt["B"])
        xy = sub[["x", "y"]].to_numpy()
        etq = sub.eqs.to_numpy()
        casadas = set()
        for o in gente:
            gt_total += 1
            if not len(xy):
                continue
            d = np.hypot(xy[:, 0] - o.pos[0], xy[:, 1] - o.pos[1])
            k = int(np.argmin(d))
            if d[k] > RADIO_M:
                continue
            casadas.add(k)
            # un jugador del GT sacado de los equipos = SACRIFICADO
            if etq[k] not in ("A", "B"):
                sacrificados += 1
        for k, e in enumerate(etq):
            if k in casadas:
                continue
            # fila que no es nadie del GT: si sale de los equipos, CAZADA
            intrusos += 1
            if e not in ("A", "B"):
                cazados += 1
    n = len(set(df.frame) & set(gt))
    return {
        "frames": n,
        "ok_A": 100 * ok_a / n,
        "ok_B": 100 * ok_b / n,
        "ok_2": 100 * ok_2 / n,
        "cazados": cazados,
        "intrusos": intrusos,
        "sacrificados": sacrificados,
        "gt_total": gt_total,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_parte_entera.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    import pickle

    import yaml

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.team_classification.pipeline_equipos import cargar_config_equipos
    from src.tracking.cache_io import cargar_cache
    from src.tracking.filtro_confianza import filtrar_por_confianza

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    cfg_eq0 = cargar_config_equipos(cfg["config_equipos"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    cache, colores = filtrar_por_confianza(
        datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    H = np.load(cfg["rutas"]["homografia"])
    gt = gt_a_por_frame(parsear_cvat(args.gt), H, args.offset, args.paso)

    variantes = {
        "HOY (catálogo por identidad)": False,
        "catálogo POR OBSERVACIÓN": True,
    }
    res = {}
    for nombre, activo in variantes.items():
        cfg_eq = copy.deepcopy(cfg_eq0)
        cfg_eq.setdefault("agregacion", {}).setdefault("por_observacion", {})
        cfg_eq["agregacion"]["por_observacion"]["catalogo_arbitral"] = activo
        ids, equipos, por_obs = correr(cfg_eq, cache, colores, datos, cfg_tr)
        df = tabla(ids, equipos, por_obs, gt)
        res[nombre] = (medir(df, gt), ids, equipos, por_obs)

    print(
        f"\n{'variante':<32}{'A ok':>7}{'B ok':>7}{'ambos':>8}"
        f"{'cazados':>10}{'sacrificados':>14}"
    )
    print("-" * 78)
    for nombre, (m, *_) in res.items():
        print(
            f"  {nombre:<30}{m['ok_A']:>6.0f}%{m['ok_B']:>6.0f}%{m['ok_2']:>7.0f}%"
            f"{m['cazados']:>6}/{m['intrusos']:<4}{m['sacrificados']:>8}/{m['gt_total']:<5}"
        )
    a = res["HOY (catálogo por identidad)"][0]
    b = res["catálogo POR OBSERVACIÓN"][0]
    print(
        f"\n  el precio: {b['sacrificados'] - a['sacrificados']} jugadores más "
        f"sacrificados por {b['cazados'] - a['cazados']} intrusos más cazados"
    )
    if b["cazados"] > a["cazados"]:
        r = (b["sacrificados"] - a["sacrificados"]) / (b["cazados"] - a["cazados"])
        print(
            f"  = {r:.2f} jugadores por intruso "
            f"(los intentos anteriores estaban en 8)"
        )

    # ── (4) ¿rompe algo aguas abajo? ─────────────────────────────────
    print("\n(4) IDENTIDADES PARTIDAS EN VARIAS ETIQUETAS")
    for nombre, (_, ids, equipos, por_obs) in res.items():
        mixtas = Counter()
        for (k, _f), e in por_obs.items():
            mixtas[k] = mixtas.get(k, 0)
        por_id = {}
        for (k, _f), e in por_obs.items():
            por_id.setdefault(k, set()).add(e)
        n_mix = sum(1 for v in por_id.values() if len(v) > 1)
        porteros = sum(1 for v in equipos.values() if str(v).startswith("portero_"))
        otros = sum(1 for v in equipos.values() if str(v) == "otro")
        print(
            f"  {nombre:<32} identidades con >1 etiqueta: {n_mix:>4} | "
            f"porteros coronados: {porteros} | tercer grupo: {otros}"
        )


if __name__ == "__main__":
    main()
