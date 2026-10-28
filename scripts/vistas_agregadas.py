#!/usr/bin/env python
"""Los cambios de color que quedan con histéresis, y vistas agregadas por equipo. Criterios en
`docs/vistas_agregadas.md`. SOLO lee los datos.

Uso:
    python scripts/vistas_agregadas.py cambios
    python scripts/vistas_agregadas.py vistas
"""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/vistas_agregadas"
CSV_MAIN = R / "outputs/diagnostico_26oct_b/posiciones_main.csv"
FPS = 29.97002997002997
LARGO, ANCHO = 62.0, 40.0
TRAMO = (840.0, 930.0)
GT_FRAMES = (9750, 10635)
PORTERIA = {"A": LARGO, "B": 0.0}  # la portería que defiende cada equipo (x)
N_LINEA = 2  # jugadores de campo más retrasados que forman la línea defensiva (F7)
K_FORMA = 7
RIVAL_M = 2.0


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def equipo(et: str):
    et = str(et)
    return (
        "A" if et in ("A", "portero_A") else ("B" if et in ("B", "portero_B") else None)
    )


# ── 1. los cambios de color que quedan ───────────────────────────────────────────────────────


def cambios() -> dict:
    fp = _mod("fichas_pizarra")
    html = R / "outputs/pizarra_dibujo/histeresis_1s.html"
    t0, t1 = TRAMO
    Ts = np.arange(t0, t1, fp.PASO_S)
    datos, cat = fp.leer_pizarra(html)
    F = [f for f in fp.simular(datos, cat, Ts) if equipo(f["col"][0]) or True]
    F = [f for f in F if not str(f["col"][0]).startswith("balon")]
    eq = [np.array([equipo(c) for c in f["col"]], dtype=object) for f in F]
    saltos, saltos_1s, rival, n = [], [], 0, 0
    for a, f in enumerate(F):
        vis, col = f["vis"], f["col"]
        for k in np.where(vis[1:] & vis[:-1] & (col[1:] != col[:-1]))[0]:
            n += 1
            saltos.append(
                np.hypot(f["x"][k + 1] - f["x"][k], f["y"][k + 1] - f["y"][k])
            )
            i0, i1 = max(k - 4, 0), min(k + 6, len(Ts) - 1)
            if vis[i0] and vis[i1]:
                saltos_1s.append(
                    np.hypot(f["x"][i1] - f["x"][i0], f["y"][i1] - f["y"][i0])
                )
            e = eq[a][k + 1]
            if _rival_cerca(F, eq, a, k + 1, e):
                rival += 1
    # tasa base: en todas las muestras visibles de fichas de equipo
    base_si = base_n = 0
    for a, f in enumerate(F):
        for k in range(0, len(Ts), 5):  # cada 0,5 s basta para la tasa
            e = eq[a][k]
            if f["vis"][k] and e is not None:
                base_n += 1
                base_si += _rival_cerca(F, eq, a, k, e)
    s, s1 = np.asarray(saltos), np.asarray(saltos_1s)
    tasa_c, tasa_b = rival / max(n, 1), base_si / max(base_n, 1)
    return {
        "cambios": n,
        "por_minuto": round(n / ((t1 - t0) / 60), 1),
        "salto_0_1s_m_p50_p90": [
            round(float(np.median(s)), 2),
            round(float(np.percentile(s, 90)), 2),
        ],
        "salto_1s_m_p50_p90": [
            round(float(np.median(s1)), 2),
            round(float(np.percentile(s1, 90)), 2),
        ],
        "criterio_alex_salto_mediano_<0,5m": bool(np.median(s) < 0.5),
        "rival_a_<2m_en_el_cambio_pct": round(100 * tasa_c, 1),
        "rival_a_<2m_tasa_base_pct": round(100 * tasa_b, 1),
        "enriquecimiento": round(tasa_c / max(tasa_b, 1e-9), 2),
    }


def _rival_cerca(F, eq, a, k, e) -> bool:
    if e is None:
        return False
    x, y = F[a]["x"][k], F[a]["y"][k]
    for b, g in enumerate(F):
        if b != a and g["vis"][k] and eq[b][k] not in (None, e):
            if np.hypot(g["x"][k] - x, g["y"][k] - y) < RIVAL_M:
                return True
    return False


# ── 2. vistas agregadas ──────────────────────────────────────────────────────────────────────


def _metricas_frame(x, y, porteros, e):
    """Centroide, anchura y altura de la línea defensiva de un equipo en un frame."""
    if len(x) == 0:
        return (np.nan,) * 4
    campo = ~porteros
    linea = np.nan
    if campo.sum() >= N_LINEA:
        prof = np.abs(PORTERIA[e] - x[campo])
        linea = float(np.sort(prof)[:N_LINEA].mean())
    return float(x.mean()), float(y.mean()), float(y.max() - y.min()), linea


