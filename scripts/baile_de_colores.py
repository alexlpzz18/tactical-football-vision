#!/usr/bin/env python
"""El baile de colores: TODOS los cambios de equipo de una identidad, con contexto.

Alex pidió (21-sep-2026): *"un jugador que cambia de equipo a mitad de jugada
no puede pasar en producto. Dame los casos concretos del partido entero:
cuántos son, qué identidades, en qué instantes y qué tienen en común."*

Un CAMBIO es un salto A↔B entre dos observaciones consecutivas de la misma
identidad. Se cuentan por separado los que ocurren en un tramo CONTINUO (hueco
≤ 0,35 s, mismo cuerpo siguiéndose) y los que ocurren tras un hueco (la
identidad reaparece con otro color: eso es otra cosa, una re-entrada).

⚠️ Lo común de los cambios solo significa algo CONTRA LA LÍNEA BASE: si el
61 % de los cambios no tiene un vecino cerca pero el 86 % de todas las filas
tampoco, "no tiene vecino" no explica nada. Por eso cada rasgo sale con el de
una muestra aleatoria de filas A/B al lado.

Escribe `outputs/baile_casos.csv` con los cambios, uno por fila.

Uso:
    python scripts/baile_de_colores.py
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("baile")

HUECO_CONTINUO_S = 0.35  # más allá, la identidad "reaparece": no es el mismo tramo
PARPADEO_S = 1.5  # una etiqueta nueva que dura menos de esto y vuelve
SEMILLA = 1


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / (area + 1e-9)


def cambios_de_equipo(csv_ruta: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(filas A/B con su tramo y su run, cambios A↔B entre consecutivas)."""
    filas = pd.read_csv(csv_ruta).query("es_real == 1")
    ab = (
        filas[filas.etiqueta.isin(["A", "B"])]
        .sort_values(["id_jugador", "tiempo_s"])
        .reset_index(drop=True)
    )
    g = ab.groupby("id_jugador")
    ab["etq_prev"] = g.etiqueta.shift()
    ab["t_prev"] = g.tiempo_s.shift()
    ab["dt"] = ab.tiempo_s - ab.t_prev
    ab["salto_m"] = np.hypot(g.x_m.diff(), g.y_m.diff())
    # tramo continuo y "run" de etiqueta constante dentro del tramo
    ab["tramo"] = (
        (ab.id_jugador != ab.id_jugador.shift()) | (ab.dt > HUECO_CONTINUO_S)
    ).cumsum()
    ab["run"] = ((ab.tramo != ab.tramo.shift()) | (ab.etiqueta != ab.etq_prev)).cumsum()
    cambios = ab[ab.etq_prev.notna() & (ab.etiqueta != ab.etq_prev)].copy()
    cambios["continuo"] = cambios.dt <= HUECO_CONTINUO_S
    return ab, cambios


def duracion_de_la_etiqueta_nueva(ab: pd.DataFrame, cambios: pd.DataFrame) -> pd.Series:
    """Cuánto dura la etiqueta nueva; NaN si el tramo termina justo ahí."""
    runs = ab.groupby("run").agg(
        tramo=("tramo", "first"), t0=("tiempo_s", "min"), t1=("tiempo_s", "max")
    )
    runs["dur"] = runs.t1 - runs.t0 + 0.1
    runs["cierra"] = runs.tramo != runs.tramo.shift(-1)
    dur = runs.dur.where(~runs.cierra)
    return cambios.run.map(dur)


