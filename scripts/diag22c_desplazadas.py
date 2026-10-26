#!/usr/bin/env python
"""Diagnóstico 22-oct (c), bloque 3: descomposición de las filas «desplazadas». Solo medición.

Criterio en `docs/diagnostico_22oct_c.md`. Misma definición que el bloque 1 del 22-oct (b)
(`diag22b_filas.py`): fila sin casar 1-a-1 a 2 m, no staff/árbitro, a ≥ 1,5 m de toda persona
casada y a ≤ 5 m de alguna persona del GT.

Uso:
    python scripts/diag22c_desplazadas.py --salida outputs/diagnostico_22oct_c
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
LARGO = {"benja": 62.0, "villa": 100.0}
BINS_DIST = [1.5, 2.0, 3.0, 4.0, 5.0001]
R_DET = 2.0  # ¿la DETECCIÓN de la fila está cerca de la persona?


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def zona(x: float, largo: float) -> str:
    if largo == 62.0:
        cortes = [(0, 20), (20, 40), (40, 62)]
    else:
        cortes = [(0, 33.3), (33.3, 66.7), (66.7, 100)]
    for a, b in cortes:
        if x < b:
            return f"x{a:g}-{b:g}"
    return f"x{cortes[-1][0]:g}-{cortes[-1][1]:g}"


def bin_dist(d: float) -> str:
    for a, b in zip(BINS_DIST[:-1], BINS_DIST[1:]):
        if a <= d < b:
            return f"{a:g}-{min(b, 5):g}"
    return "fuera"


def filas_desplazadas(nombre: str, cfg: dict, b1):
    """DataFrame con una fila por «desplazada» (causa, zona, identidad y error en píxeles)."""
    import pandas as pd

    from src.evaluation.desglose_error import casar_frame
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    filas = pd.read_csv(R / cfg["csv"])
    capt = pickle.load(open(R / cfg["cajas"], "rb"))
    H = np.load(R / cfg["H"])
    H_inv = np.linalg.inv(H)
    gt = gt_a_por_frame(parsear_cvat(R / cfg["gt"]), H, cfg["offset"], cfg["paso"])
    proxy = set()
    if nombre == "benja":
        import yaml

        from src.tracking.cache_io import cargar_cache

        am = _mod("arbitro_medicion")
        c = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
        crudo = {
            e["frame_idx"]: e["dets"]
            for e in cargar_cache(R / c["rutas"]["cache"])["cache"]
        }
        W = am.masa_de_ventana(
            filas[filas.es_real == 1],
            crudo,
            pickle.load(open(R / c["rutas"]["cache_colores"], "rb")),
        )
        zb = (W.x_m >= am.ZONA_PORTERO_B_X) & (
            (W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY
        )
        W = W[(W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")]
        proxy = set(zip(W.frame, W.id_jugador))

    porf = {f: g for f, g in filas.groupby("frame")}
    # casado de cada frame del GT y, por identidad del sistema, a qué persona del GT se casa
    casado, persona_de_id = {}, {}
    for f in sorted(gt):
        g = porf.get(f)
        if g is None:
            continue
        jug = [o for o in gt[f] if o.label != "referee"]
        fc = casar_frame(
            f,
            [("X", o.pos[0], o.pos[1]) for o in jug],
            g.x_m.to_numpy(),
            g.y_m.to_numpy(),
            g.etiqueta.to_numpy(),
            b1.RADIO_CASADO,
        )
        casado[f] = (fc, g, jug)
        ids = g.id_jugador.to_numpy()
        for k, i in fc.persona_de_fila.items():
            persona_de_id[(f, int(ids[k]))] = jug[i].obj_id

    out = []
    for f, (fc, g, jug) in casado.items():
        P = np.array([o.pos for o in jug])
        arb = [o.pos for o in gt[f] if o.label == "referee"]
        casadas = np.array(
            [P[i] for i, p in enumerate(fc.personas) if p.fila is not None]
        )
        for k, r in enumerate(g.itertuples()):
            if k in fc.persona_de_fila:
                continue
            xy = np.array([r.x_m, r.y_m])
            d_cas = (
                float(np.min(np.linalg.norm(casadas - xy, axis=1)))
                if len(casadas)
                else 1e9
            )
            dists = np.linalg.norm(P - xy, axis=1) if len(P) else np.array([1e9])
            d_tod = float(dists.min())
            es_arb = (f, int(r.id_jugador)) in proxy or any(
                np.linalg.norm(np.asarray(a) - xy) < b1.RADIO_CASADO for a in arb
            )
            if b1.clasificar_sobrante(r.etiqueta, es_arb, d_cas, d_tod) != "desplazada":
                continue
            ip = int(np.argmin(dists))
            persona = jug[ip]
            # causa
            d_det = err_px = None
            if r.es_real == 0:
                causa = "interpolada"
            else:
                d = capt["obs"].get((int(r.id_jugador), f))
                if d is None:
                    causa = "sin_deteccion_registrada"
                else:
                    det = capt["cache_filtrado"][f][d]
                    d_det = float(
                        np.hypot(det[0] - persona.pos[0], det[1] - persona.pos[1])
                    )
                    causa = "punto_del_pie" if d_det > R_DET else "post_proceso"
                    # el mismo error en PÍXELES: pie de la caja contra la persona del GT
                    # devuelta a la imagen con la homografía inversa
                    q = H_inv @ np.array([persona.pos[0], persona.pos[1], 1.0])
                    err_px = float(
                        np.hypot(
                            (det[2] + det[4]) / 2 - q[0] / q[2], det[5] - q[1] / q[2]
                        )
                    )
            # cambio de identidad: ¿con quién se casa esta identidad 15 frames antes / después?
            vecinos = []
            for df in (-cfg["paso"], cfg["paso"]):
                q = persona_de_id.get((f + df, int(r.id_jugador)))
                vecinos.append(
                    "nadie"
                    if q is None
                    else ("misma" if q == persona.obj_id else "otra")
                )
            if "otra" in vecinos:
                cambio = "otra_persona_antes_o_despues"
            elif "misma" in vecinos:
                cambio = "misma_persona"
            else:
                cambio = "sin_casar_antes_ni_despues"
            out.append(
                {
                    "frame": f,
                    "id": int(r.id_jugador),
                    "persona": int(persona.obj_id),
                    "dist": bin_dist(d_tod),
                    "zona": zona(r.x_m, LARGO[nombre]),
                    "de_quien": (
                        "persona_sin_casar_(mal_puesta)"
                        if fc.personas[ip].fila is None
                        else "persona_ya_casada_(de_mas)"
                    ),
                    "causa": causa,
                    "identidad": cambio,
                    "dist_deteccion_m": d_det,
                    "error_px": err_px,
                }
            )
    return pd.DataFrame(out)


def medir_pata(nombre: str, cfg: dict, b1) -> dict:
    D = filas_desplazadas(nombre, cfg, b1)

    def tabla(col):
        return {
            str(k): {
                "filas": int(len(v)),
                "personas_distintas": int(v.persona.nunique()),
            }
            for k, v in D.groupby(col)
        }

    return {
        "desplazadas": int(len(D)),
        "personas_distintas": int(D.persona.nunique()),
        "identidades_distintas": int(D.id.nunique()),
        **{c: tabla(c) for c in ("dist", "zona", "de_quien", "causa", "identidad")},
        "causa_x_identidad": {
            f"{a}|{b}": int(n)
            for (a, b), n in D.groupby(["causa", "identidad"]).size().items()
        },
        "de_quien_x_causa": {
            f"{a}|{b}": int(n)
            for (a, b), n in D.groupby(["de_quien", "causa"]).size().items()
        },
        "por_persona": {
            str(pid): {
                "filas": int(len(v)),
                "zonas": v.zona.value_counts().to_dict(),
                "causas": v.causa.value_counts().to_dict(),
            }
            for pid, v in sorted(D.groupby("persona"), key=lambda kv: -len(kv[1]))
        },
        "persona_que_mas_aporta": (
            {
                "persona": int(D.persona.value_counts().index[0]),
                "filas": int(D.persona.value_counts().iloc[0]),
            }
            if len(D)
            else None
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    b1 = _mod("diag22b_filas")
    res = {nombre: medir_pata(nombre, cfg, b1) for nombre, cfg in b1.PATAS.items()}
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "bloque3.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
