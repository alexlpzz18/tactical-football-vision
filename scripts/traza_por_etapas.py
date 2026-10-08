#!/usr/bin/env python
"""Traza por etapas: ¿en qué etapa se pierde cada persona del GT que falta?

Solo medición, local, sin tocar producción. Plan y criterio en `docs/traza_por_etapas.md`; el
CRITERIO de abajo se commitea ANTES de ver ningún número.

Corre la pasada de producción desde el caché (código de HOY) con espías que guardan lo que sale
de cada etapa, y casa el GT con cada etapa con UN SOLO casado (`casar_frame`, 1-a-1 en metros).

Uso:
    python scripts/traza_por_etapas.py pasada --trabajo DIR   # ~90 s, guarda etapas.pkl
    python scripts/traza_por_etapas.py medir --trabajo DIR
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

# ── Fijado ANTES de medir (commit aparte) ─────────────────────────────────────
CRITERIO = {
    "radio_banco_m": 2.0,  # el del banco y del desglose: recall y «faltan»
    "radio_traza_m": 5.0,  # a quién se traza: sin fila a ≤ 5 m
    "recalls_max_dif_pts": 1.0,  # píxeles contra metros: se reconcilian si ≤ 1 punto
    "pie_px": 20.0,  # el casado en píxeles del 96,7 % (backlog23)
}
ETAPAS = ("a_caja_cruda", "b_filtros", "c_identidad", "d_etiqueta", "e_csv")
EQUIPO_BLOQUE = ("A", "B", "portero_A", "portero_B")

CONFIG = R / "configs/processor_benja_parte_entera.yaml"
GT = R / "data/annotations/gt_benja/annotations.xml"
OFFSET_GT, PASO_GT = 9750, 15


def primera_perdida(casada: dict) -> str | None:
    """Primera etapa (en orden) en que la persona NO está casada; None si llega al final."""
    for e in ETAPAS:
        if not casada[e]:
            return e
    return None


def reaparece(casada: dict) -> bool:
    """¿Vuelve a estar casada en una etapa POSTERIOR a la de su pérdida?"""
    e = primera_perdida(casada)
    if e is None:
        return False
    despues = ETAPAS.index(e) + 1
    return any(casada[x] for x in ETAPAS[despues:])


def casado_en_pixeles(det, caja, pie_px: float = CRITERIO["pie_px"]) -> bool:
    """El casado del 96,7 %: centro de la caja del GT dentro de la detección, o pies < pie_px."""
    x1, y1, x2, y2 = det[2], det[3], det[4], det[5]
    cu, cv = (caja.xtl + caja.xbr) / 2.0, (caja.ytl + caja.ybr) / 2.0
    if x1 <= cu <= x2 and y1 <= cv <= y2:
        return True
    return float(np.hypot((x1 + x2) / 2.0 - cu, y2 - caja.ybr)) < pie_px


def reconcilian(recall_px: float, recall_m: float) -> bool:
    return abs(recall_px - recall_m) * 100 <= CRITERIO["recalls_max_dif_pts"]


# ─────────────────────────────── la pasada con espías ─────────────────────────
def pasada(args) -> None:
    import yaml

    import src.team_classification.pipeline_equipos as pe
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
    orig = {
        "plaus": pf.filtrar_por_plausibilidad,
        "perfil": perf.correr_perfil,
        "por_obs": pe.etiquetar_por_observacion,
        "post": perf.postprocesar,
    }

    def espia_plaus(*a, **k):
        r = orig["plaus"](*a, **k)
        capt["cache_filtrado"] = r[0]
        return r

    def espia_perfil(*a, **k):
        r = orig["perfil"](*a, **k)
        # (identidad 1-based, frame, det_idx en el caché FILTRADO)
        capt["obs"] = [
            (n, f, d)
            for n, ident in enumerate(r, start=1)
            for tr in ident
            for f, d in tr.det_idxs
        ]
        return r

    def espia_por_obs(*a, **k):
        r = orig["por_obs"](*a, **k)
        capt["etiquetas_por_obs"] = dict(r)
        return r

    def espia_post(*a, **k):
        r = orig["post"](*a, **k)
        capt["equipos_final"] = dict(r[1])
        return r

    pf.filtrar_por_plausibilidad = espia_plaus
    perf.correr_perfil = espia_perfil
    pe.etiquetar_por_observacion = espia_por_obs
    perf.postprocesar = espia_post
    try:
        procesar_desde_cache(cfg)
    finally:
        pf.filtrar_por_plausibilidad = orig["plaus"]
        perf.correr_perfil = orig["perfil"]
        pe.etiquetar_por_observacion = orig["por_obs"]
        perf.postprocesar = orig["post"]
    faltan = {"cache_filtrado", "obs", "etiquetas_por_obs", "equipos_final"} - set(capt)
    assert not faltan, f"un espía no se disparó: {faltan}"
    # Solo hace falta la ventana del GT: se guarda eso, no el caché entero.
    ventana = set(range(OFFSET_GT, OFFSET_GT + PASO_GT * 60, PASO_GT))
    capt["cache_filtrado"] = {
        e["frame_idx"]: e["dets"]
        for e in capt["cache_filtrado"]
        if e["frame_idx"] in ventana
    }
    capt["obs"] = [o for o in capt["obs"] if o[1] in ventana]
    with open(trabajo / "etapas.pkl", "wb") as f:
        pickle.dump(capt, f)
    print(f"✓ etapas en {trabajo / 'etapas.pkl'}")


# ─────────────────────────────── la medición ──────────────────────────────────
def _puntos_por_etapa(capt, crudas, csv, frame):
    """{etapa: (x, y)} de los puntos que sobreviven a cada etapa en ese frame."""
    fil = capt["cache_filtrado"].get(frame, [])
    en_id = [(n, d) for n, f, d in capt["obs"] if f == frame]
    etq = capt["etiquetas_por_obs"]
    eq = capt["equipos_final"]
    bloque = [
        fil[d]
        for n, d in en_id
        if (etq.get((n, frame)) or eq.get(n, "otro")) in EQUIPO_BLOQUE
    ]
    filas = csv[(csv.frame == frame) & (csv.es_real == 1)]
    filas_b = filas[filas.etiqueta.isin(EQUIPO_BLOQUE)]

    def xy(lista):
        a = np.array([(d[0], d[1]) for d in lista], dtype=float).reshape(-1, 2)
        return a[:, 0], a[:, 1]

    return {
        "a_caja_cruda": xy(crudas.get(frame, [])),
        "b_filtros": xy(fil),
        "c_identidad": xy([fil[d] for _n, d in en_id]),
        "d_etiqueta": xy(bloque),
        "e_csv": (filas_b.x_m.to_numpy(), filas_b.y_m.to_numpy()),
        "e_csv_cualquier_etiqueta": (filas.x_m.to_numpy(), filas.y_m.to_numpy()),
    }


def medir(args) -> None:
    import pandas as pd
    import yaml

    from src.evaluation.desglose_error import casar_frame
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.tracking.cache_io import cargar_cache

    trabajo = Path(args.trabajo)
    capt = pickle.load(open(trabajo / "etapas.pkl", "rb"))
    csv = pd.read_csv(trabajo / "posiciones.csv")
    cfg = yaml.safe_load(open(CONFIG))
    H = np.load(R / cfg["rutas"]["homografia"])
    tracks = parsear_cvat(GT)
    gt_m = gt_a_por_frame(tracks, H, OFFSET_GT, PASO_GT)
    cajas = {}
    for t in tracks:
        for c in t.cajas:
            cajas[(OFFSET_GT + PASO_GT * c.frame_local, t.track_id)] = c
    crudas = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }

    casos = []  # una fila por (frame, persona)
    for f in sorted(gt_m):
        obs = gt_m[f]
        gt = [("X", o.pos[0], o.pos[1]) for o in obs]  # equipo irrelevante para casar
        pts = _puntos_por_etapa(capt, crudas, csv, f)
        cas = {}
        for radio in (CRITERIO["radio_banco_m"], CRITERIO["radio_traza_m"]):
            for etapa, (x, y) in pts.items():
                fc = casar_frame(
                    f, gt, x, y, np.array(["A"] * len(x), dtype=object), radio
                )
                cas[(radio, etapa)] = [p.fila is not None for p in fc.personas]
        for k, o in enumerate(obs):
            caja = cajas[(f, o.obj_id)]
            fila = {
                "frame": f,
                "track": o.obj_id,
                "equipo": o.team,
                "x": o.pos[0],
                "y": o.pos[1],
                "px": any(casado_en_pixeles(d, caja) for d in crudas.get(f, [])),
            }
            for (radio, etapa), v in cas.items():
                fila[f"{etapa}@{radio:g}"] = v[k]
            casos.append(fila)
    C = pd.DataFrame(casos)
    C.to_csv(trabajo / "casos.csv", index=False)
    n = len(C)
    r2, r5 = CRITERIO["radio_banco_m"], CRITERIO["radio_traza_m"]

    def tabla(radio, sub):
        filas = []
        for _i, r in sub.iterrows():
            filas.append(primera_perdida({e: r[f"{e}@{radio:g}"] for e in ETAPAS}))
        return pd.Series(filas).value_counts().reindex(ETAPAS, fill_value=0)

    def reap(radio, sub):
        return int(
            sum(
                reaparece({e: r[f"{e}@{radio:g}"] for e in ETAPAS})
                for _i, r in sub.iterrows()
            )
        )

    rec_px = C.px.mean()
    rec_m2 = C[f"a_caja_cruda@{r2:g}"].mean()
    rec_m5 = C[f"a_caja_cruda@{r5:g}"].mean()
    fila2 = C[f"e_csv@{r2:g}"]
    fila5 = C[f"e_csv@{r5:g}"]
    sin5 = C[~fila5]
    aus2 = C[~fila2]
    res = {
        "criterio": CRITERIO,
        "personas_frame": n,
        "recall_detector": {
            "pixeles_96_7": round(float(rec_px), 4),
            "metros_2m": round(float(rec_m2), 4),
            "metros_5m": round(float(rec_m5), 4),
            "reconcilian_2m": reconcilian(rec_px, rec_m2),
            "px_si_metros2_no": int((C.px & ~C[f"a_caja_cruda@{r2:g}"]).sum()),
            "metros2_si_px_no": int((~C.px & C[f"a_caja_cruda@{r2:g}"]).sum()),
        },
        "hay_fila_csv": {
            "2m_bloque": round(float(fila2.mean()), 4),
            "2m_cualquier_etiqueta": round(
                float(C[f"e_csv_cualquier_etiqueta@{r2:g}"].mean()), 4
            ),
            "5m_bloque": round(float(fila5.mean()), 4),
        },
        "ausencias_2m": int(len(aus2)),
        "ausencias_2m_con_fila_2_5m": int(fila5[~fila2].sum()),
        "sin_fila_5m": int(len(sin5)),
        "tabla_5m": {k: int(v) for k, v in tabla(r5, sin5).items()},
        "reaparecen_5m": reap(r5, sin5),
        "tabla_2m_todas_las_ausencias": {k: int(v) for k, v in tabla(r2, aus2).items()},
        "reaparecen_2m": reap(r2, aus2),
        "sin_fila_5m_por_track": {
            str(k): int(v) for k, v in sin5.track.value_counts().items()
        },
    }
    res["contabilidad_cerrada_5m"] = sum(res["tabla_5m"].values()) == len(sin5)
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
