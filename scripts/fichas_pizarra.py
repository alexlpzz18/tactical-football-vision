#!/usr/bin/env python
"""La pizarra con FICHAS POR EQUIPO y persistencia. Criterios en `docs/pizarra_fichas.md`.

Solo el DIBUJO: escribe un CSV aparte para la pizarra; los CSV de datos no se tocan.

Uso:
    python scripts/fichas_pizarra.py todo
"""

import argparse
import hashlib
import json
import pickle
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/pizarra_fichas"
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
CSV_MAIN = R / "outputs/diagnostico_26oct_b/posiciones_main.csv"
META = R / "outputs/diagnostico_26oct_b/posiciones_main_meta.json"
CSV_PARTE = R / "data/tracking_benja/posiciones_benja_p1.csv"
HOMOGRAFIA = R / "data/calibracion_benja/homografia_benja.npy"
CAMPO = R / "configs/campo_benja.yaml"
FPS = 29.97002997002997
LARGO, ANCHO = 62.0, 40.0
ANCHO_IMG, ALTO_IMG, MARGEN_PX = 1920, 1080, 40
# las dos ventanas: la de Alex (14:00-15:30) y la del GT de 30 s (frames 9750-10635)
TRAMO = (840.0, 930.0)
VENTANA_GT = (9750 / FPS, 10635 / FPS)
MARGEN_CORTE_S = 5.0
# la pizarra (replay_tactico): hueco que interpola y vida del último fotograma clave
MAX_HUECO_S, VIDA_ULTIMO_S, PASO_S = 3.0, 0.25, 0.1
# (A) fichas por equipo — fijado en docs/pizarra_fichas.md ANTES de medir
GRUPOS = ("A", "B", "portero_A", "portero_B")
PUERTA_BASE_M, PUERTA_V_M_S, PUERTA_MAX_M = 1.0, 7.0, 3.0
DUPLICADO_M = 1.0
CIERRE_S = 1.5
MEDIA_MOVIL = 5
V_MAX_M_S = 8.0
ID_BASE_FICHAS = 100000
# intento 2 (docs/pizarra_fichas.md): velocidad sobre ≥ 0,5 s, extrapolación ≤ 0,3 s, puerta local
VEL_VENTANA_S, EXTRAPOLA_MAX_S = 0.5, 0.3
JITTER_PX, PUERTA_JITTER_K, PUERTA_MAX_2_M = 3.5, 3.0, 4.0
INTENTO = 1
# (B) persistencia
PERSISTENCIA_S = 1.5
RADIO_CASADO_M = 2.0
PY = sys.executable


def equipo(et: str) -> str | None:
    et = str(et)
    if et in ("A", "portero_A"):
        return "A"
    if et in ("B", "portero_B"):
        return "B"
    return None


# ── la cámara: qué se ve ─────────────────────────────────────────────────────────────────────


def en_camara(x, y, Hinv) -> np.ndarray:
    """¿El punto del suelo (m) cae dentro del fotograma, a ≥ MARGEN_PX de los bordes?"""
    p = np.column_stack([x, y, np.ones_like(x)]) @ Hinv.T
    # el signo de la coordenada homogénea depende de cómo se escaló H (aquí sale negativa)
    ok = np.abs(p[:, 2]) > 1e-12
    u, v = p[:, 0] / p[:, 2], p[:, 1] / p[:, 2]
    return (
        ok
        & (u >= MARGEN_PX)
        & (u <= ANCHO_IMG - MARGEN_PX)
        & (v >= MARGEN_PX)
        & (v <= ALTO_IMG - MARGEN_PX)
    )


def zona_no_visible(Hinv, paso=0.5) -> list:
    """Celdas del campo cuyo centro no cae en el fotograma, unidas por filas en rectángulos."""
    rects = []
    for x in np.arange(0, LARGO, paso):
        ys = np.arange(0, ANCHO, paso)
        fuera = ~en_camara(np.full_like(ys, x + paso / 2), ys + paso / 2, Hinv)
        i = 0
        while i < len(ys):
            if fuera[i]:
                j = i
                while j + 1 < len(ys) and fuera[j + 1]:
                    j += 1
                rects.append(
                    [float(x), float(ys[i]), paso, float(ys[j] - ys[i] + paso)]
                )
                i = j + 1
            else:
                i += 1
    return rects


# ── simulador de lo que DIBUJA la pizarra ────────────────────────────────────────────────────