def series(df: pd.DataFrame) -> pd.DataFrame:
    """Por frame y equipo: cx, cy, anchura y línea defensiva (columnas frame, x, y, eq, et)."""
    filas = []
    for (f, e), g in df.groupby(["frame", "eq"]):
        por = g.et.astype(str).str.startswith("portero").to_numpy()
        cx, cy, an, li = _metricas_frame(g.x.to_numpy(), g.y.to_numpy(), por, e)
        filas.append((f, f / FPS, e, cx, cy, an, li))
    return pd.DataFrame(
        filas, columns=["frame", "t", "eq", "cx", "cy", "anchura", "linea"]
    )


def _sistema() -> pd.DataFrame:
    d = pd.read_csv(CSV_MAIN)
    d = d[(d.es_real == 1) & d.x_m.between(0, LARGO) & d.y_m.between(0, ANCHO)]
    d = d.assign(eq=d.etiqueta.map(equipo), x=d.x_m, y=d.y_m, et=d.etiqueta)
    return d[d["eq"].notna()][["frame", "x", "y", "eq", "et"]]


def _gt() -> pd.DataFrame:
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"), H, 9750, 15
    )
    filas = [
        (f, float(o.pos[0]), float(o.pos[1]), equipo(o.team), str(o.team))
        for f, obs in gt.items()
        for o in obs
        if o.team and equipo(o.team)
    ]
    return pd.DataFrame(filas, columns=["frame", "x", "y", "eq", "et"])


def formas(df: pd.DataFrame, t0: float, t1: float, paso: float) -> list[dict]:
    """KMeans k=7 por equipo y ventana: la forma media sin identidades."""
    from sklearn.cluster import KMeans

    salida = []
    for a in np.arange(t0, t1 - 1e-9, paso):
        w = df[(df.frame / FPS >= a) & (df.frame / FPS < a + paso)]
        for e in ("A", "B"):
            g = w[w["eq"] == e]
            if len(g) < K_FORMA:
                continue
            km = KMeans(K_FORMA, n_init=10, random_state=0).fit(
                g[["x", "y"]].to_numpy()
            )
            salida.append(
                {
                    "t0": float(a),
                    "eq": e,
                    "centros": km.cluster_centers_.tolist(),
                    "centroide": [float(g.x.mean()), float(g.y.mean())],
                }
            )
    return salida


def evaluar(sis: pd.DataFrame, gt: pd.DataFrame) -> dict:
    frames = sorted(gt.frame.unique())
    s = series(sis[sis.frame.isin(frames)]).set_index(["frame", "eq"])
    g = series(gt).set_index(["frame", "eq"])
    j = s.join(g, rsuffix="_gt", how="inner").reset_index()
    j["e_c"] = np.hypot(j.cx - j.cx_gt, j.cy - j.cy_gt)
    j["e_a"] = (j.anchura - j.anchura_gt).abs()
    j["e_l"] = (j.linea - j.linea_gt).abs()
    inst = {
        k: [round(float(j[k].median()), 2), round(float(j[k].quantile(0.95)), 2)]
        for k in ("e_c", "e_a", "e_l")
    }
    # ventanas de 10 s = 20 frames del GT
    j["v"] = j.frame.map({f: i // 20 for i, f in enumerate(frames)})
    w = j.groupby(["v", "eq"]).mean(numeric_only=True)
    e_c = np.hypot(w.cx - w.cx_gt, w.cy - w.cy_gt)
    e_a = (w.anchura - w.anchura_gt).abs()
    e_l = (w.linea - w.linea_gt).abs()
    # formas a 10 s
    t0 = frames[0] / FPS
    fs, fg = formas(sis[sis.frame.isin(frames)], t0, t0 + 30, 10), formas(
        gt, t0, t0 + 30, 10
    )
    dist = []
    for a in fs:
        b = next(
            (x for x in fg if x["eq"] == a["eq"] and abs(x["t0"] - a["t0"]) < 1e-6),
            None,
        )
        if b:
            A, B = np.array(a["centros"]), np.array(b["centros"])
            c = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1])
            i, k = linear_sum_assignment(c)
            dist.append(float(c[i, k].mean()))
    return {
        "instante_p50_p95": {
            "centroide": inst["e_c"],
            "anchura": inst["e_a"],
            "linea_defensiva": inst["e_l"],
        },
        "a_10s": {
            "centroide_max_media": [
                round(float(e_c.max()), 2),
                round(float(e_c.mean()), 2),
            ],
            "anchura_max_media": [
                round(float(e_a.max()), 2),
                round(float(e_a.mean()), 2),
            ],
            "linea_defensiva_max_media": [
                round(float(e_l.max()), 2),
                round(float(e_l.mean()), 2),
            ],
            "ventanas_equipo": int(len(w)),
        },
        "forma_media_10s_distancia_media_m": [round(d, 2) for d in dist],
        "criterio_centroide_<=1_y_anchura_<=1,5_a_10s": bool(
            e_c.max() <= 1.0 and e_a.max() <= 1.5
        ),
    }


