#!/usr/bin/env python
"""Diagnóstico 22-oct (f), bloque A: pureza de las identidades por etapa y dónde cambian de persona.

Solo medición. Criterio en `docs/diagnostico_22oct_f.md`. Se interceptan, SIN cambiarlas, las
funciones de producción mientras corre `procesar_desde_cache`, y se guarda la salida de cada etapa:
ByteTrack → puerta de re-entrada → cosido por pureza → post-proceso.

Uso:
    python scripts/diag22f_pureza.py --salida outputs/diagnostico_22oct_f
"""

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
RADIO, CERCA_M, BORDE_PX, HUECO_S, N_AZAR = 2.0, 2.0, 20.0, 1.0, 20
PATAS = {
    "benja": dict(
        config=R / "configs/processor_benja_parte_entera.yaml",
        gt=R / "data/annotations/gt_benja/annotations.xml",
        H=R / "data/calibracion_benja/homografia_benja.npy",
        offset=9750,
        paso=15,
    ),
    "villa": dict(
        config=R / "configs/processor.yaml",
        gt=R / "data/annotations/ground_truth_tracking/annotations.xml",
        H=R / "data/calibracion/homografia.npy",
        offset=7500,
        paso=15,
    ),
}
ETAPAS = ["bytetrack", "puerta", "cosido", "postproceso"]


def capturar(config: Path, salida_csv: Path, ajustar=None) -> tuple[dict, dict]:
    """Corre producción `desde_cache` y devuelve {etapa: identidades} y el caché.

    `ajustar(cfg)`, opcional, modifica el config en memoria antes de correr (variantes).
    """
    import yaml

    import src.tracking.perfiles as perfiles
    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import procesar_desde_cache

    captura = {}
    originales = {
        "asociar_con_bytetrack": perfiles.asociar_con_bytetrack,
        "aplicar_puerta_reentrada": perfiles.aplicar_puerta_reentrada,
        "coser_por_pureza": perfiles.coser_por_pureza,
        "postprocesar": perfiles.postprocesar,
    }

    def espia(nombre, etapa, extraer=lambda r: r):
        def envuelta(*a, **k):
            r = originales[nombre](*a, **k)
            captura[etapa] = copy.deepcopy(extraer(r))
            return r

        return envuelta

    perfiles.asociar_con_bytetrack = espia("asociar_con_bytetrack", "bytetrack")
    perfiles.aplicar_puerta_reentrada = espia("aplicar_puerta_reentrada", "puerta")
    perfiles.coser_por_pureza = espia("coser_por_pureza", "cosido")
    perfiles.postprocesar = espia("postprocesar", "postproceso", lambda r: r[0])
    try:
        cfg = yaml.safe_load(open(config))
        cfg["modo"] = "desde_cache"
        cfg["rutas"]["salida_csv"] = str(salida_csv)
        cfg["rutas"]["salida_meta"] = str(salida_csv.with_suffix(".meta.json"))
        if ajustar is not None:
            ajustar(cfg)
        procesar_desde_cache(cfg)
    finally:
        for nombre, f in originales.items():
            setattr(perfiles, nombre, f)
    datos = cargar_cache(R / cfg["rutas"]["cache"])
    return captura, datos


def observaciones(etapa: str, ident, tray=None) -> list[tuple]:
    """[(frame, pos, det|None, tracklet_k)] de una identidad en esa etapa."""
    if etapa != "postproceso":
        return [
            (int(par[0]), np.asarray(pos), tuple(par), k)
            for k, tr in enumerate(ident)
            for pos, par in zip(tr.pos, tr.det_idxs)
        ]
    # post-proceso: posiciones (reales e interpoladas); las reales se reconocen por el frame
    por_frame = {
        int(par[0]): (tuple(par), k)
        for k, tr in enumerate(ident)
        for par in tr.det_idxs
    }
    out = []
    for f, pos, es_real in tray:
        det, k = por_frame.get(int(f), (None, None)) if es_real else (None, None)
        out.append((int(f), np.asarray(pos), det, k))
    return out