def leer_pizarra(html: Path) -> tuple[list, list]:
    texto = html.read_text()
    datos = json.loads(re.search(r"const DATOS = (\[.*?\]);\n", texto, re.S).group(1))
    catalogo = json.loads(re.search(r"const CATALOGO = (\[.*?\]);", texto).group(1))
    return datos, catalogo


def simular(datos, catalogo, Ts) -> list[dict]:
    """Por ficha: visible, x, y y color en cada T (la regla de `posicionEn`)."""
    salida = []
    for d in datos:
        ts = np.asarray(d["t"], float)
        x, y = np.asarray(d["x"], float), np.asarray(d["y"], float)
        p = np.searchsorted(ts, Ts, side="right") - 1
        valido = p >= 0
        pc = np.clip(p, 0, len(ts) - 1)
        ultimo = pc == len(ts) - 1
        sig = np.clip(pc + 1, 0, len(ts) - 1)
        dt = ts[sig] - ts[pc]
        vis = valido & np.where(ultimo, ts[pc] >= Ts - VIDA_ULTIMO_S, dt <= MAX_HUECO_S)
        a = np.where(dt > 0, (Ts - ts[pc]) / np.where(dt > 0, dt, 1), 0)
        a = np.where(ultimo, 0, a)
        xx = x[pc] + a * (x[sig] - x[pc])
        yy = y[pc] + a * (y[sig] - y[pc])
        col = (
            np.array([catalogo[k] for k in d["ets"]])[pc]
            if "ets" in d
            else np.full(len(Ts), d["et"])
        )
        salida.append({"id": d["id"], "vis": vis, "x": xx, "y": yy, "col": col})
    return salida


def metricas(html: Path, ventana, Hinv) -> dict:
    datos, catalogo = leer_pizarra(html)
    t0, t1 = ventana
    Ts = np.arange(t0, t1, PASO_S)
    fichas = [
        f
        for f in simular(datos, catalogo, Ts)
        if not str(f["col"][0]).startswith("balon")
    ]
    minutos = (t1 - t0) / 60
    cambios, saltos, eventos = 0, [], 0
    simult = {"A": np.zeros(len(Ts), int), "B": np.zeros(len(Ts), int)}
    distintas = {"A": set(), "B": set()}
    cambios_por_ficha = []
    for f in fichas:
        vis, col = f["vis"], f["col"]
        both = vis[1:] & vis[:-1]
        cambia = both & (col[1:] != col[:-1])
        n = int(cambia.sum())
        cambios += n
        if vis.any():
            cambios_por_ficha.append(n)
        for k in np.where(cambia)[0]:
            saltos.append(
                float(np.hypot(f["x"][k + 1] - f["x"][k], f["y"][k + 1] - f["y"][k]))
            )
        # eventos de aparición/desaparición dentro del campo visible (sin los bordes de la ventana)
        for k in np.where(vis[1:] != vis[:-1])[0]:
            j = k + 1 if vis[k + 1] else k
            x, y = f["x"][j], f["y"][j]
            if (
                0 <= x <= LARGO
                and 0 <= y <= ANCHO
                and en_camara(np.array([x]), np.array([y]), Hinv)[0]
            ):
                eventos += 1
        for e in ("A", "B"):
            m = vis & np.array([equipo(c) == e for c in col])
            simult[e] += m
            if m.any():
                distintas[e].add(f["id"])
    sim = {
        e: {
            "p50": float(np.percentile(v, 50)),
            "p95": float(np.percentile(v, 95)),
            "max": int(v.max()),
            "pct_tiempo_mas_de_7": round(100 * float((v > 7).mean()), 1),
        }
        for e, v in simult.items()
    }
    s = np.asarray(saltos) if saltos else np.zeros(1)
    return {
        "segundos": round(t1 - t0, 1),
        "fichas_dibujadas": sum(1 for f in fichas if f["vis"].any()),
        "cambios_de_color_por_minuto": round(cambios / minutos, 1),
        "cambios_de_color_por_ficha_p50_p90_max": [
            float(np.percentile(cambios_por_ficha, 50)),
            float(np.percentile(cambios_por_ficha, 90)),
            int(max(cambios_por_ficha)),
        ],
        "fichas_distintas_por_equipo": {e: len(v) for e, v in distintas.items()},
        "simultaneas_por_equipo": sim,
        "eventos_aparicion_desaparicion_por_minuto": round(eventos / minutos, 1),
        "salto_en_cambio_de_color_m_p50_p90": [
            round(float(np.percentile(s, 50)), 2),
            round(float(np.percentile(s, 90)), 2),
        ],
    }


# ── IDF1 por equipo contra el GT de 30 s ─────────────────────────────────────────────────────


