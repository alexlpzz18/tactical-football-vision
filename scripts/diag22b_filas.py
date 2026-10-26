#!/usr/bin/env python
"""Diagnóstico 22-oct (b), bloque 1: ¿de dónde salen las filas de más? Solo medición.

Criterios en `docs/diagnostico_22oct_b.md`.

Uso:
    python scripts/diag22b_filas.py --salida outputs/diagnostico_22oct_b
"""

import argparse
import importlib.util
import json
import pickle
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
RADIO_CASADO, R_DUP, R_FANTASMA, R_PAR, MIN_PAR_S = 2.0, 1.5, 5.0, 1.5, 1.0

PATAS = {
    "benja": dict(
        csv="outputs/arbitro_obs/posiciones.csv",
        cajas="outputs/arbitro_obs/cajas.pkl",
        gt="data/annotations/gt_benja/annotations.xml",
        H="data/calibracion_benja/homografia_benja.npy",
        offset=9750,
        paso=15,
        fps=29.97002997002997,
        por_equipo=7,
    ),
    "villa": dict(
        csv="outputs/diagnostico_22oct/villa/posiciones.csv",
        cajas="outputs/diagnostico_22oct/villa/cajas.pkl",
        gt="data/annotations/ground_truth_tracking/annotations.xml",
        H="data/calibracion/homografia.npy",
        offset=7500,
        paso=15,
        fps=25.0,
        por_equipo=11,
    ),
}


def equipo(etq: str) -> str:
    e = str(etq)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def clasificar_sobrante(etq, es_arbitro, d_casadas, d_todas) -> str:
    """Clase de una fila sin casar, en el orden fijado en el criterio."""
    if str(etq) in ("staff", "otro") or es_arbitro:
        return "staff_arbitro"
    if d_casadas < R_DUP:
        return "duplicado"
    if d_todas > R_FANTASMA:
        return "fantasma"
    return "desplazada"


