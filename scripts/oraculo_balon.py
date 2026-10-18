#!/usr/bin/env python
"""¿Merece la pena etiquetar más frames de balón? Un oráculo lo decide.

Pregunta de Alex (28-ago-2026): *"con el balón detectado en el 53 % de
los frames, ¿cuánto mejora la posesión si subo ese porcentaje? ¿Mi
próximo lote de etiquetado va al balón o el cuello de botella está en
otro sitio?"*

No hay GT de posición de balón, así que no cabe un oráculo perfecto. Sí
caben dos medidas que responden la pregunta entre las dos:

**1. La CURVA DE CANTIDAD (submuestreo).** Se tiran detecciones al azar
para simular tasas de detección más bajas y se mira cuánto se mueve la
posesión. Si bajar del 53 % al 30 % apenas la mueve, subir del 53 % al
90 % tampoco la va a mover: la pendiente es la misma información.

**2. El ORÁCULO DE CONTINUIDAD.** Se interpola la posición del balón en
los huecos cortos —donde el balón no puede haberse ido lejos— y se mide
cuánto cambia el reparto. Es una cota de lo que daría detectar más, bajo
el supuesto de que el balón se mueve de forma continua.

⚠️ Y la distinción que decide la respuesta: el submuestreo aleatorio mide
el efecto de la CANTIDAD. El sesgo medido —el balón se ve el 86,3 % del
tiempo cuando lo lleva A y el 71,4 % cuando lo lleva B— es un problema de
CALIDAD, de QUÉ frames faltan. Etiquetar más frames sube la cantidad; no
arregla por sí solo un sesgo de dónde falla el detector.

Uso:
    python scripts/oraculo_balon.py
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("oraculo_balon")

RADIO_M = 3.0
SEMILLAS = 12


def cargar(ruta_balon, ruta_csv, campo):
    import pickle

    from src.balon.tracking_balon import filtrar_balon_plausible
    from src.campo_modelo import cargar_modelo

    with open(ruta_balon, "rb") as f:
        datos = pickle.load(f)
    modelo = cargar_modelo(config=campo)
    dets = {e["frame_idx"]: e["dets"] for e in datos["cache"] if e["dets"]}
    dets = filtrar_balon_plausible(dets, modelo)
    tiempos = {e["frame_idx"]: e["t"] for e in datos["cache"]}
    n_frames = len(datos["cache"])

    df = pd.read_csv(ruta_csv)
    df = df[df.es_real == 1]
    df = df[df.etiqueta.isin(["A", "B", "portero_A", "portero_B"])].copy()
    df["eq"] = df.etiqueta.str.replace("portero_", "", regex=False)
    jug = {t: g[["x_m", "y_m", "eq"]].to_numpy() for t, g in df.groupby("tiempo_s")}
    return dets, tiempos, jug, n_frames


def posesion(dets, tiempos, jug, radio=RADIO_M):
    """% de posesión de A por proximidad, y cuántos instantes se asignan."""
    ts_jug = np.array(sorted(jug))
    votos = {"A": 0, "B": 0}
    for frame, ds in dets.items():
        t = tiempos.get(frame)
        if t is None:
            continue
        # El caché de jugadores va a otro `sample`: se casa por TIEMPO.
        k = int(np.argmin(np.abs(ts_jug - t)))
        if abs(ts_jug[k] - t) > 0.2:
            continue
        gente = jug[ts_jug[k]]
        bx, by = float(ds[0][0]), float(ds[0][1])
        d = np.hypot(gente[:, 0].astype(float) - bx, gente[:, 1].astype(float) - by)
        i = int(np.argmin(d))
        if d[i] > radio:
            continue
        votos[str(gente[i, 2])] += 1
    total = votos["A"] + votos["B"]
    return (100.0 * votos["A"] / total if total else float("nan")), total


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--balon", default="data/tracking_benja/cache_balon_piloto.pkl")
    p.add_argument("--csv", default="data/tracking_benja/posiciones_piloto5min_hoy.csv")
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    dets, tiempos, jug, n_frames = cargar(args.balon, args.csv, args.campo)
    tasa_base = 100.0 * len(dets) / n_frames
    base, n_base = posesion(dets, tiempos, jug)
    print(
        f"\nbalón detectado en {len(dets)} de {n_frames} frames "
        f"({tasa_base:.1f} %), tras el filtro de plausibilidad"
    )
    print(
        f"posesión de A con todo lo que hay: {base:.1f} % "
        f"({n_base} instantes asignados)\n"
    )

    # ── 1. Curva de CANTIDAD ─────────────────────────────────────────
    print("1) CURVA DE CANTIDAD: qué pasa si el detector viera MENOS")
    print(f"   {'tasa':>8} {'posesión A':>12} {'desv.':>8} {'instantes':>10}")
    claves = sorted(dets)
    puntos = []
    for frac in (1.0, 0.8, 0.6, 0.4, 0.25, 0.15):
        vals = []
        for s in range(SEMILLAS if frac < 1.0 else 1):
            rng2 = np.random.default_rng(s)
            sel = rng2.choice(len(claves), size=int(len(claves) * frac), replace=False)
            sub = {claves[i]: dets[claves[i]] for i in sel}
            v, _ = posesion(sub, tiempos, jug)
            vals.append(v)
        media, sd = float(np.mean(vals)), float(np.std(vals))
        puntos.append((frac * tasa_base, media))
        print(
            f"   {frac*tasa_base:>7.1f}% {media:>11.1f}% {sd:>8.2f} "
            f"{int(len(claves)*frac):>10}"
        )

    # La pendiente dice cuánto movería SUBIR la tasa.
    xs = np.array([x for x, _ in puntos])
    ys = np.array([y for _, y in puntos])
    pend = float(np.polyfit(xs, ys, 1)[0])
    print(f"\n   pendiente: {pend:+.3f} puntos de posesión por punto de tasa")
    print(
        f"   -> subir del {tasa_base:.0f} % al 90 % movería la posesión "
        f"{abs(pend) * (90 - tasa_base):.1f} puntos"
    )

    # ── 2. Oráculo de CONTINUIDAD ────────────────────────────────────
    print("\n2) ORÁCULO DE CONTINUIDAD: rellenando los huecos cortos")
    print(f"   {'hueco máx':>10} {'tasa':>8} {'posesión A':>12} {'cambio':>9}")
    ts_orden = sorted(tiempos)
    for hueco_max in (0.0, 0.5, 1.0, 2.0, 5.0):
        rell = dict(dets)
        if hueco_max > 0:
            vistos = sorted(dets)
            for a, b in zip(vistos, vistos[1:]):
                dt = tiempos[b] - tiempos[a]
                if 0 < dt <= hueco_max:
                    pa, pb = dets[a][0], dets[b][0]
                    for f in ts_orden:
                        if a < f < b and f not in rell:
                            w = (tiempos[f] - tiempos[a]) / dt
                            rell[f] = [
                                (
                                    pa[0] + w * (pb[0] - pa[0]),
                                    pa[1] + w * (pb[1] - pa[1]),
                                    0,
                                    0,
                                    1,
                                    1,
                                    0.5,
                                )
                            ]
        v, _ = posesion(rell, tiempos, jug)
        print(
            f"   {hueco_max:>9.1f}s {100*len(rell)/n_frames:>7.1f}% "
            f"{v:>11.1f}% {v - base:>+8.1f}"
        )


if __name__ == "__main__":
    main()
