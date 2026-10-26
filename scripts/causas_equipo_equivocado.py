#!/usr/bin/env python
"""¿Por qué una fila sale con el EQUIPO EQUIVOCADO? Solo medición (rama clasificacion-benja).

Plan y criterio: `docs/plan_causas_equipo_equivocado.md`. El CRITERIO de abajo se commitea ANTES de
medir. Producción no se toca: se regenera su salida desde el caché con un espía que guarda la CAJA
exacta de cada fila real.

Uso:
    python scripts/causas_equipo_equivocado.py pasada --trabajo DIR   # ~2 min
    python scripts/causas_equipo_equivocado.py medir --trabajo DIR
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

# ── Fijado ANTES de medir (commit aparte) ─────────────────────────────────────
CRITERIO = {
    "radio_casado_m": 2.0,  # el protocolo del desglose
    "orden_causas": [
        "arbitro",
        "staff",
        "portero",
        "caja_dos_personas",
        "recorte_limpio",
    ],
    "staff_fuera_m": 2.0,  # tolerancia de la regla de staff
    "margen_area_m": 2.0,
    "iou_solape": 0.10,  # como en el baile
    "ancha_factor": 1.25,  # > 25 % más ancha de lo normal para su alto
    "franjas_alto_px": [0, 30, 45, 60, 80, 110, 400],
    "n_base_partido": 5000,
    "semilla": 0,
    # controles del instrumento
    "arbitro_min_frames_ventana": 55,  # de 60: el árbitro está en el campo
    "n_minimo_para_tasa": 30,
}
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
GT = R / "data/annotations/gt_benja/annotations.xml"
OFFSET_GT, PASO_GT = 9750, 15
LARGO, ANCHO = 62.0, 40.0


def _cargar(nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────── piezas puras (con tests) ─────────────────────
def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / (area + 1e-9)


def fuera_del_campo(x: float, y: float, tolerancia: float) -> bool:
    return (
        x < -tolerancia
        or x > LARGO + tolerancia
        or y < -tolerancia
        or y > ANCHO + tolerancia
    )


def es_portero_posicional(x, y, areas, xs_del_frame) -> bool:
    """Dentro de un área Y la fila más cercana a esa portería de todas las del bloque."""
    for lado, ((x0, x1), (y0, y1)) in areas.items():
        if x0 <= x <= x1 and y0 <= y <= y1:
            if lado == "bajo":
                return x <= min(xs_del_frame)
            return x >= max(xs_del_frame)
    return False


def caja_ancha(ancho_px, alto_px, medianas: dict, franjas, factor) -> bool:
    """¿Más ancha de lo normal para su alto? `medianas`: {índice de franja: ancho/alto}."""
    if alto_px <= 0:
        return False
    k = int(np.searchsorted(franjas, alto_px, side="right")) - 1
    esperado = medianas.get(k)
    return bool(esperado) and (ancho_px / alto_px) / esperado > factor


def causa(arbitro: bool, staff: bool, portero: bool, dos_personas: bool) -> str:
    """La primera causa que se cumple, en el orden fijado."""
    for nombre, cumple in zip(
        CRITERIO["orden_causas"], (arbitro, staff, portero, dos_personas, True)
    ):
        if cumple:
            return nombre
    return "recorte_limpio"  # inalcanzable: la última siempre se cumple


def exceso(n: int, p: float, p_base: float) -> float:
    """Cuántos casos explica una causa POR ENCIMA de lo que ya pasa en la base."""
    return n * (p - p_base) if p > p_base else 0.0


# ─────────────────────────────── la pasada con espía ──────────────────────────
def pasada(args) -> None:
    import yaml

    import src.tracking.perfiles as perf
    import src.tracking.plausibilidad_fisica as pf
    from src.tracking_data.processor import procesar_desde_cache

    trabajo = Path(args.trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(trabajo / "posiciones.csv")
    cfg["rutas"]["salida_meta"] = str(trabajo / "posiciones_meta.json")
    capt = {}
    orig = (pf.filtrar_por_plausibilidad, perf.correr_perfil)

    def espia_plaus(*a, **k):
        r = orig[0](*a, **k)
        capt["cache_filtrado"] = {e["frame_idx"]: e["dets"] for e in r[0]}
        return r

    def espia_perfil(*a, **k):
        r = orig[1](*a, **k)
        capt["obs"] = {}
        for n, ident in enumerate(r, start=1):
            for tr in ident:
                for f, d in tr.det_idxs:
                    capt["obs"].setdefault((n, f), d)
        return r

    pf.filtrar_por_plausibilidad, perf.correr_perfil = espia_plaus, espia_perfil
    try:
        procesar_desde_cache(cfg)
    finally:
        pf.filtrar_por_plausibilidad, perf.correr_perfil = orig
    assert {"cache_filtrado", "obs"} <= set(capt), "un espía no se disparó"
    pickle.dump(capt, open(trabajo / "cajas.pkl", "wb"))
    print(f"✓ {len(capt['obs'])} observaciones con su caja en {trabajo}")


# ─────────────────────────────── la medición ──────────────────────────────────
def medir(args) -> None:
    import pandas as pd
    import yaml

    from src.campo_modelo import cargar_modelo
    from src.evaluation.desglose_error import casar_frame, equipo_de_etiqueta
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.tracking.cache_io import cargar_cache

    trabajo = Path(args.trabajo)
    cfg = yaml.safe_load(open(CONFIG))
    csv = pd.read_csv(trabajo / "posiciones.csv")
    capt = pickle.load(open(trabajo / "cajas.pkl", "rb"))
    reales = csv[csv.es_real == 1].copy()
    am = _cargar("arbitro_medicion")
    baile = _cargar("baile_de_colores")

    # 1. árbitro por píxeles (el proxy calibrado, tal cual)
    crudo = cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    dets_crudas = {e["frame_idx"]: e["dets"] for e in crudo}
    colores = pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    W = am.masa_de_ventana(reales, dets_crudas, colores)
    zona_b = (W.x_m >= am.ZONA_PORTERO_B_X) & (
        (W.y_m - ANCHO / 2).abs() <= am.ZONA_PORTERO_B_DY
    )
    W["arbitro"] = (W.masa >= am.UMBRAL_MASA) & ~zona_b & (W.etiqueta != "portero_B")
    reales = reales.join(W[["masa", "arbitro"]])
    reales["arbitro"] = reales["arbitro"].fillna(False).astype(bool)
    del colores

    # 2. caja exacta, solape, proporciones; staff; portero posicional
    areas = cargar_modelo(config=R / "configs/campo_benja.yaml").areas_porteria(
        margen=CRITERIO["margen_area_m"]
    )
    bloque = reales[reales.etiqueta.isin(["A", "B", "portero_A", "portero_B"])]
    xs_frame = bloque.groupby("frame").x_m.apply(list).to_dict()
    filas = []
    for r in reales.itertuples():
        d = capt["obs"].get((int(r.id_jugador), int(r.frame)))
        dets = capt["cache_filtrado"].get(int(r.frame), [])
        if d is None or d >= len(dets):
            filas.append((np.nan, np.nan, np.nan, False))
            continue
        caja = dets[d][2:6]
        solape = max([iou(caja, x[2:6]) for j, x in enumerate(dets) if j != d] or [0.0])
        filas.append((solape, caja[2] - caja[0], caja[3] - caja[1], True))
    reales[["iou_max", "ancho_px", "alto_px", "con_caja"]] = pd.DataFrame(
        filas, index=reales.index
    )
    reales["staff"] = [
        fuera_del_campo(x, y, CRITERIO["staff_fuera_m"])
        for x, y in zip(reales.x_m, reales.y_m)
    ]
    reales["portero_pos"] = [
        es_portero_posicional(x, y, areas, xs_frame.get(f, [x]))
        for x, y, f in zip(reales.x_m, reales.y_m, reales.frame)
    ]
    rng = np.random.default_rng(CRITERIO["semilla"])
    ab = reales[reales.etiqueta.isin(["A", "B"]) & reales.con_caja]
    base = ab.loc[rng.choice(ab.index, CRITERIO["n_base_partido"], replace=False)]
    fr = CRITERIO["franjas_alto_px"]
    medianas = (
        (base.ancho_px / base.alto_px)
        .groupby(np.searchsorted(fr, base.alto_px, side="right") - 1)
        .median()
        .to_dict()
    )

    def clasificar(df, portero_gt=None):
        out = []
        for i, r in zip(df.index, df.itertuples()):
            dos = bool(r.con_caja) and (
                r.iou_max > CRITERIO["iou_solape"]
                or caja_ancha(
                    r.ancho_px, r.alto_px, medianas, fr, CRITERIO["ancha_factor"]
                )
            )
            port = bool(r.portero_pos) or bool(
                portero_gt is not None and portero_gt.get(i)
            )
            out.append(causa(bool(r.arbitro), bool(r.staff), port, dos))
        return pd.Series(out, index=df.index, dtype=object)

    # 3. E: con verdad, en la ventana del GT
    H = np.load(R / cfg["rutas"]["homografia"])
    gt = gt_a_por_frame(parsear_cvat(GT), H, OFFSET_GT, PASO_GT)
    porf = {f: g for f, g in reales.groupby("frame")}
    E_err, E_bien, E_otro, portero_gt = [], [], [], {}
    for f in sorted(gt):
        g = porf.get(f)
        if g is None:
            continue
        personas = [(equipo_de_etiqueta(o.team), o.pos[0], o.pos[1]) for o in gt[f]]
        fc = casar_frame(
            f,
            personas,
            g.x_m.to_numpy(),
            g.y_m.to_numpy(),
            g.etiqueta.to_numpy(),
            CRITERIO["radio_casado_m"],
        )
        for k, p in enumerate(fc.personas):
            if p.fila is None:
                continue
            idx = g.index[p.fila]
            portero_gt[idx] = str(gt[f][k].team).startswith("portero")
            etq = equipo_de_etiqueta(g.etiqueta.iloc[p.fila])
            if etq == p.equipo:
                E_bien.append(idx)
            elif etq in ("A", "B"):
                E_err.append(idx)
            else:
                E_otro.append(idx)
    ventana = reales[reales.frame.isin(set(gt))]
    frames_con_arbitro = int(ventana[ventana.arbitro].frame.nunique())

    # 4. C: cambios A↔B (definición del baile) sobre el CSV de hoy
    _ab, cambios = baile.cambios_de_equipo(str(trabajo / "posiciones.csv"))
    clave = reales.set_index(["frame", "id_jugador"]).index
    pos_c = [
        reales.index[clave.get_loc((f, i))]
        for f, i in zip(cambios.frame, cambios.id_jugador)
        if (f, i) in clave
    ]

    poblaciones = {
        "E_equipo_equivocado": reales.loc[E_err],
        "E_a_otro_o_staff": reales.loc[E_otro],
        "E_bien (base)": reales.loc[E_bien],
        "C_cambios_AB": reales.loc[pos_c],
        "C_cambios_AB_continuos": reales.loc[
            [p for p, c in zip(pos_c, cambios.continuo) if c]
        ],
        "partido_base_AB": base,
    }
    tabla = {}
    for nombre, df in poblaciones.items():
        c = clasificar(df, portero_gt if nombre.startswith("E") else None)
        tabla[nombre] = {
            "n": int(len(df)),
            **{k: int((c == k).sum()) for k in CRITERIO["orden_causas"]},
        }
    arbitro_ab = reales[reales.arbitro & reales.etiqueta.isin(["A", "B"])]
    res = {
        "criterio": CRITERIO,
        "controles": {
            "exhaustiva": all(
                sum(v[k] for k in CRITERIO["orden_causas"]) == v["n"]
                for v in tabla.values()
            ),
            "frames_ventana_con_arbitro_proxy": frames_con_arbitro,
            "frames_ventana": len(gt),
            "arbitro_ok": frames_con_arbitro >= CRITERIO["arbitro_min_frames_ventana"],
            "cambios_AB_hoy": int(len(cambios)),
            "cambios_continuos_hoy": int(cambios.continuo.sum()),
            "filas_reales_sin_caja": int((~reales.con_caja.astype(bool)).sum()),
        },
        "tabla": tabla,
        "arbitro_contado_en_un_equipo": {
            "ventana_filas": int(arbitro_ab.frame.isin(set(gt)).sum()),
            "partido_filas": int(len(arbitro_ab)),
            "partido_filas_reales_AB": int(reales.etiqueta.isin(["A", "B"]).sum()),
        },
        "medianas_ancho_alto_base": {str(k): float(v) for k, v in medianas.items()},
    }
    # Exceso sobre la base de cada causa (solo se atribuye lo que pasa MÁS que en la base)
    for nombre, ref in (
        ("E_equipo_equivocado", "E_bien (base)"),
        ("E_a_otro_o_staff", "E_bien (base)"),
        ("C_cambios_AB", "partido_base_AB"),
        ("C_cambios_AB_continuos", "partido_base_AB"),
    ):
        t, b = tabla[nombre], tabla[ref]
        res.setdefault("exceso_sobre_base", {})[nombre] = {
            k: round(exceso(t["n"], t[k] / max(t["n"], 1), b[k] / max(b["n"], 1)), 1)
            for k in CRITERIO["orden_causas"]
        }
    # el detalle de E, caso a caso (es pequeño: se describe, no se promedia)
    cols = [
        "frame",
        "tiempo_s",
        "id_jugador",
        "etiqueta",
        "x_m",
        "y_m",
        "masa",
        "iou_max",
        "ancho_px",
        "alto_px",
        "staff",
        "portero_pos",
    ]
    det = reales.loc[E_err + E_otro, cols].copy()
    det["causa"] = clasificar(reales.loc[E_err + E_otro], portero_gt)
    det["portero_gt"] = [portero_gt.get(i, False) for i in det.index]
    det.to_csv(trabajo / "E_casos.csv", index=False)
    (trabajo / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre in ("pasada", "medir"):
        s = sub.add_parser(nombre)
        s.add_argument("--trabajo", required=True)
    args = ap.parse_args()
    pasada(args) if args.cmd == "pasada" else medir(args)


if __name__ == "__main__":
    main()
