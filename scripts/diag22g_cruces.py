#!/usr/bin/env python
"""Diagnóstico 22-oct (g), bloque A: ¿los cambios de persona en los cruces son entre rivales?

Solo medición. Criterio en `docs/diagnostico_22oct_g.md`. Reutiliza la captura de etapas y el casado
de `scripts/diag22f_pureza.py`.

Uso:
    python scripts/diag22g_cruces.py --salida outputs/diagnostico_22oct_g
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CSV_POR_IDENTIDAD = {
    # benjamín SIN voto por observación (el 16,0 % del 22-oct e)
    "benja": R / "outputs/diagnostico_22oct_e/diag_sin_por_obs_benja.csv",
    # Villaviciosa ya etiqueta por identidad (el 23,6 %)
    "villa": R / "outputs/diagnostico_22oct/villa/posiciones.csv",
}


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def equipo(e) -> str:
    e = str(e)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def tipo(pa: int, pb: int, info: dict) -> str:
    if info[pa]["arbitro"] or info[pb]["arbitro"]:
        return "con_el_arbitro"
    return "rivales" if info[pa]["equipo"] != info[pb]["equipo"] else "companeros"


def cruces_e_impureza(obs_de, persona, gt, info) -> dict:
    """Cambios de persona (en cruce y en total) e impureza, por tipo."""
    pos_gt = {
        f: {int(o.obj_id): np.asarray(o.pos) for o in obs} for f, obs in gt.items()
    }
    cambios = {"en_cruce": {}, "todos": {}}
    for i, lista in enumerate(obs_de):
        casadas = sorted(f for f, _p, _d, _k in lista if (i, f) in persona)
        for f, g in zip(casadas[:-1], casadas[1:]):
            pa, pb = persona[(i, f)], persona[(i, g)]
            if pa == pb:
                continue
            t = tipo(pa, pb, info)
            cambios["todos"][t] = cambios["todos"].get(t, 0) + 1
            cerca = any(
                pa in pos_gt[ff]
                and pb in pos_gt[ff]
                and np.linalg.norm(pos_gt[ff][pa] - pos_gt[ff][pb]) < 2.0
                for ff in (f, g)
            )
            if cerca:
                cambios["en_cruce"][t] = cambios["en_cruce"].get(t, 0) + 1
    # impureza por tipo: las observaciones minoritarias de cada identidad
    por_id: dict[int, list[int]] = {}
    for (i, _f), p in persona.items():
        por_id.setdefault(i, []).append(p)
    total = sum(len(v) for v in por_id.values())
    impura = {}
    for ps in por_id.values():
        vals, n = np.unique(ps, return_counts=True)
        m = int(vals[np.argmax(n)])
        for p in ps:
            if p != m:
                t = tipo(m, int(p), info)
                impura[t] = impura.get(t, 0) + 1
    n_imp = sum(impura.values())
    return {
        "cambios_en_cruce": cambios["en_cruce"],
        "pct_rivales_en_cruce": round(
            100
            * cambios["en_cruce"].get("rivales", 0)
            / max(sum(cambios["en_cruce"].values()), 1),
            1,
        ),
        "cambios_todos": cambios["todos"],
        "impureza_pct": round(100 * n_imp / max(total, 1), 2),
        "impureza_por_tipo_puntos": {
            k: round(100 * v / total, 2) for k, v in impura.items()
        },
        "pct_de_la_impureza_entre_rivales": round(
            100 * impura.get("rivales", 0) / max(n_imp, 1), 1
        ),
    }


def error_por_identidad(csv: Path, gt, info) -> dict:
    """Las filas con el equipo mal, según la persona mayoritaria de su identidad."""
    import pandas as pd
    from scipy.optimize import linear_sum_assignment

    filas = pd.read_csv(csv)
    r = filas[filas.es_real == 1]
    porf = {f: g for f, g in r.groupby("frame")}
    casos = []  # (identidad, persona, etiqueta del sistema)
    for f, obs in gt.items():
        g = porf.get(f)
        gente = [
            o for o in obs if o.label != "referee" and equipo(o.team) in ("A", "B")
        ]
        if g is None or not gente:
            continue
        P = np.array([o.pos for o in gente])
        xy = g[["x_m", "y_m"]].to_numpy()
        coste = np.hypot(xy[None, :, 0] - P[:, None, 0], xy[None, :, 1] - P[:, None, 1])
        coste = np.where(coste > 2.0, 1e6, coste)
        for a, b in zip(*linear_sum_assignment(coste)):
            if coste[a, b] < 1e6:
                fila = g.iloc[b]
                casos.append(
                    (int(fila.id_jugador), int(gente[a].obj_id), equipo(fila.etiqueta))
                )
    con_eq = [c for c in casos if c[2] in ("A", "B")]
    directo = sum(info[p]["equipo"] == e for _i, p, e in con_eq)
    cruzado = len(con_eq) - directo
    mapa = {"A": "A", "B": "B"} if directo >= cruzado else {"A": "B", "B": "A"}
    por_id: dict[int, list[int]] = {}
    for i, p, _e in casos:
        por_id.setdefault(i, []).append(p)
    mayoritaria = {
        i: int(
            np.unique(ps, return_counts=True)[0][
                np.argmax(np.unique(ps, return_counts=True)[1])
            ]
        )
        for i, ps in por_id.items()
    }
    tiene_rival = {
        i: any(info[p]["equipo"] != info[mayoritaria[i]]["equipo"] for p in ps)
        for i, ps in por_id.items()
    }
    clases = {}
    for i, p, e in con_eq:
        if mapa[e] == info[p]["equipo"]:
            continue
        m = mayoritaria[i]
        if info[m]["equipo"] != info[p]["equipo"]:
            c = "mezcla_con_rival_(la_identidad_sigue_a_un_rival)"
        elif tiene_rival[i]:
            c = "identidad_de_su_equipo_con_rivales_dentro"
        else:
            c = "identidad_pura_mal_coloreada"
        clases[c] = clases.get(c, 0) + 1
    n_mal = sum(clases.values())
    return {
        "equipo_equivocado": (
            f"{n_mal} de {len(con_eq)} ({100 * n_mal / max(len(con_eq), 1):.1f} %)"
        ),
        "por_clase": {
            k: f"{v} ({100 * v / max(n_mal, 1):.0f} %)" for k, v in clases.items()
        },
    }


def main() -> None:
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    dp = _mod("diag22f_pureza")
    res = {}
    for pata, p in dp.PATAS.items():
        gt = gt_a_por_frame(
            parsear_cvat(p["gt"]), np.load(p["H"]), p["offset"], p["paso"]
        )
        info = {
            int(o.obj_id): {"equipo": equipo(o.team), "arbitro": o.label == "referee"}
            for obs in gt.values()
            for o in obs
        }
        captura, _datos = dp.capturar(p["config"], salida / f"cruces_{pata}.csv")
        res[pata] = {}
        for etapa in ("bytetrack", "postproceso"):
            idents = captura["cosido"] if etapa == "postproceso" else captura[etapa]
            trays = captura["postproceso"] if etapa == "postproceso" else None
            obs_de, persona = dp.casar_etapa(etapa, idents, trays, gt)
            res[pata][etapa] = cruces_e_impureza(obs_de, persona, gt, info)
        res[pata]["error_de_equipo_por_identidad"] = error_por_identidad(
            CSV_POR_IDENTIDAD[pata], gt, info
        )
    (salida / "bloqueA.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
