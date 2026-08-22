#!/usr/bin/env python
"""¿Son las uniones de los 244 trozos MÁS FÁCILES que las del grafo?

El modo "cortar 2 m" deja 244 trozos con 98,7 % de pureza y, con unión
perfecta, un centroide de 1,22 m — mejor que el 1,57 m de la puerta por
apariencia. Pero el oráculo del grafo ya dijo que unir no llega, así que
la pregunta es por qué este caso sería distinto.

**Hipótesis**: cortar en el momento de proximidad parte la identidad
justo donde la trayectoria es CONTINUA a ambos lados, así que las uniones
son triviales —hueco de un fotograma, misma posición, misma dirección— y
el filtro de plausibilidad física debería resolverlas casi solo.

**Criterio de abandono, fijado antes de medir**: si unir por
plausibilidad (una sola candidata → se une, sin apariencia ni coste ni
grafo global) NO baja de 1,57 m, es el mismo callejón del grafo con otro
nombre y se aplica la regla de los dos intentos.

Uso:
    python scripts/unir_por_plausibilidad.py
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from oraculos import metricas_producto  # noqa: E402
from pureza_sin_reentrada import analizar, duenos  # noqa: E402
from puerta_proximidad import aplicar  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402

logger = logging.getLogger("unir")
V_MAX = 7.0
HUECO_MAX_S = 3.0


def sigma(y):
    return float(np.clip(0.11 + 0.026 * y, 0.11, 1.85))


def extremos(ident):
    obs = sorted(
        ((par, p, t) for tr in ident for p, par, t in zip(tr.pos, tr.det_idxs, tr.ts)),
        key=lambda o: o[0][0],
    )
    return {
        "t_ini": obs[0][2],
        "t_fin": obs[-1][2],
        "p_ini": np.asarray(obs[0][1]),
        "p_fin": np.asarray(obs[-1][1]),
        "n": len(obs),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--dist-corte", type=float, default=2.0)
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
    gt = gt_a_por_frame(parsear_cvat(args.gt), H, frame_offset=9750, paso_gt=15)
    mapa = duenos(cache, gt)

    d = pickle.load(open("data/tracking_benja/emb_benja_siglip.pkl", "rb"))
    V = np.asarray(d["embeddings"], dtype=np.float32)
    crudo = {tuple(c): V[i] for i, c in enumerate(d["claves"])}
    emb = {}
    for e in datos["cache"]:
        f, j = e["frame_idx"], 0
        for i, det in enumerate(e["dets"]):
            if det[6] < conf:
                continue
            if (f, i) in crudo:
                emb[(f, j)] = crudo[(f, i)]
            j += 1

    eq_gt, pf_gt = {}, {}
    for f, obs in gt.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            eq_gt.setdefault(o.obj_id, eq)
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])

    base = asociar_con_bytetrack(
        cache,
        datos["fps"],
        datos["sample"],
        ParametrosByteTrack.desde_dict(cfg_tr.get("bytetrack")),
    )
    trozos, _r, _c = aplicar(base, emb, args.dist_corte, "cortar", 0.0)
    print(f"\nTrozos tras cortar a {args.dist_corte} m: {len(trozos)}")

    R = [extremos(t) for t in trozos]

    # ── ¿Cómo de fáciles son estas uniones? ──
    candidatas = {i: [] for i in range(len(trozos))}
    huecos, distancias = [], []
    for a in range(len(trozos)):
        for b in range(len(trozos)):
            if a == b:
                continue
            A, B = R[a], R[b]
            dt = B["t_ini"] - A["t_fin"]
            if dt <= 0 or dt > HUECO_MAX_S:
                continue
            dist = float(np.linalg.norm(B["p_ini"] - A["p_fin"]))
            if dist > V_MAX * dt + 2 * sigma(float(B["p_ini"][1])):
                continue
            candidatas[a].append(b)
            huecos.append(dt)
            distancias.append(dist)

    g = np.array([len(v) for v in candidatas.values()])
    print("\n── ¿SON UNIONES FÁCILES? ──\n")
    print(
        f"  hueco temporal: mediana {np.median(huecos):.2f} s "
        f"· p90 {np.percentile(huecos, 90):.2f} s"
    )
    print(
        f"  salto de posición: mediana {np.median(distancias):.2f} m "
        f"· p90 {np.percentile(distancias, 90):.2f} m"
    )
    print(
        f"\n  candidatas por trozo: media {g.mean():.1f} · mediana {np.median(g):.0f}"
    )
    for u in (0, 1, 2):
        print(f"    con {u}: {(g == u).sum()} ({(g == u).mean():.0%})")
    print(f"    con más de 2: {(g > 2).sum()} ({(g > 2).mean():.0%})")

    # ── Unir SOLO por plausibilidad: candidata única y mutua ──
    padre = list(range(len(trozos)))

    def raiz(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    entradas = {i: [] for i in range(len(trozos))}
    for a, vs in candidatas.items():
        for b in vs:
            entradas[b].append(a)
    n_uniones = 0
    for a, vs in candidatas.items():
        if len(vs) != 1:
            continue
        b = vs[0]
        if len(entradas[b]) != 1:  # mutua: b tampoco tiene otro origen
            continue
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[rb] = ra
            n_uniones += 1
    grupos = {}
    for i in range(len(trozos)):
        grupos.setdefault(raiz(i), []).extend(trozos[i])
    unidos = list(grupos.values())
    print(
        f"\n  uniones por candidata ÚNICA Y MUTUA: {n_uniones} "
        f"→ {len(trozos)} → {len(unidos)} identidades"
    )

    def evalua(identidades, perfecto=False):
        r = analizar(identidades, mapa)
        gr = {}
        for ident in identidades:
            gg = [mapa.get(tuple(par)) for tr in ident for par in tr.det_idxs]
            gg = [x for x in gg if x is not None]
            if not gg:
                continue
            clave = Counter(gg).most_common(1)[0][0] if perfecto else id(ident)
            gr.setdefault(clave, []).append(ident)
        pf = {}
        for clave, lista in gr.items():
            gg = [
                mapa.get(tuple(par))
                for ident in lista
                for tr in ident
                for par in tr.det_idxs
            ]
            gg = [x for x in gg if x is not None]
            if not gg:
                continue
            eq = eq_gt.get(Counter(gg).most_common(1)[0][0])
            if eq not in ("A", "B"):
                continue
            for ident in lista:
                for tr in ident:
                    for pp, (f, _dd) in zip(tr.pos, tr.det_idxs):
                        pf.setdefault((f, eq), []).append((pp[0], pp[1]))
        m = (
            metricas_producto(pf)
            .set_index(["frame", "equipo"])
            .join(verdad, rsuffix="_gt", how="inner")
        )
        cen = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt).median() if len(m) else np.nan
        return r, cen

    print("\n── CENTROIDE ──\n")
    cab = f"{'variante':<44}{'ident.':>8}{'pureza':>9}{'centroide':>12}"
    print(cab)
    print("-" * len(cab))
    r, cen = evalua(trozos, perfecto=True)
    print(
        f"{'244 trozos + UNIÓN PERFECTA (el techo)':<44}{'14':>8}"
        f"{r['pureza_obs']:>8.1%}{cen:>11.2f}m"
    )
    r, cen = evalua(unidos, perfecto=True)
    print(
        f"{'unidos por plausibilidad + unión perfecta':<44}{len(unidos):>8}"
        f"{r['pureza_obs']:>8.1%}{cen:>11.2f}m"
    )
    r, cen = evalua(unidos, perfecto=False)
    print(
        f"{'unidos por plausibilidad, SIN oráculo':<44}{len(unidos):>8}"
        f"{r['pureza_obs']:>8.1%}{cen:>11.2f}m"
    )
    print("\n  referencia a batir: 1.57 m (puerta por apariencia 3 m)")
    print("  techo del oráculo de asociación: 0.42 m")


if __name__ == "__main__":
    main()
