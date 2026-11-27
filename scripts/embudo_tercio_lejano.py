#!/usr/bin/env python
"""Embudo: ¿en qué etapa muere cada persona del GT que «falta» en el tercio lejano del F11?

Segunda opinión, 27-nov-2026. El oráculo de F11 (`docs/segunda_opinion_26nov.md`) dice que en el
tercio lejano del alevín A («Villaviciosa», GT de 30 s) falta el 47 % de las personas del GT. Aquí
se
sigue a CADA persona del GT (A/B) por las etapas del pipeline y se anota la PRIMERA en la que se
pierde:

  E1 detector: ¿hay una detección del caché de producción (SAHI, conf ≥ 0,3, ya fusionada con
     GREEDYNMM y filtrada por área) que case con su caja del GT? (casado 1-a-1 de centros, con el
     centro dentro de la caja del GT ampliada un 20 %: el mismo de `lit_franjas_lejanas.py`).
  E2 pre-tracking: ¿esa detección llega al caché que recibe el tracker? (el processor puede
     filtrarla antes, p. ej. por estar fuera del campo).
  E3 tracking: ¿pertenece a alguna identidad? (ByteTrack descarta lo que no confirma).
  E4 post-proceso y export: ¿su identidad tiene fila REAL en ese frame en el CSV?
  E5 posición: ¿esa fila está a ≤ 2 m de la persona? Si no, se separa:
     E5a la propia DETECCIÓN ya está a > 2 m (pie de la caja / proyección en el fondo);
     E5b la detección está cerca y es la FILA la que se mueve (suavizado o identidad que mezcla).
  E6 casado: ¿el casado 1-a-1 del oráculo le da una fila? (puede quedarse sin ella si otra persona
     se lleva la suya).

Para cada etapa: cuántas personas del tercio lejano mueren ahí y su alto en píxeles.

**Control del instrumento**: el CSV de esta pasada (configs de `main`, exportados con `git show`)
tiene que ser idéntico byte a byte al del oráculo (`outputs/literatura/banco/villa/
posiciones_actual.csv`), y la cifra de «faltan» del tercio lejano tiene que salir igual (47 %).

Solo lee: corre `procesar_desde_cache` con los configs de `main` en una carpeta de salida nueva.

Uso:
    python scripts/embudo_tercio_lejano.py --configs-main <carpeta con configs/ de main> \\
        --salida outputs/embudo_tercio_lejano
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

from src.evaluation.desglose_error import (  # noqa: E402
    EQUIPOS,
    casar_frame,
    equipo_de_etiqueta,
)
from src.evaluation.gt_parser import parsear_cvat  # noqa: E402

GT = R / "data/annotations/ground_truth_tracking/annotations.xml"
HOMOGRAFIA = R / "data/calibracion/homografia.npy"
OFFSET, PASO, ANCHO, RADIO = 7500, 15, 68.0, 2.0
CSV_ORACULO = R / "outputs/literatura/banco/villa/posiciones_actual.csv"
ETAPAS = ["E1_detector", "E2_pre_tracking", "E3_tracking", "E4_sin_fila",
          "E5a_deteccion_lejos", "E5b_fila_movida", "E6_casado", "presente"]  # fmt: skip


def casar_cajas(g: np.ndarray, dd: np.ndarray) -> dict:
    """{i del GT: j de la detección}: casado 1-a-1 de centros, centro dentro de la caja ±20 %."""
    if not len(g) or not len(dd):
        return {}
    cg, cd = (g[:, :2] + g[:, 2:]) / 2, (dd[:, :2] + dd[:, 2:]) / 2
    dist = np.linalg.norm(cg[:, None] - cd[None], axis=2)
    mw, mh = 0.2 * (g[:, 2] - g[:, 0]), 0.2 * (g[:, 3] - g[:, 1])
    ok = (
        (cd[None, :, 0] >= (g[:, 0] - mw)[:, None])
        & (cd[None, :, 0] <= (g[:, 2] + mw)[:, None])
        & (cd[None, :, 1] >= (g[:, 1] - mh)[:, None])
        & (cd[None, :, 1] <= (g[:, 3] + mh)[:, None])
    )
    i_, j_ = linear_sum_assignment(np.where(ok, dist, 1e6))
    return {int(i): int(j) for i, j in zip(i_, j_) if ok[i, j]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--configs-main", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    import pickle

    import banco_mision as bm

    bm.SALIDA, bm.BASE_CONFIGS = a.salida, a.configs_main
    csv, identidades, cache_trk = bm.correr_capturando("villa", "main", {}, {})
    identico = Path(csv).read_bytes() == CSV_ORACULO.read_bytes()
    print(f"control: CSV idéntico al del oráculo: {identico}")

    import yaml

    cfg = yaml.safe_load(open(a.configs_main / bm.PATAS["villa"]["config"]))
    crudo = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(open(R / cfg["rutas"]["cache"], "rb"))["cache"]
    }
    H = np.load(HOMOGRAFIA)
    filas = pd.read_csv(csv)
    reales = filas[filas.es_real == 1]
    por_frame = {f: g.reset_index(drop=True) for f, g in reales.groupby("frame")}
    fila_de = {(int(r.frame), int(r.id_jugador)): r for r in reales.itertuples()}
    ident_de = {fj: n for n, ident in enumerate(identidades, start=1) for fj in ident}

    def a_metros(x, y):
        p = H @ np.array([x, y, 1.0])
        return p[:2] / p[2]

    # el GT por frame: caja, equipo y posición en metros (el pie: centro del borde inferior)
    gt = {}
    for tr in parsear_cvat(GT):
        for c in tr.cajas:
            e = equipo_de_etiqueta(c.team if c.team is not None else tr.team)
            if e not in EQUIPOS:
                continue
            f = OFFSET + PASO * c.frame_local
            pos = a_metros((c.xtl + c.xbr) / 2, c.ybr)
            gt.setdefault(f, []).append((e, (c.xtl, c.ytl, c.xbr, c.ybr), pos))

    salida = []
    for f in sorted(gt):
        personas = gt[f]
        g = np.array([p[1] for p in personas], float)
        dets = crudo.get(f, [])
        dd = np.array([d[2:6] for d in dets], float).reshape(-1, 4)
        caja_de = casar_cajas(g, dd)
        trk = np.array([d[2:6] for d in cache_trk.get(f, [])], float).reshape(-1, 4)
        s = por_frame.get(f)
        fc = casar_frame(
            f,
            [(e, pos[0], pos[1]) for e, _c, pos in personas],
            *(
                (s.x_m.to_numpy(), s.y_m.to_numpy(), s.etiqueta.to_numpy())
                if s is not None
                else (np.array([]), np.array([]), np.array([], dtype=object))
            ),
            RADIO,
        )
        for i, (e, caja, pos) in enumerate(personas):
            alto = caja[3] - caja[1]
            etapa, detalle, d_det = None, "", np.nan
            if i in caja_de:
                mx, my = dets[caja_de[i]][:2]
                d_det = float(np.hypot(mx - pos[0], my - pos[1]))
            if fc.personas[i].fila is not None:
                etapa = "presente"
            elif i not in caja_de:
                etapa = "E1_detector"
            else:
                det = dd[caja_de[i]]
                dif = np.abs(trk - det).sum(axis=1) if len(trk) else np.array([])
                if not len(dif) or dif.min() > 1e-3:
                    etapa = "E2_pre_tracking"
                else:
                    j = int(np.argmin(dif))
                    n = ident_de.get((f, j))
                    if n is None:
                        etapa = "E3_tracking"
                    elif (f, n) not in fila_de:
                        etapa = "E4_sin_fila"
                    else:
                        r = fila_de[(f, n)]
                        d = float(np.hypot(r.x_m - pos[0], r.y_m - pos[1]))
                        detalle = f"{d:.1f}"
                        if d <= RADIO:
                            etapa = "E6_casado"
                        elif d_det > RADIO:
                            # la propia detección ya cae lejos: pie/proyección, no la fila
                            etapa = "E5a_deteccion_lejos"
                        else:
                            etapa = "E5b_fila_movida"
            salida.append(
                (f, e, float(pos[0]), float(pos[1]), alto, etapa, detalle, d_det)
            )
    df = pd.DataFrame(
        salida,
        columns=["frame", "equipo", "x_m", "y_m", "alto_px", "etapa", "dist_fila_m",
                 "dist_det_m"],
    )  # fmt: skip
    df["tercio"] = np.minimum((df.y_m / ANCHO * 3).astype(int).clip(lower=0), 2)
    a.salida.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.salida / "embudo.csv", index=False)
    res = {"csv_identico_al_oraculo": identico, "por_tercio": {}}
    for t, gg in df.groupby("tercio"):
        c = Counter(gg.etapa)
        n, faltan = len(gg), len(gg) - c["presente"]
        res["por_tercio"][int(t)] = {
            "personas": n,
            "faltan_pct": round(100 * faltan / n, 1),
            "muere_en_pct_de_las_que_faltan": {
                k: round(100 * c[k] / max(faltan, 1), 1) for k in ETAPAS[:-1]
            },
            "alto_px_mediano_por_etapa": {
                k: round(float(gg[gg.etapa == k].alto_px.median()), 1)
                for k in ETAPAS
                if c[k]
            },
        }
    lej = df[(df.tercio == 2) & df.etapa.str.startswith("E5")]
    res["tercio_lejano_desplazadas"] = {
        "dist_fila_m_p25_p50_p75": [
            round(float(v), 2)
            for v in lej.dist_fila_m.astype(float).quantile([0.25, 0.5, 0.75])
        ],
        "dist_det_m_p25_p50_p75": [
            round(float(v), 2) for v in lej.dist_det_m.quantile([0.25, 0.5, 0.75])
        ],
    }
    pres = df[(df.tercio == 2) & (df.etapa == "presente")]
    res["tercio_lejano_presentes_dist_det_m_p50_p90"] = [
        round(float(v), 2) for v in pres.dist_det_m.quantile([0.5, 0.9])
    ]
    print(json.dumps(res, indent=1, ensure_ascii=False))
    (a.salida / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
