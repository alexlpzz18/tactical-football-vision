#!/usr/bin/env python
"""Auditoría de las hojas: ¿la caja dibujada es la detección de la fila? Criterios en
`docs/auditoria_hojas.md`. SOLO mide.

Uso:
    python scripts/auditar_hojas.py
"""

import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/auditoria_hojas"
HOJA = R / "outputs/hoja_equipos"
FPS = 29.97002997002997
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
CRUDO_P1 = R / "data/tracking_benja/cache_detecciones_benja_p1.pkl"
VITERBI_CSV = R / "outputs/diagnostico_23oct_c/viterbi_benja_v1_sustituye.csv"
MAIN_CSV = R / "outputs/diagnostico_26oct_b/posiciones_main.csv"
LIMITE = 0.02  # el criterio de Alex: discrepancias en < 2 % de las filas
EXACTA_M, OTRA_A_M = 0.05, 2.0  # el proxy del mini-GT


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def exacta(nombre: str, clave: pd.DataFrame, cap: dict, crudo: dict) -> dict:
    """Compara la caja dibujada (`k` de la clave) con la detección de la identidad de la fila."""
    hoja = _mod("hoja_otro_v3")
    filt = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    filas = clave.rename(columns={"id": "id_jugador"})
    de_la_fila = hoja.deteccion_de_la_fila(filas, cap["identidades"], filt, crudo)
    dueno = {}
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            dueno[(int(f), int(k))] = i
    detalle = []
    for r, k_fila in zip(filas.itertuples(), de_la_fila):
        f = int(r.frame)
        dib = [float(v) for v in crudo[f][int(r.k)][2:6]]
        if k_fila is None:
            detalle.append(
                {"imagen": r.imagen, "frame": f, "tipo": "fila sin detección"}
            )
            continue
        fila = [float(v) for v in crudo[f][k_fila][2:6]]
        v = iou(dib, fila)
        if v < 0.5:
            # ¿de quién es la caja que se dibujó?
            kf = [
                j
                for j, d in enumerate(filt[f])
                if iou(dib, [float(x) for x in d[2:6]]) > 0.99
            ]
            detalle.append(
                {
                    "imagen": r.imagen,
                    "frame": f,
                    "relojes": _relojes(f),
                    "tipo": "caja de otra identidad",
                    "id_fila": int(r.id_jugador),
                    "id_de_la_caja_dibujada": dueno.get((f, kf[0])) if kf else None,
                    "iou": round(v, 3),
                }
            )
    n = len(filas)
    return {
        "hoja": nombre,
        "filas": n,
        "discrepancias": len(detalle),
        "pct": round(100 * len(detalle) / max(n, 1), 1),
        "valen_las_conclusiones_(<2%)": len(detalle) / max(n, 1) < LIMITE,
        "a_remarcar": detalle,
    }