def idf1_por_equipo(html: Path) -> dict:
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    H = np.load(HOMOGRAFIA)
    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"), H, 9750, 15
    )
    frames = sorted(gt)
    Ts = np.array([f / FPS for f in frames])
    datos, catalogo = leer_pizarra(html)
    fichas = simular(datos, catalogo, Ts)
    res = {}
    for e in ("A", "B"):
        cuenta, n_gt, n_pred = {}, 0, 0
        for k, f in enumerate(frames):
            gente = [o for o in gt[f] if o.team and equipo(str(o.team)) == e]
            pred = [
                (fi["id"], fi["x"][k], fi["y"][k])
                for fi in fichas
                if fi["vis"][k] and equipo(fi["col"][k]) == e
            ]
            n_gt += len(gente)
            n_pred += len(pred)
            if not gente or not pred:
                continue
            c = np.hypot(
                np.array([p[1] for p in pred])[None, :]
                - np.array([o.pos[0] for o in gente])[:, None],
                np.array([p[2] for p in pred])[None, :]
                - np.array([o.pos[1] for o in gente])[:, None],
            )
            c = np.where(c > RADIO_CASADO_M, 1e6, c)
            for i, j in zip(*linear_sum_assignment(c)):
                if c[i, j] < 1e6:
                    par = (pred[j][0], int(gente[i].obj_id))
                    cuenta[par] = cuenta.get(par, 0) + 1
        ids_p = sorted({p for p, _g in cuenta})
        ids_g = sorted({g for _p, g in cuenta})
        if ids_p and ids_g:
            M = np.zeros((len(ids_p), len(ids_g)))
            for (p, g), v in cuenta.items():
                M[ids_p.index(p), ids_g.index(g)] = v
            fi, co = linear_sum_assignment(-M)
            idtp = float(M[fi, co].sum())
        else:
            idtp = 0.0
        res[e] = {
            "IDF1": round(2 * idtp / max(n_gt + n_pred, 1), 3),
            "IDTP": int(idtp),
            "detecciones_gt": n_gt,
            "fichas_visibles": n_pred,
            "fichas_casadas_distintas": len(ids_p),
        }
    return res


# ── (A) fichas por equipo ─────────────────────────────────────────────────────────────────────


def observaciones() -> pd.DataFrame:
    """Cada observación real del tracker: frame, grupo (su etiqueta) y el pie sin suavizar."""
    cap = pickle.load(open(CAPTURA, "rb"))
    cache = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    filas = []
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            et = str(cap["final"].get((i, f)) or cap["voto"].get(i, "otro"))
            if et in GRUPOS:
                d = cache[f][k]
                filas.append((int(f), et, float(d[0]), float(d[1])))
    return pd.DataFrame(filas, columns=["frame", "grupo", "x", "y"])


def _sin_duplicados(xy: np.ndarray) -> np.ndarray:
    """Funde las observaciones del mismo grupo a < DUPLICADO_M en el mismo frame (media)."""
    quedan, salida = list(range(len(xy))), []
    while quedan:
        i = quedan.pop(0)
        cerca = [j for j in quedan if np.hypot(*(xy[j] - xy[i])) < DUPLICADO_M]
        for j in cerca:
            quedan.remove(j)
        salida.append(xy[[i] + cerca].mean(axis=0))
    return np.array(salida)


_HINV = []


def metros_por_px(pts: np.ndarray) -> np.ndarray:
    """Metros por píxel (horizontal) en cada punto del suelo, con la homografía."""
    from src.balon.tracking_balon import escala_px_por_m

    if not _HINV:
        _HINV.extend([np.load(HOMOGRAFIA), np.linalg.inv(np.load(HOMOGRAFIA))])
    H = _HINV[0]
    p = np.column_stack([pts, np.ones(len(pts))]) @ _HINV[1].T
    u, v = p[:, 0] / p[:, 2], p[:, 1] / p[:, 2]
    return np.array([1.0 / escala_px_por_m(H, a, b) for a, b in zip(u, v)])


