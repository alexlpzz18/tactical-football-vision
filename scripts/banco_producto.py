#!/usr/bin/env python
"""Banco de métricas de PRODUCTO, con las dos familias separadas.

Corrección del 20-ago-2026: el centroide de equipo agrupa los puntos por
`(frame, equipo)` y **no usa la identidad**. Tres agrupaciones distintas
de las mismas observaciones —14 identidades y 1.914— dan el mismo
centroide. Llevábamos una semana decidiendo con una métrica que no medía
lo que creíamos.

Aquí las métricas van en dos familias, etiquetadas:

**FAMILIA A — dependen de la IDENTIDAD.** Son las que un entrenador
acabará leyendo por jugador, y las que se degradan cuando el tracker
falla:
- error de posición por jugador (emparejado con su persona del GT)
- distancia recorrida por jugador
- estabilidad de la identidad a lo largo del tramo

**FAMILIA B — NO dependen de la identidad.** Centroide, anchura,
ocupación por zonas. Se conservan a propósito: son exactamente las que
dicen que **un informe colectivo SÍ es viable con lo que hay hoy**. Es
información de producto, no un defecto — pero no sirven para juzgar el
tracker.

El emparejamiento identidad↔persona es UNO A UNO por solape máximo
(húngaro), como hace IDF1. Sin eso, varias identidades podrían reclamar
a la misma persona y las cifras saldrían infladas.

Uso:
    python scripts/banco_producto.py
"""

import argparse
import logging
import pickle
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import yaml
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from oraculos import metricas_producto  # noqa: E402
from pureza_sin_reentrada import duenos  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("banco_producto")
ZONAS_X, ZONAS_Y = 3, 3


