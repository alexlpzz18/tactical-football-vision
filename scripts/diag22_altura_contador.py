#!/usr/bin/env python
"""Diagnóstico 22-oct, bloques 3 (altura relativa de caja) y 4 (contador sin GT). Solo medición.

Criterios en `docs/diagnostico_22oct.md`.

Uso:
    python scripts/diag22_altura_contador.py pasada-villa --trabajo outputs/diagnostico_22oct/villa
    python scripts/diag22_altura_contador.py medir --benja outputs/arbitro_obs \\
        --villa outputs/diagnostico_22oct/villa --salida outputs/diagnostico_22oct
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
FPS_BENJA = 29.97002997002997
TRAMO_BENJA = (8991, 10790)  # 5:00-6:00 de archivo
UMBRAL_RATIO = 1.15
MIN_OBS = 40


def ajustar_f(u, v, h):
    """f(u, v) = altura esperada (px): cuadrática en (u, v) con pérdida de Huber (IRLS)."""
    u0, v0 = np.median(u), np.median(v)
    us, vs = (u - u0) / 1000.0, (v - v0) / 1000.0
    X = np.column_stack([np.ones_like(us), us, vs, us * vs, us**2, vs**2])
    w = np.ones(len(h))
    for _ in range(30):
        W = np.sqrt(w)
        beta, *_ = np.linalg.lstsq(X * W[:, None], h * W, rcond=None)
        r = h - X @ beta
        s = 1.4826 * np.median(np.abs(r - np.median(r))) or 1.0
        k = 1.345 * s
        w = np.where(np.abs(r) <= k, 1.0, k / np.maximum(np.abs(r), 1e-9))

    def f(uu, vv):
        a, b = (np.asarray(uu) - u0) / 1000.0, (np.asarray(vv) - v0) / 1000.0
        return np.column_stack([np.ones_like(a), a, b, a * b, a**2, b**2]) @ beta

    return f


def auc(pos, neg) -> float:
    """AUC de Mann-Whitney: P(un positivo > un negativo), empates a medias."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    mayor = (pos[:, None] > neg[None, :]).sum() + 0.5 * (
        pos[:, None] == neg[None, :]
    ).sum()
    return float(mayor / (len(pos) * len(neg)))


def cumple(ratios_arb, ratios_jug) -> dict:
    fa = (
        float(np.mean(np.asarray(ratios_arb) > UMBRAL_RATIO))
        if len(ratios_arb)
        else float("nan")
    )
    fj = (
        float(np.mean(np.asarray(ratios_jug) > UMBRAL_RATIO))
        if len(ratios_jug)
        else float("nan")
    )
    return {
        "arbitro_sobre_1_15": fa,
        "jugador_sobre_1_15": fj,
        "cumple": bool(fa >= 0.80 and fj <= 0.02),
    }


