#!/usr/bin/env python
"""Los instantes que hay que mirar de una parte entera, y por qué.

Encargo de Alex (28-ago-2026): *"dime dónde mirar: los instantes donde la
posesión cambia de equipo y los tramos con más fases aéreas o sin balón
detectado, para que mi revisión sea quirúrgica y no un 'a ver si veo
algo'."*

Tres listas, cada una por un motivo distinto:

  A. **Cambios de posesión.** Es donde la proximidad falla más (36,4 %
     de acierto justo tras un cambio de dueño, peor que una moneda).
  B. **Tramos sin balón detectado.** Ahí el replay pinta jugadores sin
     balón y hay que ver si se entiende o parece un fallo.
  C. **Rachas de fase aérea.** Donde el balón se pinta como recta
     atenuada entre despegue y bote: hay que ver si se lee como "no lo
     sabemos" o como una posición afirmada.

Uso:
    python scripts/donde_mirar.py
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("donde_mirar")


def mmss(t):
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_conjunto_p1.csv")
    p.add_argument("--radio", type=float, default=3.0)
    p.add_argument("--top", type=int, default=8)
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    df = pd.read_csv(args.csv)
    real = df[df.es_real == 1]
    # ⚠️ Las observaciones AÉREAS van con es_real=0 a propósito: son la
    # recta entre despegue y bote, no una posición medida. Filtrarlas por
    # `es_real` las hacía desaparecer de esta guía, que es justo donde más
    # falta hacen.
    balon = df[df.etiqueta.isin(["balon", "balon_aereo"])]
    jug = real[real.etiqueta.isin(["A", "B", "portero_A", "portero_B"])].copy()
    jug["eqb"] = jug.etiqueta.str.replace("portero_", "", regex=False)

    # ── posesión por proximidad, instante a instante ─────────────────
    porj = {t: g[["x_m", "y_m", "eqb"]].to_numpy() for t, g in jug.groupby("tiempo_s")}
    ts_j = np.array(sorted(porj))
    serie = []
    for _, b in balon.iterrows():
        k = int(np.argmin(np.abs(ts_j - b.tiempo_s)))
        if abs(ts_j[k] - b.tiempo_s) > 0.2:
            continue
        g = porj[ts_j[k]]
        d = np.hypot(g[:, 0].astype(float) - b.x_m, g[:, 1].astype(float) - b.y_m)
        i = int(np.argmin(d))
        if d[i] > args.radio:
            continue
        # El MARGEN entre equipos es lo que hace dudoso un cambio: si el
        # rival está igual de cerca, la proximidad está tirando una moneda.
        # Ordenar por la distancia a secas no sirve: casi todas caen en el
        # tope del radio y el ranking mide el tope, no la duda.
        eq = str(g[i, 2])
        otros = d[g[:, 2] != eq]
        margen = float(otros.min() - d[i]) if len(otros) else float("inf")
        serie.append(
            (
                float(b.tiempo_s),
                eq,
                float(d[i]),
                margen,
                str(b.etiqueta) == "balon_aereo",
            )
        )
    s = pd.DataFrame(
        serie, columns=["t", "equipo", "dist", "margen", "aereo"]
    ).sort_values("t")

    print(f"\nposesión asignada en {len(s)} instantes")

    # ── A. Cambios de posesión ───────────────────────────────────────
    cambios = s[s.equipo != s.equipo.shift()].iloc[1:]
    # los más "disputados": el segundo jugador estaba muy cerca
    print(f"\nA. CAMBIOS DE POSESIÓN — {len(cambios)} en total")
    print("   (es donde la proximidad falla más: 36,4 % de acierto justo tras")
    print("    un cambio de dueño, peor que una moneda)")
    print(f"\n   los {args.top} MÁS DISPUTADOS (el rival estaba casi igual de cerca:")
    print("    ahí la proximidad tira una moneda y el color decide el resultado)")
    for _, r in cambios.nsmallest(args.top, "margen").iterrows():
        print(
            f"     {mmss(r.t)}  ->  {r.equipo}   balón a {r.dist:.1f} m, "
            f"rival a solo {r.margen:+.2f} m más lejos"
            f"{'  [AÉREO]' if r.aereo else ''}"
        )

    # ── B. Tramos sin balón ──────────────────────────────────────────
    tb = balon.tiempo_s.to_numpy()
    huecos = []
    for a, b in zip(tb, tb[1:]):
        if b - a > 2.0:
            huecos.append((a, b, b - a))
    huecos.sort(key=lambda h: -h[2])
    total_hueco = sum(h[2] for h in huecos)
    print(
        f"\nB. TRAMOS SIN BALÓN DETECTADO — {len(huecos)} huecos de más de 2 s, "
        f"{total_hueco:.0f} s en total ({100*total_hueco/1200:.0f} % del partido)"
    )
    print(f"\n   los {args.top} más largos:")
    for a, b, dur in huecos[: args.top]:
        print(f"     {mmss(a)} → {mmss(b)}   ({dur:.0f} s sin balón)")

    # ── C. Rachas de fase aérea ──────────────────────────────────────
    ae = balon[balon.etiqueta == "balon_aereo"].tiempo_s.to_numpy()
    rachas = []
    if len(ae):
        ini = ae[0]
        ant = ae[0]
        for t in ae[1:]:
            if t - ant > 1.0:
                rachas.append((ini, ant, ant - ini))
                ini = t
            ant = t
        rachas.append((ini, ant, ant - ini))
    rachas.sort(key=lambda r: -r[2])
    print(f"\nC. FASES AÉREAS — {len(ae)} observaciones en {len(rachas)} rachas")
    print("   (el balón se pinta como RECTA atenuada entre despegue y bote:")
    print("    hay que ver si se lee como 'no lo sabemos')")
    print(f"\n   las {args.top} más largas:")
    for a, b, dur in rachas[: args.top]:
        print(f"     {mmss(a)} → {mmss(b)}   ({dur:.1f} s en el aire)")

    # ── y el minuto peor de todo ─────────────────────────────────────
    print("\nD. EL MINUTO CON MENOS BALÓN (el peor caso del partido)")
    balon_min = balon.groupby((balon.tiempo_s // 60).astype(int)).size()
    todos = pd.Series(0, index=range(20))
    todos.update(balon_min)
    for minuto, n in todos.nsmallest(3).items():
        print(
            f"     minuto {minuto:02d}:00 → {minuto:02d}:59   solo {n} "
            f"observaciones de balón"
        )


if __name__ == "__main__":
    main()
