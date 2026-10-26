#!/usr/bin/env python
"""Diagnóstico 22-oct (g), bloque C: ¿la persona 21 de Villaviciosa (y las 6 y 0) es un portero?

Solo medición, con el GT (posiciones; sin vídeo). Criterio en `docs/diagnostico_22oct_g.md`.

Uso:
    python scripts/diag22g_persona21.py --salida outputs/diagnostico_22oct_g
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
PERSONAS = (21, 6, 0)


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def equipo(e) -> str:
    e = str(e)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def main() -> None:
    import pandas as pd

    from src.campo_modelo import MODELO_F11
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    dv = _mod("diag22f_villa")
    gt = gt_a_por_frame(parsear_cvat(dv.GT), np.load(dv.H_GT), 7500, 15)
    modelo = MODELO_F11.con_dimensiones(100.0, 64.0)
    hoy = pd.read_csv(dv.HOY)
    cas = dv.casar_todas(hoy[hoy.es_real == 1], gt)
    etiqueta_de = {}
    for _f, fila, o in cas:
        etiqueta_de.setdefault(int(o.obj_id), []).append(str(fila.etiqueta))
    res = {}
    for pid in PERSONAS:
        pos, team, label = [], None, None
        ultimo = {"de_su_equipo_hacia_x0": 0, "de_su_equipo_hacia_x100": 0}
        for f, obs in gt.items():
            yo = [o for o in obs if int(o.obj_id) == pid]
            if not yo:
                continue
            o = yo[0]
            team, label = str(o.team), o.label
            pos.append(o.pos)
            mismos = [
                q.pos[0]
                for q in obs
                if equipo(q.team) == equipo(o.team) and q.label != "referee"
            ]
            if mismos and o.pos[0] <= min(mismos):
                ultimo["de_su_equipo_hacia_x0"] += 1
            if mismos and o.pos[0] >= max(mismos):
                ultimo["de_su_equipo_hacia_x100"] += 1
        P = np.array(pos)
        en_area = {}
        for margen in (0.0, 2.0):
            for lado, ((x0, x1), (y0, y1)) in modelo.areas_porteria(margen).items():
                dentro = (
                    (P[:, 0] >= x0)
                    & (P[:, 0] <= x1)
                    & (P[:, 1] >= y0)
                    & (P[:, 1] <= y1)
                )
                en_area[f"area_{lado}_margen_{margen:g}m"] = round(
                    100 * float(dentro.mean()), 1
                )
        etq = pd.Series(etiqueta_de.get(pid, [])).value_counts().to_dict()
        res[str(pid)] = {
            "equipo_gt": team,
            "label_gt": label,
            "frames": int(len(P)),
            "posicion_media": [round(float(x), 1) for x in P.mean(axis=0)],
            "posicion_mediana": [round(float(x), 1) for x in np.median(P, axis=0)],
            "rango_x": [round(float(P[:, 0].min()), 1), round(float(P[:, 0].max()), 1)],
            "pct_frames_en_area": en_area,
            "pct_frames_ultimo_hombre": {
                k: round(100 * v / len(P), 1) for k, v in ultimo.items()
            },
            "etiquetas_del_sistema_en_sus_filas": etq,
        }
    salida = Path(args.salida)
    (salida / "bloqueC.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
