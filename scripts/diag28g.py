#!/usr/bin/env python
"""Diagnóstico 28-oct (g), punto 1: la puerta de calidad de caja. Criterios en
`docs/diagnostico_28oct_g.md`. SOLO mide.

Uso:
    python scripts/diag28g.py pasadas   # desde_cache de la parte entera, flag apagado y encendido
    python scripts/diag28g.py medir     # los 11 errores, excluidas y errores nuevos
    python scripts/diag28g.py eventos   # punto 2: los 10 eventos del clip 1
"""

import argparse
import csv
import hashlib
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
SALIDA = R / "outputs/diagnostico_28oct_g"
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
MAIN_CSV = R / "outputs/diagnostico_26oct_b/posiciones_main.csv"
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
CRUDO = R / "data/tracking_benja/cache_detecciones_benja_p1.pkl"
HOJA = R / "outputs/hoja_equipos"


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def pasada(nombre: str, activo: bool) -> Path:
    """`desde_cache` de la parte entera con la puerta apagada o encendida (YAML temporal)."""
    from src.tracking_data.processor import procesar_desde_cache

    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    ce = yaml.safe_load(open(R / cfg["config_equipos"]))
    ce["agregacion"]["por_observacion"]["excluir_cajas_anormales"]["activo"] = activo
    ruta_ce = SALIDA / f"equipos_{nombre}.yaml"
    yaml.safe_dump(ce, open(ruta_ce, "w"), allow_unicode=True)
    cfg["config_equipos"] = str(ruta_ce)
    csv_salida = SALIDA / f"posiciones_{nombre}.csv"
    cfg["rutas"]["salida_csv"] = str(csv_salida)
    cfg["rutas"]["salida_meta"] = str(SALIDA / f"posiciones_{nombre}_meta.json")
    procesar_desde_cache(cfg)
    return csv_salida


def pasadas() -> dict:
    SALIDA.mkdir(parents=True, exist_ok=True)
    apagado = pasada("apagado", False)
    encendido = pasada("encendido", True)
    return {
        "apagado_identico_a_main_byte_a_byte": _sha(apagado) == _sha(MAIN_CSV),
        "encendido_distinto": _sha(encendido) != _sha(apagado),
    }


def _errores_gt(df: pd.DataFrame) -> dict:
    """{(frame, persona del GT): (equipo GT, equipo sistema)} de los ERRORES del casado 1-a-1."""
    from scipy.optimize import linear_sum_assignment

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    ce = _mod("comparar_escalas")
    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"), H, 9750, 15
    )
    df = df[df.es_real == 1]
    por_frame = {f: g for f, g in df.groupby("frame")}
    errores, casadas = {}, 0
    for frame, obs in sorted(gt.items()):
        gente = [o for o in obs if ce.equipo_gt(o) in ("A", "B")]
        if not gente or frame not in por_frame:
            continue
        sub = por_frame[frame]
        xy = sub[["x_m", "y_m"]].to_numpy()
        et = sub.etiqueta.to_numpy()
        coste = np.hypot(
            xy[None, :, 0] - np.array([o.pos[0] for o in gente])[:, None],
            xy[None, :, 1] - np.array([o.pos[1] for o in gente])[:, None],
        )
        coste = np.where(coste > ce.RADIO_CASADO_M, 1e6, coste)
        for i, j in zip(*linear_sum_assignment(coste)):
            if coste[i, j] >= 1e6:
                continue
            casadas += 1
            g, s = ce.equipo_gt(gente[i]), str(et[j]).replace("portero_", "")
            if s in ("A", "B") and s != g:
                errores[(int(frame), int(gente[i].obj_id))] = (g, s)
    return {"casadas": casadas, "errores": errores}


