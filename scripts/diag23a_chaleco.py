#!/usr/bin/env python
"""Diagnóstico 23-oct (a), bloque 2: ¿se ve el chaleco del árbitro POR FILA, en píxeles?

Criterio en `docs/diagnostico_23oct_a.md`. Por cada fila real, el torso de su caja (filas
0,12-0,45 y columnas 0,15-0,85, la franja de la feature) decodificado con el ffmpeg CLI y SIN
la máscara anti-césped. Puntuación = fracción de sus píxeles en la banda del chaleco.

En local solo el benjamín (el vídeo de Villaviciosa no está). Para Villaviciosa, en Colab:
    !python scripts/diag23a_chaleco.py --pata villa --salida outputs/chaleco_villa

Uso:
    python scripts/diag23a_chaleco.py --pata benja --salida outputs/diagnostico_23oct_a
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
TORSO_FILAS, TORSO_COLS = (0.12, 0.45), (0.15, 0.85)
MAX_FP = 0.005
PATAS = {
    "benja": dict(
        config=R / "configs/processor_benja_parte_entera.yaml",
        csv=R / "outputs/diagnostico_22oct_d/posiciones_hoy.csv",
        largo=62.0,
        ancho=40.0,
        mitad=10185,  # la ventana del GT es 9750-10635
    ),
    "villa": dict(
        config=R / "configs/processor.yaml",
        csv=R / "outputs/diagnostico_22oct/villa/posiciones.csv",
        largo=100.0,
        ancho=64.0,
        mitad=8250,  # la ventana del GT es 7500-8985 (60 s a 25 fps)
    ),
}


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def torso_hsv(img, caja) -> np.ndarray:
    """Píxeles HSV (N × 3) del torso de la caja, SIN máscara."""
    import cv2

    x1, y1, x2, y2 = caja
    h, w = y2 - y1, x2 - x1
    ya, yb = int(y1 + TORSO_FILAS[0] * h), int(y1 + TORSO_FILAS[1] * h)
    xa, xb = int(x1 + TORSO_COLS[0] * w), int(x1 + TORSO_COLS[1] * w)
    ya, xa = max(ya, 0), max(xa, 0)
    rec = img[slice(ya, max(yb, ya + 1)), slice(xa, max(xb, xa + 1))]
    if rec.size == 0:
        return np.zeros((0, 3))
    return cv2.cvtColor(rec, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)


def en_banda(px, banda) -> np.ndarray:
    h0, h1, s0, v0 = banda
    return (px[:, 0] >= h0) & (px[:, 0] <= h1) & (px[:, 1] >= s0) & (px[:, 2] >= v0)


def puntuaciones(px, banda) -> dict:
    """Fracción en la banda; con la banda desplazada +30 en H; y tras la máscara anti-césped."""
    if not len(px):
        return {"banda": 0.0, "desplazada": 0.0, "con_mascara": 0.0}
    h0, h1, s0, v0 = banda
    cesped = (px[:, 0] >= 35) & (px[:, 0] <= 85) & (px[:, 1] >= 40) & (px[:, 2] >= 40)
    queda = px[~cesped]
    return {
        "banda": float(en_banda(px, banda).mean()),
        "desplazada": float(en_banda(px, (h0 + 30, h1 + 30, s0, v0)).mean()),
        "con_mascara": float(en_banda(queda, banda).mean()) if len(queda) else 0.0,
    }


def auc(pos, neg) -> float:
    """AUC = P(puntuación de un árbitro > la de un jugador), con empates a la mitad."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    if not len(pos) or not len(neg):
        return float("nan")
    mayor = (pos[:, None] > neg[None, :]).mean()
    igual = (pos[:, None] == neg[None, :]).mean()
    return float(mayor + 0.5 * igual)


def elegir_tau(pos, neg) -> float:
    """El umbral de MAYOR recall con ≤ 0,5 % de falsos positivos (sobre la primera mitad)."""
    cands = sorted(set(np.round(np.concatenate([pos, neg]), 4)) | {1.0001})
    for t in cands:  # de menor a mayor: el primero que cumple da el mayor recall
        if np.mean(np.asarray(neg) >= t) <= MAX_FP:
            return float(t)
    return 1.0001


