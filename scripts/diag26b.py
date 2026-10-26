#!/usr/bin/env python
"""Diagnóstico 26-oct (b): error de equipo por observación (pista encendida) y hoja de revisión.

Criterios en `docs/diagnostico_26oct_b.md`. SOLO mide: corre `main` tal cual.

Uso:
    python scripts/diag26b.py capturar --salida outputs/diagnostico_26oct_b
    python scripts/diag26b.py error --salida outputs/diagnostico_26oct_b
    python scripts/diag26b.py hoja --salida outputs/diagnostico_26oct_b
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
FPS = 29.97002997002997
RADIO_CRUCE_M = 2.0
N_BOOT = 2000


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def relojes(frame: int) -> str:
    t = frame / FPS
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int(r // 60)}:{r % 60:04.1f} repr"


def equipo(etiqueta) -> str:
    e = str(etiqueta)
    return e.replace("portero_", "") if e.startswith("portero_") else e


# ── captura ───────────────────────────────────────────────────────────────────────────────────


def capturar(salida: Path) -> dict:
    """`desde_cache` de main tal cual, espiando la pista: identidades, voto y etiqueta final."""
    import src.team_classification.arbitro_viterbi as av
    from src.tracking_data.processor import procesar_desde_cache

    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    csv = salida / "posiciones_main.csv"
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(salida / "posiciones_main_meta.json")
    cap = {}
    orig_pista, orig_aplicar = av.pista_del_arbitro, av.aplicar_pista

    def espia_pista(cache, chaleco, mod, params, dims):
        p = orig_pista(cache, chaleco, mod, params, dims)
        cap.update(pista=p, cache=cache)
        return p

    def espia_aplicar(identidades, equipos, etiquetas, pista, colores, clf, params):
        final = orig_aplicar(
            identidades, equipos, etiquetas, pista, colores, clf, params
        )
        cap.update(
            identidades=[
                [(int(f), int(j)) for tr in ident for (f, j) in tr.det_idxs]
                for ident in identidades
            ],
            voto=dict(equipos),
            final=dict(final),
        )
        return final

    av.pista_del_arbitro, av.aplicar_pista = espia_pista, espia_aplicar
    try:
        procesar_desde_cache(cfg)
    finally:
        av.pista_del_arbitro, av.aplicar_pista = orig_pista, orig_aplicar
    if "voto" not in cap:
        raise SystemExit(
            "La pista no corrió: ¿está encendida en main? (no se cambia nada aquí)"
        )
    pickle.dump(cap, open(salida / "captura_main.pkl", "wb"))
    filas = filas_con_dos_etiquetas(salida, cap)
    reales = filas[filas.es_real == 1]
    coinciden = (reales.etiqueta == reales.etiqueta_final_captura).mean()
    return {
        "filas": len(filas),
        "reales": len(reales),
        "identidades": len(cap["identidades"]),
        "frames_pista": len(cap["pista"]),
        "csv_etiqueta_igual_a_la_captura_pct": round(100 * float(coinciden), 3),
        "filas_reales_con_obs_distinta_del_voto": int(
            (reales.etiqueta_identidad != reales.etiqueta).sum()
        ),
    }


def filas_con_dos_etiquetas(salida: Path, cap: dict) -> pd.DataFrame:
    """El CSV con la etiqueta del VOTO de la identidad y la final de la captura al lado."""
    filas = pd.read_csv(salida / "posiciones_main.csv")
    voto = {int(i): str(e) for i, e in cap["voto"].items()}
    filas["etiqueta_identidad"] = filas.id_jugador.map(voto).fillna("otro")
    final = cap["final"]
    filas["etiqueta_final_captura"] = [
        str(final.get((int(i), int(f)), voto.get(int(i), "otro")))
        for i, f in zip(filas.id_jugador, filas.frame)
    ]
    return filas


# ── A: error por observación contra el voto de la identidad, sobre las mismas filas ───────────


def _pares(df, gt, columna):
    """Casado de comparar_escalas (posiciones, 1-a-1, 2 m), con la etiqueta de `columna`."""
    ce = _mod("comparar_escalas")
    d = df.assign(etiqueta=df[columna])
    return ce.casar(d, gt)


def error(salida: Path) -> dict:
    from scipy.optimize import linear_sum_assignment

    col = _mod("diag22g_color")
    gt = col.gt_de("benja")
    cap = pickle.load(open(salida / "captura_main.pkl", "rb"))
    filas = filas_con_dos_etiquetas(salida, cap)
    reales = filas[filas.es_real == 1]
    comunes = sorted(set(gt) & set(reales.frame))
    gtc = {f: gt[f] for f in comunes}
    # las parejas: el casado solo mira posiciones, así que es el MISMO para las dos etiquetas
    filas_par = []
    por_frame = {f: g for f, g in reales.groupby("frame")}
    for f in comunes:
        gente = [o for o in gtc[f] if equipo(o.team) in ("A", "B")]
        sub = por_frame[f]
        xy = sub[["x_m", "y_m"]].to_numpy()
        P = np.array([o.pos for o in gente], float)
        coste = np.hypot(xy[None, :, 0] - P[:, 0, None], xy[None, :, 1] - P[:, 1, None])
        coste = np.where(coste > 2.0, 1e6, coste)
        fi, cj = linear_sum_assignment(coste)
        for i, j in zip(fi, cj):
            if coste[i, j] >= 1e6:
                continue
            rival = [
                q
                for q in gente
                if equipo(q.team) != equipo(gente[i].team)
                and np.hypot(q.pos[0] - P[i, 0], q.pos[1] - P[i, 1]) <= RADIO_CRUCE_M
            ]
            r = sub.iloc[j]
            filas_par.append(
                {
                    "frame": f,
                    "gt": equipo(gente[i].team),
                    "identidad": equipo(r.etiqueta_identidad),
                    "observacion": equipo(r.etiqueta),
                    "cruce": bool(rival),
                }
            )
    p = pd.DataFrame(filas_par)
    # control: la misma medida con comparar_escalas.casar tiene que dar las mismas parejas
    control = {
        c: _mod("comparar_escalas").informar(c, _pares(reales, gtc, c))
        for c in ("etiqueta_identidad", "etiqueta")
    }
    # A/B son arbitrarias: se usa el emparejamiento (directo o cruzado) que más acierta
    en_eq = p[p.observacion.isin(["A", "B"]) & p.identidad.isin(["A", "B"])]
    directo = (en_eq["gt"] == en_eq.observacion).sum()
    invertir = (en_eq["gt"] != en_eq.observacion).sum() > directo
    mapa = {"A": "B", "B": "A"} if invertir else {"A": "A", "B": "B"}
    p = p[p.identidad.isin(["A", "B"]) & p.observacion.isin(["A", "B"])].copy()
    p["mal_identidad"] = p.identidad.map(mapa) != p["gt"]
    p["mal_observacion"] = p.observacion.map(mapa) != p["gt"]
    rng = np.random.default_rng(0)
    frames = p.frame.unique()

    def con_ic(g) -> dict:
        por_f = g.groupby("frame")[["mal_identidad", "mal_observacion"]].agg(
            ["sum", "size"]
        )
        fs = por_f.index.to_numpy()
        mi, mo = [], []
        for _ in range(N_BOOT):
            m = por_f.loc[rng.choice(fs, len(fs), replace=True)]
            n = m[("mal_identidad", "size")].sum()
            mi.append(m[("mal_identidad", "sum")].sum() / n)
            mo.append(m[("mal_observacion", "sum")].sum() / n)
        mi, mo = np.array(mi), np.array(mo)

        def ic(v):
            return [round(100 * float(x), 2) for x in np.quantile(v, [0.025, 0.975])]

        return {
            "filas": int(len(g)),
            "frames": int(len(fs)),
            "identidad_pct": round(100 * float(g.mal_identidad.mean()), 2),
            "identidad_ic95": ic(mi),
            "observacion_pct": round(100 * float(g.mal_observacion.mean()), 2),
            "observacion_ic95": ic(mo),
            "diferencia_identidad_menos_obs_pts": round(
                100 * float(g.mal_identidad.mean() - g.mal_observacion.mean()), 2
            ),
            "diferencia_ic95": ic(mi - mo),
        }

    res = {
        "control_comparar_escalas": control,
        "frames_gt": len(frames),
        "emparejamiento_invertido": bool(invertir),
        "total": con_ic(p),
        "cruce": con_ic(p[p.cruce.astype(bool)]),
        "no_cruce": con_ic(p[~p.cruce.astype(bool)]),
        "equipo_A": con_ic(p[p["gt"] == "A"]),
        "equipo_B": con_ic(p[p["gt"] == "B"]),
    }
    t = res["total"]
    res["criterio"] = {
        "diferencia_ic_entero_>_0": t["diferencia_ic95"][0] > 0,
        "observacion_ic_entero_<_16": t["observacion_ic95"][1] < 16.0,
        "control_identidad_aprox_16": control["etiqueta_identidad"],
    }
    p.to_csv(salida / "parejas_gt.csv", index=False)
    return res


# ── la hoja de revisión por los 20 minutos ────────────────────────────────────────────────────


def hoja(salida: Path) -> dict:
    """120 filas reales: 10 tramos de 2 min × (6 en cruce + 6 fuera), etiquetas OCULTAS."""
    from src.tracking.cache_io import cargar_cache

    hoja_mod = _mod("hoja_otro_v3")
    inv = _mod("diag22e_invariantes")
    cap = pickle.load(open(salida / "captura_main.pkl", "rb"))
    filas = filas_con_dos_etiquetas(salida, cap)
    r = filas[(filas.es_real == 1) & filas.etiqueta.map(equipo).isin(["A", "B"])].copy()
    # cruce: otra fila real del equipo CONTRARIO (etiqueta por observación) a ≤ 2 m
    cruce = np.zeros(len(r), bool)
    for _f, idx in r.groupby("frame").indices.items():
        g = r.iloc[idx]
        xy = g[["x_m", "y_m"]].to_numpy()
        eq = g.etiqueta.map(equipo).to_numpy()
        d = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
        cruce[idx] = ((d <= RADIO_CRUCE_M) & (eq[:, None] != eq[None, :])).any(axis=1)
    r["cruce"] = cruce
    r["tramo"] = (r.frame / FPS // 120).astype(int)
    elegidas = []
    for tramo, g in r.groupby("tramo"):
        for c in (True, False):
            sub = g[g.cruce == c]
            elegidas.append(
                sub.sample(n=min(6, len(sub)), random_state=int(tramo) * 2 + c)
            )
    m = pd.concat(elegidas).sample(frac=1, random_state=7)  # barajadas
    cfg = yaml.safe_load(open(CONFIG))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    m = inv.con_caja(m, dets)
    n = hoja_mod.escribir_hoja(
        "equipo_por_obs_20min",
        m,
        dets,
        R / cfg["rutas"]["video"],
        lambda f: {
            "id": int(f.id_jugador),
            "etiqueta_observacion": f.etiqueta,
            "etiqueta_identidad": f.etiqueta_identidad,
            "cruce": bool(f.cruce),
            "tramo_2min": int(f.tramo),
        },
    )
    return {
        "filas_en_la_hoja": n,
        "en_cruce": int(m.cruce.sum()),
        "fuera_de_cruce": int((~m.cruce).sum()),
        "con_obs_distinta_del_voto": int((m.etiqueta != m.etiqueta_identidad).sum()),
    }


def main() -> None:
    acciones = {"capturar": capturar, "error": error, "hoja": hoja}
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=list(acciones))
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    res = acciones[args.accion](salida)
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / f"{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
