#!/usr/bin/env python
"""La posesión sobre la PARTE ENTERA, fuera de los tres clips fáciles.

Encargo de Alex (28-ago-2026): *"es la primera vez que se mide fuera de
mis tres clips, que sabemos que eran el top-12 en visibilidad de balón.
Quiero ver cuánto cae respecto a ellos, que es la comprobación honesta
que faltaba."*

⚠️ LO QUE SE PUEDE Y LO QUE NO. Fuera de los clips **no hay GT**, así que
el ERROR no se puede medir ahí. Lo que sí se puede, y decide igual:

  1. **La curva de detección por zona**, que no necesita verdad: se
     estratifica por el centroide de los jugadores (existe en todos los
     frames) y se mide en qué franjas se ve el balón.
  2. **Cuánto MUEVE la corrección de zona** el reparto. Si lo mueve
     mucho, el sesgo también estaba ahí.
  3. **La sensibilidad**: cuánto se mueve la respuesta entre
     configuraciones razonables. Si cambiar la ventana o el radio lleva
     el resultado de 55-45 a 70-30, la métrica no es utilizable aunque
     acertara en los clips.

Uso:
    python scripts/posesion_parte_entera.py
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("posesion_p1")

FRANJAS = [0, 30, 35, 40, 62]
ETIQ = ["<30", "30-35", "35-40", ">40"]


def cargar(ruta_balon, ruta_csv, campo):
    import pickle

    from src.balon.tracking_balon import filtrar_balon_plausible
    from src.campo_modelo import cargar_modelo

    with open(ruta_balon, "rb") as f:
        datos = pickle.load(f)
    modelo = cargar_modelo(config=campo)
    dets = filtrar_balon_plausible(
        {e["frame_idx"]: e["dets"] for e in datos["cache"] if e["dets"]}, modelo
    )
    tiempos = {e["frame_idx"]: e["t"] for e in datos["cache"]}

    df = pd.read_csv(ruta_csv)
    df = df[(df.es_real == 1) & df.etiqueta.isin(["A", "B", "portero_A", "portero_B"])]
    df = df.assign(equipo_base=df.etiqueta.str.replace("portero_", "", regex=False))
    jug = {
        t: g[["x_m", "y_m", "equipo_base"]].to_numpy()
        for t, g in df.groupby("tiempo_s")
    }
    centro = df.groupby("tiempo_s").x_m.mean()
    return dets, tiempos, jug, centro, len(datos["cache"])


def asignar(dets, tiempos, jug, centro, radio, ventana=0.0):
    """[(t, equipo, franja)] de cada instante con balón y dueño."""
    ts_j = np.array(sorted(jug))
    ts_c = centro.index.to_numpy()
    fuera = []
    for frame, ds in dets.items():
        t = tiempos.get(frame)
        if t is None:
            continue
        k = int(np.argmin(np.abs(ts_j - t)))
        if abs(ts_j[k] - t) > 0.2:
            continue
        gente = jug[ts_j[k]]
        bx, by = float(ds[0][0]), float(ds[0][1])
        d = np.hypot(gente[:, 0].astype(float) - bx, gente[:, 1].astype(float) - by)
        i = int(np.argmin(d))
        if d[i] > radio:
            continue
        c = int(np.argmin(np.abs(ts_c - t)))
        fuera.append((t, str(gente[i, 2]), float(centro.iloc[c])))
    return pd.DataFrame(fuera, columns=["t", "equipo", "centroide"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--balon", default="data/tracking_benja/cache_balon_p1.pkl")
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v2.csv")
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    dets, tiempos, jug, centro, n_frames = cargar(args.balon, args.csv, args.campo)
    print(
        f"\nparte entera: {n_frames} frames, balón en {len(dets)} "
        f"({100*len(dets)/n_frames:.1f} %) tras el filtro de plausibilidad"
    )

    # ── 1. La curva de detección por zona, SIN GT ────────────────────
    ts_c = centro.index.to_numpy()
    visto = []
    for frame, t in sorted(tiempos.items()):
        c = int(np.argmin(np.abs(ts_c - t)))
        if abs(ts_c[c] - t) > 0.2:
            continue
        visto.append((float(centro.iloc[c]), frame in dets))
    vf = pd.DataFrame(visto, columns=["centroide", "visto"])
    vf["franja"] = pd.cut(vf.centroide, bins=FRANJAS, labels=ETIQ)
    tasa = vf.groupby("franja", observed=True).visto.mean()
    print("\n1) DETECCIÓN POR ZONA (sin GT: el centroide existe en todos los frames)")
    print(f"   {'franja':>8} {'balón visto':>13} {'frames':>9}")
    for fr, g in vf.groupby("franja", observed=True):
        print(f"   {str(fr):>8} {100*g.visto.mean():>12.1f}% {len(g):>9}")
    print("   (medido dentro de los clips daba de 88,0 % a 57,8 %)")

    # ── 2. El reparto, crudo y corregido ─────────────────────────────
    a = asignar(dets, tiempos, jug, centro, radio=3.0)
    a["franja"] = pd.cut(a.centroide, bins=FRANJAS, labels=ETIQ)
    crudo = 100 * (a.equipo == "A").mean()
    peso = np.array([1.0 / max(tasa.get(f, np.nan), 1e-6) for f in a.franja])
    ok = ~np.isnan(peso)
    es_a = (a.equipo == "A").to_numpy()
    corr = 100 * peso[ok & es_a].sum() / peso[ok].sum()
    print("\n2) EL REPARTO")
    print(f"   instantes con dueño: {len(a)} ({100*len(a)/n_frames:.1f} % del partido)")
    print(f"   posesión de A, CRUDA           : {crudo:.1f} %")
    print(
        f"   posesión de A, CORREGIDA por zona: {corr:.1f} %   "
        f"(la corrección mueve {corr-crudo:+.1f} pts)"
    )

    # ── 3. Sensibilidad: ¿cuánto se mueve entre configuraciones? ─────
    print("\n3) SENSIBILIDAD (sin GT, y es lo que decide si va con número)")
    print(f"   {'radio':>7} {'crudo':>9} {'corregido':>11} {'instantes':>11}")
    vals = []
    for radio in (1.0, 2.0, 3.0, 5.0, 99.0):
        b = asignar(dets, tiempos, jug, centro, radio=radio)
        if not len(b):
            continue
        b["franja"] = pd.cut(b.centroide, bins=FRANJAS, labels=ETIQ)
        c0 = 100 * (b.equipo == "A").mean()
        w = np.array([1.0 / max(tasa.get(f, np.nan), 1e-6) for f in b.franja])
        m = ~np.isnan(w)
        e = (b.equipo == "A").to_numpy()
        c1 = 100 * w[m & e].sum() / w[m].sum()
        vals.append(c1)
        print(f"   {radio:>7.1f} {c0:>8.1f}% {c1:>10.1f}% {len(b):>11}")
    if vals:
        print(
            f"\n   el corregido se mueve {max(vals)-min(vals):.1f} puntos entre "
            f"radios de 1 m a sin límite"
        )


if __name__ == "__main__":
    main()
