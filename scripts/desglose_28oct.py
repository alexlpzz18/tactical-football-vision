#!/usr/bin/env python
"""Desglose de los cambios de color que quedan y del error de las vistas por componentes.
Criterios en `docs/desglose_cambios_y_vistas.md`. SOLO lee los datos.

Uso:
    python scripts/desglose_28oct.py cambios
    python scripts/desglose_28oct.py componentes
"""

import argparse
import importlib.util
import itertools
import json
import math
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/desglose_28oct"
CSV_MAIN = R / "outputs/diagnostico_26oct_b/posiciones_main.csv"
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
FPS = 29.97002997002997
LARGO, ANCHO = 62.0, 40.0
RADIO_M = 2.0
COMPONENTES = ("etiqueta", "posicion", "presencia")


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def categoria(a: str, b: str) -> str:
    par = {str(a), str(b)}
    if "staff" in par:
        return "con staff"
    if "otro" in par:
        return "con otro"
    if any(p.startswith("portero") for p in par):
        return "con portero"
    return "A <-> B"


# ── 1. los cambios que quedan ────────────────────────────────────────────────────────────────


def cambios() -> dict:
    fp = _mod("fichas_pizarra")
    t0, t1 = fp.TRAMO
    Ts = np.arange(t0, t1, fp.PASO_S)
    datos, cat = fp.leer_pizarra(R / "outputs/pizarra_dibujo/histeresis_1s.html")
    F = [
        f
        for f in fp.simular(datos, cat, Ts)
        if not str(f["col"][0]).startswith("balon")
    ]
    lista = []
    for f in F:
        vis, col = f["vis"], f["col"]
        for k in np.where(vis[1:] & vis[:-1] & (col[1:] != col[:-1]))[0]:
            lista.append((f["id"], str(col[k]), str(col[k + 1]), float(Ts[k + 1])))
    n = len(lista)
    por_cat = Counter(categoria(a, b) for _i, a, b, _t in lista)
    por_dir = Counter(f"{a} -> {b}" for _i, a, b, _t in lista)
    por_ficha = Counter(i for i, *_ in lista)
    top = por_ficha.most_common(5)
    frac_top = sum(c for _i, c in top) / max(n, 1)
    # el porqué de las 5: etiquetas, tiempo en cada una, posición y pista del árbitro
    cap = pickle.load(open(CAPTURA, "rb"))
    pista = {(int(f), int(j)) for f, j in cap["pista"].items()}
    detalle = []
    for i, c in top:
        f = next(x for x in F if x["id"] == i)
        v = f["vis"]
        tiempo = Counter(str(x) for x in f["col"][v])
        obs = cap["identidades"][i - 1]
        en_tramo = [(a, b) for a, b in obs if t0 * FPS <= a < t1 * FPS]
        frac_pista = sum((int(a), int(b)) in pista for a, b in en_tramo) / max(
            len(en_tramo), 1
        )
        detalle.append(
            {
                "ficha": int(i),
                "cambios": c,
                "segundos_por_color": {
                    k: round(v_ * 0.1, 1) for k, v_ in tiempo.items()
                },
                "posicion_media_m": [
                    round(float(f["x"][v].mean()), 1),
                    round(float(f["y"][v].mean()), 1),
                ],
                "fraccion_en_la_pista_del_arbitro": round(frac_pista, 2),
                "cambios_en": [
                    f"{a}->{b} @ {int(t // 60)}:{t % 60:04.1f}"
                    for j, a, b, t in lista
                    if j == i
                ][:6],
            }
        )
    return {
        "cambios": n,
        "por_categoria": dict(por_cat),
        "por_direccion": dict(por_dir.most_common()),
        "fichas_con_cambios": len(por_ficha),
        "cambios_por_ficha": sorted(por_ficha.values(), reverse=True),
        "top5_fraccion": round(frac_top, 3),
        "concentrado_(>=50%_en_<=5)": frac_top >= 0.5,
        "top5": detalle,
    }


# ── 2. el error de las vistas, por componentes ───────────────────────────────────────────────


def _cargar():
    va = _mod("vistas_agregadas")
    gt = va._gt()
    frames = sorted(gt.frame.unique())
    d = pd.read_csv(CSV_MAIN)
    d = d[
        (d.es_real == 1)
        & d.x_m.between(0, LARGO)
        & d.y_m.between(0, ANCHO)
        & d.frame.isin(frames)
    ]
    sis = pd.DataFrame(
        {"frame": d.frame, "x": d.x_m, "y": d.y_m, "et": d.etiqueta.astype(str)}
    ).reset_index(drop=True)
    sis["eq"] = sis.et.map(va.equipo)
    # casado 1-a-1 a ≤ 2 m de TODAS las filas (también otro y staff) con el GT
    gt = gt.reset_index(drop=True)
    sis["fila_gt"] = -1
    gt["casada"] = False
    for f in frames:
        si, gi = np.where(sis.frame == f)[0], np.where(gt.frame == f)[0]
        if not len(si) or not len(gi):
            continue
        c = np.hypot(
            sis.x.to_numpy()[si][None, :] - gt.x.to_numpy()[gi][:, None],
            sis.y.to_numpy()[si][None, :] - gt.y.to_numpy()[gi][:, None],
        )
        c = np.where(c > RADIO_M, 1e6, c)
        for a, b in zip(*linear_sum_assignment(c)):
            if c[a, b] < 1e6:
                sis.loc[si[b], "fila_gt"] = gi[a]
                gt.loc[gi[a], "casada"] = True
    return va, sis, gt, frames


