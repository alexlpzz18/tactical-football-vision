#!/usr/bin/env python
"""¿Rellenar los huecos del balón MIRANDO AL FUTURO acierta más que con solo el pasado?

Alex (21-sep-2026): procesamos en diferido, así que en un hueco ya sabemos
dónde REAPARECE el balón. *"Compara «rellenar solo con lo de antes» (lo que hay
hoy) contra «rellenar sabiendo dónde reaparece». Si el acierto sube claramente,
hay margen; si no, lo cerramos."*

No hay verdad DENTRO de un hueco real (por definición no se ve el balón), así
que se mide con huecos SINTÉTICOS: en tramos donde el balón sí se detecta sin
interrupción se esconde un bloque de L muestras y se compara cada predicción con
la detección real de cada frame escondido.

⚠️ Ese banco es OPTIMISTA: los huecos reales son los difíciles (balón tapado,
lejano o fuera de encuadre). Dos correcciones:
  1. Se REPONDERA la mezcla (duración del hueco, distancia entre extremos) para
     que coincida con la de los huecos reales.
  2. Se informa aparte de los casos duros (bloque con un contacto y el balón a
     menos de 1,5 m de un jugador).

Predictores: `hold` (mantener la última posición: lo que hay hoy) y `lineal`
(recta entre el punto de antes y el de después, por TIEMPO).

Uso:
    python scripts/balon_huecos_con_futuro.py
"""

import argparse
import contextlib
import io
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.carga import (  # noqa: E402
    cargar_detecciones_limpias,
    jugadores_por_frame_de_balon,
)
from src.balon.tracking_balon import (  # noqa: E402
    ParametrosBalon,
    detectar_fases_aereas,
    seleccionar_balon_activo,
)
from src.campo_modelo import cargar_modelo  # noqa: E402

BINS_DUR = [0, 0.2, 0.4, 0.7, 1.2, 2.2, 1e9]
BINS_DIST = [-1, 1, 3, 8, 20, 1e9]
LONGITUDES = [2, 3, 5, 8, 12, 20, 30]  # muestras escondidas (~0,13-2 s)


def trayectoria_de_suelo(ruta_balon, ruta_csv, ruta_campo):
    """(frames, tiempos, posiciones, aéreo) del balón activo, como el pipeline."""
    logging.disable(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()):
        dets, tiempos, _ = cargar_detecciones_limpias(
            ruta_balon, cargar_modelo(config=ruta_campo)
        )
    jug = jugadores_por_frame_de_balon(ruta_csv, tiempos, dets)
    params = ParametrosBalon()
    activo = seleccionar_balon_activo(
        dets, {f: [(j[0], j[1]) for j in v] for f, v in jug.items()}, params
    )
    tray = [(f, np.array(d[:2]), d[5] - d[3], d[6]) for f, d in sorted(activo.items())]
    aereo = np.array(detectar_fases_aereas(tray, tiempos, params))
    f = np.array([x[0] for x in tray])
    return f, np.array([tiempos[x] for x in f]), np.array([x[1] for x in tray]), aereo


def tramos_continuos(t, aereo, max_dt=0.2):
    tramos, cur = [], []
    for i in range(len(t)):
        if aereo[i]:
            if cur:
                tramos.append(cur)
                cur = []
        elif cur and t[i] - t[cur[-1]] <= max_dt and i == cur[-1] + 1:
            cur.append(i)
        else:
            if cur:
                tramos.append(cur)
            cur = [i]
    if cur:
        tramos.append(cur)
    return tramos