def bordes_teselas(w: int, h: int) -> tuple[list[float], list[float]]:
    """Bordes INTERIORES de las teselas de SAHI (la geometría de `get_slice_bboxes`)."""
    from sahi.slicing import get_slice_bboxes

    cajas = get_slice_bboxes(h, w, h // 2, w // 4, 0.2, 0.2)
    xs = sorted({c for b in cajas for c in (b[0], b[2]) if 0 < c < w})
    ys = sorted({c for b in cajas for c in (b[1], b[3]) if 0 < c < h})
    return xs, ys


def casar_etapa(etapa, idents, trays, gt):
    """(observaciones por identidad en frames del GT, {(identidad, frame): persona del GT})."""
    from scipy.optimize import linear_sum_assignment

    # observaciones por frame del GT
    obs_de = []
    for i, ident in enumerate(idents):
        tray = trays[i] if trays is not None else None
        obs_de.append([o for o in observaciones(etapa, ident, tray) if o[0] in gt])
    por_frame: dict[int, list] = {}
    for i, lista in enumerate(obs_de):
        for f, pos, det, k in lista:
            por_frame.setdefault(f, []).append((i, pos, det, k))
    persona = {}  # (identidad, frame) -> obj_id
    for f, obs in gt.items():
        filas = por_frame.get(f, [])
        if not filas:
            continue
        P = np.array([o.pos for o in obs])
        X = np.array([p for _i, p, _d, _k in filas])
        coste = np.hypot(X[None, :, 0] - P[:, None, 0], X[None, :, 1] - P[:, None, 1])
        coste = np.where(coste > RADIO, 1e6, coste)
        for a, b in zip(*linear_sum_assignment(coste)):
            if coste[a, b] < 1e6:
                persona[(filas[b][0], f)] = int(obs[a].obj_id)
    return obs_de, persona


def medir_etapa(etapa, idents, trays, gt, dets_de, fps, bordes, origen_bt, rng) -> dict:
    """Pureza, cambios de persona y sus marcas; y el control al azar."""
    obs_de, persona = casar_etapa(etapa, idents, trays, gt)

    def pureza(asig: dict) -> tuple[float, int]:
        por_id: dict[int, list] = {}
        for (i, _f), p in asig.items():
            por_id.setdefault(i, []).append(p)
        tot = sum(len(v) for v in por_id.values())
        maj = sum(max(np.unique(v, return_counts=True)[1]) for v in por_id.values())
        return (maj / tot if tot else float("nan")), tot

    pur, casadas = pureza(persona)
    # control: en cada frame, las personas casadas se reparten al azar entre las identidades
    azar = []
    por_f: dict[int, list] = {}
    for (i, f), p in persona.items():
        por_f.setdefault(f, []).append((i, p))
    for _ in range(N_AZAR):
        asig = {}
        for f, lista in por_f.items():
            ids = [i for i, _p in lista]
            ps = [p for _i, p in lista]
            rng.shuffle(ps)
            asig.update({(i, f): p for i, p in zip(ids, ps)})
        azar.append(pureza(asig)[0])

    # cambios de persona entre observaciones casadas CONSECUTIVAS de la identidad, y sus marcas;
    # las mismas marcas sobre TODOS los pares consecutivos dan la tasa base de cada una
    pos_gt = {
        f: {int(o.obj_id): np.asarray(o.pos) for o in obs} for f, obs in gt.items()
    }
    claves = ("cerca", "borde_tesela", "union_de_cosido", "tras_hueco_1s")
    marcas = dict.fromkeys(claves, 0)
    base = dict.fromkeys(claves, 0)
    n_cambios = sin_marca = n_pares = 0
    xs, ys = bordes
    for i, lista in enumerate(obs_de):
        info = {f: (det, k) for f, _p, det, k in lista}
        todas = sorted(
            o[0]
            for o in observaciones(etapa, idents[i], trays[i] if trays else None)
            if o[2] is not None
        )
        casadas_i = sorted(f for f in info if (i, f) in persona)
        for f, g in zip(casadas_i[:-1], casadas_i[1:]):
            pa, pb = persona[(i, f)], persona[(i, g)]
            m = set()
            for ff in (f, g):
                a = pos_gt[ff].get(pa)
                otros = [q for pid, q in pos_gt[ff].items() if pid != pa]
                if (
                    a is not None
                    and otros
                    and min(np.linalg.norm(q - a) for q in otros) < CERCA_M
                ):
                    m.add("cerca")
            det_f, _k_f = info.get(f, (None, None))
            det_g, _k_g = info.get(g, (None, None))
            if det_g is not None:
                d = dets_de[det_g[0]][det_g[1]]
                cx, cy = (d[2] + d[4]) / 2, (d[3] + d[5]) / 2
                if (
                    min([abs(cx - x) for x in xs] + [abs(cy - y) for y in ys])
                    <= BORDE_PX
                ):
                    m.add("borde_tesela")
            if (
                etapa in ("cosido", "postproceso")
                and det_f is not None
                and det_g is not None
            ):
                if origen_bt.get(det_f) != origen_bt.get(det_g):
                    m.add("union_de_cosido")
            reales = [x for x in todas if f <= x <= g]
            if len(reales) < 2 or max(np.diff(reales)) / fps > HUECO_S:
                m.add("tras_hueco_1s")
            n_pares += 1
            for x in m:
                base[x] += 1
            if pa == pb:
                continue
            n_cambios += 1
            for x in m:
                marcas[x] += 1
            sin_marca += not m
    return {
        "identidades": len(idents),
        "observaciones_casadas": casadas,
        "pureza": round(100 * pur, 2),
        "impureza": round(100 * (1 - pur), 2),
        "control_azar_pureza_media": round(100 * float(np.mean(azar)), 2),
        "pares_consecutivos": n_pares,
        "cambios_de_persona": n_cambios,
        "marcas_en_los_cambios": marcas,
        "sin_marca": sin_marca,
        "tasa_en_cambios_vs_base_pct": {
            x: [
                round(100 * marcas[x] / max(n_cambios, 1), 1),
                round(100 * base[x] / max(n_pares, 1), 1),
            ]
            for x in claves
        },
    }


def main() -> None:
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    res = {}
    for pata, p in PATAS.items():
        import pandas as pd

        csv = salida / f"pureza_{pata}.csv"
        captura, datos = capturar(p["config"], csv)
        gt = gt_a_por_frame(
            parsear_cvat(p["gt"]), np.load(p["H"]), p["offset"], p["paso"]
        )
        dets_de = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
        w, h = datos["wh"]
        bordes = bordes_teselas(int(w), int(h))
        fps = float(datos["fps"])
        # de qué identidad de ByteTrack viene cada detección (para las uniones del cosido)
        origen_bt = {
            tuple(par): i
            for i, ident in enumerate(captura["bytetrack"])
            for tr in ident
            for par in tr.det_idxs
        }
        # control del montaje: el post-proceso reproduce las posiciones del CSV
        filas = pd.read_csv(csv)
        csv_pos = set(zip(filas.frame, filas.x_m.round(2), filas.y_m.round(2)))
        tray_pos = {
            (int(f), round(float(pos[0]), 2), round(float(pos[1]), 2))
            for tray in captura["postproceso"]
            for f, pos, _r in tray
        }
        res[pata] = {
            "control_montaje_filas_csv_en_postproceso_pct": round(
                100 * len(csv_pos & tray_pos) / len(csv_pos), 2
            )
        }
        rng = np.random.default_rng(0)
        for etapa in ETAPAS:
            idents = captura["cosido"] if etapa == "postproceso" else captura[etapa]
            trays = captura["postproceso"] if etapa == "postproceso" else None
            res[pata][etapa] = medir_etapa(
                etapa, idents, trays, gt, dets_de, fps, bordes, origen_bt, rng
            )
    (salida / "bloqueA.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