def _variante(sis, gt, arreglos: frozenset) -> pd.DataFrame:
    s = sis.copy()
    casada = s["fila_gt"] >= 0
    g = gt.loc[s["fila_gt"][casada]]
    if "etiqueta" in arreglos:
        s.loc[casada, "eq"] = g["eq"].to_numpy()
        s.loc[casada, "et"] = g.et.to_numpy()
    if "posicion" in arreglos:
        s.loc[casada, "x"] = g.x.to_numpy()
        s.loc[casada, "y"] = g.y.to_numpy()
    if "presencia" in arreglos:
        s = s[casada]
        faltan = gt[~gt.casada][["frame", "x", "y", "eq", "et"]]
        s = pd.concat([s, faltan.assign(fila_gt=-2)], ignore_index=True)
    return s[s["eq"].notna()][["frame", "x", "y", "eq", "et"]]


def _errores_ventana(va, var, gt, frames) -> dict:
    a = va.series(var).set_index(["frame", "eq"])
    b = va.series(gt[["frame", "x", "y", "eq", "et"]]).set_index(["frame", "eq"])
    j = a.join(b, rsuffix="_gt", how="right").reset_index()
    j["v"] = j.frame.map({f: i // 20 for i, f in enumerate(frames)})
    w = j.groupby(["v", "eq"]).mean(numeric_only=True)
    return {
        k: (
            float(np.hypot(r.cx - r.cx_gt, r.cy - r.cy_gt)),
            float(abs(r.anchura - r.anchura_gt)),
        )
        for k, r in w.iterrows()
    }


def componentes() -> dict:
    va, sis, gt, frames = _cargar()
    subconj = [
        frozenset(c) for n in range(4) for c in itertools.combinations(COMPONENTES, n)
    ]
    err = {s: _errores_ventana(va, _variante(sis, gt, s), gt, frames) for s in subconj}
    res = {}
    for clave in err[frozenset()]:
        fila = {}
        for m, nombre in enumerate(("centroide", "anchura")):
            v = {s: err[s][clave][m] for s in subconj}
            phi = {}
            for c in COMPONENTES:
                tot = 0.0
                otros = [x for x in COMPONENTES if x != c]
                for n in range(3):
                    for S in itertools.combinations(otros, n):
                        S = frozenset(S)
                        peso = (
                            math.factorial(len(S)) * math.factorial(3 - len(S) - 1) / 6
                        )
                        # contribución = cuánto BAJA el error al arreglar c
                        tot += peso * (v[S] - v[S | {c}])
                phi[c] = round(tot, 3)
            total = v[frozenset()] - v[frozenset(COMPONENTES)]
            fila[nombre] = {
                "error": round(v[frozenset()], 3),
                "con_todo_arreglado": round(v[frozenset(COMPONENTES)], 3),
                "shapley": phi,
                "por_separado": {c: round(v[frozenset({c})], 3) for c in COMPONENTES},
                "posicion+presencia_pct": (
                    round(100 * (phi["posicion"] + phi["presencia"]) / total, 1)
                    if total > 1e-9
                    else None
                ),
            }
        v_, e = clave
        fila["falla"] = (
            fila["centroide"]["error"] > 1.0 or fila["anchura"]["error"] > 1.5
        )
        res[f"ventana_{v_}_{e}"] = fila
    fallan = [k for k, f in res.items() if f["falla"]]
    res["criterio"] = {
        "ventanas_que_fallan": fallan,
        "posicion+presencia_>50%_en_las_que_fallan": {
            k: {
                m: (res[k][m]["posicion+presencia_pct"] or 0) > 50
                for m in ("centroide", "anchura")
                if (m == "centroide" and res[k]["centroide"]["error"] > 1.0)
                or (m == "anchura" and res[k]["anchura"]["error"] > 1.5)
            }
            for k in fallan
        },
    }
    res["filas_casadas"] = int((sis["fila_gt"] >= 0).sum())
    res["sobran_de_equipo"] = int(((sis["fila_gt"] < 0) & sis["eq"].notna()).sum())
    res["faltan"] = int((~gt.casada).sum())
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["cambios", "componentes"])
    args = ap.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)
    res = {"cambios": cambios, "componentes": componentes}[args.accion]()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=str)
    (SALIDA / f"{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
