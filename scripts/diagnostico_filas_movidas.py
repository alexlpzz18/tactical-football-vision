#!/usr/bin/env python
"""¿Qué etapa mueve la fila del CSV a 4-6 m de su propia detección? (docs/traza_por_etapas.md)

Solo diagnóstico, local, sin tocar producción. Parte de las pérdidas «e» (post-proceso) de la
traza por etapas: personas con una detección propia dentro de una identidad A/B, pero cuya fila
del CSV no las cubre a ≤ 5 m.

Candidatas, y cómo se separan:
- **reproyección**: ByteTrack guarda la posición de la DETECCIÓN (mx, my) del caché, no la de
  su Kalman (`asociacion_bytetrack.py`). Se comprueba: posición de entrada al post-proceso =
  posición de la detección.
- **suavizado**: espía en `suavizar_trayectorias` con la trayectoria antes y después. Si antes
  está sobre la detección y después a metros, es el suavizado; y se reconstruye su ventana
  (cuántas muestras, cuánto TIEMPO abarca, qué saltos contiene) para decir POR QUÉ.
- **casado**: si la fila está cerca y el 1-a-1 se la da a otra persona, no se ha movido nada.

Uso:
    python scripts/diagnostico_filas_movidas.py --traza DIR   # DIR de traza_por_etapas.py
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

CONFIG = R / "configs/processor_benja_parte_entera.yaml"
ETAPAS = ("a_caja_cruda", "b_filtros", "c_identidad", "d_etiqueta", "e_csv")
BLOQUE = ("A", "B", "portero_A", "portero_B")


def ventana_de_suavizado(base: int, factor_medio: float, escalar: float, n: int) -> int:
    """La ventana que usa `suavizar_trayectorias` (misma fórmula), en muestras."""
    v = int(round(base * (1 + escalar * np.log1p(factor_medio))))
    v = max(base, min(v, n // 2 * 2 - 1, 61))
    return v - 1 if v % 2 == 0 else v


def casos_e(trabajo: Path):
    """Las personas perdidas en la etapa e (radio 5 m) y la detección/identidad que las cubría."""
    import pandas as pd
    import yaml

    from src.evaluation.desglose_error import casar_frame
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    C = pd.read_csv(trabajo / "casos.csv")
    cap = pickle.load(open(trabajo / "etapas.pkl", "rb"))
    cfg = yaml.safe_load(open(CONFIG))
    H = np.load(R / cfg["rutas"]["homografia"])
    gtm = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"), H, 9750, 15
    )
    etq, eq = cap["etiquetas_por_obs"], cap["equipos_final"]

    def primera(r):
        return next((e for e in ETAPAS if not r[f"{e}@5"]), None)

    salida = []
    for r in C[C.apply(primera, axis=1) == "e_csv"].itertuples():
        f, fil, obs = r.frame, cap["cache_filtrado"][r.frame], gtm[r.frame]
        lst = [
            (n, d)
            for n, ff, d in cap["obs"]
            if ff == f and (etq.get((n, f)) or eq.get(n, "otro")) in BLOQUE
        ]
        x = np.array([fil[d][0] for _n, d in lst])
        y = np.array([fil[d][1] for _n, d in lst])
        fc = casar_frame(
            f,
            [("X", o.pos[0], o.pos[1]) for o in obs],
            x,
            y,
            np.array(["A"] * len(x)),
            5.0,
        )
        k = [o.obj_id for o in obs].index(r.track)
        j = fc.personas[k].fila
        n, d = lst[j]
        salida.append({"frame": f, "track": r.track, "gt": (r.x, r.y), "id": n,
                       "det": (float(fil[d][0]), float(fil[d][1]))})  # fmt: skip
    return salida


def main() -> None:
    import pandas as pd
    import yaml

    import src.tracking.suavizado as sv
    from src.tracking_data.processor import procesar_desde_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--traza", required=True)
    args = ap.parse_args()
    trabajo = Path(args.traza)
    casos = casos_e(trabajo)

    capt = {}
    original = sv.suavizar_trayectorias

    def espia(trayectorias, params=None, resolucion=None, dt=0.12):
        capt["antes"] = [list(t) for t in trayectorias]
        capt["params"], capt["resolucion"], capt["dt"] = params, resolucion, dt
        out = original(trayectorias, params, resolucion=resolucion, dt=dt)
        capt["despues"] = [list(t) for t in out]
        return out

    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(trabajo / "diag.csv")
    cfg["rutas"]["salida_meta"] = str(trabajo / "diag_meta.json")
    sv.suavizar_trayectorias = espia
    try:
        procesar_desde_cache(cfg)
    finally:
        sv.suavizar_trayectorias = original
    csv = pd.read_csv(trabajo / "diag.csv")
    p, res, dt = capt["params"], capt["resolucion"], capt["dt"]
    base = max(3, int(round(p.ventana_s / dt)))
    base += base % 2 == 0

    informe = []
    for c in casos:
        n, f = c["id"], c["frame"]
        antes = capt["antes"][n - 1]
        despues = capt["despues"][n - 1]
        reales = [i for i, (_f, _p, real) in enumerate(antes) if real]
        k = next(i for i, ii in enumerate(reales) if antes[ii][0] == f)
        puntos = np.array([antes[i][1] for i in reales], dtype=float)
        factor = float(
            np.mean([res.factor(q) for q in puntos[:: max(1, len(puntos) // 10)]])
        )
        v = ventana_de_suavizado(base, factor, p.escalar_con_resolucion, len(puntos))
        lo, hi = max(0, k - v // 2), min(len(reales), k + v // 2 + 1)
        frames_v = [antes[reales[i]][0] for i in range(lo, hi)]
        pts_v = puntos[lo:hi]
        pasos = np.linalg.norm(np.diff(pts_v, axis=0), axis=1)
        huecos = np.diff(frames_v) / 29.97
        fila = csv[(csv.frame == f) & (csv.id_jugador == n)][["x_m", "y_m"]].to_numpy()[
            0
        ]
        pos_antes = np.asarray(antes[reales[k]][1], dtype=float)
        pos_despues = np.asarray(despues[reales[k]][1], dtype=float)
        gt = np.asarray(c["gt"])
        informe.append(
            {
                **c,
                "entrada_igual_a_det_m": float(
                    np.linalg.norm(pos_antes - np.asarray(c["det"]))
                ),
                "suavizado_mueve_m": float(np.linalg.norm(pos_despues - pos_antes)),
                "csv_igual_a_suavizada_m": float(np.linalg.norm(fila - pos_despues)),
                "csv_a_gt_m": float(np.linalg.norm(fila - gt)),
                "det_a_gt_m": float(np.linalg.norm(np.asarray(c["det"]) - gt)),
                "ventana_muestras": v,
                "ventana_base": base,
                "factor_resolucion_medio": factor,
                "ventana_abarca_s": (frames_v[-1] - frames_v[0]) / 29.97,
                "ventana_nominal_s": v * dt,
                "mayor_hueco_s": float(huecos.max()) if len(huecos) else 0.0,
                "mayor_salto_m": float(pasos.max()) if len(pasos) else 0.0,
                "media_ventana_a_suavizada_m": float(
                    np.linalg.norm(pts_v.mean(axis=0) - pos_despues)
                ),
                "x_ventana_min_max": (
                    float(pts_v[:, 0].min()),
                    float(pts_v[:, 0].max()),
                ),
            }
        )
        # Contrafactuales (solo para separar causas, no son una propuesta): la ventana BASE
        # (0,5 s, sin escalar) y la MEDIANA de la misma ventana larga.
        lo5, hi5 = max(0, k - base // 2), min(len(reales), k + base // 2 + 1)
        informe[-1]["csv_a_gt_con_ventana_base_m"] = float(
            np.linalg.norm(puntos[lo5:hi5].mean(axis=0) - gt)
        )
        informe[-1]["csv_a_gt_con_mediana_m"] = float(
            np.linalg.norm(np.median(pts_v, axis=0) - gt)
        )

    # El partido entero: qué ventana usa de verdad cada trayectoria, y cuántos pasos imposibles
    # (> 12 m/s entre muestras reales consecutivas) contiene la entrada al suavizado.
    ventanas, imposibles, pasos_tot = [], 0, 0
    for tr in capt["antes"]:
        pts = np.array([q for _f, q, real in tr if real], dtype=float)
        fr = np.array([f for f, _q, real in tr if real])
        if len(pts) < base:
            continue
        fac = float(np.mean([res.factor(q) for q in pts[:: max(1, len(pts) // 10)]]))
        ventanas.append(
            ventana_de_suavizado(base, fac, p.escalar_con_resolucion, len(pts))
        )
        v_ms = np.linalg.norm(np.diff(pts, axis=0), axis=1) / (np.diff(fr) / 29.97)
        imposibles += int((v_ms > 12).sum())
        pasos_tot += len(v_ms)
    ventanas = np.array(ventanas)
    partido = {
        "metodo": p.metodo,
        "ventana_nominal_s": base * dt,
        "ventana_real_s_p10_p50_p90": [
            float(q) * dt for q in np.percentile(ventanas, [10, 50, 90])
        ],
        "trayectorias_con_ventana_mayor_que_1s": float((ventanas * dt > 1.0).mean()),
        "pasos_imposibles_frac": imposibles / max(pasos_tot, 1),
    }
    print(json.dumps(partido))
    ids = {c["id"] for c in casos}
    pickle.dump(
        {n: capt["antes"][n - 1] for n in ids},
        open(trabajo / "trayectorias_casos.pkl", "wb"),
    )
    (trabajo / "filas_movidas.json").write_text(
        json.dumps({"casos": informe, "partido": partido}, indent=1)
    )
    for it in informe:
        print(
            json.dumps(
                {k: (round(v, 2) if isinstance(v, float) else v) for k, v in it.items()}
            )
        )


if __name__ == "__main__":
    main()