def seguir_grupo(obs: pd.DataFrame) -> list[list[tuple]]:
    """Hungarian en metros con velocidad constante, dentro de UN grupo. [[(t, x, y), ...], ...]"""
    vivas, cerradas = [], []  # ficha: {"pts": [...], "pos", "vel", "t"}
    for f, g in obs.groupby("frame"):
        t = f / FPS
        xy = _sin_duplicados(g[["x", "y"]].to_numpy())
        siguen = []
        for fi in vivas:
            (siguen if t - fi["t"] <= CIERRE_S else cerradas).append(fi)
        vivas = siguen
        asignadas = set()
        if vivas and len(xy):
            dts = np.array([t - fi["t"] for fi in vivas])
            if INTENTO == 1:
                pred = np.array(
                    [fi["pos"] + fi["vel"] * dt for fi, dt in zip(vivas, dts)]
                )
                puerta = np.minimum(PUERTA_BASE_M + PUERTA_V_M_S * dts, PUERTA_MAX_M)
            else:
                pred = np.array(
                    [
                        fi["pos"] + fi["vel"] * min(dt, EXTRAPOLA_MAX_S)
                        for fi, dt in zip(vivas, dts)
                    ]
                )
                base = np.maximum(
                    PUERTA_BASE_M, PUERTA_JITTER_K * JITTER_PX * metros_por_px(pred)
                )
                puerta = np.minimum(base + PUERTA_V_M_S * dts, PUERTA_MAX_2_M)
            c = np.hypot(
                pred[:, None, 0] - xy[None, :, 0], pred[:, None, 1] - xy[None, :, 1]
            )
            c = np.where(c > puerta[:, None], 1e6, c)
            for i, j in zip(*linear_sum_assignment(c)):
                if c[i, j] >= 1e6:
                    continue
                fi = vivas[i]
                if INTENTO == 1:
                    # el del intento 1, tal cual: se acota la instantánea y luego se promedia
                    v = (xy[j] - fi["pos"]) / max(t - fi["t"], 1e-6)
                    rapidez = np.hypot(*v)
                    if rapidez > V_MAX_M_S:
                        v = v * V_MAX_M_S / rapidez
                    fi["vel"] = 0.5 * fi["vel"] + 0.5 * v
                else:
                    # el desplazamiento en su último ≥ 0,5 s de observaciones; 0 si lleva menos
                    ant = [q for q in fi["pts"] if q[0] <= t - VEL_VENTANA_S]
                    v = (
                        (xy[j] - np.array(ant[-1][1:])) / (t - ant[-1][0])
                        if ant
                        else np.zeros(2)
                    )
                    rapidez = np.hypot(*v)
                    if rapidez > V_MAX_M_S:
                        v = v * V_MAX_M_S / rapidez
                    fi["vel"] = v
                fi["pos"], fi["t"] = xy[j], t
                fi["pts"].append((t, xy[j][0], xy[j][1]))
                asignadas.add(j)
        for j in range(len(xy)):
            if j not in asignadas:
                vivas.append(
                    {
                        "pts": [(t, xy[j][0], xy[j][1])],
                        "pos": xy[j],
                        "vel": np.zeros(2),
                        "t": t,
                    }
                )
    return [fi["pts"] for fi in cerradas + vivas]


