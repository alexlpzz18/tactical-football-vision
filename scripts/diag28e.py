#!/usr/bin/env python
"""Diagnóstico 28-oct (e). Criterios en `docs/diagnostico_28oct_e.md`. SOLO mide.

Uso:
    python scripts/diag28e.py cerca     # balón en el juego cercano (hoja de 60 frames)
    python scripts/diag28e.py rachas    # oráculo de error de equipo por rachas y por ventanas
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/diagnostico_28oct_e"
P_CRUCE, P_FUERA, RADIO_CRUCE_M, REPETICIONES = 0.167, 0.033, 2.0, 200
VENTANAS_FRAMES = [1, 2, 4, 6, 10, 20, 30, 60]  # frames del GT (0,5 s cada uno)
PASO_GT_S = 0.5
LIMITE_CENTROIDE, LIMITE_ANCHURA = 1.0, 1.5


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * max(c - h, 0.0), 1), round(100 * min(c + h, 1.0), 1)]


# ── 1. balón cercano ──────────────────────────────────────────────────────────────────────────


def cerca() -> dict:
    gt = pd.read_csv(R / "data/annotations/gt_balon_benja/gt_balon_cerca.csv")
    meta = json.loads((R / "outputs/gt_balon_cerca/frames.json").read_text())["filas"]
    info = {int(r["frame"]): r for r in meta}
    gt["episodio"] = gt.frame.map(lambda f: info[int(f)]["episodio"])
    gt["con_candidata"] = gt.frame.map(lambda f: info[int(f)]["elegida"] is not None)
    n_no_se = int((gt.respuesta == "no_se").sum())
    g = gt[gt.respuesta != "no_se"]
    n = len(g)
    a = int((g.respuesta == "acepta").sum())
    c = int((g.respuesta == "clic").sum())
    rz = int((g.respuesta == "rechaza_no_visible").sum())
    vis, rec = a + c, a
    # por episodio: ¿hay algún frame visible?, ¿alguno aceptado?
    ep = g.groupby("episodio").respuesta.agg(lambda s: Counter(s))
    pct_vis = 100 * vis / max(n, 1)
    pct_rec = 100 * rec / max(vis, 1)
    if pct_vis < 50:
        veredicto = "ENCUADRE: visible < 50 %"
    elif pct_rec < 30:
        veredicto = "DETECTOR: visible >= 50 % y recall < 30 %"
    else:
        veredicto = "NINGUNA RAMA: visible >= 50 % y recall >= 30 %"
    return {
        "respondidos": n,
        "no_se_excluidos": n_no_se,
        "respuestas": {"acepta": a, "clic": c, "rechaza_no_visible": rz},
        "clic_sin_candidata": int(((g.respuesta == "clic") & ~g.con_candidata).sum()),
        "clic_con_candidata": int(((g.respuesta == "clic") & g.con_candidata).sum()),
        "rechaza_con_candidata": int(
            ((g.respuesta == "rechaza_no_visible") & g.con_candidata).sum()
        ),
        "visible": f"{vis}/{n}",
        "visible_pct": round(pct_vis, 1),
        "visible_ic95": wilson(vis, n),
        "recall": f"{rec}/{vis}",
        "recall_pct": round(pct_rec, 1),
        "recall_ic95": wilson(rec, vis),
        "episodios": len(ep),
        "episodios_con_algun_visible": int(
            sum((v.get("acepta", 0) + v.get("clic", 0)) > 0 for v in ep)
        ),
        "episodios_con_algun_acepta": int(sum(v.get("acepta", 0) > 0 for v in ep)),
        "veredicto": veredicto,
    }


# ── 2. oráculo de rachas ──────────────────────────────────────────────────────────────────────


def _cargar_gt():
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"), H, 9750, 15
    )
    filas = []
    for k, f in enumerate(sorted(gt)):
        obs = [o for o in gt[f] if o.label == "player" and o.team]
        x = np.array([o.pos[0] for o in obs], float)
        y = np.array([o.pos[1] for o in obs], float)
        eq = np.array([str(o.team).replace("portero_", "") for o in obs])
        d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
        cruce = ((d <= RADIO_CRUCE_M) & (eq[:, None] != eq[None, :])).any(axis=1)
        for o, xi, yi, ei, ci in zip(obs, x, y, eq, cruce):
            filas.append((k, int(o.obj_id), xi, yi, ei, bool(ci)))
    df = pd.DataFrame(filas, columns=["k", "persona", "x", "y", "eq", "cruce"])
    # episodio de cruce: racha de frames consecutivos del GT con la misma persona en cruce
    df = df.sort_values(["persona", "k"]).reset_index(drop=True)
    df["episodio"] = -1
    n_ep = 0
    for _, g in df[df.cruce].groupby("persona"):
        ks = g.k.to_numpy()
        corte = np.r_[0, np.cumsum(np.diff(ks) > 1)]
        df.loc[g.index, "episodio"] = n_ep + corte
        n_ep += int(corte.max()) + 1
    return df.sort_values(["k", "persona"]).reset_index(drop=True), n_ep


def _por_frame(df: pd.DataFrame, eq: np.ndarray, n_frames: int) -> np.ndarray:
    """Matriz [frame, equipo, (cx, cy, anchura)] con NaN si no hay jugadores suficientes."""
    out = np.full((n_frames, 2, 3), np.nan)
    k = df.k.to_numpy()
    x, y = df.x.to_numpy(), df.y.to_numpy()
    for j, e in enumerate(("A", "B")):
        m = eq == e
        for f in range(n_frames):
            s = m & (k == f)
            if s.sum():
                out[f, j, 0] = x[s].mean()
                out[f, j, 1] = y[s].mean()
            if s.sum() >= 2:
                out[f, j, 2] = y[s].max() - y[s].min()
    return out


def _ventanas(v: np.ndarray, w: np.ndarray, tam: int):
    """Desviaciones de centroide y anchura por (ventana, equipo), promediando `tam` frames."""
    n = v.shape[0] // tam
    vv = np.nanmean(v[: n * tam].reshape(n, tam, 2, 3), axis=1)
    ww = np.nanmean(w[: n * tam].reshape(n, tam, 2, 3), axis=1)
    dc = np.hypot(ww[..., 0] - vv[..., 0], ww[..., 1] - vv[..., 1]).ravel()
    da = np.abs(ww[..., 2] - vv[..., 2]).ravel()
    return dc[np.isfinite(dc)], da[np.isfinite(da)]


def rachas() -> dict:
    df, n_ep = _cargar_gt()
    n_frames = int(df.k.max()) + 1
    eq = df["eq"].to_numpy()
    cruce = df.cruce.to_numpy()
    episodio = df.episodio.to_numpy()
    verdad = _por_frame(df, eq, n_frames)
    otro = np.where(eq == "A", "B", "A")
    res = {}
    frac_cruce_inv = []
    for modo in ("filas", "rachas"):
        acum = {t: ([], []) for t in VENTANAS_FRAMES}
        for semilla in range(REPETICIONES):
            rng = np.random.default_rng(semilla)
            if modo == "filas":
                inv = rng.random(len(eq)) < np.where(cruce, P_CRUCE, P_FUERA)
            else:
                ep_inv = rng.random(n_ep) < P_CRUCE
                inv = np.where(
                    cruce,
                    ep_inv[np.maximum(episodio, 0)],
                    rng.random(len(eq)) < P_FUERA,
                )
                frac_cruce_inv.append(inv[cruce].mean())
            w = _por_frame(df, np.where(inv, otro, eq), n_frames)
            for t in VENTANAS_FRAMES:
                dc, da = _ventanas(verdad, w, t)
                acum[t][0].append(dc)
                acum[t][1].append(da)
        tabla = {}
        for t in VENTANAS_FRAMES:
            dc = np.concatenate(acum[t][0])
            da = np.concatenate(acum[t][1])
            p95c, p95a = float(np.percentile(dc, 95)), float(np.percentile(da, 95))
            tabla[f"{t * PASO_GT_S:g} s"] = {
                "ventanas_por_rep_y_equipo": n_frames // t,
                "centroide_media": round(float(dc.mean()), 3),
                "centroide_p95": round(p95c, 3),
                "anchura_media": round(float(da.mean()), 3),
                "anchura_p95": round(p95a, 3),
                "cumple": bool(p95c <= LIMITE_CENTROIDE and p95a <= LIMITE_ANCHURA),
            }
        primera = next((k for k, v in tabla.items() if v["cumple"]), None)
        res[modo] = {"por_ventana": tabla, "ventana_mas_corta_que_cumple": primera}
    largos = df[df.cruce].groupby("episodio").size()
    res["episodios_de_cruce"] = {
        "n": n_ep,
        "filas_en_cruce": int(cruce.sum()),
        "longitud_frames": {
            "media": round(float(largos.mean()), 2),
            "p50": float(largos.median()),
            "max": int(largos.max()),
        },
        "fraccion_de_filas_de_cruce_invertidas_(control_~16,7%)": round(
            100 * float(np.mean(frac_cruce_inv)), 2
        ),
    }
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["cerca", "rachas"])
    args = ap.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)
    res = {"cerca": cerca, "rachas": rachas}[args.accion]()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=float)
    (SALIDA / f"{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