def huecos_reales(f, t, p, aereo):
    paso = int(np.median(np.diff(f)))
    filas = []
    for i in range(1, len(f)):
        if f[i] - f[i - 1] > paso and not aereo[i] and not aereo[i - 1]:
            filas.append(
                {
                    "dur": t[i] - t[i - 1],
                    "D": float(np.hypot(*(p[i] - p[i - 1]))),
                    "falta": int((f[i] - f[i - 1]) // paso - 1),
                    "x": float((p[i][0] + p[i - 1][0]) / 2),
                }
            )
    return pd.DataFrame(filas)


def huecos_sinteticos(t, p, tramos):
    filas = []
    for L in LONGITUDES:
        for sg in tramos:
            for k in range(1, len(sg) - L):
                ia, ib = sg[k - 1], sg[k + L]
                dur = t[ib] - t[ia]
                D = float(np.hypot(*(p[ib] - p[ia])))
                for j in range(k, k + L):
                    ij = sg[j]
                    lineal = p[ia] + (p[ib] - p[ia]) * (t[ij] - t[ia]) / dur
                    filas.append(
                        (
                            dur,
                            D,
                            float(np.hypot(*(p[ia] - p[ij]))),
                            float(np.hypot(*(lineal - p[ij]))),
                        )
                    )
    return pd.DataFrame(filas, columns=["dur", "D", "hold", "lineal"])


def cuantil_ponderado(x, w, q):
    orden = np.argsort(x.to_numpy())
    acum = np.cumsum(w.to_numpy()[orden])
    return float(x.to_numpy()[orden][np.searchsorted(acum, q * acum[-1])])


def resumen(g, nombre):
    w = g.w
    print(
        f"{nombre:<38} frames reales {int(w.sum()):>5} | hold <2m "
        f"{np.average(g.hold < 2, weights=w):4.0%} p90 {cuantil_ponderado(g.hold, w, 0.9):5.1f}"
        f" | LINEAL <1m {np.average(g.lineal < 1, weights=w):4.0%} <2m "
        f"{np.average(g.lineal < 2, weights=w):4.0%} p90 {cuantil_ponderado(g.lineal, w, 0.9):4.1f}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--balon", default="data/tracking_benja/cache_balon_p1.pkl")
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v2.csv")
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    args = p.parse_args()

    f, t, pos, aereo = trayectoria_de_suelo(args.balon, args.csv, args.campo)
    reales = huecos_reales(f, t, pos, aereo)
    sint = huecos_sinteticos(t, pos, tramos_continuos(t, aereo))
    print(
        f"\nHuecos REALES entre dos observaciones de suelo: {len(reales)} "
        f"({int(reales.falta.sum())} frames sin balón dentro)"
    )
    print(f"Frames sintéticos evaluados: {len(sint)}")

    for X in (reales, sint):
        X["bd"] = pd.cut(X.dur, BINS_DUR)
        X["bD"] = pd.cut(X.D, BINS_DIST)
    w_real = reales.groupby(["bd", "bD"], observed=False).falta.sum()
    w_sint = sint.groupby(["bd", "bD"], observed=False).size()
    peso = (w_real / w_sint.replace(0, np.nan)).fillna(0)
    sint["w"] = [peso.get((a, b), 0.0) for a, b in zip(sint.bd, sint.bD)]
    sin_cobertura = int(w_real[w_sint == 0].sum())
    print(f"Frames reales sin equivalente sintético (excluidos): {sin_cobertura}")

    G = sint[sint.w > 0]
    print("\nACIERTO reponderado al reparto de los huecos reales:")
    resumen(G, "TODOS")
    for a, g in G.groupby("bd", observed=True):
        resumen(g, f"  duración {a}")

    reales["v_ext"] = reales.D / reales.dur
    print("\nCOBERTURA de cada regla (frames que rellenaría) y precisión esperada:")
    for nombre, dur, vmax, xmin in [
        ("dur <= 0,4 s", 0.4, None, None),
        ("dur <= 1,2 s", 1.2, None, None),
        ("dur <= 1,2 s, v_ext <= 12", 1.2, 12, None),
        ("dur <= 1,2 s, v_ext <= 12, x >= 20", 1.2, 12, 20),
    ]:
        m = reales.dur <= dur
        if vmax:
            m &= reales.v_ext <= vmax
        if xmin:
            m &= reales.x >= xmin
        s = G[G.dur <= dur]
        if vmax:
            s = s[(s.D / s.dur) <= vmax]
        print(
            f"  {nombre:<36} frames {int(reales[m].falta.sum()):>5} | "
            f"LINEAL <1m {np.average(s.lineal < 1, weights=s.w):4.0%} "
            f"<2m {np.average(s.lineal < 2, weights=s.w):4.0%}"
        )


if __name__ == "__main__":
    main()
