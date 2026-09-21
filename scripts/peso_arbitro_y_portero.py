#!/usr/bin/env python
"""¿Cuánto pesan, en las métricas de producto, dos fallos del catálogo arbitral?

Alex (21-sep-2026): *"antes de tocar el umbral de saturación, mide cuánto pesa
el portero de A mal contado como árbitro en el CENTROIDE y el RECUENTO — puede
que parte del ruido que llevamos semanas persiguiendo sea esto y no el árbitro.
Con eso decido si vale la pena arreglar el catálogo (BACKLOG 26)."*

Dos contrafactuales, con las definiciones de producto de `scripts/oraculos.py`
(centroide = media de x e y; anchura = extensión en y; profundidad = extensión
en x; por equipo y frame, con el portero en su equipo):

1. **El portero de A mandado a `otro`**: se DEVUELVEN a A / `portero_A` las filas
   que v2 movió a `otro`, que no parecen árbitro y están en su área.
2. **El árbitro contado como jugador**: se SACAN de A/B las filas del árbitro
   (proxy de `scripts/arbitro_medicion.py`).

Se compara siempre contra la versión de producción (`posiciones_benja_p1_v2.csv`).

⚠️ El GT no anota al árbitro ni cubre los instantes del portero, así que esto
NO mide el error contra la verdad: mide cuánto se MUEVE cada métrica.

Uso:
    python scripts/peso_arbitro_y_portero.py
"""

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from arbitro_medicion import (  # noqa: E402
    UMBRAL_MASA,
    ZONA_PORTERO_B_DY,
    ZONA_PORTERO_B_X,
    masa_de_ventana,
)


def grupo(etiquetas: pd.Series) -> np.ndarray:
    """El portero cuenta con su equipo (como en el banco de producto)."""
    return np.where(
        etiquetas.isin(["A", "portero_A"]),
        "A",
        np.where(etiquetas.isin(["B", "portero_B"]), "B", None),
    )


def metricas(d: pd.DataFrame) -> pd.DataFrame:
    d = d.assign(eqp=grupo(d.etiqueta))
    d = d[d.eqp.notna()]
    r = d.groupby(["frame", "eqp"]).agg(
        n=("x_m", "size"),
        cx=("x_m", "mean"),
        cy=("y_m", "mean"),
        ymax=("y_m", "max"),
        ymin=("y_m", "min"),
        xmax=("x_m", "max"),
        xmin=("x_m", "min"),
    )
    r = r.reset_index()
    r["ancho"] = r.ymax - r.ymin
    r["prof"] = r.xmax - r.xmin
    return r


def informe(base: pd.DataFrame, contra: pd.DataFrame, equipo: str, afectados: set):
    J = base.merge(contra, on=["frame", "eqp"], suffixes=("_0", "_1"), how="outer")
    T = J[J.eqp == equipo]
    a = T[T.frame.isin(afectados)]
    print(
        f"  EQUIPO {equipo} · frames afectados {len(a)} de {T.frame.nunique()} "
        f"({len(a) / T.frame.nunique():.1%})"
    )
    print(
        f"    recuento en los afectados: mediana {a.n_0.median():.0f} → "
        f"{a.n_1.median():.0f} · exactamente 7: {(a.n_0 == 7).mean():.0%} → "
        f"{(a.n_1 == 7).mean():.0%}"
    )
    for col, nombre in [
        ("cx", "centroide x"),
        ("ancho", "anchura"),
        ("prof", "profundidad"),
    ]:
        d = (a[col + "_1"] - a[col + "_0"]).dropna()
        print(
            f"    {nombre:<12} en los afectados: mediana {d.median():+6.2f} m · "
            f"|·| p90 {d.abs().quantile(0.9):5.2f} m"
        )
    print(
        "    PARTIDO ENTERO: media |Δ| "
        f"centroide {(T.cx_1 - T.cx_0).abs().mean():.3f} m · "
        f"anchura {(T.ancho_1 - T.ancho_0).abs().mean():.3f} m · "
        f"profundidad {(T.prof_1 - T.prof_0).abs().mean():.3f} m · "
        f"recuento=7: {(T.n_0 == 7).mean():.1%} → {(T.n_1 == 7).mean():.1%}"
    )


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

    with open(args.dets, "rb") as f:
        dets = {e["frame_idx"]: e["dets"] for e in pickle.load(f)["cache"]}
    with open(args.colores, "rb") as f:
        colores = pickle.load(f)
    v2 = pd.read_csv(args.csv).query("es_real == 1")
    W = masa_de_ventana(v2, dets, colores)[["frame", "id_jugador", "masa"]]
    D = v2.merge(W, on=["frame", "id_jugador"], how="left")
    zona_b = (D.x_m >= ZONA_PORTERO_B_X) & ((D.y_m - 20).abs() <= ZONA_PORTERO_B_DY)
    D["arbitro"] = (
        (D.masa >= UMBRAL_MASA) & ~zona_b & (D.etiqueta != "portero_B")
    ).fillna(False)
    base = metricas(D)

    # 1. el portero de A devuelto a su equipo
    ant = pd.read_csv(args.csv_anterior).query("es_real == 1")
    j = D.merge(
        ant[["frame", "id_jugador", "etiqueta"]],
        on=["frame", "id_jugador"],
        suffixes=("", "_ant"),
    )
    mov = j[(j.etiqueta == "otro") & (j.etiqueta_ant != "otro")]
    gk = mov[
        (mov.masa.fillna(0) < UMBRAL_MASA)
        & (mov.x_m < 10)
        & ((mov.y_m - 20).abs() < 8)
        & mov.etiqueta_ant.isin(["A", "portero_A"])
    ]
    cf = D.copy()
    clave = pd.MultiIndex.from_frame(cf[["frame", "id_jugador"]])
    quita = clave.isin(pd.MultiIndex.from_frame(gk[["frame", "id_jugador"]]))
    previa = cf.loc[quita, ["frame", "id_jugador"]].merge(
        gk[["frame", "id_jugador", "etiqueta_ant"]], on=["frame", "id_jugador"]
    )
    cf.loc[quita, "etiqueta"] = previa.etiqueta_ant.to_numpy()
    print(
        f"\n1. PORTERO DE A MANDADO A 'otro': {len(gk)} filas, "
        f"{gk.id_jugador.nunique()} identidades, {gk.frame.nunique()} frames"
    )
    informe(base, metricas(cf), "A", set(gk.frame))

    # 2. el árbitro fuera de los equipos
    mal = D[D.arbitro & D.etiqueta.isin(["A", "B"])]
    cf2 = D.copy()
    cf2.loc[cf2.arbitro & cf2.etiqueta.isin(["A", "B"]), "etiqueta"] = "otro"
    print(
        f"\n2. ÁRBITRO CONTADO COMO JUGADOR: {len(mal)} filas "
        f"({mal.etiqueta.value_counts().to_dict()}), {mal.frame.nunique()} frames"
    )
    informe(base, metricas(cf2), "B", set(mal.frame))
    informe(base, metricas(cf2), "A", set(mal.frame))


if __name__ == "__main__":
    main()