def frames_por_encima(df, maximo: int):
    """Frames con más de `maximo` filas de un equipo (portero incluido): {frame: [equipos]}."""
    eq = df.etiqueta.astype(str).str.replace("portero_", "", regex=False)
    df = df.assign(eq=eq)[eq.isin(["A", "B"])]
    n = df.groupby(["frame", "eq"]).size()
    out = {}
    for (f, e), c in n.items():
        if c > maximo:
            out.setdefault(int(f), []).append(e)
    return out


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pasada_villa(args) -> None:
    """Producción de Villaviciosa desde caché, con espía para la caja de cada fila."""
    import yaml

    import src.tracking.perfiles as perf
    from src.tracking_data.processor import procesar_desde_cache

    trabajo = Path(args.trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(R / "configs/processor.yaml"))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(trabajo / "posiciones.csv")
    cfg["rutas"]["salida_meta"] = str(trabajo / "posiciones_meta.json")
    capt, orig = {}, perf.correr_perfil

    def espia(*a, **k):
        r = orig(*a, **k)
        capt["obs"] = {
            (n, f): d
            for n, ident in enumerate(r, 1)
            for tr in ident
            for f, d in tr.det_idxs
        }
        return r

    perf.correr_perfil = espia
    try:
        procesar_desde_cache(cfg)
    finally:
        perf.correr_perfil = orig
    # Villaviciosa no lleva filtro de plausibilidad: las cajas son las del caché (tras confianza)
    from src.tracking.cache_io import cargar_cache
    from src.tracking.filtro_confianza import filtrar_por_confianza

    cfg_tr = yaml.safe_load(open(R / cfg["config_tracking"]))
    datos = cargar_cache(R / cfg["rutas"]["cache"])
    cache, _ = filtrar_por_confianza(
        datos["cache"], None, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    fis = cfg_tr.get("plausibilidad_fisica", {}) or {}
    assert not fis.get(
        "activo", False
    ), "Villaviciosa con plausibilidad: habría que replicarla"
    capt["cache_filtrado"] = {e["frame_idx"]: e["dets"] for e in cache}
    pickle.dump(capt, open(trabajo / "cajas.pkl", "wb"))
    print(f"✓ Villaviciosa: {len(capt['obs'])} observaciones con caja")


def tabla_identidades(reales, capt, tramo=None):
    """Por fila real: (id, u_pie, v_pie, alto_px). Y el ajuste f sobre TODAS las detecciones."""
    import pandas as pd

    if tramo is not None:
        reales = reales[reales.frame.between(*tramo)]
    filas = []
    for r in reales.itertuples():
        d = capt["obs"].get((int(r.id_jugador), int(r.frame)))
        dets = capt["cache_filtrado"].get(int(r.frame), [])
        if d is None or d >= len(dets):
            continue
        x1, y1, x2, y2 = dets[d][2:6]
        filas.append(
            (int(r.id_jugador), int(r.frame), r.etiqueta, (x1 + x2) / 2, y2, y2 - y1)
        )
    T = pd.DataFrame(filas, columns=["id", "frame", "etiqueta", "u", "v", "h"])
    frames = set(T.frame)
    todas = np.array(
        [
            ((d[2] + d[4]) / 2, d[5], d[5] - d[3])
            for f, ds in capt["cache_filtrado"].items()
            if f in frames
            for d in ds
        ]
    )
    f = ajustar_f(todas[:, 0], todas[:, 1], todas[:, 2])
    T["ratio"] = T.h / f(T.u, T.v)
    return T


def medir(args) -> None:
    import pandas as pd

    from src.evaluation.desglose_error import casar_frame
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.tracking.cache_io import cargar_cache

    salida = Path(args.salida)
    rng = np.random.default_rng(0)
    res = {}

    # ── benjamín ──
    bj = Path(args.benja)
    fb = pd.read_csv(bj / "posiciones.csv")
    rb = fb[fb.es_real == 1]
    cb = pickle.load(open(bj / "cajas.pkl", "rb"))
    am = _mod("arbitro_medicion")
    import yaml

    cfg = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
    crudo = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    W = am.masa_de_ventana(
        rb, crudo, pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    )
    zb = (W.x_m >= am.ZONA_PORTERO_B_X) & ((W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY)
    W["proxy"] = (W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")
    proxy_fila = set(zip(W[W.proxy].frame, W[W.proxy].id_jugador))
    Tb = tabla_identidades(rb, cb, TRAMO_BENJA)
    Tb["proxy"] = [(f, i) in proxy_fila for f, i in zip(Tb.frame, Tb.id)]
    g = Tb.groupby("id").agg(
        n=("ratio", "size"),
        ratio=("ratio", "median"),
        proxy=("proxy", "mean"),
        etq=("etiqueta", lambda s: s.mode().iat[0]),
    )
    g = g[g.n >= MIN_OBS]
    arb_b = g[g.proxy > 0.5]
    jug_b = g[(g.proxy < 0.05) & g.etq.isin(["A", "B", "portero_A", "portero_B"])]
    res["3_benja"] = _bloque3(arb_b, jug_b, rng)

    # ── Villaviciosa ──
    vj = Path(args.villa)
    fv = pd.read_csv(vj / "posiciones.csv")
    rv = fv[fv.es_real == 1]
    cv_ = pickle.load(open(vj / "cajas.pkl", "rb"))
    Tv = tabla_identidades(rv, cv_)
    H = np.load(R / "data/calibracion/homografia.npy")
    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/ground_truth_tracking/annotations.xml"),
        H,
        7500,
        15,
    )
    porf = {f: x for f, x in rv.groupby("frame")}
    voto = {}
    for f in gt:
        x = porf.get(f)
        if x is None:
            continue
        gtf = [("X", o.pos[0], o.pos[1]) for o in gt[f]]
        fc = casar_frame(
            f, gtf, x.x_m.to_numpy(), x.y_m.to_numpy(), x.etiqueta.to_numpy(), 2.0
        )
        for k, p in enumerate(fc.personas):
            if p.fila is not None:
                ident = int(x.id_jugador.iloc[p.fila])
                voto.setdefault(ident, []).append(gt[f][k].label == "referee")
    es_arb_v = {i for i, v in voto.items() if len(v) >= 5 and np.mean(v) > 0.5}
    gv = Tv.groupby("id").agg(
        n=("ratio", "size"),
        ratio=("ratio", "median"),
        etq=("etiqueta", lambda s: s.mode().iat[0]),
    )
    gv = gv[gv.n >= MIN_OBS]
    arb_v = gv[gv.index.isin(es_arb_v)]
    jug_v = gv[
        ~gv.index.isin(es_arb_v)
        & gv.etq.isin(["A", "B", "portero_A", "portero_B"])
        & gv.index.isin(voto)
    ]
    res["3_villa"] = _bloque3(arb_v, jug_v, rng)

    # ── bloque 4 ──
    staff_b = set(
        zip(fb[fb.etiqueta == "staff"].frame, fb[fb.etiqueta == "staff"].id_jugador)
    )
    res["4_benja"] = _bloque4(
        fb,
        rb,
        7,
        lambda f: any((f, i) in proxy_fila for i in fb[fb.frame == f].id_jugador),
        staff_b,
    )
    staff_v = set(
        zip(fv[fv.etiqueta == "staff"].frame, fv[fv.etiqueta == "staff"].id_jugador)
    )
    res["4_villa"] = _bloque4(
        fv,
        rv,
        11,
        lambda f: bool(set(fv[fv.frame == f].id_jugador) & es_arb_v),
        staff_v,
    )
    (salida / "bloque3_4.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


def _bloque3(arb, jug, rng) -> dict:
    out = {
        "identidades_arbitro": {
            str(i): round(float(r), 3) for i, r in arb.ratio.items()
        },
        "n_jugadores": int(len(jug)),
        "jugadores_ratio_p50_p90_p99": (
            [float(x) for x in np.percentile(jug.ratio, [50, 90, 99])]
            if len(jug)
            else None
        ),
        "auc": auc(arb.ratio, jug.ratio),
        **cumple(arb.ratio, jug.ratio),
    }
    falsos = []
    js = jug.ratio.to_numpy()
    for _ in range(500):
        k = rng.integers(len(js))
        falsos.append(auc([js[k]], np.delete(js, k)))
    out["control_arbitro_falso_auc_media_p95"] = [
        float(np.mean(falsos)),
        float(np.percentile(falsos, 95)),
    ]
    return out


def _bloque4(todas, reales, maximo, hay_arbitro, staff) -> dict:
    out = {"maximo_por_equipo": maximo}
    for nombre, df in (("todas_las_filas", todas), ("solo_reales", reales)):
        fr = frames_por_encima(df, maximo)
        con_arb = sum(1 for f in fr if hay_arbitro(f))
        con_staff = sum(
            1 for f in fr if any((f, i) in staff for i in df[df.frame == f].id_jugador)
        )
        ids = df[df.frame.isin(fr)].id_jugador.value_counts()
        out[nombre] = {
            "frames": len(fr),
            "de": int(df.frame.nunique()),
            "frames_con_arbitro": con_arb,
            "frames_con_staff": con_staff,
            "identidades_mas_frecuentes": {
                str(k): int(v) for k, v in ids.head(8).items()
            },
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pasada-villa")
    p.add_argument("--trabajo", required=True)
    m = sub.add_parser("medir")
    m.add_argument("--benja", required=True)
    m.add_argument("--villa", required=True)
    m.add_argument("--salida", required=True)
    args = ap.parse_args()
    pasada_villa(args) if args.cmd == "pasada-villa" else medir(args)


if __name__ == "__main__":
    main()
