#!/usr/bin/env python
"""Mide la calibración AUTOMÁTICA del campo contra la manual (benjamín). SOLO MEDICIÓN.

Plan: docs/plan_calibracion_automatica.md. El CRITERIO de abajo se commiteó ANTES de
implementar el método y de ver ningún número.

Uso:
    python scripts/medir_calibracion_automatica.py
"""

# ══════════════════════════ CRITERIO (fijado ANTES de medir) ══════════════════════════
CRITERIO = {
    # a) 19 clics: mediana px con H auto ≤ factor × mediana px con H manual
    "a_factor_vs_manual": 1.5,
    # b) pies del GT: mediana |auto − manual| en metros
    "b_pies_m_max": 1.0,
    # c) dispersión entre frames (px) ≤ error de (a) con la H auto; y aceptados ≥ esto
    "c_frames": 20,
    "c_aceptados_min": 16,
    # confianza: fracción de puntos visibles del modelo a ≤ tol px de una línea
    "s_tol_px": 4.0,
    "s_min": 0.5,
    # d) controles: 10 máscaras aleatorias + la real volteada, TODOS rechazados (S < s_min)
    "d_aleatorias": 10,
}
# ═══════════════════════════════════════════════════════════════════════════════════════


def veredicto(r: dict, crit: dict = CRITERIO) -> dict:
    """r: {'a_auto_px', 'a_manual_px', 's_frame', 'b_pies_m', 'c_dispersion_px',
    'c_aceptados', 'd_scores': [...]}. Devuelve {punto: bool, 'viable': bool}."""
    v = {
        "a_reproyeccion": r["s_frame"] >= crit["s_min"]
        and r["a_auto_px"] <= crit["a_factor_vs_manual"] * r["a_manual_px"],
        "b_pies": r["b_pies_m"] <= crit["b_pies_m_max"],
        "c_dispersion": r["c_dispersion_px"] <= r["a_auto_px"],
        "c_aceptados": r["c_aceptados"] >= crit["c_aceptados_min"],
        "d_control": bool(r["d_scores"])
        and all(s < crit["s_min"] for s in r["d_scores"]),
    }
    v["viable"] = all(v.values())
    return v


# ──────────────────────────────────── medición ────────────────────────────────────
import json  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.evaluation.gt_parser import parsear_cvat, proyectar_punto  # noqa: E402
from src.homography import auto_calibracion as ac  # noqa: E402
from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

LARGO, ANCHO = 62.0, 40.0  # el modelo de los clics (configs/campo_benja.yaml)
VIDEO = R / "data/raw/benja_gredos_p1_20min.mp4"
FRAME_CLICS = R / "data/calibracion_benja/frame.png"
CLICS = R / "data/calibracion_benja/puntos_marcados_benja.json"
H_MANUAL = R / "data/calibracion_benja/homografia_benja.npy"  # píxel → metros
GT = R / "data/annotations/gt_benja/annotations.xml"


def error_clics(H_m2px: np.ndarray, clics: list) -> np.ndarray:
    """Distancia (px) entre cada clic y la proyección de su punto del campo."""
    m = np.array([c["metros"] for c in clics], float)
    px, _ = ac.proyectar(H_m2px, m)
    return np.hypot(*(px - np.array([c["pixel"] for c in clics], float)).T)


def frames_repartidos(n: int) -> dict:
    """n frames repartidos por los 20 min, leídos en orden con posicionar_en_frame()."""
    cap = cv2.VideoCapture(str(VIDEO))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    objetivos = [int((k + 0.5) * total / n) for k in range(n)]
    salida = {}
    for f in objetivos:
        posicionar_en_frame(cap, f)
        ok, img = cap.read()
        if ok:
            salida[f] = img
    cap.release()
    return salida


