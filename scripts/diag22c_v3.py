#!/usr/bin/env python
"""Diagnóstico 22-oct (c), bloque 2: v3 intento 2 (cobertura y «devolver a su equipo»).

Criterio en `docs/diagnostico_22oct_c.md`. Tres pasadas `desde_cache` de la parte entera del
benjamín, que solo cambian la caché de color y una clave de equipos (sin tocar producción):
- hoy: la configuración de producción;
- v3: la caché de color v3 (máscara por posición, 22-oct b);
- v3_devolver: v3 + `arbitro.devolver_por_color: true` (`uno_solo` ya está en true).

Uso:
    python scripts/diag22c_v3.py --v3 outputs/diagnostico_22oct_b/cache_colores_v3.pkl \\
        --salida outputs/diagnostico_22oct_c
"""

import argparse
import importlib.util
import json
import logging
import pickle
import re
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
GT = R / "data/annotations/gt_benja/annotations.xml"
H_BENJA = R / "data/calibracion_benja/homografia_benja.npy"
RADIO = 2.0
EQUIPOS = ("A", "B")
LARGO, ANCHO, FUERA_STAFF_M = 62.0, 40.0, 2.0


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Captura(logging.Handler):
    """Guarda los mensajes del log para leer el aviso del tercer grupo."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.mensajes: list[str] = []

    def emit(self, record):
        self.mensajes.append(record.getMessage())


def tercer_grupo(mensajes: list[str]) -> int | None:
    """Nº de identidades del tercer grupo según `avisar_tercer_grupo` (el último aviso)."""
    n = None
    for m in mensajes:
        if m.startswith("Tercer grupo: 1 identidad"):
            n = 1
        elif m.startswith("TERCER GRUPO VACÍO"):
            n = 0
        elif (g := re.match(r"TERCER GRUPO CON (\d+) IDENTIDADES", m)) is not None:
            n = int(g.group(1))
    return n


def pasada(nombre: str, salida: Path, cache_colores: Path, devolver: bool) -> dict:
    import yaml

    from src.tracking_data.processor import procesar_desde_cache

    csv = salida / f"posiciones_{nombre}.csv"
    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["cache_colores"] = str(cache_colores)
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(salida / f"posiciones_{nombre}_meta.json")
    if devolver:
        eq = yaml.safe_load(open(R / cfg["config_equipos"]))
        eq["arbitro"]["devolver_por_color"] = True
        ruta_eq = salida / f"equipos_{nombre}.yaml"
        ruta_eq.write_text(yaml.safe_dump(eq, allow_unicode=True))
        cfg["config_equipos"] = str(ruta_eq)
    cap = _Captura()
    raiz = logging.getLogger()
    raiz.addHandler(cap)
    nivel = raiz.level
    raiz.setLevel(logging.INFO)
    try:
        procesar_desde_cache(cfg)
    finally:
        raiz.removeHandler(cap)
        raiz.setLevel(nivel)
    (salida / f"posiciones_{nombre}.log").write_text("\n".join(cap.mensajes))
    return {"csv": csv, "tercer_grupo": tercer_grupo(cap.mensajes)}


def gt_benja():
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    return gt_a_por_frame(parsear_cvat(GT), np.load(H_BENJA), 9750, 15)


def casados(filas, gt):
    """{frame: FrameCasado} contra los jugadores del GT (sin árbitro), 1-a-1 a RADIO."""
    from src.evaluation.desglose_error import casar_frame

    porf = {f: g for f, g in filas.groupby("frame")}
    out = {}
    for f in sorted(gt):
        g = porf.get(f)
        if g is None:
            continue
        jug = [o for o in gt[f] if o.label != "referee"]
        out[f] = (
            casar_frame(
                f,
                [("X", o.pos[0], o.pos[1]) for o in jug],
                g.x_m.to_numpy(),
                g.y_m.to_numpy(),
                g.etiqueta.to_numpy(),
                RADIO,
            ),
            g,
        )
    return out


def cobertura(filas, gt) -> dict:
    """% de personas-jugador del GT casadas con una fila de equipo (A, B o portero)."""
    total = cubiertas = 0
    for fc, _g in casados(filas, gt).values():
        for p in fc.personas:
            total += 1
            cubiertas += p.fila is not None and fc.etiqueta[p.fila] in EQUIPOS
    return {"personas": total, "cubiertas": cubiertas, "pct": 100 * cubiertas / total}


def recuento(filas) -> dict:
    eq = filas.etiqueta.astype(str).str.replace("portero_", "")
    c = (
        filas.assign(e=eq)[eq.isin(EQUIPOS)]
        .groupby(["frame", "e"])
        .size()
        .unstack(fill_value=0)
    )
    return {
        "media_A_B": [round(float(c.A.mean()), 2), round(float(c.B.mean()), 2)],
        "frames_A_mas_de_7": int((c.A > 7).sum()),
        "frames_B_mas_de_7": int((c.B > 7).sum()),
    }


def desglose_movidas(base, v3, dets, det_arbitro, gt, b3) -> dict:
    """Las filas no-árbitro que pasan de A/B (hoy) a `otro` (v3): qué son y por qué."""

    def prep(d):
        r = d[d.es_real == 1].copy()
        r["k"] = b3.caja_cruda_mas_cercana(r, dets)
        r["arb"] = [(f, k) in det_arbitro for f, k in zip(r.frame, r.k)]
        return r

    hb, nv = prep(base), prep(v3)
    j = hb.drop_duplicates(["frame", "k"]).merge(
        nv.drop_duplicates(["frame", "k"])[["frame", "k", "etiqueta", "id_jugador"]],
        on=["frame", "k"],
        suffixes=("", "_v3"),
    )
    mov = j[(~j.arb) & j.etiqueta.isin(EQUIPOS) & (j.etiqueta_v3 == "otro")].copy()
    # árbitro por identidad (de HOY): su identidad tiene > 50 % de detecciones del proxy
    frac_arb = hb.groupby("id_jugador").arb.mean()
    mov["arb_identidad"] = mov.id_jugador.map(frac_arb).fillna(0) > 0.5
    fuera = np.maximum.reduce(
        [
            -mov.x_m.to_numpy(),
            mov.x_m.to_numpy() - LARGO,
            -mov.y_m.to_numpy(),
            mov.y_m.to_numpy() - ANCHO,
            np.zeros(len(mov)),
        ]
    )
    mov["staff"] = fuera > FUERA_STAFF_M
    mov["clase"] = np.where(
        mov.staff,
        "staff",
        np.where(mov.arb_identidad, "arbitro_por_identidad", "resto"),
    )
    # mecanismo: la identidad v3 entera en 'otro' (voto de identidad) o solo esa observación
    todo_otro = nv.groupby("id_jugador").etiqueta.agg(
        lambda s: bool((s == "otro").all())
    )
    mov["mecanismo"] = np.where(
        mov.id_jugador_v3.map(todo_otro).fillna(False),
        "identidad_entera_en_otro",
        "observacion_suelta_de_identidad_AB",
    )
    # ventana del GT: ¿la fila de hoy estaba casada con un jugador del GT?
    en_gt = mov[mov.frame.isin(set(gt))]
    cas = casados(base, gt)
    jugador_gt = 0
    for r in en_gt.itertuples():
        fc, g = cas.get(r.frame, (None, None))
        if fc is None:
            continue
        pos = np.flatnonzero(
            (g.x_m.to_numpy() == r.x_m)
            & (g.y_m.to_numpy() == r.y_m)
            & (g.id_jugador.to_numpy() == r.id_jugador)
        )
        jugador_gt += bool(len(pos)) and int(pos[0]) in fc.persona_de_fila
    return {
        "movidas": int(len(mov)),
        "por_clase": mov.clase.value_counts().to_dict(),
        "por_mecanismo": mov.mecanismo.value_counts().to_dict(),
        "clase_x_mecanismo": {
            f"{a}|{b}": int(n)
            for (a, b), n in mov.groupby(["clase", "mecanismo"]).size().items()
        },
        "en_ventana_gt": int(len(en_gt)),
        "en_ventana_gt_casadas_con_jugador_del_gt": int(jugador_gt),
        "personas_distintas_aprox_ids_hoy": int(mov.id_jugador.nunique()),
    }


def main() -> None:
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v3", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(CONFIG))
    prod_colores = R / cfg["rutas"]["cache_colores"]
    v3_colores = Path(args.v3).resolve()

    pasadas = {
        "hoy": pasada("hoy", salida, prod_colores, devolver=False),
        "v3": pasada("v3", salida, v3_colores, devolver=False),
        "v3_devolver": pasada("v3_devolver", salida, v3_colores, devolver=True),
    }
    # control: la pasada «hoy» tiene que reproducir el CSV con el que se midió el 22-oct (b)
    base_b = R / "outputs/arbitro_obs/posiciones.csv"
    control_hoy = pasadas["hoy"]["csv"].read_bytes() == base_b.read_bytes()

    b3 = _mod("diag22b_bloque3_medir")
    am = _mod("arbitro_medicion")
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    base = pd.read_csv(pasadas["hoy"]["csv"])
    W = am.masa_de_ventana(
        base[base.es_real == 1], dets, pickle.load(open(prod_colores, "rb"))
    )
    zb = (W.x_m >= am.ZONA_PORTERO_B_X) & ((W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY)
    W = W[(W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")]
    det_arbitro = set(zip(W.frame, W.k))
    gt = gt_benja()

    res = {"control_hoy_identico_al_csv_del_22oct_b": control_hoy}
    for nombre, p in pasadas.items():
        filas = pd.read_csv(p["csv"])
        res[nombre] = {
            "cobertura": cobertura(filas, gt),
            "error_equipo_jugadores_pct": b3.error_equipo(p["csv"]),
            **b3.metricas_arbitro(filas, dets, det_arbitro),
            "tercer_grupo": p["tercer_grupo"],
            **recuento(filas),
        }
    res["desglose_movidas_hoy_a_v3"] = desglose_movidas(
        base, pd.read_csv(pasadas["v3"]["csv"]), dets, det_arbitro, gt, b3
    )
    h, n = res["hoy"], res["v3_devolver"]
    crit = {
        "1_cobertura": n["cobertura"]["pct"] >= h["cobertura"]["pct"] - 0.5,
        "2_error_equipo": n["error_equipo_jugadores_pct"]
        <= h["error_equipo_jugadores_pct"] + 0.3,
        "3_arbitro_en_equipo_20": n["en_un_equipo_pct"] <= 20.0,
        "4_tercer_grupo_3": n["tercer_grupo"] is not None and n["tercer_grupo"] <= 3,
        "villaviciosa": "NO MEDIDO (sin vídeo en local): no se adopta",
    }
    crit["cumple_benjamin"] = all(v is True for k, v in crit.items() if k[0].isdigit())
    res["criterio_v3_devolver"] = crit
    (salida / "bloque2.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