def dibujar(salida: Path, sr: pd.DataFrame, fo: list, titulo: str, paso: float) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    col = {"A": "#7f86d6", "B": "#eb2d06"}
    # series
    fig, ax = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    for e in ("A", "B"):
        s = sr[sr["eq"] == e].set_index("t")
        for i, k in enumerate(("cx", "anchura", "linea")):
            ax[i].plot(
                s.index,
                s[k].rolling(10, min_periods=1).mean(),
                color=col[e],
                label=e,
                lw=1,
            )
    for i, n in enumerate(
        ("centroide x (m)", "anchura (m)", "línea defensiva (m a su portería)")
    ):
        ax[i].set_ylabel(n)
    ax[0].legend()
    ax[0].set_title(
        f"{titulo} · media móvil de 1 s · solo dibujo, los datos no cambian"
    )
    ax[-1].set_xlabel("archivo (s)")
    fig.tight_layout()
    fig.savefig(salida.with_name(salida.stem + "_series.png"), dpi=110)
    plt.close(fig)
    # formas
    ventanas = sorted({f["t0"] for f in fo})
    n = len(ventanas)
    cols = min(n, 6)
    filas = int(np.ceil(n / cols))
    fig, axs = plt.subplots(
        filas, cols, figsize=(3.2 * cols, 2.3 * filas), squeeze=False
    )
    for ax in axs.ravel():
        ax.axis("off")
    for i, t0 in enumerate(ventanas):
        ax = axs.ravel()[i]
        ax.add_patch(plt.Rectangle((0, 0), LARGO, ANCHO, fill=True, color="#2f7d4a"))
        ax.plot([LARGO / 2] * 2, [0, ANCHO], color="white", lw=0.8)
        for f in fo:
            if f["t0"] == t0:
                c = np.array(f["centros"])
                ax.scatter(
                    c[:, 0],
                    c[:, 1],
                    s=28,
                    color=col[f["eq"]],
                    edgecolor="white",
                    lw=0.5,
                )
                ax.scatter(*f["centroide"], marker="x", s=40, color=col[f["eq"]])
        m, s = divmod(t0, 60)
        ax.set_title(f"{int(m)}:{s:04.1f} (+{paso:g} s)", fontsize=7)
        ax.set_xlim(-2, LARGO + 2)
        ax.set_ylim(-2, ANCHO + 2)
        ax.set_aspect("equal")
    fig.suptitle(
        f"{titulo} · forma media por ventana de {paso:g} s (k=7) · x = centroide",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(salida.with_name(salida.stem + f"_formas_{paso:g}s.png"), dpi=110)
    plt.close(fig)


def vistas() -> dict:
    SALIDA.mkdir(parents=True, exist_ok=True)
    sis = _sistema()
    t = time.perf_counter()
    sr = series(sis)
    t_series = time.perf_counter() - t
    t = time.perf_counter()
    fo = {
        p: formas(sis, 0.0, float(sis.frame.max() / FPS), p)
        for p in (10.0, 60.0, 300.0)
    }
    t_formas = time.perf_counter() - t
    res = {
        "cpu_s_20min": {
            "series": round(t_series, 1),
            "formas_10s_1min_5min": round(t_formas, 1),
        },
        "evaluacion_gt_30s": evaluar(sis, _gt()),
    }
    a, b = TRAMO
    tramo = sis[(sis.frame / FPS >= a) & (sis.frame / FPS < b)]
    sr_t = sr[(sr.t >= a) & (sr.t < b)]
    for p in (10.0, 60.0):
        dibujar(
            SALIDA / "tramo_14_00_15_30",
            sr_t,
            formas(tramo, a, b, p),
            "14:00-15:30 (archivo) · 15:33-17:03 (reproductor)",
            p,
        )
    for p, f in fo.items():
        dibujar(SALIDA / "partido_20min", sr, f, "parte entera (20 min)", p)
    sr.to_csv(SALIDA / "series_20min.csv", index=False)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["cambios", "vistas"])
    args = ap.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)
    res = {"cambios": cambios, "vistas": vistas}[args.accion]()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=float)
    (SALIDA / f"{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
