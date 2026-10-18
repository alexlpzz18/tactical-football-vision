#!/usr/bin/env python
"""4b: ¿cuántas aristas sobreviven al filtro físico, y cuál es el TECHO?

Dos preguntas, y las dos van antes de construir el grafo.

**La barata**: sobre los tracklets ya partidos, ¿cuántas uniones son
siquiera *posibles*? Si el filtro de plausibilidad física —hueco acotado,
distancia compatible con la velocidad máxima, equipo compatible, escala
compatible— deja una o dos candidatas por tracklet, medio problema está
resuelto sin tocar la apariencia.

**La que evita perseguir un techo equivocado**: el ORÁCULO DEL GRAFO. Si
las uniones fueran perfectas —decididas con el GT— ¿a cuánto llega el
centroide? Ese número, y no el 0,42 m del oráculo de asociación, es el
listón del grafo real: el oráculo de asociación supone identidad perfecta
POR OBSERVACIÓN, y los tracklets que entran ya vienen con un 12 % de
contaminación que ninguna unión arregla.

Uso:
    python scripts/grafo_4b.py
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
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.partir_tracklets import (  # noqa: E402
    ParametrosPartir,
    partir_tracklets,
)

logger = logging.getLogger("grafo")

# Plausibilidad física. Nada de umbrales abstractos: velocidad humana,
# incertidumbre de proyección medida, y coherencia de escala.
V_MAX = 7.0  # m/s de un benjamín
SIGMA_CERCA, SIGMA_LEJOS = 0.11, 1.85
HUECO_MAX_S = 8.0  # más allá, el grafo no debería opinar
ESCALA_TOL = 0.45  # 45 % de diferencia de altura de caja admitida


def sigma(y):
    return float(np.clip(0.11 + 0.026 * y, SIGMA_CERCA, SIGMA_LEJOS))


def resumen(ident, alturas):
    """Extremos de un tracklet: cuándo, dónde y de qué tamaño."""
    obs = sorted(
        ((par, p) for tr in ident for p, par in zip(tr.pos, tr.det_idxs)),
        key=lambda o: o[0][0],
    )
    ts = sorted(t for tr in ident for t in tr.ts)
    alts = [alturas.get(tuple(par), 0.0) for par, _p in obs]
    return {
        "f_ini": obs[0][0][0],
        "f_fin": obs[-1][0][0],
        "t_ini": ts[0],
        "t_fin": ts[-1],
        "p_ini": np.asarray(obs[0][1]),
        "p_fin": np.asarray(obs[-1][1]),
        "alto": float(np.median([a for a in alts if a > 0] or [1.0])),
        "n": len(obs),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--umbral-partir", type=float, default=0.08)
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
    alturas = {
        (e["frame_idx"], i): float(d[5] - d[3])
        for e in cache
        for i, d in enumerate(e["dets"])
    }
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

    base = asociar_con_bytetrack(
        cache,
        datos["fps"],
        datos["sample"],
        ParametrosByteTrack.desde_dict(cfg_tr.get("bytetrack")),
    )
    ids = partir_tracklets(
        base, emb, ParametrosPartir(activo=True, umbral=args.umbral_partir)
    )
    print(f"\nTracklets tras partir (umbral {args.umbral_partir}): {len(ids)}")

    # Equipo dominante por tracklet, para el filtro de compatibilidad
    eq_gt = {}
    for obs in gt.values():
        for o in obs:
            eq_gt.setdefault(o.obj_id, str(o.team).replace("portero_", ""))
    equipo = []
    for ident in ids:
        gids = [mapa.get(tuple(par)) for tr in ident for par in tr.det_idxs]
        gids = [g for g in gids if g is not None]
        equipo.append(eq_gt.get(Counter(gids).most_common(1)[0][0]) if gids else None)

    R = [resumen(i, alturas) for i in ids]

    # ── Filtro de plausibilidad, acumulativo ──
    filtros = {"temporal": 0, "+velocidad": 0, "+equipo": 0, "+escala": 0}
    candidatas = {i: [] for i in range(len(ids))}
    total_pares = 0
    for a in range(len(ids)):
        for b in range(len(ids)):
            if a == b:
                continue
            A, B = R[a], R[b]
            if B["t_ini"] <= A["t_fin"]:  # B tiene que empezar DESPUÉS
                continue
            total_pares += 1
            dt = B["t_ini"] - A["t_fin"]
            if dt > HUECO_MAX_S:
                continue
            filtros["temporal"] += 1
            dist = float(np.linalg.norm(B["p_ini"] - A["p_fin"]))
            radio = V_MAX * dt + 2 * sigma(float(B["p_ini"][1]))
            if dist > radio:
                continue
            filtros["+velocidad"] += 1
            if equipo[a] and equipo[b] and equipo[a] != equipo[b]:
                continue
            filtros["+equipo"] += 1
            if A["alto"] > 0 and B["alto"] > 0:
                rel = abs(A["alto"] - B["alto"]) / max(A["alto"], B["alto"])
                if rel > ESCALA_TOL:
                    continue
            filtros["+escala"] += 1
            candidatas[a].append(b)

    print(
        f"\n── FILTRO DE PLAUSIBILIDAD (pares ordenados posibles: {total_pares}) ──\n"
    )
    cab = f"{'filtro':<26}{'aristas':>10}{'% del total':>13}"
    print(cab)
    print("-" * len(cab))
    for nombre, n in filtros.items():
        print(f"{nombre:<26}{n:>10}{n/max(total_pares,1):>12.1%}")

    grados = np.array([len(v) for v in candidatas.values()])
    print("\n── CANDIDATAS POR TRACKLET ──\n")
    print(
        f"  media {grados.mean():.1f} · mediana {np.median(grados):.0f} · "
        f"máx {grados.max()}"
    )
    for u in (0, 1, 2, 3):
        print(
            f"  con {u} candidata(s): {(grados == u).sum()} tracklets "
            f"({(grados == u).mean():.0%})"
        )
    print(f"  con más de 3: {(grados > 3).sum()} ({(grados > 3).mean():.0%})")

    # ── ORÁCULO DEL GRAFO: uniones perfectas sobre estas piezas ──
    grupos = {}
    for k, ident in enumerate(ids):
        gids = [mapa.get(tuple(par)) for tr in ident for par in tr.det_idxs]
        gids = [g for g in gids if g is not None]
        if gids:
            grupos.setdefault(Counter(gids).most_common(1)[0][0], []).append(ident)

    def producto(identidades_por_persona):
        pf = {}
        for gid, lista in identidades_por_persona.items():
            eq = eq_gt.get(gid)
            if eq not in ("A", "B"):
                continue
            for ident in lista:
                for tr in ident:
                    for pos, (f, _dd) in zip(tr.pos, tr.det_idxs):
                        pf.setdefault((f, eq), []).append((pos[0], pos[1]))
        return metricas_producto(pf)

    pf_gt = {}
    for f, obs in gt.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])

    m = (
        producto(grupos)
        .set_index(["frame", "equipo"])
        .join(verdad, rsuffix="_gt", how="inner")
    )
    ec = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt).median()
    ea = (m.ancho - m.ancho_gt).abs().median()
    ep = (m.profundo - m.profundo_gt).abs().median()
    r = analizar(ids, mapa)

    print("\n── ORÁCULO DEL GRAFO: si las uniones fueran PERFECTAS ──\n")
    cab2 = f"{'variante':<34}{'ident.':>8}{'centroide':>12}{'anchura':>10}"
    print(cab2)
    print("-" * len(cab2))
    print(f"{'sistema (línea base)':<34}{'84':>8}{'1.55 m':>12}{'0.93 m':>10}")
    print(
        f"{'ORÁCULO DEL GRAFO (piezas al 88 %)':<34}{len(grupos):>8}"
        f"{ec:>11.2f}m{ea:>9.2f}m"
    )
    print(
        f"{'oráculo de ASOCIACIÓN (perfecta)':<34}{'14':>8}{'0.42 m':>12}{'0.33 m':>10}"
    )
    print(f"\n  profundidad del oráculo del grafo: {ep:.2f} m")
    print(f"  pureza de las piezas que une: {r['pureza_obs']:.1%}")


if __name__ == "__main__":
    main()