def leer(video, frames, cfg):
    """Frames con ffmpeg CLI y la corrección de distorsión del modo `full`."""
    from src.tracking_data.processor import _build_camera_matrix, _corregir_distorsion
    from src.utils.video_ffmpeg import leer_frames_ffmpeg, tamano_video

    w, h = tamano_video(video)
    K = _build_camera_matrix(w, h)
    dist = np.array(
        [cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], dtype=np.float64
    )
    for f, img in leer_frames_ffmpeg(video, frames):
        yield f, _corregir_distorsion(img, K, dist)


def main() -> None:
    import pandas as pd
    import yaml
    from scipy.optimize import linear_sum_assignment

    from src.tracking.cache_io import cargar_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pata", choices=list(PATAS), required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--sin-partido", action="store_true", help="solo la ventana del GT")
    args = ap.parse_args()
    p = PATAS[args.pata]
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(p["config"]))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    col, inv = _mod("diag22g_color"), _mod("diag22e_invariantes")
    gt = col.gt_de(args.pata)
    filas = pd.read_csv(p["csv"])
    fk = inv.con_caja(filas, dets)  # filas reales con su detección cruda k
    L, W = p["largo"], p["ancho"]

    # ── verdad por fila en la ventana del GT ──
    verdad = {}  # (frame, k) -> "arbitro" | "jugador"
    for f, obs in gt.items():
        g = fk[fk.frame == f]
        if not len(g):
            continue
        D = np.array([dets[f][k][:2] for k in g.k])
        jug = [o for o in obs if o.label != "referee"]
        P = np.array([o.pos for o in jug])
        coste = np.hypot(D[None, :, 0] - P[:, None, 0], D[None, :, 1] - P[:, None, 1])
        for i, j in zip(*linear_sum_assignment(np.where(coste > 1.0, 1e6, coste))):
            if coste[i, j] <= 1.0:
                verdad[(f, int(g.k.iloc[j]))] = "jugador"
        if args.pata == "villa":
            arb = [o for o in obs if o.label == "referee"]
            for o in arb:
                d = np.hypot(D[:, 0] - o.pos[0], D[:, 1] - o.pos[1])
                j = int(np.argmin(d))
                if d[j] <= 2.0:
                    verdad[(f, int(g.k.iloc[j]))] = "arbitro"
        else:
            # benjamín: el GT no anota al árbitro → ELIMINACIÓN (el único no anotado en el campo)
            todos = np.array([o.pos for o in obs])
            for j, (x, y) in enumerate(D):
                lejos = np.min(np.hypot(todos[:, 0] - x, todos[:, 1] - y)) > 3.0
                dentro = 2.0 <= x <= L - 2.0 and 2.0 <= y <= W - 2.0
                if lejos and dentro:
                    verdad[(f, int(g.k.iloc[j]))] = "arbitro"

    # marcas de Alex (solo benjamín): cajas «arbitro» de la hoja de revisión
    marcas = {}
    if args.pata == "benja":
        hoja = R / "outputs/hoja_equipos"
        rev = pd.read_csv(hoja / "revision.csv")
        cajas = pd.read_csv(hoja / "cajas.csv")
        a = rev[rev.equipo_correcto == "arbitro"].merge(
            cajas, on=["ventana", "imagen", "caja"]
        )
        for r in a.itertuples():
            B = np.array([d[2:6] for d in dets[int(r.frame)]], float)
            k = int(np.argmin(np.abs(B - [r.x1, r.y1, r.x2, r.y2]).sum(axis=1)))
            marcas[(int(r.frame), k)] = "arbitro_marcado_por_alex"

    claves = sorted(set(verdad) | set(marcas))
    px_de = {}
    for f, img in leer(R / cfg["rutas"]["video"], {f for f, _k in claves}, cfg):
        for ff, k in claves:
            if ff == f:
                px_de[(f, k)] = torso_hsv(img, [int(round(v)) for v in dets[f][k][2:6]])

    # ── la banda, fijada en la PRIMERA mitad sobre las filas «árbitro» ──
    arb1 = [
        px_de[c] for c, v in verdad.items() if v == "arbitro" and c[0] <= p["mitad"]
    ]
    cand = np.vstack([x[(x[:, 1] >= 100) & (x[:, 2] >= 150)] for x in arb1 if len(x)])
    banda = (
        float(np.percentile(cand[:, 0], 5)),
        float(np.percentile(cand[:, 0], 95)),
        float(np.percentile(cand[:, 1], 5)),
        float(np.percentile(cand[:, 2], 5)),
    )
    sc = {c: puntuaciones(px_de[c], banda) for c in claves}

    def separa(tipo, mitad):
        pos = [sc[c][tipo] for c, v in verdad.items() if v == "arbitro" and mitad(c[0])]
        neg = [sc[c][tipo] for c, v in verdad.items() if v == "jugador" and mitad(c[0])]
        return pos, neg

    primera = lambda f: f <= p["mitad"]  # noqa: E731
    segunda = lambda f: f > p["mitad"]  # noqa: E731
    toda = lambda f: True  # noqa: E731
    tau = elegir_tau(*separa("banda", primera))
    res = {
        "pata": args.pata,
        "banda_medida_H_S_V": [round(x, 1) for x in banda],
        "banda_de_partida": [40, 52, 150, 235],
        "pixeles_candidatos_del_arbitro": int(len(cand)),
        "tau": tau,
        "filas_verdad": {
            "arbitro": sum(v == "arbitro" for v in verdad.values()),
            "jugador": sum(v == "jugador" for v in verdad.values()),
        },
    }
    for nombre, mitad in (("segunda_mitad", segunda), ("ventana_entera", toda)):
        out = {}
        for tipo in ("banda", "desplazada", "con_mascara"):
            pos, neg = separa(tipo, mitad)
            out[tipo] = {
                "AUC": round(auc(pos, neg), 3),
                "recall_arbitro": (
                    round(float(np.mean(np.asarray(pos) >= tau)), 3) if pos else None
                ),
                "falsos_positivos_jugador": (
                    round(float(np.mean(np.asarray(neg) >= tau)), 4) if neg else None
                ),
                "n_arbitro_jugador": [len(pos), len(neg)],
            }
        res[nombre] = out
    seg = res["segunda_mitad"]["banda"]
    res["criterio"] = {
        "FP_<=0,5%": seg["falsos_positivos_jugador"] is not None
        and seg["falsos_positivos_jugador"] <= MAX_FP,
        "recall_>=80%": seg["recall_arbitro"] is not None
        and seg["recall_arbitro"] >= 0.80,
        "control_desplazada_no_separa": abs(
            res["segunda_mitad"]["desplazada"]["AUC"] - 0.5
        )
        < abs(seg["AUC"] - 0.5),
        "control_mascara_separa_peor": res["segunda_mitad"]["con_mascara"]["AUC"]
        < seg["AUC"],
    }
    if marcas:
        v = [sc[c]["banda"] >= tau for c in marcas]
        res["marcas_de_alex"] = {"cajas": len(v), "marcadas_por_la_prueba": int(sum(v))}

    # ── partido entero, sin GT ──
    if not args.sin_partido:
        dentro = fk[fk.x_m.between(0, L) & fk.y_m.between(0, W)]
        por_frame = {f: g for f, g in dentro.groupby("frame")}
        marcada = {}
        for f, img in leer(R / cfg["rutas"]["video"], por_frame, cfg):
            for idx, k in zip(por_frame[f].index, por_frame[f].k):
                px = torso_hsv(img, [int(round(v)) for v in dets[f][int(k)][2:6]])
                marcada[idx] = len(px) > 0 and float(en_banda(px, banda).mean()) >= tau
        dentro = dentro.assign(marcada=pd.Series(marcada))
        n = dentro.groupby("frame").marcada.sum()
        maj = (
            filas[filas.es_real == 1]
            .groupby("id_jugador")
            .etiqueta.agg(
                lambda s: s.map(lambda e: str(e).replace("portero_", "")).mode().iloc[0]
            )
        )
        m = dentro[dentro.marcada]
        de_equipo = m.id_jugador.map(maj).isin(["A", "B"])
        res["partido"] = {
            "frames": int(len(n)),
            "pct_frames_con_2_o_mas_marcadas": round(100 * float((n >= 2).mean()), 2),
            "pct_frames_con_1": round(100 * float((n == 1).mean()), 2),
            "filas_marcadas": int(len(m)),
            "en_identidades_que_hoy_son_de_equipo": int(de_equipo.sum()),
            "con_etiqueta_A_B_hoy": int(
                m.etiqueta.map(lambda e: str(e)).isin(["A", "B"]).sum()
            ),
        }
        res["criterio"]["partido_>=2_marcadas_<=5%"] = (
            res["partido"]["pct_frames_con_2_o_mas_marcadas"] <= 5.0
        )
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / f"bloque2_{args.pata}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
