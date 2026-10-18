#!/usr/bin/env python
"""Tests de ORÁCULO: cuánto mejoraría si cada etapa fuera PERFECTA.

Llevamos un mes decidiendo por intuición dónde está el margen. Esto lo
mide: se sustituye una etapa por su versión perfecta —usando el GT— y se
mira cuánto sube el resultado. El que más suba es donde hay que invertir.

## Una trampa que hay que esquivar

El oráculo de punto de contacto NO se puede evaluar contra el error de
localización, porque la "verdad" del anclaje son los propios clics de
Alex: el error saldría cero por construcción y no diría nada.

Lo que sí dice algo: **qué le pasa a la ASOCIACIÓN cuando las posiciones
son mejores**. Si con anclaje perfecto el tracker sigue mezclando
identidades, el anclaje no es el cuello de botella y la línea de la pose
no paga.

## Los oráculos

- **contacto**: las detecciones que casan con el GT reciben la posición
  proyectada del clic de Alex en vez del borde inferior de la caja. El
  resto siguen igual. Mide el techo del anclaje.
- **asociación**: cada detección que casa con el GT recibe la identidad
  del GT. Mide el techo de arreglar el tracker.
- **ambos**: el techo conjunto.

Uso:
    python scripts/oraculos.py
"""

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402
from src.tracking_data.processor import project_point  # noqa: E402

logger = logging.getLogger("oraculos")
RADIO_BASE, RADIO_POR_METRO, RADIO_MAX = 1.5, 0.09, 6.0
FRAME_INI, PASO_GT = 9750, 15


def radio(y):
    return float(np.clip(RADIO_BASE + RADIO_POR_METRO * y, RADIO_BASE, RADIO_MAX))


def emparejar(cache, gt):
    """{(frame, det_idx): (obj_id, pos_gt)} — qué detección es quién."""
    mapa = {}
    for entrada in cache:
        f = entrada["frame_idx"]
        obs = gt.get(f)
        if not obs:
            continue
        usados = set()
        for o in obs:
            gx, gy = float(o.pos[0]), float(o.pos[1])
            mejor, dmin = None, radio(gy)
            for i, d in enumerate(entrada["dets"]):
                if i in usados:
                    continue
                dist = float(np.hypot(d[0] - gx, d[1] - gy))
                if dist < dmin:
                    mejor, dmin = i, dist
            if mejor is not None:
                usados.add(mejor)
                mapa[(f, mejor)] = (o.obj_id, (gx, gy))
    return mapa