def _errores_hoja(df: pd.DataFrame) -> set:
    """Las filas de la hoja de 120 cuya marca no coincide con la etiqueta del DUEÑO de la caja."""
    aud = _mod("auditar_hojas")
    cap = pickle.load(open(CAPTURA, "rb"))
    filt = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    crudo = {e["frame_idx"]: e["dets"] for e in pickle.load(open(CRUDO, "rb"))["cache"]}
    dueno = {}
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            dueno[(int(f), int(k))] = i
    et = {(int(r.frame), int(r.id_jugador)): str(r.etiqueta) for r in df.itertuples()}
    marcas = {
        r["imagen"]: r["equipo_correcto"]
        for r in csv.DictReader(
            open(
                R / "outputs/diagnostico_28oct_c/revision_equipo_por_obs_20min_alex.csv"
            )
        )
    }
    mapa = {"A": "A", "B": "B", "portero_A": "A", "portero_B": "B"}
    malas = set()
    for r in csv.DictReader(open(HOJA / "clave_equipo_por_obs_20min.csv")):
        f = int(r["frame"])
        caja = [float(v) for v in crudo[f][int(r["k"])][2:6]]
        kf = [
            j
            for j, d in enumerate(filt[f])
            if aud.iou(caja, [float(x) for x in d[2:6]]) > 0.99
        ]
        d = dueno.get((f, kf[0])) if kf else None
        sis = et.get((f, d), "?").replace("portero_", "")
        if mapa.get(marcas[r["imagen"]], "ERR") != sis:
            malas.add(r["imagen"])
    return malas


def medir() -> dict:
    from src.team_classification.calidad_caja import cajas_anormales

    off = pd.read_csv(SALIDA / "posiciones_apagado.csv")
    on = pd.read_csv(SALIDA / "posiciones_encendido.csv")
    g_off, g_on = _errores_gt(off), _errores_gt(on)
    h_off, h_on = _errores_hoja(off), _errores_hoja(on)
    antes = set(g_off["errores"]) | {("hoja", x) for x in h_off}
    despues = set(g_on["errores"]) | {("hoja", x) for x in h_on}
    # fracción excluida: detecciones del caché del tracker que la puerta deja sin voto
    cfg = yaml.safe_load(open(CONFIG))
    ce = yaml.safe_load(open(R / cfg["config_equipos"]))
    p = ce["agregacion"]["por_observacion"]["excluir_cajas_anormales"]
    cap = pickle.load(open(CAPTURA, "rb"))
    anorm = cajas_anormales(
        cap["cache"],
        alto_max=p["alto_max"],
        ancho_max=p["ancho_max"],
        alto_min=p["alto_min"],
    )
    total = sum(len(e["dets"]) for e in cap["cache"])
    # cuántas excluidas son de identidades A/B (las que votan) y de porteros
    voto = cap["voto"]
    de = {}
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            de[(int(f), int(k))] = voto.get(i, "?")
    tipo = (
        pd.Series([de.get(c, "sin identidad") for c in anorm]).value_counts().to_dict()
    )
    ab = [c for c in de if de[c] in ("A", "B")]
    ab_anorm = sum(1 for c in ab if c in anorm)
    corregidos = antes - despues
    nuevos = despues - antes
    return {
        "errores_antes": len(antes),
        "errores_despues": len(despues),
        "gt_casadas": [g_off["casadas"], g_on["casadas"]],
        "gt_errores": [len(g_off["errores"]), len(g_on["errores"])],
        "hoja_errores": [sorted(h_off), sorted(h_on)],
        "corregidos": sorted(map(str, corregidos)),
        "nuevos": sorted(map(str, nuevos)),
        "excluidas_pct_de_todas_las_detecciones": round(100 * len(anorm) / total, 2),
        "excluidas_pct_de_observaciones_A_B": round(
            100 * ab_anorm / max(len(ab), 1), 2
        ),
        "excluidas_por_voto_de_su_identidad": tipo,
        "filas_con_etiqueta_distinta": int((off.etiqueta != on.etiqueta).sum()),
        "criterio": {
            "corrige_>=6_de_11": len(corregidos) >= 6,
            "excluye_<=3%": ab_anorm / max(len(ab), 1) <= 0.03,
            "0_nuevos": len(nuevos) == 0,
        },
    }


