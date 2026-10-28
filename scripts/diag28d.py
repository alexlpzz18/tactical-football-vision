#!/usr/bin/env python
"""Diagnóstico 28-oct (d). Criterios en `docs/diagnostico_28oct_d.md`. SOLO mide.

Uso:
    python scripts/diag28d.py control    # balón inventado: control con la mini-hoja y cifra final
    python scripts/diag28d.py oraculo    # error de equipo inyectado sobre el GT de 30 s
    python scripts/diag28d.py hoja       # genera la hoja de 60 frames de juego cercano
    python scripts/diag28d.py leer ~/Downloads/respuestas_gt_balon_cerca.csv
"""

import argparse
import csv
import importlib.util
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/diagnostico_28oct_d"
FPS = 29.97002997002997
VENTANAS = {"14:46-14:48": (886.0, 888.5), "15:12-15:15": (912.0, 915.5)}  # archivo, s
LIMITE_M = 2.0
# oráculo
P_CRUCE, P_FUERA, RADIO_CRUCE_M, REPETICIONES = 0.167, 0.033, 2.0, 200
LARGO, ANCHO, ZONAS = 62.0, 40.0, 3
# hoja cercana
HOJA = R / "outputs/gt_balon_cerca"
GT_CERCA = R / "data/annotations/gt_balon_benja/gt_balon_cerca.csv"
N_HOJA, SEPARACION_S = 60, 1.0


def _mod(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * max(c - h, 0.0), 1), round(100 * min(c + h, 1.0), 1)]