def iou(a, b) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / (
        (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9
    )


def rachas_cerca(frames_cerca: list[int], paso: int) -> list[int]:
    """Longitudes (en muestras) de las rachas de frames consecutivos (paso del caché)."""
    if not frames_cerca:
        return []
    fs = sorted(frames_cerca)
    out, n = [], 1
    for a, b in zip(fs[:-1], fs[1:]):
        if b - a == paso:
            n += 1
        else:
            out.append(n)
            n = 1
    out.append(n)
    return out


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def medir_pata(nombre: str, cfg: dict) -> dict:
    import pandas as pd
    import yaml

    from src.evaluation.desglose_error import casar_frame
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.tracking.cache_io import cargar_cache

    filas = pd.read_csv(R / cfg["csv"])
    capt = pickle.load(open(R / cfg["cajas"], "rb"))
    gt = gt_a_por_frame(
        parsear_cvat(R / cfg["gt"]), np.load(R / cfg["H"]), cfg["offset"], cfg["paso"]
    )
    paso = int(np.median(np.diff(sorted(filas.frame.unique()))))
    proxy = set()
    if nombre == "benja":
        am = _mod("arbitro_medicion")
        c = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
        reales = filas[filas.es_real == 1]
        crudo = {
            e["frame_idx"]: e["dets"]
            for e in cargar_cache(R / c["rutas"]["cache"])["cache"]
        }
        W = am.masa_de_ventana(
            reales, crudo, pickle.load(open(R / c["rutas"]["cache_colores"], "rb"))
        )
        zb = (W.x_m >= am.ZONA_PORTERO_B_X) & (
            (W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY
        )
        W = W[(W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")]
        proxy = set(zip(W.frame, W.id_jugador))
    res = {}

    # 1a
    porf = {f: g for f, g in filas.groupby("frame")}
    clases, n_filas = [], 0
    for f in sorted(gt):
        g = porf.get(f)
        if g is None:
            continue
        jug = [o for o in gt[f] if o.label != "referee"]
        arb = [o.pos for o in gt[f] if o.label == "referee"]
        P = np.array([o.pos for o in jug])
        fc = casar_frame(
            f,
            [("X", p[0], p[1]) for p in P],
            g.x_m.to_numpy(),
            g.y_m.to_numpy(),
            g.etiqueta.to_numpy(),
            RADIO_CASADO,
        )
        casadas = np.array(
            [P[i] for i, p in enumerate(fc.personas) if p.fila is not None]
        )
        n_filas += len(g)
        for k, r in enumerate(g.itertuples()):
            if k in fc.persona_de_fila:
                continue
            xy = np.array([r.x_m, r.y_m])
            d_cas = (
                float(np.min(np.linalg.norm(casadas - xy, axis=1)))
                if len(casadas)
                else 1e9
            )
            d_tod = float(np.min(np.linalg.norm(P - xy, axis=1))) if len(P) else 1e9
            es_arb = (f, int(r.id_jugador)) in proxy or any(
                np.linalg.norm(np.asarray(a) - xy) < RADIO_CASADO for a in arb
            )
            clases.append(
                (clasificar_sobrante(r.etiqueta, es_arb, d_cas, d_tod), int(r.es_real))
            )
    C = pd.DataFrame(clases, columns=["clase", "real"])
    res["1a"] = {
        "frames_gt": len(gt),
        "filas_en_esos_frames": n_filas,
        "sin_casar": int(len(C)),
        "por_clase": {
            k: {
                "reales": int(((C.clase == k) & (C.real == 1)).sum()),
                "interpoladas": int(((C.clase == k) & (C.real == 0)).sum()),
            }
            for k in ("staff_arbitro", "duplicado", "fantasma", "desplazada")
        },
    }

    # 1b
    eq = filas.etiqueta.map(equipo)
    cuenta = (
        filas.assign(eq=eq)[eq.isin(["A", "B"])]
        .groupby(["frame", "eq"])
        .size()
        .unstack(fill_value=0)
    )
    cabe = cfg["por_equipo"]
    res["1b"] = {
        "partido_media_A_B": [float(cuenta.A.mean()), float(cuenta.B.mean())],
        "partido_frames_exceso_A_B_ambos": [
            int((cuenta.A > cabe).sum()),
            int((cuenta.B > cabe).sum()),
            int(((cuenta.A > cabe) & (cuenta.B > cabe)).sum()),
        ],
        "partido_frames": int(len(cuenta)),
    }
    dif = []
    for f in sorted(gt):
        if f not in cuenta.index:
            continue
        gte = pd.Series(
            [equipo(o.team) for o in gt[f] if o.label != "referee"]
        ).value_counts()
        dif.append(
            (cuenta.loc[f, "A"] - gte.get("A", 0), cuenta.loc[f, "B"] - gte.get("B", 0))
        )
    dif = np.array(dif)
    res["1b"]["ventana_gt_filas_menos_personas_A_B"] = [
        float(dif[:, 0].mean()),
        float(dif[:, 1].mean()),
    ]

    # 1c: pares simultáneos cerca, mismo equipo contra equipos contrarios
    reales = filas[(filas.es_real == 1) & eq.isin(["A", "B"])].assign(eq=eq)
    cerca, posibles = {}, {"mismo": 0, "contrario": 0}
    for f, g in reales.groupby("frame"):
        ids, P, E = (
            g.id_jugador.to_numpy(),
            g[["x_m", "y_m"]].to_numpy(),
            g["eq"].to_numpy(),
        )
        for i, j in combinations(range(len(g)), 2):
            tipo = "mismo" if E[i] == E[j] else "contrario"
            posibles[tipo] += 1
            if np.linalg.norm(P[i] - P[j]) < R_PAR:
                cerca.setdefault(
                    (min(ids[i], ids[j]), max(ids[i], ids[j]), tipo), []
                ).append(f)
    min_muestras = int(np.ceil(MIN_PAR_S * cfg["fps"] / paso))
    pares = {"mismo": 0, "contrario": 0}
    muestras = {"mismo": 0, "contrario": 0}
    for (_a, _b, tipo), fs in cerca.items():
        largas = [n for n in rachas_cerca(fs, paso) if n >= min_muestras]
        if largas:
            pares[tipo] += 1
            muestras[tipo] += sum(largas)
    res["1c"] = {
        "pares_mismo_equipo": pares["mismo"],
        "pares_equipo_contrario": pares["contrario"],
        "tasa_por_par_posible_mismo": muestras["mismo"] / max(posibles["mismo"], 1),
        "tasa_por_par_posible_contrario": muestras["contrario"]
        / max(posibles["contrario"], 1),
    }

    # 1d: cajas solapadas en la caché, antes del tracker
    n_cajas = n_solapadas = n_pares = 0
    for _f, dets in capt["cache_filtrado"].items():
        cajas = [d[2:6] for d in dets]
        n_cajas += len(cajas)
        tocadas = set()
        for i, j in combinations(range(len(cajas)), 2):
            if iou(cajas[i], cajas[j]) > 0.5:
                n_pares += 1
                tocadas |= {i, j}
        n_solapadas += len(tocadas)
    res["1d"] = {
        "cajas": n_cajas,
        "pares_iou_mayor_0_5": n_pares,
        "cajas_implicadas": n_solapadas,
        "pct_cajas": 100 * n_solapadas / max(n_cajas, 1),
    }
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    res = {nombre: medir_pata(nombre, cfg) for nombre, cfg in PATAS.items()}
    (salida / "bloque1.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