# ── 2. los 10 eventos del clip 1 ─────────────────────────────────────────────────────────────

INICIO_CLIP_S = 840.0  # el clip 1 empieza en 14:00 del archivo
FPS = 29.97002997002997
EVENTOS = [
    (1, "0:04 B689 y A683 naranjas un instante", 4, 4, [689, 683]),
    (2, "0:15 cambio de id a la derecha, colores bien", 15, 15, None),
    (3, "0:21 el blanco pierde la caja", 21, 21, None),
    (4, "0:40-0:41 A683 detrás de B708", 40, 41, [683, 708]),
    (5, "0:44 la caja se vuelve naranja", 44, 44, [683, 708]),
    (6, "1:00-1:01 A683 pasa a B683", 60, 61, [683, 708]),
    (7, "1:06-1:07 A708 y B525 en una caja", 66, 67, [708, 525, 742]),
    (8, "0:00-0:33 el portero de A", -1, 33, [695, 718]),
    (9, "1:11 el árbitro desaparece", 71, 71, "arbitro"),
    (10, "1:30 el árbitro pasa a A", 90, 90, "arbitro"),
]


def _rachas_cortas(seq, frames, f0, f1, min_s=1.0):
    """Rachas de < min_s (sin contar la primera de la identidad) que tocan [f0, f1]."""
    n, i, cortas = len(seq), 0, 0
    primera = True
    while i < n:
        j = i
        while j + 1 < n and seq[j + 1] == seq[i]:
            j += 1
        fin = frames[j + 1] if j + 1 < n else frames[j] + 3
        if (
            not primera
            and (fin - frames[i]) / FPS < min_s
            and frames[j] >= f0
            and frames[i] <= f1
        ):
            cortas += 1
        primera = False
        i = j + 1
    return cortas


def eventos() -> dict:
    rc = _mod("render_clips_26oct")
    d = rc.cargar(R / "outputs/diagnostico_26oct_b")
    cap = pickle.load(open(CAPTURA, "rb"))
    frames_de = {
        i: sorted({int(f) for f, _j in obs})
        for i, obs in enumerate(cap["identidades"], 1)
    }
    res, resueltos = [], 0
    for n, texto, a, b, ids in EVENTOS:
        f0 = int((INICIO_CLIP_S + max(a, 0) - 1) * FPS)
        f1 = int((INICIO_CLIP_S + b + 1) * FPS)
        if ids == "arbitro":
            ids = sorted(
                {
                    d["ident_de"].get((f, j))
                    for f, j in d["pista"].items()
                    if f0 <= f <= f1
                }
                - {None}
            )
        elif ids is None:  # las que cambian de etiqueta en la ventana
            ids = [
                i
                for i, fs in frames_de.items()
                if len({rc.etiqueta_obs(d, i, f) for f in fs if f0 <= f <= f1}) > 1
            ]
        crudo = pintado = 0
        for i in ids:
            fs = frames_de.get(i, [])
            if not fs:
                continue
            crudo += _rachas_cortas([rc.etiqueta_obs(d, i, f) for f in fs], fs, f0, f1)
            pintado += _rachas_cortas([d["pintada"][(i, f)] for f in fs], fs, f0, f1)
        ok = crudo >= 1 and pintado == 0
        resueltos += ok
        res.append(
            {
                "evento": n,
                "que": texto,
                "identidades": ids,
                "rachas_cortas_crudo": crudo,
                "rachas_cortas_pintado": pintado,
                "deja_de_verse_como_parpadeo": bool(ok),
            }
        )
    return {"eventos": res, "resueltos": resueltos, "criterio_>=8": resueltos >= 8}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["pasadas", "medir", "eventos"])
    args = ap.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)
    res = {"pasadas": pasadas, "medir": medir, "eventos": eventos}[args.accion]()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=str)
    (SALIDA / f"{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