def metricas_producto(por_frame_equipo):
    """Centroide, anchura y profundidad del bloque, por equipo y frame."""
    filas = []
    for (frame, equipo), puntos in por_frame_equipo.items():
        if len(puntos) < 3:
            continue
        P = np.array(puntos)
        filas.append(
            {
                "frame": frame,
                "equipo": equipo,
                "cx": P[:, 0].mean(),
                "cy": P[:, 1].mean(),
                "ancho": P[:, 1].max() - P[:, 1].min(),
                "profundo": P[:, 0].max() - P[:, 0].min(),
            }
        )
    return pd.DataFrame(filas)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--clics", default="data/annotations/gt_benja/clics.csv")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    H = np.load(cfg["rutas"]["homografia"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    cache, colores = filtrar_por_confianza(
        datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    clf = entrenar_clasificador(colores, cfg_eq, cache)

    gt = gt_a_por_frame(
        parsear_cvat(args.gt), H, frame_offset=FRAME_INI, paso_gt=PASO_GT
    )
    mapa = emparejar(cache, gt)
    n_gt = sum(len(v) for v in gt.values())
    print(
        f"\nGT: {n_gt} observaciones · emparejadas con una detección: {len(mapa)} "
        f"({len(mapa)/n_gt:.0%})"
    )

    # Clics SIN corregir, proyectados: la referencia de anclaje "perfecto"
    clics = pd.read_csv(args.clics)
    # OJO: el conversor a CVAT numera los tracks 0..N-1 por orden de
    # `jugador`, así que obj_id NO es el número de jugador. Sin esta
    # traducción cada detección recibía la posición de OTRO jugador, y el
    # oráculo salía 16 m peor que el sistema — implausible, que es lo que
    # delató el fallo.
    jugadores = sorted(clics.jugador.unique())
    gid_a_jugador = {i: int(j) for i, j in enumerate(jugadores)}

    from src.evaluation.correccion_pies import corregir_clics

    clics_corr = corregir_clics(clics, cache)
    pos_clic_corr = {}
    for f in clics_corr.itertuples():
        pos_clic_corr[(int(f.frame), int(f.jugador))] = project_point(
            float(f.x_px), float(f.y_px), H
        )
    pos_clic = {}
    for f in clics.itertuples():
        pos_clic[(int(f.frame), int(f.jugador))] = project_point(
            float(f.x_px), float(f.y_px), H
        )

    def cache_con_oraculo(usar_contacto, fuente=None):
        fuente = fuente if fuente is not None else pos_clic
        nuevo = []
        for entrada in cache:
            dets = list(entrada["dets"])
            if usar_contacto:
                for i, d in enumerate(dets):
                    clave = (entrada["frame_idx"], i)
                    if clave not in mapa:
                        continue
                    gid, _pos = mapa[clave]
                    jug = gid_a_jugador.get(gid, gid)
                    pc = fuente.get((entrada["frame_idx"], jug))
                    if pc:
                        dets[i] = (pc[0], pc[1]) + tuple(d[2:])
            nuevo.append({**entrada, "dets": dets})
        return nuevo

    resultados = []
    for nombre, oraculo_contacto, oraculo_asoc, fuente in (
        ("SISTEMA (línea base)", False, False, None),
        ("+ contacto: clics CRUDOS", True, False, pos_clic),
        ("+ contacto: clics CORREGIDOS", True, False, pos_clic_corr),
        ("+ oráculo de ASOCIACIÓN", False, True, None),
        ("+ asociación y contacto corr.", True, True, pos_clic_corr),
    ):
        c = cache_con_oraculo(oraculo_contacto, fuente)
        if oraculo_asoc:
            # Identidad perfecta: una identidad por persona del GT
            grupos = {}
            for (f, i), (gid, _p) in mapa.items():
                grupos.setdefault(gid, []).append((f, i))
            por_frame = {e["frame_idx"]: e["dets"] for e in c}
            pf_eq = {}
            eq_gt = {}
            for obs in gt.values():
                for o in obs:
                    eq_gt.setdefault(o.obj_id, str(o.team))
            for gid, pares in grupos.items():
                for f, i in pares:
                    d = por_frame[f][i]
                    eq = eq_gt.get(gid, "otro").replace("portero_", "")
                    pf_eq.setdefault((f, eq), []).append((d[0], d[1]))
            n_ids = len(grupos)
        else:
            ids = correr_perfil(
                c,
                datos["fps"],
                datos["sample"],
                cfg_tr,
                perfil="bytetrack",
                colores=colores,
                clasificador=clf,
                cfg_equipos=cfg_eq,
            )
            equipos = dict(clasificar_identidades(ids, colores, clf, cfg_eq))
            pf_eq = {}
            for k, ident in enumerate(ids, start=1):
                eq = str(equipos.get(k, "otro")).replace("portero_", "")
                if eq not in ("A", "B"):
                    continue
                for tr in ident:
                    for pos, (f, _d) in zip(tr.pos, tr.det_idxs):
                        pf_eq.setdefault((f, eq), []).append((pos[0], pos[1]))
            n_ids = len(ids)
        resultados.append((nombre, n_ids, metricas_producto(pf_eq)))

    # Verdad de producto: el GT
    pf_gt = {}
    eq_gt = {}
    for f, obs in gt.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            eq_gt.setdefault(o.obj_id, eq)
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])

    print("\n── MÉTRICAS DE PRODUCTO: error contra el GT ──\n")
    cab = f"{'variante':<26}{'nIds':>6}{'centroide':>12}{'anchura':>10}{'profundidad':>13}"
    print(cab)
    print("-" * len(cab))
    for nombre, n_ids, m in resultados:
        if m.empty:
            print(f"{nombre:<26}{n_ids:>6}{'—':>12}{'—':>10}{'—':>13}")
            continue
        j = m.set_index(["frame", "equipo"]).join(verdad, rsuffix="_gt", how="inner")
        if j.empty:
            print(f"{nombre:<26}{n_ids:>6}{'sin solape':>12}")
            continue
        ec = np.hypot(j.cx - j.cx_gt, j.cy - j.cy_gt).median()
        ea = (j.ancho - j.ancho_gt).abs().median()
        ep = (j.profundo - j.profundo_gt).abs().median()
        print(f"{nombre:<26}{n_ids:>6}{ec:>11.2f}m{ea:>9.2f}m{ep:>12.2f}m")

    print(
        "\n  El oráculo de CONTACTO no se evalúa contra el error de\n"
        "  localización: la verdad del anclaje son los propios clics, así\n"
        "  que saldría cero por construcción. Se mide por lo que le hace a\n"
        "  las métricas COLECTIVAS, que es lo que ve el producto."
    )


if __name__ == "__main__":
    main()
