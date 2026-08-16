#!/usr/bin/env python
"""Elige tramos de JUEGO CONTINUO para etiquetar a mano.

Corrige un fallo de método que costó medio clip (16-ago-2026): la primera
versión puntuaba "balón parado" por la fracción de muestras con velocidad
casi nula, y con eso **un tramo en el que el balón SALE DEL PLANO parecía
juego continuo perfecto** — no hay observaciones que delaten el parón,
así que la ventana salía inmaculada. El clip elegido tenía 13 de sus 30
segundos con el balón fuera de cámara.

La señal que faltaba es la contraria: la fracción de tiempo **SIN
detección**. Un tramo bueno tiene el balón visible casi siempre; uno con
el balón fuera del encuadre, no.

Uso:
    python scripts/elegir_clip.py --csv data/tracking_benja/posiciones_conjunto.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def puntuar(balon, ini, dur, muestras_esperadas):
    """Puntuación de 'juego continuo' de una ventana, y sus componentes."""
    v = balon[(balon.tiempo_s >= ini) & (balon.tiempo_s < ini + dur)]
    suelo = v[v.etiqueta == "balon"]
    if len(suelo) < 20:
        return None
    # 1. SIN DETECCIÓN: la señal que faltaba. Si el balón no está en el
    #    plano no hay observaciones, y su ausencia era invisible antes.
    sin_deteccion = max(0.0, 1 - len(v) / muestras_esperadas)
    # 2. Fase aérea: la posición no es fiable.
    aereo = (v.etiqueta == "balon_aereo").mean()
    # 3. Balón quieto: saques, faltas, celebraciones.
    d = (np.hypot(suelo.x_m.diff(), suelo.y_m.diff()) / suelo.tiempo_s.diff()).dropna()
    quieto = float((d < 0.5).mean()) if len(d) else 1.0
    return {
        "ini": ini,
        "sin_deteccion": sin_deteccion,
        "aereo": float(aereo),
        "quieto": quieto,
        "v_mediana": float(d.median()) if len(d) else 0.0,
        "n_suelo": len(suelo),
        # El sin-detección pesa el doble: es el único que puede esconder
        # un parón entero sin dejar rastro.
        "punt": 1 - 2 * sin_deteccion - aereo - quieto,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--dur", type=float, default=30.0)
    parser.add_argument("--paso", type=float, default=5.0)
    parser.add_argument("--excluir", nargs="*", type=float, default=[])
    parser.add_argument("--top", type=int, default=6)
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    balon = df[df.id_jugador.isin([-1, -2])].sort_values("tiempo_s")
    if balon.empty:
        raise SystemExit("El CSV no tiene filas de balón (id -1/-2).")

    # Muestras que TOCARÍAN si el balón se viera todo el rato
    dt = float(np.median(np.diff(sorted(balon.tiempo_s.unique()))))
    esperadas = args.dur / dt

    excluidos = [
        (args.excluir[i], args.excluir[i + 1]) for i in range(0, len(args.excluir), 2)
    ]
    filas = []
    t0, t1 = balon.tiempo_s.min(), balon.tiempo_s.max() - args.dur
    for ini in np.arange(t0, t1, args.paso):
        if any(not (ini + args.dur <= a or ini >= b) for a, b in excluidos):
            continue
        p = puntuar(balon, ini, args.dur, esperadas)
        if p:
            filas.append(p)
    filas.sort(key=lambda x: -x["punt"])

    print(
        f"\n{'ventana':>16}{'sin balón':>11}{'aéreo':>8}{'quieto':>8}"
        f"{'v med.':>8}{'punt':>7}"
    )
    print("-" * 58)
    for f in filas[: args.top]:
        a, b = f["ini"], f["ini"] + args.dur
        print(
            f"{int(a//60)}:{int(a%60):02d}-{int(b//60)}:{int(b%60):02d}"
            f"{100 * f['sin_deteccion']:>13.0f}%{100 * f['aereo']:>7.0f}%"
            f"{100 * f['quieto']:>7.0f}%{f['v_mediana']:>8.1f}{f['punt']:>7.2f}"
        )
    if filas:
        m = filas[0]
        a = m["ini"]
        print(
            f"\n→ ELEGIDO: archivo {int(a//60)}:{int(a%60):02d}–"
            f"{int((a+args.dur)//60)}:{int((a+args.dur)%60):02d}"
            f"  ·  {100 * m['sin_deteccion']:.0f} % del tiempo sin balón en plano"
        )


if __name__ == "__main__":
    main()
