#!/usr/bin/env python
"""¿Cuánto se recupera y cuánta basura entra al bajar el umbral del detector en el tercio lejano?

Lee las predicciones crudas guardadas por `embudo_detector_lejano.py` (SAHI en CPU, umbral 0,05, sin
fusionar) y, para cada umbral, repite el postproceso de producción (GREEDYNMM, IOS 0,5, sobre las
predicciones ≥ umbral; filtro de área) y cuenta, SOLO en el tercio lejano (y ≥ 2/3 del ancho, dentro
del campo):
- personas del GT (jugadores y árbitro) que casan con una detección (recall);
- detecciones que no casan con nadie del GT (falsos positivos por frame).
Mismo casado que el embudo (centro dentro de la caja del GT ±20 %, 1-a-1).

⚠️ Son los 74 frames del GT que tenían alguna persona perdida en el detector (no todos): el recall
absoluto está sesgado a la baja; lo que importa es la DIFERENCIA entre umbrales.

Uso:
    ~/.venvs/detector-cpu/bin/python scripts/embudo_umbral_lejano.py \\
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

LARGO = 105.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument(
        "--umbrales", type=float, nargs="+", default=[0.3, 0.25, 0.2, 0.15, 0.1]
    )
    a = ap.parse_args()
    from sahi.postprocess.combine import GreedyNMMPostprocess
    from sahi.prediction import ObjectPrediction

    from src.evaluation.gt_parser import parsear_cvat

    H = np.load(HOMOGRAFIA)

    def metros(x, y):
        p = H @ np.array([x, y, 1.0])
        return p[:2] / p[2]

    preds = pickle.load(open(a.salida / "predicciones_lejano.pkl", "rb"))
    gt = {}
    for tr in parsear_cvat(GT):  # todas las personas: un árbitro detectado no es basura
        for c in tr.cajas:
            gt.setdefault(OFFSET + PASO * c.frame_local, []).append(
                (c.xtl, c.ytl, c.xbr, c.ybr)
            )
    fusionar = GreedyNMMPostprocess(
        match_threshold=0.5, match_metric="IOS", class_agnostic=True
    )
    w, h = 2560, 1064

    def lejos(caja):
        x, y = metros((caja[0] + caja[2]) / 2, caja[3])
        return 0 <= x <= LARGO and ANCHO * 2 / 3 <= y <= ANCHO

    res = {"frames": len(preds)}
    for u in a.umbrales:
        recup = total = fp = 0
        for f, (crudas, _fus) in preds.items():
            ops = [
                ObjectPrediction(
                    bbox=[c[0], c[1], c[2], c[3]],
                    category_id=0,
                    score=c[4],
                    category_name="p",
                )
                for c in crudas
                if c[4] >= u
            ]
            dets = []
            for p in fusionar(ops):
                b = p.bbox
                if (b.maxx - b.minx) * (b.maxy - b.miny) <= 0.05 * w * h:
                    dets.append((b.minx, b.miny, b.maxx, b.maxy))
            g = np.array(gt[f], float)
            dd = np.array(dets, float).reshape(-1, 4)
            casa = casar_cajas(g, dd)
            g_lejos = [i for i in range(len(g)) if lejos(g[i])]
            total += len(g_lejos)
            recup += sum(i in casa for i in g_lejos)
            casadas = set(casa.values())
            fp += sum(1 for j in range(len(dd)) if j not in casadas and lejos(dd[j]))
        res[f"umbral_{u:g}"] = {
            "recall_lejano_pct": round(100 * recup / max(total, 1), 1),
            "personas_lejanas": total,
            "falsos_positivos_lejanos_por_frame": round(fp / len(preds), 2),
        }
    print(json.dumps(res, indent=1, ensure_ascii=False))
    (a.salida / "umbral_lejano.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
