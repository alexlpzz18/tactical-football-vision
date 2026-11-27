#!/usr/bin/env python
"""Opción barata para la etapa «fusión» del embudo lejano: no absorber una caja de ALTURA COMPLETA.

En el tercio lejano del alevín A, el 25 % de las personas que el detector pierde existen antes de la
fusión (conf ≥ 0,3) y GREEDYNMM las absorbe: en los 51 casos están contenidas ENTERAS en otra caja
(IOS = 1,0) que mide casi lo mismo de alto (×1,10) y es mucho más ancha (IoU 0,51). Es una caja que
cubre a DOS jugadores de pie. Un fragmento (cabeza, torso, pierna) también está contenido, pero es
mucho más bajo que su caja: por eso cambiar IOS por IOU se cerró (separaba fragmentos,
`docs/ios_vs_iou_jugadores.md`).

Variante: el mismo GREEDYNMM (IOS ≥ 0,5, por confianza, la caja fusionada es la unión), salvo que NO
se fusionan dos cajas si la más baja mide ≥ `ratio_alto` de la más alta (las dos son cuerpos
enteros)
y la unión es más ancha que `ratio_ancho` veces la más estrecha.

**Control del instrumento**: la reimplementación sin la excepción tiene que reproducir el GREEDYNMM
de
SAHI (mismas cajas) en los 74 frames.

Mide, por tercio de profundidad: personas del GT casadas (recall) y detecciones que no casan con
nadie
(falsos positivos por frame). La pregunta «¿qué podría estar inventando?»: fragmentos separados como
personas, que saldrían como falsos positivos nuevos sobre todo CERCA de la cámara (cajas grandes).

Uso:
    ~/.venvs/detector-cpu/bin/python scripts/embudo_fusion_lejano.py \\
        --salida outputs/embudo_tercio_lejano
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

from embudo_tercio_lejano import (  # noqa: E402
    ANCHO,
    GT,
    HOMOGRAFIA,
    OFFSET,
    PASO,
    casar_cajas,
)

CONF, MAX_AREA, W, H_IMG = 0.3, 0.05, 2560, 1064


def ios(a, b) -> float:
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return (
        iw
        * ih
        / max(min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])), 1e-9)
    )


def greedy_nmm(cajas: list, excepcion: dict | None) -> list:
    """GREEDYNMM (IOS ≥ 0,5): la de más confianza absorbe a las que solapan; caja = unión."""
    orden = sorted(range(len(cajas)), key=lambda i: -cajas[i][4])
    usada = [False] * len(cajas)
    salida = []
    for i in orden:
        if usada[i]:
            continue
        usada[i] = True
        a = list(cajas[i][:4])
        for j in orden:
            if usada[j] or ios(cajas[i], cajas[j]) < 0.5:
                continue
            if excepcion:
                bi, bj = cajas[i], cajas[j]
                hi, hj = bi[3] - bi[1], bj[3] - bj[1]
                wi, wj = bi[2] - bi[0], bj[2] - bj[0]
                ancho_union = max(bi[2], bj[2]) - min(bi[0], bj[0])
                if min(hi, hj) >= excepcion["ratio_alto"] * max(
                    hi, hj
                ) and ancho_union >= excepcion["ratio_ancho"] * min(wi, wj):
                    continue
            usada[j] = True
            b = cajas[j]
            a = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
        salida.append((*a, cajas[i][4]))
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--ratio-alto", type=float, default=0.85)
    ap.add_argument("--ratio-ancho", type=float, default=1.5)
    a = ap.parse_args()
    from sahi.postprocess.combine import GreedyNMMPostprocess
    from sahi.prediction import ObjectPrediction

    from src.evaluation.gt_parser import parsear_cvat

    fusionar = GreedyNMMPostprocess(
        match_threshold=0.5, match_metric="IOS", class_agnostic=True
    )
    Hm = np.load(HOMOGRAFIA)

    def tercio(caja) -> int | None:
        p = Hm @ np.array([(caja[0] + caja[2]) / 2, caja[3], 1.0])
        x, y = p[:2] / p[2]
        if not (0 <= x <= 105 and 0 <= y <= ANCHO):
            return None
        return min(int(y / ANCHO * 3), 2)

    preds = pickle.load(open(a.salida / "predicciones_lejano.pkl", "rb"))
    gt = {}
    for tr in parsear_cvat(GT):
        for c in tr.cajas:
            gt.setdefault(OFFSET + PASO * c.frame_local, []).append(
                (c.xtl, c.ytl, c.xbr, c.ybr)
            )
    variantes = {
        "produccion": None,
        "altura_completa": {"ratio_alto": a.ratio_alto, "ratio_ancho": a.ratio_ancho},
    }
    res, control = {}, [0, 0]
    for nombre, exc in variantes.items():
        cuenta = {
            t: [0, 0, 0] for t in (0, 1, 2)
        }  # personas, casadas, falsos positivos
        for f, (crudas, _fusion_005) in preds.items():
            altas = [c for c in crudas if c[4] >= CONF]
            dets = [
                d
                for d in greedy_nmm(altas, exc)
                if (d[2] - d[0]) * (d[3] - d[1]) <= MAX_AREA * W * H_IMG
            ]
            if exc is None:  # control: ¿reproduce el GREEDYNMM de SAHI sobre las ≥ 0,3?
                ops = [
                    ObjectPrediction(
                        bbox=list(c[:4]), category_id=0, score=c[4], category_name="p"
                    )
                    for c in altas
                ]
                ref = sorted(
                    tuple(
                        round(v, 1)
                        for v in (p.bbox.minx, p.bbox.miny, p.bbox.maxx, p.bbox.maxy)
                    )
                    for p in fusionar(ops)
                    if (p.bbox.maxx - p.bbox.minx) * (p.bbox.maxy - p.bbox.miny)
                    <= MAX_AREA * W * H_IMG
                )
                mia = sorted(tuple(round(v, 1) for v in d[:4]) for d in dets)
                control[0] += ref == mia
                control[1] += 1
            g = np.array(gt[f], float)
            dd = np.array([d[:4] for d in dets], float).reshape(-1, 4)
            casa = casar_cajas(g, dd)
            for i in range(len(g)):
                t = tercio(g[i])
                if t is not None:
                    cuenta[t][0] += 1
                    cuenta[t][1] += i in casa
            casadas = set(casa.values())
            for j in range(len(dd)):
                t = tercio(dd[j])
                if t is not None and j not in casadas:
                    cuenta[t][2] += 1
        res[nombre] = {
            f"tercio_{t}": {
                "recall_pct": round(100 * c[1] / max(c[0], 1), 1),
                "falsos_positivos_por_frame": round(c[2] / len(preds), 2),
            }
            for t, c in cuenta.items()
        }
    res["control_frames_identicos_a_sahi"] = f"{control[0]} de {control[1]}"
    print(json.dumps(res, indent=1, ensure_ascii=False))
    (a.salida / "fusion_lejano.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