def contexto(filas: pd.DataFrame, cache: dict, muestra: pd.DataFrame) -> pd.DataFrame:
    """Vecinos y solape de cajas de cada fila de `muestra`, en su frame."""
    por_frame = {
        f: (
            g.id_jugador.to_numpy(),
            g.etiqueta.to_numpy(),
            g[["x_m", "y_m"]].to_numpy(),
        )
        for f, g in filas.groupby("frame")
    }
    salida = []
    for r in muestra.itertuples():
        ids, etq, pos = por_frame[r.frame]
        d = np.hypot(pos[:, 0] - r.x_m, pos[:, 1] - r.y_m)
        yo = np.where(ids == r.id_jugador)[0]
        if len(yo):
            d[yo[0]] = np.inf
        rival = (etq != r.etiqueta) & np.isin(etq, ["A", "B"])
        dets = cache[int(r.frame)]
        k = int(np.argmin([(x[0] - r.x_m) ** 2 + (x[1] - r.y_m) ** 2 for x in dets]))
        caja = dets[k][2:6]
        solape = max([iou(caja, x[2:6]) for j, x in enumerate(dets) if j != k] or [0.0])
        salida.append(
            {
                "d_vecino": d.min(),
                "d_rival": d[rival].min() if rival.any() else np.inf,
                "iou_max": solape,
                "alto_px": caja[3] - caja[1],
                "ratio": (caja[2] - caja[0]) / (caja[3] - caja[1]),
            }
        )
    return pd.DataFrame(salida, index=muestra.index)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v2.csv")
    p.add_argument(
        "--cache", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument("--salida", default="outputs/baile_casos.csv")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    ab, cambios = cambios_de_equipo(args.csv)
    n_id = ab.id_jugador.nunique()
    print(f"\nObservaciones A/B: {len(ab)} · identidades: {n_id}")
    print(
        f"CAMBIOS A↔B: {len(cambios)}  "
        f"(continuos {int(cambios.continuo.sum())} · tras un hueco "
        f"{int((~cambios.continuo).sum())})"
    )
    print(
        f"  identidades con al menos uno: {cambios.id_jugador.nunique()} de {n_id}"
        f" · ritmo: {len(cambios) / (ab.tiempo_s.max() / 60):.0f} por minuto"
    )
    c = cambios[cambios.continuo]
    print(
        f"  salto de posición en los continuos: mediana {c.salto_m.median():.2f} m · "
        f"con salto > 1,5 m: {int((c.salto_m > 1.5).sum())}"
    )

    cambios["dur_nueva_s"] = duracion_de_la_etiqueta_nueva(ab, cambios)
    cont = cambios[cambios.continuo]
    tipo = np.select(
        [
            cont.dur_nueva_s.isna(),
            cont.dur_nueva_s <= PARPADEO_S,
            cont.dur_nueva_s <= 5,
        ],
        ["cierra el tramo", "PARPADEO (<= 1,5 s)", "corto (1,5-5 s)"],
        "DURADERO (> 5 s)",
    )
    print("\nPor lo que dura la etiqueta nueva (continuos):")
    print(pd.Series(tipo).value_counts().to_string())

    pur = ab.groupby("id_jugador").etiqueta.agg(
        lambda s: min((s == "A").mean(), (s == "B").mean())
    )
    cambios["minoritaria"] = cambios.id_jugador.map(pur)
    mez = (cambios.minoritaria > 0.2) & cambios.continuo
    print(
        f"\nContinuos en identidades MEZCLADAS (>20 % de la etiqueta minoritaria): "
        f"{int(mez.sum())} de {int(cambios.continuo.sum())} "
        f"({mez.sum() / cambios.continuo.sum():.0%}) · identidades mezcladas "
        f"{int((pur > 0.2).sum())} de {n_id}"
    )

    print("\nLas 10 identidades con más cambios:")
    print(
        cambios.groupby("id_jugador")
        .size()
        .sort_values(ascending=False)
        .head(10)
        .to_string()
    )

    # contexto contra la línea base
    with open(args.cache, "rb") as f:
        cache = {e["frame_idx"]: e["dets"] for e in pickle.load(f)["cache"]}
    filas = pd.read_csv(args.csv).query("es_real == 1")
    base = ab.sample(20000, random_state=SEMILLA)
    Cb = contexto(filas, cache, base)
    Cc = contexto(filas, cache, cambios)
    mediana = Cb.groupby(
        pd.cut(Cb.alto_px, [0, 30, 45, 60, 80, 110, 400]), observed=True
    ).ratio.median()
    for C in (Cb, Cc):
        esperado = (
            pd.cut(C.alto_px, mediana.index.categories).map(mediana).astype(float)
        )
        C["ancha"] = C.ratio / esperado > 1.25
    filas_rasgos = [
        ("vecino a < 1,5 m", lambda C: (C.d_vecino < 1.5).mean()),
        ("rival a < 1 m", lambda C: (C.d_rival < 1).mean()),
        ("caja solapada (IoU > 0,10)", lambda C: (C.iou_max > 0.10).mean()),
        ("caja solapada fuerte (IoU > 0,30)", lambda C: (C.iou_max > 0.30).mean()),
        ("solapada O ancha (> 25 %)", lambda C: ((C.iou_max > 0.10) | C.ancha).mean()),
    ]
    print(f"\n{'RASGO':<38}{'CAMBIOS':>10}{'LÍNEA BASE':>12}")
    for nombre, f in filas_rasgos:
        print(f"{nombre:<38}{f(Cc):10.1%}{f(Cb):12.1%}")

    out = cambios.join(Cc)
    out["mmss"] = out.tiempo_s.map(lambda t: f"{int(t // 60):02d}:{t % 60:04.1f}")
    cols = [
        "id_jugador", "mmss", "tiempo_s", "etq_prev", "etiqueta", "continuo",
        "dt", "salto_m", "dur_nueva_s", "minoritaria", "d_vecino", "d_rival",
        "iou_max", "ancha", "x_m", "y_m", "frame",
    ]  # fmt: skip
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    out[cols].to_csv(args.salida, index=False)
    print(f"\n✓ {len(out)} cambios en {args.salida}")


if __name__ == "__main__":
    main()