def _relojes(f: int) -> str:
    t = f / FPS
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int((t + 93) // 60)}:{(t + 93) % 60:04.1f} repr"


def arbitro_viterbi(crudo: dict, cap: dict) -> dict:
    """La caja es la de la pista por construcción; se comprueba que la igualdad de caja es exacta
    (existe una detección filtrada idéntica) y, como cruce, contra la pista de `main`.
    """
    clave = pd.read_csv(HOJA / "clave_arbitro_viterbi.csv")
    filt = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    no_exactas, distinta_de_main, sin_pista_main = [], 0, 0
    for r in clave.itertuples():
        f = int(r.frame)
        dib = np.asarray(crudo[f][int(r.k)][2:6], float)
        d = min(np.abs(np.asarray(x[2:6], float) - dib).sum() for x in filt[f])
        if d > 1e-6:
            no_exactas.append(r.imagen)
        j = cap["pista"].get(f)
        if j is None:
            sin_pista_main += 1
        elif iou(list(dib), [float(v) for v in filt[f][j][2:6]]) < 0.5:
            distinta_de_main += 1
    return {
        "hoja": "arbitro_viterbi",
        "filas": len(clave),
        "discrepancias": len(no_exactas),
        "pct": round(100 * len(no_exactas) / len(clave), 1),
        "valen_las_conclusiones_(<2%)": len(no_exactas) / len(clave) < LIMITE,
        "a_remarcar": no_exactas,
        "informativo_pista_de_main_distinta": distinta_de_main,
        "informativo_frames_sin_pista_en_main": sin_pista_main,
    }


def proxy_dudosa(x: float, y: float, dets) -> bool:
    """Dudosa: la más cercana NO es la misma proyección y hay otra detección a ≤ 2 m."""
    d = np.sort([np.hypot(det[0] - x, det[1] - y) for det in dets])
    return bool(d[0] > EXACTA_M and len(d) > 1 and d[1] <= OTRA_A_M)


def control_del_proxy(crudo: dict, equipo_por_obs: dict) -> dict:
    """El proxy sobre `equipo_por_obs_20min`, donde la verdad se conoce (las 11 discrepancias)."""
    clave = pd.read_csv(HOJA / "clave_equipo_por_obs_20min.csv")
    pos = pd.read_csv(MAIN_CSV).set_index(["frame", "id_jugador"])
    malas = {d["imagen"] for d in equipo_por_obs["a_remarcar"]}
    dudosas = set()
    for r in clave.itertuples():
        p = pos.loc[(int(r.frame), int(r.id))]
        if proxy_dudosa(float(p.x_m), float(p.y_m), crudo[int(r.frame)]):
            dudosas.add(r.imagen)
    return {
        "discrepancias_conocidas": len(malas),
        "marcadas_dudosas": len(dudosas),
        "conocidas_que_marca": len(malas & dudosas),
        "pasa_(marca_las_11)": malas <= dudosas,
    }


def mini_gt() -> dict:
    """El mini-GT de equipos de agosto, con las MISMAS muestras que generó la herramienta."""
    import yaml

    from src.tracking.cache_io import cargar_cache

    eg = _mod("etiquetar_equipos_gt")
    cfg = yaml.safe_load(open(R / "configs/processor_benja.yaml"))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    df = pd.read_csv(R / "data/tracking_benja/posiciones_benja.csv")
    ids = eg.construir_identidades(df, dets, 8, 1)
    gt = pd.read_csv(R / "data/tracking_benja/gt_equipos_benja.csv")
    pos = (
        df[df.es_real == 1].set_index(["frame", "id_jugador"])
        if "es_real" in df
        else None
    )
    casadas, dudosas, sin_casar = 0, [], 0
    for r in gt.itertuples():
        ident = ids.get(int(r.id_jugador))
        cand = [
            m
            for m in (ident or {}).get("muestras", [])
            if abs(m["frame"] / FPS - r.t_s) < 0.06
        ]
        if not cand:
            sin_casar += 1
            continue
        casadas += 1
        m = cand[0]
        p = pos.loc[(m["frame"], int(r.id_jugador))]
        if proxy_dudosa(float(p.x_m), float(p.y_m), dets[m["frame"]]):
            dudosas.append(
                {"id": int(r.id_jugador), "t_s": float(r.t_s), "frame": m["frame"]}
            )
    return {
        "hoja": "mini-GT de equipos (agosto)",
        "filas": len(gt),
        "muestras_reconstruidas_casadas": casadas,
        "sin_casar": sin_casar,
        "dudosas": len(dudosas),
        "pct_dudosas": round(100 * len(dudosas) / max(casadas, 1), 1),
        "detalle": dudosas,
    }


def oraculo_corregido() -> dict:
    """El oráculo de rachas del 28-oct (e) con la tasa CORREGIDA (1,7 % en cruce y fuera), en el
    instante (0,5 s) y en ventanas de 1 s."""
    d28e = _mod("diag28e")
    d28e.P_CRUCE = d28e.P_FUERA = 0.017
    d28e.VENTANAS_FRAMES = [1, 2]
    return d28e.rachas()


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    cap = pickle.load(open(CAPTURA, "rb"))
    crudo = {
        e["frame_idx"]: e["dets"] for e in pickle.load(open(CRUDO_P1, "rb"))["cache"]
    }
    # el tracking de la pasada del viterbi es el de la captura: mismas posiciones fila a fila
    a, b = pd.read_csv(VITERBI_CSV), pd.read_csv(MAIN_CSV)
    m = a.merge(b, on=["frame", "id_jugador"], suffixes=("_v", "_m"))
    mismas = bool(
        len(m) == len(a) == len(b)
        and (m.x_m_v == m.x_m_m).all()
        and (m.y_m_v == m.y_m_m).all()
    )
    res = {"tracking_viterbi_igual_a_captura": mismas}
    epo = exacta(
        "equipo_por_obs_20min",
        pd.read_csv(HOJA / "clave_equipo_por_obs_20min.csv"),
        cap,
        crudo,
    )
    res["equipo_por_obs_20min"] = epo
    if mismas:
        res["viterbi_a_otro"] = exacta(
            "viterbi_a_otro", pd.read_csv(HOJA / "clave_viterbi_a_otro.csv"), cap, crudo
        )
    res["arbitro_viterbi"] = arbitro_viterbi(crudo, cap)
    res["control_del_proxy"] = control_del_proxy(crudo, epo)
    res["mini_gt"] = mini_gt()
    res["oraculo_1_7"] = oraculo_corregido()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=str)
    (SALIDA / "auditoria.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
