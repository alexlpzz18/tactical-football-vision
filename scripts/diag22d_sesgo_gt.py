#!/usr/bin/env python
"""Diagnóstico 22-oct (d), bloque 4: desplazadas en píxeles por zona y sesgo sistemático del GT.

Solo medición. Criterio en `docs/diagnostico_22oct_d.md`.
- 4a: por zona, fracción de desplazadas con la caja a > 2 m («punto del pie») y su error en
  píxeles (pie de la caja contra la persona del GT devuelta a la imagen).
- 4b: personas del GT con offset SISTEMÁTICO respecto a la detección cruda más cercana (≤ 5 m),
  con parejas que NO salen del casado.
- 4c: métricas del benjamín con y sin esas personas.

Uso:
    python scripts/diag22d_sesgo_gt.py --salida outputs/diagnostico_22oct_d
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
R_PAREJA_M, MIN_MUESTRAS, MIN_OFFSET_M = 5.0, 10, 1.0


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tabla_por_zona(D) -> dict:
    out = {}
    for z, g in D.groupby("zona"):
        pie = g[g.causa == "punto_del_pie"]
        out[z] = {
            "desplazadas": int(len(g)),
            "con_la_caja_a_mas_de_2m": int(len(pie)),
            "fraccion": round(len(pie) / len(g), 2),
            "error_px_mediana_p90": (
                [round(float(x), 1) for x in np.percentile(pie.error_px, [50, 90])]
                if len(pie)
                else None
            ),
            "error_m_mediana": (
                round(float(pie.dist_deteccion_m.median()), 2) if len(pie) else None
            ),
            "personas_distintas": int(g.persona.nunique()),
        }
    return out


def offsets_por_persona(cfg: dict) -> dict:
    """{persona: offsets (det − GT) en metros} con la detección cruda más cercana a ≤ 5 m."""
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    capt = pickle.load(open(R / cfg["cajas"], "rb"))
    gt = gt_a_por_frame(
        parsear_cvat(R / cfg["gt"]), np.load(R / cfg["H"]), cfg["offset"], cfg["paso"]
    )
    out: dict[int, list] = {}
    for f, obs in gt.items():
        dets = capt["cache_filtrado"].get(f)
        if not dets:
            continue
        P = np.array([(d[0], d[1]) for d in dets])
        for o in obs:
            if o.label == "referee":
                continue
            d = np.hypot(P[:, 0] - o.pos[0], P[:, 1] - o.pos[1])
            k = int(np.argmin(d))
            if d[k] <= R_PAREJA_M:
                out.setdefault(int(o.obj_id), []).append(P[k] - np.asarray(o.pos))
    return out


def sistematicos(offsets: dict) -> list[dict]:
    filas = []
    for pid, lista in offsets.items():
        V = np.array(lista)
        med = np.median(V, axis=0)
        norma = float(np.linalg.norm(med))
        u = med / norma if norma > 0 else med
        proy = V @ u
        filas.append(
            {
                "persona": pid,
                "n": int(len(V)),
                "offset_mediano_m": [round(float(med[0]), 2), round(float(med[1]), 2)],
                "norma_m": round(norma, 2),
                "p25_proyeccion_m": round(float(np.percentile(proy, 25)), 2),
                "sistematico": bool(
                    len(V) >= MIN_MUESTRAS
                    and norma >= MIN_OFFSET_M
                    and np.percentile(proy, 25) > 0
                ),
            }
        )
    return sorted(filas, key=lambda r: -r["norma_m"])


def metricas_benja(cfg: dict, excluir: set[int], D) -> dict:
    import pandas as pd

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    ce, c3 = _mod("comparar_escalas"), _mod("diag22c_v3")
    gt = gt_a_por_frame(
        parsear_cvat(R / cfg["gt"]), np.load(R / cfg["H"]), cfg["offset"], cfg["paso"]
    )
    gt = {f: [o for o in obs if int(o.obj_id) not in excluir] for f, obs in gt.items()}
    filas = pd.read_csv(R / cfg["csv"])
    # MISMO protocolo que `comparar_escalas.py` (el número de CLAUDE.md): solo filas reales y
    # solo los frames del GT que están en el CSV.
    reales = filas[filas.es_real == 1]
    comunes = sorted(set(reales.frame) & set(gt))
    r = ce.informar("benja", ce.casar(reales, {f: gt[f] for f in comunes}))
    Dx = D[~D.persona.isin(excluir)]
    return {
        "equipo_equivocado": f"{r['mal']} de {r['en_equipo']}",
        "equipo_equivocado_pct": round(100 * r["mal"] / max(r["en_equipo"], 1), 2),
        "personas_gt": r["gt"],
        "casadas_pct": round(100 * r["casadas"] / max(r["gt"], 1), 1),
        "cobertura_pct": round(c3.cobertura(filas, gt)["pct"], 2),
        "desplazadas": int(len(Dx)),
        "desplazadas_con_la_caja_a_mas_de_2m": int((Dx.causa == "punto_del_pie").sum()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    b1, dz = _mod("diag22b_filas"), _mod("diag22c_desplazadas")
    res = {}
    for nombre, cfg in b1.PATAS.items():
        D = dz.filas_desplazadas(nombre, cfg, b1)
        sis = sistematicos(offsets_por_persona(cfg))
        res[nombre] = {
            "4a_por_zona": tabla_por_zona(D),
            "4b_personas": sis,
            "4b_sistematicas": [s["persona"] for s in sis if s["sistematico"]],
        }
        if nombre == "benja":
            excl = set(res[nombre]["4b_sistematicas"])
            res[nombre]["4c"] = {
                "con_todas": metricas_benja(cfg, set(), D),
                "sin_las_sistematicas": metricas_benja(cfg, excl, D),
            }
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "bloque4.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
