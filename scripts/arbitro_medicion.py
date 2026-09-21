#!/usr/bin/env python
"""Cuánto del ÁRBITRO está bien etiquetado, y qué le hace fallar al catálogo.

El GT del benjamín NO anota al árbitro, así que no hay verdad directa. Se
construye una en dos pasos, y el segundo es lo que la hace creíble:

1. **En la ventana del GT (60 frames)** el árbitro es la única fila que no
   casa con ninguna persona anotada Y tiene verde flúor en el torso, medido
   sobre los PÍXELES del vídeo (independiente del histograma que usa el
   catálogo). Sale una fila por frame en 59 de 60, comprobado a ojo.
2. **En el partido entero** se usa un proxy sobre el histograma HS de la
   ventana de 1,5 s (masa en H 20-90 con S ≥ 80 mayor de 0,27) y se
   CALIBRA contra ese paso 1: separa 58 ventanas de árbitro de 663 de jugador
   sin un solo falso. Se descarta la zona del portero de B (x ≥ 48), que
   también viste verde flúor.

⚠️ El proxy NO es un clasificador para producción: se usa para MEDIR. Bajar
el umbral de saturación del catálogo (regla del bin dominante) a 70 recupera
el 93 % del árbitro pero captura el 6,4 % de todas las ventanas A/B del
partido: la trampa de siempre.

Uso:
    python scripts/arbitro_medicion.py
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.team_classification.feature_v2 import parte_camiseta_hs  # noqa: E402

logger = logging.getLogger("arbitro")

VENTANA_S = 1.5  # la misma del etiquetado por observación
UMBRAL_MASA = 0.27  # centro de la zona de separación medida (ver docstring)
# Región "verde/amarillo flúor" del histograma HS 16x16: H 20-90 (bins 2..7)
# y S >= 80 (bins 5..15). Más laxa que S >= 170 del catálogo a propósito: en
# esta cámara el chaleco cae a S≈72-104 la mitad del tiempo.
MASCARA = np.zeros((16, 16), bool)
MASCARA[2:8, 5:] = True
# Zona del portero de B: también viste verde flúor y no es el árbitro.
ZONA_PORTERO_B_X, ZONA_PORTERO_B_DY = 48.0, 12.0


def masa_de_ventana(filas: pd.DataFrame, cache_dets: dict, cache_color: dict):
    """Añade `masa` = fracción del histograma medio de la ventana en la región flúor."""
    filas = filas.copy()
    filas["k"] = [
        int(
            np.argmin(
                [(x[0] - r.x_m) ** 2 + (x[1] - r.y_m) ** 2 for x in cache_dets[r.frame]]
            )
        )
        for r in filas.itertuples()
    ]
    feats = [cache_color.get((f, k)) for f, k in zip(filas.frame, filas.k)]
    filas = filas[[v is not None for v in feats]].copy()
    filas["hs"] = [parte_camiseta_hs(np.asarray(v)) for v in feats if v is not None]
    masas = pd.Series(np.nan, index=filas.index)
    for _id, g in filas.sort_values("tiempo_s").groupby("id_jugador"):
        t = g.tiempo_s.to_numpy()
        M = np.stack(g.hs.to_numpy())
        M = M / np.maximum(M.sum(1, keepdims=True), 1e-9)
        for i in range(len(g)):
            m = M[np.abs(t - t[i]) <= VENTANA_S / 2].mean(0)
            masas[g.index[i]] = m[MASCARA.ravel()].sum()
    filas["masa"] = masas
    return filas.drop(columns="hs")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v2.csv")
    p.add_argument(
        "--csv-anterior", default="data/tracking_benja/posiciones_benja_p1.csv"
    )
    p.add_argument(
        "--dets", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument(
        "--colores", default="data/tracking_benja/cache_colores_benja_p1.pkl"
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with open(args.dets, "rb") as f:
        dets = {e["frame_idx"]: e["dets"] for e in pickle.load(f)["cache"]}
    with open(args.colores, "rb") as f:
        colores = pickle.load(f)
    filas = pd.read_csv(args.csv).query("es_real == 1")
    W = masa_de_ventana(filas, dets, colores)
    W["zona_portero_b"] = (W.x_m >= ZONA_PORTERO_B_X) & (
        (W.y_m - 20).abs() <= ZONA_PORTERO_B_DY
    )
    W["arbitro"] = (
        (W.masa >= UMBRAL_MASA) & ~W.zona_portero_b & (W.etiqueta != "portero_B")
    )
    A = W[W.arbitro]

    print(f"\nFILAS DE ÁRBITRO (proxy, sin la zona del portero de B): {len(A)}")
    print(
        "  etiqueta:",
        (A.etiqueta.value_counts(normalize=True) * 100).round(1).to_dict(),
    )
    pf = A.groupby("frame").agg(
        n=("arbitro", "size"), otro=("etiqueta", lambda s: (s == "otro").any())
    )
    print(
        f"  frames con árbitro visible: {len(pf)} de {filas.frame.nunique()} "
        f"({len(pf) / filas.frame.nunique():.0%})"
    )
    print(f"  frames de UNA fila: árbitro como 'otro' {pf[pf.n == 1].otro.mean():.1%}")

    # pureza de la identidad que contiene las filas mal etiquetadas
    frac = W[W.etiqueta != "portero_B"].groupby("id_jugador").arbitro.mean()
    mal = A[A.etiqueta != "otro"].groupby("id_jugador").size().rename("mal").to_frame()
    mal["frac"] = mal.index.map(frac)
    mal["tipo"] = pd.cut(
        mal.frac,
        [-0.01, 0.2, 0.8, 1.01],
        labels=[
            "jugador con un tramo de árbitro (<20 %)",
            "MEZCLADA (20-80 %)",
            "PURA (>=80 %)",
        ],
    )
    t = mal.groupby("tipo", observed=True).mal.agg(["sum", "size"])
    t["%"] = (t["sum"] / t["sum"].sum() * 100).round(1)
    print("\nFILAS DE ÁRBITRO MAL ETIQUETADAS, por pureza de su identidad:")
    print(t.rename(columns={"sum": "filas", "size": "identidades"}).to_string())

    # qué disparó el catálogo que NO parece árbitro (falsos capturados)
    ant = pd.read_csv(args.csv_anterior).query("es_real == 1")
    j = ant.merge(
        W[["frame", "id_jugador", "etiqueta", "masa"]],
        on=["frame", "id_jugador"],
        suffixes=("_ant", "_v2"),
    )
    mov = j[(j.etiqueta_ant != "otro") & (j.etiqueta_v2 == "otro")]
    no_arb = mov[mov.masa < UMBRAL_MASA]
    print(
        f"\nFILAS QUE v2 MANDA A 'otro' Y ANTES NO LO ERAN: {len(mov)} "
        f"· parecen árbitro {len(mov) - len(no_arb)} · NO lo parecen {len(no_arb)}"
    )
    g = (
        no_arb.groupby(["id_jugador", "etiqueta_ant"])
        .agg(
            n=("frame", "size"),
            x=("x_m", "median"),
            y=("y_m", "median"),
            t0=("tiempo_s", "min"),
        )
        .sort_values("n", ascending=False)
        .head(8)
    )
    print(g.round(1).to_string())
    en_area_a = no_arb[(no_arb.x_m < 10) & ((no_arb.y_m - 20).abs() < 8)]
    print(
        f"  de las que no lo parecen, en el área del portero de A (x<10): "
        f"{len(en_area_a)} filas, identidades {sorted(en_area_a.id_jugador.unique())}"
    )


if __name__ == "__main__":
    main()