def csv_fichas(salida: Path) -> dict:
    """El CSV de DIBUJO: fichas por equipo (+ persistencia) y `otro`/`staff` como hoy."""
    obs = observaciones()
    filas, n_fichas = [], 0
    for grupo in GRUPOS:
        for pts in seguir_grupo(obs[obs.grupo == grupo]):
            n_fichas += 1
            fid = ID_BASE_FICHAS + n_fichas
            p = np.array(pts)
            if len(p) >= MEDIA_MOVIL:
                k = np.ones(MEDIA_MOVIL) / MEDIA_MOVIL
                for c in (1, 2):
                    p[:, c] = np.convolve(
                        np.pad(p[:, c], MEDIA_MOVIL // 2, mode="edge"), k, "valid"
                    )
            for t, x, y in p:
                filas.append((int(round(t * FPS)), round(t, 2), fid, grupo, x, y, 1))
            # (B) persistencia: quieta y atenuada hasta 1,5 s tras su última observación
            t_fin, x_fin, y_fin = p[-1]
            for dt in np.arange(PASO_S, PERSISTENCIA_S + 1e-9, PASO_S):
                t = t_fin + dt
                filas.append(
                    (int(round(t * FPS)), round(t, 2), fid, grupo, x_fin, y_fin, 0)
                )
    df = pd.DataFrame(
        filas,
        columns=[
            "frame",
            "tiempo_s",
            "id_jugador",
            "etiqueta",
            "x_m",
            "y_m",
            "es_real",
        ],
    )
    base = pd.read_csv(CSV_MAIN)
    resto = base[base.etiqueta.isin(["otro", "staff"])][df.columns]
    df = pd.concat([df, resto]).sort_values(["tiempo_s", "id_jugador"])
    df.to_csv(salida, index=False)
    return {"fichas_de_equipo": n_fichas, "observaciones": len(obs)}


# ── pizarras ─────────────────────────────────────────────────────────────────────────────────


def pizarra(csv: Path, ventana, html: Path, titulo: str, extra=()) -> Path:
    t0, t1 = ventana
    df = pd.read_csv(csv)
    corte = df[
        (df.tiempo_s >= t0 - MARGEN_CORTE_S) & (df.tiempo_s <= t1 + MARGEN_CORTE_S)
    ]
    ruta = html.with_suffix(".csv")
    corte.to_csv(ruta, index=False)
    subprocess.run(
        [
            PY,
            str(R / "scripts/generar_replay.py"),
            "--csv",
            str(ruta),
            "--salida",
            str(html),
            "--config-campo",
            str(CAMPO),
            "--meta",
            str(META),
            "--suavizado-visual-ventana",
            "1",
            "--titulo",
            titulo,
            *extra,
        ],
        check=True,
        capture_output=True,
    )
    return html


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def todo() -> dict:
    SALIDA.mkdir(parents=True, exist_ok=True)
    antes = {p.name: _sha(p) for p in (CSV_MAIN, CSV_PARTE) if p.exists()}
    Hinv = np.linalg.inv(np.load(HOMOGRAFIA))
    zona = zona_no_visible(Hinv)
    (SALIDA / "zona_no_visible.json").write_text(json.dumps(zona))
    info = csv_fichas(SALIDA / "fichas_pizarra.csv")
    extra_ab = [
        "--max-edad-interp",
        str(PERSISTENCIA_S),
        "--zona-no-visible",
        str(SALIDA / "zona_no_visible.json"),
    ]
    res = {"fichas": info, "zona_no_visible_rectangulos": len(zona)}
    for nombre, ventana, rel in (
        (
            "tramo_14_00_15_30",
            TRAMO,
            "14:00-15:30 (archivo) · 15:33-17:03 (reproductor)",
        ),
        ("gt_5_25_5_55", VENTANA_GT, "5:25-5:55 (archivo) · ventana del GT"),
    ):
        h_base = pizarra(
            CSV_MAIN, ventana, SALIDA / f"base_{nombre}.html", f"main · {rel}"
        )
        h_ab = pizarra(
            SALIDA / "fichas_pizarra.csv",
            ventana,
            SALIDA / f"fichas_{nombre}.html",
            f"fichas por equipo + persistencia (SOLO DIBUJO) · {rel}",
            extra_ab,
        )
        res[nombre] = {
            "base": metricas(h_base, ventana, Hinv),
            "fichas": metricas(h_ab, ventana, Hinv),
        }
        if nombre.startswith("gt"):
            res[nombre]["IDF1_base"] = idf1_por_equipo(h_base)
            res[nombre]["IDF1_fichas"] = idf1_por_equipo(h_ab)
    despues = {p.name: _sha(p) for p in (CSV_MAIN, CSV_PARTE) if p.exists()}
    res["csv_de_datos_identicos"] = antes == despues
    b, a = res["tramo_14_00_15_30"]["base"], res["tramo_14_00_15_30"]["fichas"]
    g = res["gt_5_25_5_55"]
    ev_b = b["eventos_aparicion_desaparicion_por_minuto"]
    ev_a = a["eventos_aparicion_desaparicion_por_minuto"]

    def tope_ok(m_base, m_ab):
        return all(
            m_ab["simultaneas_por_equipo"][e]["pct_tiempo_mas_de_7"]
            <= m_base["simultaneas_por_equipo"][e]["pct_tiempo_mas_de_7"]
            and m_ab["simultaneas_por_equipo"][e]["p95"] <= 7
            for e in ("A", "B")
        )

    res["criterio"] = {
        "IDF1_>=_base_en_los_dos_equipos": all(
            g["IDF1_fichas"][e]["IDF1"] >= g["IDF1_base"][e]["IDF1"] for e in ("A", "B")
        ),
        "tope_simultaneas_tramo": tope_ok(b, a),
        "tope_simultaneas_gt": tope_ok(g["base"], g["fichas"]),
        "eventos_bajan_>=50%": ev_a <= 0.5 * ev_b,
    }
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    global INTENTO, SALIDA
    ap.add_argument("accion", choices=["todo"])
    ap.add_argument("--intento", type=int, choices=[1, 2], default=1)
    args = ap.parse_args()
    INTENTO = args.intento
    SALIDA = R / f"outputs/pizarra_fichas_intento{INTENTO}"
    res = todo()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=float)
    (SALIDA / "resultado.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