def recorrido(puntos_por_frame):
    """Metros recorridos sumando los saltos entre frames consecutivos."""
    fs = sorted(puntos_por_frame)
    if len(fs) < 2:
        return 0.0
    return float(
        sum(
            np.linalg.norm(
                np.asarray(puntos_por_frame[fs[i]])
                - np.asarray(puntos_por_frame[fs[i - 1]])
            )
            for i in range(1, len(fs))
        )
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    H = np.load(cfg["rutas"]["homografia"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    conf = float(cfg_tr.get("confianza_min", 0) or 0)
    cache, colores = filtrar_por_confianza(datos["cache"], colores, conf)
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    gt = gt_a_por_frame(parsear_cvat(args.gt), H, frame_offset=9750, paso_gt=15)
    mapa = duenos(cache, gt)

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
    equipos = dict(clasificar_identidades(ids, colores, clf, cfg_eq))

    # Posiciones del sistema por identidad y frame
    pos_sis = {}
    for k, ident in enumerate(ids, start=1):
        for tr in ident:
            for pp, (f, _d) in zip(tr.pos, tr.det_idxs):
                pos_sis.setdefault(k, {})[f] = (float(pp[0]), float(pp[1]))
    # Posiciones del GT por persona y frame
    pos_gt, eq_gt = {}, {}
    for f, obs in gt.items():
        for o in obs:
            pos_gt.setdefault(o.obj_id, {})[f] = (float(o.pos[0]), float(o.pos[1]))
            eq_gt.setdefault(o.obj_id, str(o.team).replace("portero_", ""))
    personas = sorted(pos_gt)

    # Solape identidad↔persona, y asignación UNO A UNO
    solape = np.zeros((len(ids), len(personas)))
    for (f, di), g in mapa.items():
        for k, ident in enumerate(ids, start=1):
            if any((f, di) == tuple(par) for tr in ident for par in tr.det_idxs):
                solape[k - 1, personas.index(g)] += 1
                break
    filas, cols = linear_sum_assignment(-solape)
    asignacion = {personas[c]: r + 1 for r, c in zip(filas, cols) if solape[r, c] > 0}

    print(f"\nPersonas del GT: {len(personas)} · identidades del sistema: {len(ids)}")
    print(f"Emparejadas uno a uno: {len(asignacion)}\n")

    print("=" * 72)
    print("FAMILIA A — MÉTRICAS QUE SÍ DEPENDEN DE LA IDENTIDAD")
    print("=" * 72)
    cab = (
        f"{'jugador':<9}{'eq':>5}{'obs GT':>8}{'cubiertas':>11}"
        f"{'error m':>9}{'recorrido GT':>14}{'recorrido sis':>15}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    errores, cobertura, rec_gt_t, rec_sis_t, estabilidad = [], [], [], [], []
    for g in personas:
        k = asignacion.get(g)
        pgt = pos_gt[g]
        if k is None:
            print(
                f"{g:<9}{eq_gt[g]:>5}{len(pgt):>8}{'—':>11}{'—':>9}"
                f"{recorrido(pgt):>13.1f}m{'—':>15}"
            )
            cobertura.append(0.0)
            continue
        psis = pos_sis[k]
        comunes = sorted(set(pgt) & set(psis))
        if not comunes:
            continue
        e = [
            float(np.hypot(psis[f][0] - pgt[f][0], psis[f][1] - pgt[f][1]))
            for f in comunes
        ]
        r_gt = recorrido({f: pgt[f] for f in comunes})
        r_sis = recorrido({f: psis[f] for f in comunes})
        errores.extend(e)
        cobertura.append(len(comunes) / len(pgt))
        rec_gt_t.append(r_gt)
        rec_sis_t.append(r_sis)
        # Estabilidad: cuántas identidades distintas tocan a esta persona
        tocan = {
            k2
            for k2, ident in enumerate(ids, start=1)
            for tr in ident
            for par in tr.det_idxs
            if mapa.get(tuple(par)) == g
        }
        estabilidad.append(len(tocan))
        print(
            f"{g:<9}{eq_gt[g]:>5}{len(pgt):>8}{len(comunes)/len(pgt):>10.0%}"
            f"{np.median(e):>9.2f}{r_gt:>13.1f}m{r_sis:>14.1f}m"
        )
    print("-" * len(cab))
    print(
        f"\n  error de posición por jugador: mediana "
        f"{np.median(errores):.2f} m · p90 {np.percentile(errores, 90):.2f} m"
    )
    print(
        f"  cobertura de la identidad asignada: mediana " f"{np.median(cobertura):.0%}"
    )
    print(
        f"  recorrido: GT {np.sum(rec_gt_t):.0f} m · sistema "
        f"{np.sum(rec_sis_t):.0f} m "
        f"({np.sum(rec_sis_t)/max(np.sum(rec_gt_t),1e-9)-1:+.0%})"
    )
    print(
        f"  ESTABILIDAD: identidades distintas por jugador, mediana "
        f"{np.median(estabilidad):.0f} · máx {max(estabilidad)}"
    )

    print("\n" + "=" * 72)
    print("FAMILIA B — NO DEPENDEN DE LA IDENTIDAD  (⚠ insensibles al tracker)")
    print("=" * 72)
    print("  Se conservan porque dicen que un informe COLECTIVO es viable")
    print("  con lo que hay hoy. No sirven para juzgar la asociación.\n")

    def por_equipo(fuente_pos, fuente_eq):
        pf = {}
        for clave, puntos in fuente_pos.items():
            eq = fuente_eq(clave)
            if eq not in ("A", "B"):
                continue
            for f, xy in puntos.items():
                pf.setdefault((f, eq), []).append(xy)
        return pf

    pf_sis = por_equipo(
        pos_sis, lambda k: str(equipos.get(k, "otro")).replace("portero_", "")
    )
    pf_gt = por_equipo(pos_gt, lambda g: eq_gt[g])
    m = (
        metricas_producto(pf_sis)
        .set_index(["frame", "equipo"])
        .join(
            metricas_producto(pf_gt).set_index(["frame", "equipo"]),
            rsuffix="_gt",
            how="inner",
        )
    )
    print(
        f"  centroide del equipo: "
        f"{np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt).median():.2f} m"
    )
    print(f"  anchura del bloque:   {(m.ancho - m.ancho_gt).abs().median():.2f} m")
    print(
        f"  profundidad:          {(m.profundo - m.profundo_gt).abs().median():.2f} m"
    )

    # Ocupación por zonas (3x3), también insensible a la identidad
    largo, ancho = cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]

    def ocupacion(pf):
        z = Counter()
        for (_f, eq), puntos in pf.items():
            for x, y in puntos:
                zx = min(int(x / largo * ZONAS_X), ZONAS_X - 1)
                zy = min(int(y / ancho * ZONAS_Y), ZONAS_Y - 1)
                z[(eq, zx, zy)] += 1
        total = sum(z.values()) or 1
        return {k: v / total for k, v in z.items()}

    oc_s, oc_g = ocupacion(pf_sis), ocupacion(pf_gt)
    dif = sum(abs(oc_s.get(k, 0) - oc_g.get(k, 0)) for k in set(oc_s) | set(oc_g)) / 2
    print(
        f"  ocupación por zonas (3×3): error total {dif:.1%} "
        "de la masa mal repartida"
    )


if __name__ == "__main__":
    main()