def relojes(f: int) -> str:
    t = f / FPS
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int((t + 93) // 60)}:{(t + 93) % 60:04.1f} repr"


# ── 1. balón inventado ────────────────────────────────────────────────────────────────────────


def inventados(gt: pd.DataFrame, eleg: dict) -> list[dict]:
    """Frames con candidata elegida que la medida llama inventados (rechaza, o clic a > 2 m)."""
    from src.balon.tracking_balon import escala_px_por_m

    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    out = []
    for row in gt.itertuples():
        e = eleg.get(int(row.frame))
        if e is None:
            continue
        cx, cy = (e[0] + e[2]) / 2, (e[1] + e[3]) / 2
        if row.respuesta == "rechaza_no_visible":
            out.append({"frame": int(row.frame), "tipo": "sin balón visible"})
        elif row.respuesta == "clic":
            d = float(np.hypot(cx - float(row.x_px), cy - float(row.y_px)))
            lim = LIMITE_M * escala_px_por_m(H, float(row.x_px), float(row.y_px))
            if d > lim:
                out.append(
                    {
                        "frame": int(row.frame),
                        "tipo": "balón en otro sitio",
                        "dist_px": round(d),
                        "limite_px": round(lim),
                    }
                )
    for o in out:
        o["relojes"] = relojes(o["frame"])
    return out


def control() -> dict:
    gt = pd.read_csv(R / "data/annotations/gt_balon_benja/gt_balon_control.csv")
    meta = json.loads((R / "outputs/gt_balon_control/frames.json").read_text())["filas"]
    eleg = {int(r["frame"]): r["elegida"] for r in meta}
    inv = inventados(gt, eleg)
    marcados = {i["frame"] for i in inv}
    por_ventana = {}
    for nombre, (t0, t1) in VENTANAS.items():
        g = gt[(gt.frame >= t0 * FPS) & (gt.frame <= t1 * FPS)]
        por_ventana[nombre] = {
            "frames": len(g),
            "respuestas": dict(Counter(g.respuesta)),
            "con_candidata": int(sum(eleg.get(int(f)) is not None for f in g.frame)),
            "inventados": int(sum(int(f) in marcados for f in g.frame)),
            "detalle": [i for i in inv if t0 * FPS <= i["frame"] <= t1 * FPS],
        }
    pasa = all(v["inventados"] >= 1 for v in por_ventana.values())
    res = {"control_por_ventana": por_ventana, "control_pasa": pasa}
    if not pasa:
        res["cifra_final"] = "NO SE DA: el control falla y la medida no vale"
        return res
    # cifra final: la hoja de 200 (sin los 20 del control)
    gt2 = pd.read_csv(R / "data/annotations/gt_balon_benja/gt_balon_por_frame.csv")
    gt2 = gt2[gt2.respuesta != "no_se"]
    meta2 = json.loads((R / "outputs/gt_balon_rapido/frames.json").read_text())["filas"]
    eleg2 = {int(r["frame"]): r["elegida"] for r in meta2}
    zona = {int(r["frame"]): r.get("zona") for r in meta2}
    inv2 = inventados(gt2, eleg2)
    con = [int(f) for f in gt2.frame if eleg2.get(int(f)) is not None]
    marc2 = {i["frame"] for i in inv2}
    por_zona = {}
    for z in sorted({zona[f] for f in con}):
        fz = [f for f in con if zona[f] == z]
        k = sum(f in marc2 for f in fz)
        por_zona[z] = {"inventados": f"{k}/{len(fz)}", "ic95": wilson(k, len(fz))}
    res["cifra_final"] = {
        "inventados": f"{len(inv2)}/{len(con)}",
        "pct": round(100 * len(inv2) / max(len(con), 1), 1),
        "ic95": wilson(len(inv2), len(con)),
        "por_zona_de_la_hoja": por_zona,
        "por_tipo": dict(Counter(i["tipo"] for i in inv2)),
        "detalle": inv2,
    }
    return res


# ── 2. oráculo ────────────────────────────────────────────────────────────────────────────────


def _metricas(x, y, eq):
    """Centroide y anchura por equipo, como `desglose_error.metricas_de_puntos`."""
    out = {}
    for e in ("A", "B"):
        m = eq == e
        n = int(m.sum())
        cx = float(x[m].mean()) if n else np.nan
        cy = float(y[m].mean()) if n else np.nan
        an = float(y[m].max() - y[m].min()) if n >= 2 else np.nan
        out[e] = (cx, cy, an)
    return out


def _ocupacion(filas_x, filas_y, eq) -> Counter:
    zx = np.minimum((filas_x / LARGO * ZONAS).astype(int), ZONAS - 1).clip(0)
    zy = np.minimum((filas_y / ANCHO * ZONAS).astype(int), ZONAS - 1).clip(0)
    c = Counter(zip(eq, zx, zy))
    tot = sum(c.values()) or 1
    return {k: v / tot for k, v in c.items()}


def oraculo() -> dict:
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"), H, 9750, 15
    )
    frames = []
    for f in sorted(gt):
        obs = [o for o in gt[f] if o.label == "player" and o.team]
        if not obs:
            continue
        x = np.array([o.pos[0] for o in obs], float)
        y = np.array([o.pos[1] for o in obs], float)
        eq = np.array([str(o.team).replace("portero_", "") for o in obs])
        d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
        cruce = ((d <= RADIO_CRUCE_M) & (eq[:, None] != eq[None, :])).any(axis=1)
        frames.append((f, x, y, eq, cruce))
    n_filas = sum(len(t[1]) for t in frames)
    n_cruce = sum(int(t[4].sum()) for t in frames)
    verdad = [_metricas(x, y, eq) for _, x, y, eq, _ in frames]
    X = np.concatenate([t[1] for t in frames])
    Y = np.concatenate([t[2] for t in frames])
    EQ = np.concatenate([t[3] for t in frames])
    oc_v = _ocupacion(X, Y, EQ)
    dc, da, sin_anchura = [], [], 0
    media_c, media_a, ocup = [], [], []
    for semilla in range(REPETICIONES):
        rng = np.random.default_rng(semilla)
        rc, ra, eqs = [], [], []
        for (f, x, y, eq, cruce), v in zip(frames, verdad):
            p = np.where(cruce, P_CRUCE, P_FUERA)
            inv = rng.random(len(eq)) < p
            eq2 = np.where(inv, np.where(eq == "A", "B", "A"), eq)
            eqs.append(eq2)
            m = _metricas(x, y, eq2)
            for e in ("A", "B"):
                c = np.hypot(m[e][0] - v[e][0], m[e][1] - v[e][1])
                if np.isfinite(c):
                    rc.append(c)
                a = abs(m[e][2] - v[e][2])
                if np.isfinite(a):
                    ra.append(a)
                else:
                    sin_anchura += 1
        dc += rc
        da += ra
        media_c.append(np.mean(rc))
        media_a.append(np.mean(ra))
        oc = _ocupacion(X, Y, np.concatenate(eqs))
        ocup.append(
            100
            * sum(abs(oc.get(k, 0) - oc_v.get(k, 0)) for k in set(oc) | set(oc_v))
            / 2
        )

    def res(v, unidad):
        v = np.asarray(v)
        return {
            "media": round(float(v.mean()), 3),
            "p50": round(float(np.percentile(v, 50)), 3),
            "p95": round(float(np.percentile(v, 95)), 3),
            "p99": round(float(np.percentile(v, 99)), 3),
            "max": round(float(v.max()), 3),
            "pct_cero": round(100 * float((v == 0).mean()), 1),
            "unidad": unidad,
        }

    dc, da = np.asarray(dc), np.asarray(da)
    out = {
        "frames_gt": len(frames),
        "filas": n_filas,
        "filas_en_cruce": n_cruce,
        "pct_cruce": round(100 * n_cruce / n_filas, 1),
        "inversiones_esperadas_por_frame": round(
            (n_cruce * P_CRUCE + (n_filas - n_cruce) * P_FUERA) / len(frames), 2
        ),
        "centroide_instante": res(dc, "m"),
        "anchura_instante": res(da, "m"),
        "centroide_media_por_repeticion": res(media_c, "m"),
        "anchura_media_por_repeticion": res(media_a, "m"),
        "ocupacion_3x3_por_repeticion": res(ocup, "% de masa"),
        "pares_sin_anchura_(<2_jugadores)": sin_anchura,
        # cuando hay error: la desviación solo en los (frame, equipo) que se mueven
        "centroide_si_hay_inversion": res(dc[dc > 0], "m"),
        "anchura_si_hay_inversion": res(da[da > 0], "m"),
    }
    out["criterio"] = {
        "p95_centroide_<=1m": out["centroide_instante"]["p95"] <= 1.0,
        "p95_anchura_<=1.5m": out["anchura_instante"]["p95"] <= 1.5,
    }
    return out