def mascara_aleatoria(n_pix: int, forma, campo, rng) -> np.ndarray:
    """Segmentos rectos al azar dentro del césped, hasta igualar los píxeles de línea."""
    m = np.zeros(forma, np.uint8)
    ys, xs = np.nonzero(campo)
    while (m > 0).sum() < n_pix:
        i = rng.integers(len(xs))
        ang, largo = rng.uniform(0, np.pi), rng.uniform(60, 600)
        x2, y2 = xs[i] + largo * np.cos(ang), ys[i] + largo * np.sin(ang)
        cv2.line(m, (int(xs[i]), int(ys[i])), (int(x2), int(y2)), 255, 4)
    return m & campo


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--busqueda", default="amplia", choices=["estrecha", "amplia"])
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    print(f"búsqueda: {args.busqueda} (estrecha = intento 1, amplia = intento 2)")
    clics = json.load(open(CLICS))
    Hm_px2m = np.load(H_MANUAL)
    Hm = np.linalg.inv(Hm_px2m)
    Hm /= Hm[2, 2]
    r = {}
    t0 = time.time()

    # (a) frame de los clics
    img = cv2.imread(str(FRAME_CLICS))
    im = ac.preparar(img)
    res = ac.calibrar(im, LARGO, ANCHO, busqueda=args.busqueda)
    e_auto, e_man = error_clics(res.H_m2px, clics), error_clics(Hm, clics)
    r.update(
        a_auto_px=float(np.median(e_auto)),
        a_manual_px=float(np.median(e_man)),
        s_frame=res.S,
    )
    print(
        f"(a) S={res.S:.3f} · mediana px auto {r['a_auto_px']:.1f} vs manual "
        f"{r['a_manual_px']:.1f} ({time.time() - t0:.0f} s)",
        flush=True,
    )
    for c, ea, em in zip(clics, e_auto, e_man):
        print(f"    {c['nombre']:<24} auto {ea:8.1f} px · manual {em:6.1f} px")

    # (b) pies del GT: misma caja, las dos H
    H_auto_px2m = np.linalg.inv(res.H_m2px)
    d = []
    for tr in parsear_cvat(GT):
        for caja in tr.cajas:
            pa = proyectar_punto(*caja.pie, H_auto_px2m)
            pm = proyectar_punto(*caja.pie, Hm_px2m)
            d.append(float(np.hypot(*(pa - pm))))
    r["b_pies_m"] = float(np.median(d))
    print(
        f"(b) pies del GT: mediana |auto − manual| {r['b_pies_m']:.2f} m "
        f"(p90 {np.percentile(d, 90):.2f}, n={len(d)})",
        flush=True,
    )

    # (c) 20 frames repartidos
    frames = frames_repartidos(CRITERIO["c_frames"])
    proy, aceptados = [], 0
    m19 = np.array([c["metros"] for c in clics], float)
    for f, im_f in frames.items():
        rf = ac.calibrar(ac.preparar(im_f), LARGO, ANCHO, busqueda=args.busqueda)
        ok = rf.S >= CRITERIO["s_min"]
        aceptados += ok
        e = np.median(error_clics(rf.H_m2px, clics))
        print(
            f"    frame {f:>6} S={rf.S:.3f} {'acepta' if ok else 'RECHAZA'} · error clics "
            f"{e:.1f} px",
            flush=True,
        )
        if ok:
            proy.append(ac.proyectar(rf.H_m2px, m19)[0])
    if proy:
        P = np.array(proy)  # (frames, 19, 2)
        disp = np.median(np.hypot(*(P - np.median(P, 0)).transpose(2, 0, 1)), 0)
        r["c_dispersion_px"] = float(np.median(disp))
    else:
        r["c_dispersion_px"] = float("inf")
    r["c_aceptados"] = int(aceptados)
    print(
        f"(c) aceptados {aceptados}/{len(frames)} · dispersión {r['c_dispersion_px']:.1f} px",
        flush=True,
    )

    # (d) controles: máscaras aleatorias y la real volteada
    campo = ac.mascara_campo(img)
    lineas = ac.mascara_lineas(img, campo)
    rng = np.random.default_rng(20261003)
    scores = []
    for k in range(CRITERIO["d_aleatorias"]):
        m = mascara_aleatoria(int((lineas > 0).sum()), lineas.shape, campo, rng)
        im_c = ac.preparar_desde_lineas(m, campo)
        scores.append(ac.calibrar(im_c, LARGO, ANCHO, busqueda=args.busqueda).S)
    im_v = ac.preparar_desde_lineas(lineas[::-1].copy(), campo[::-1].copy())
    volteada = ac.calibrar(im_v, LARGO, ANCHO, busqueda=args.busqueda).S
    scores.append(volteada)
    r["d_scores"] = [float(s) for s in scores]
    print(
        f"(d) S de los controles: {[round(s, 2) for s in scores]} (el último, la volteada)"
    )

    v = veredicto(r)
    print(f"\nVEREDICTO: {v}  ({time.time() - t0:.0f} s)")
    salida = R / "outputs/calibracion_automatica"
    salida.mkdir(parents=True, exist_ok=True)
    json.dump(
        {"criterio": CRITERIO, "resultados": r, "veredicto": v},
        open(salida / f"resultados_{args.busqueda}.json", "w"),
        indent=1,
    )


if __name__ == "__main__":
    main()