# ── 3. hoja de juego cercano ──────────────────────────────────────────────────────────────────


def hoja() -> dict:
    import cv2

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    gbr = _mod(R / "scripts/gt_balon_rapido.py", "gbr")
    gv = _mod(R / "scripts/generar_video_detecciones.py", "gv")
    pos = pd.read_csv(R / "outputs/diagnostico_26oct_b/posiciones_main.csv")
    r = pos[(pos.es_real == 1) & pos.x_m.between(0, LARGO) & pos.y_m.between(0, ANCHO)]
    med = r.groupby("frame").x_m.median()
    fr_jug = np.array(sorted(med.index))
    todas = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(open(gbr.CACHE_BALON, "rb"))["cache"]
    }

    def x_juego(f):
        i = np.searchsorted(fr_jug, f)
        cand = [fr_jug[j] for j in (i - 1, i) if 0 <= j < len(fr_jug)]
        return float(med[min(cand, key=lambda c: abs(c - f))])

    usados = [
        int(x["frame"])
        for p in (
            "outputs/gt_balon_rapido/frames.json",
            "outputs/gt_balon_control/frames.json",
        )
        for x in json.loads((R / p).read_text())["filas"]
    ]
    usados = np.array(sorted(usados))
    lejos_de_usados = [
        f for f in sorted(todas) if np.min(np.abs(usados - f)) >= SEPARACION_S * FPS
    ]
    eleg = [f for f in lejos_de_usados if x_juego(f) < LARGO / 3]
    idx = np.linspace(0, len(eleg) - 1, N_HOJA).round().astype(int)
    sel = [eleg[i] for i in idx]
    # episodios: tramos de juego cercano separados por > 1 s, sobre TODOS los elegibles (no sobre
    # los 60 elegidos, que están a ~2 s unos de otros y saldrían cada uno en su episodio)
    ep_de = np.zeros(len(eleg), int)
    ep_de[1:] = np.cumsum(np.diff(eleg) > FPS * 1.0)
    episodio = ep_de[idx]
    activo = gv.balon_activo(
        gbr.CACHE_BALON,
        R / "outputs/diagnostico_26oct_b/posiciones_main.csv",
        gbr.CAMPO,
    )
    filas = []
    for f, ep in zip(sel, episodio):
        s = activo.get(f)
        e = [float(v) for v in s[0][2:6]] if s is not None else None
        filas.append(
            {
                "frame": int(f),
                "zona": "cerca",
                "episodio": int(ep),
                "x_juego": round(x_juego(f), 1),
                "elegida": e,
                "otras": [
                    [float(v) for v in d[2:6]]
                    for d in todas.get(f, [])
                    if e is None or [float(v) for v in d[2:6]] != e
                ],
                "relojes": gbr.relojes(int(f)),
            }
        )
    (HOJA / "img").mkdir(parents=True, exist_ok=True)
    for f, img in leer_frames_ffmpeg(gbr.VIDEO, [x["frame"] for x in filas]):
        cv2.imwrite(str(HOJA / f"img/f{f}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    (HOJA / "frames.json").write_text(json.dumps({"filas": filas}, indent=1))
    pagina = (
        gbr.PAGINA.replace("__FILAS__", json.dumps(filas))
        .replace('"gt_balon_rapido_23oct_f"', '"gt_balon_cerca_28oct"')
        .replace('"respuestas_gt_balon.csv"', '"respuestas_gt_balon_cerca.csv"')
        .replace(
            "<title>GT rápido del balón</title>", "<title>Balón: juego cercano</title>"
        )
    )
    assert (
        '"gt_balon_cerca_28oct"' in pagina and "respuestas_gt_balon_cerca.csv" in pagina
    )
    (HOJA / "index.html").write_text(pagina)
    return {
        "frames_de_balon_lejos_de_hojas_previas": len(lejos_de_usados),
        "de_ellos_juego_cercano": len(eleg),
        "frames_en_la_hoja": len(filas),
        "episodios": int(episodio.max() + 1),
        "frames_por_episodio": dict(Counter(int(e) for e in episodio)),
        "con_candidata_elegida": sum(x["elegida"] is not None for x in filas),
        "pagina": str(HOJA / "index.html"),
    }


def leer(ruta: Path) -> None:
    filas = list(csv.DictReader(open(ruta)))
    GT_CERCA.parent.mkdir(parents=True, exist_ok=True)
    with open(GT_CERCA, "w", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["frame", "zona", "respuesta", "x_px", "y_px"]
        )
        w.writeheader()
        w.writerows(filas)
    print(f"✓ {len(filas)} respuestas → {GT_CERCA}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["control", "oraculo", "hoja", "leer"])
    ap.add_argument("csv", nargs="?")
    args = ap.parse_args()
    if args.accion == "leer":
        leer(Path(args.csv))
        return
    SALIDA.mkdir(parents=True, exist_ok=True)
    res = {"control": control, "oraculo": oraculo, "hoja": hoja}[args.accion]()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=float)
    (SALIDA / f"{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
