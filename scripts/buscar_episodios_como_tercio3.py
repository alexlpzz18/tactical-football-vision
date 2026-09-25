#!/usr/bin/env python
"""¿Hay más episodios como el tercio 3 del GT en el resto del partido? (sin GT)

Alex (25-sep-2026): *«busca si hay MÁS episodios como el del tercio 3 (déficit grande
de presencia sin que ningún proxy lo explique) en el resto del partido. Si aparecen
varios, hay un patrón por nombrar; si es solo ese, puede ser un incidente puntual y
lo veré yo mismo cuando mire el vídeo en ese segundo exacto.»*

El tercio 3 (`docs/desglose_del_error.md`, `docs/desglose_por_episodios.md`) tenía
detecciones NORMALES (14,6 en campo) pero el 21 % de las personas del GT sin fila,
sobre todo por filas DESPLAZADAS 2-5 m (35 de 46 parejas del partido caen ahí). Sin
GT no se puede repetir esa medida exacta (necesita la posición REAL de cada persona),
así que este script usa dos PROXIES que sí se pueden calcular en todo el partido, y
dice honestamente cuánto se parecen al tercio 3 conocido:

1. **Déficit detección↔fila**: detecciones en campo que no acaban siendo una fila de
   equipo ni del árbitro. ⚠️ Confundido por staff/banda fuera del rectángulo de
   detección «en campo»; NO mide lo mismo que el tercio 3 (allí las filas SÍ existían,
   solo estaban mal puestas).
2. **Tasa de "saltos"**: fracción de tramos reales consecutivos de una identidad con
   velocidad entre 3 y 8,5 m/s (rápido pero bajo el corte de teletransporte) — el
   mismo mecanismo que el balón (`docs/balon_sin_alas.md`: "un cambio de candidato se
   disfraza de vuelo"). Si una fila salta a otro candidato cercano, aquí se ve.

**Control de honestidad**: el propio bin del tercio 3 (5:45) se puntúa con ambos
proxies y se dice en qué percentil cae. Si no destaca, los proxies son un eco débil
y la lista de "candidatos" no es una detección fiable — es una lista de sitios donde
mirar, no una confirmación.

Uso:
    python scripts/buscar_episodios_como_tercio3.py
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
from src.evaluation.desglose_error import equipo_de_etiqueta  # noqa: E402

BIN_S = 15
LARGO_M, ANCHO_M = 62.0, 40.0
BIN_TERCIO3 = 23  # t0=345s: el bin de 15s donde cae el tercio 3 del GT (t=325-355s)


def en_campo(D: np.ndarray) -> np.ndarray:
    return (D[:, 0] >= 0) & (D[:, 0] <= LARGO_M) & (D[:, 1] >= 0) & (D[:, 1] <= ANCHO_M)


def proxy_deficit(filas: pd.DataFrame, dets: dict, masa: pd.DataFrame) -> pd.DataFrame:
    """Detecciones en campo que no son ni fila de equipo ni árbitro proxy, por bin."""
    m = filas.merge(masa, on=["frame", "id_jugador"], how="left")
    m["equipo_s"] = m.etiqueta.map(equipo_de_etiqueta)
    zona_b = (m.x_m >= ZONA_PORTERO_B_X) & ((m.y_m - 20).abs() <= ZONA_PORTERO_B_DY)
    m["arbitro"] = (
        (m.masa >= UMBRAL_MASA) & ~zona_b & (m.etiqueta != "portero_B")
    ).fillna(False)
    esta_en_equipo = m.equipo_s.isin(["A", "B"])
    rows = []
    for f, D in dets.items():
        Den = D[en_campo(D)]
        rows.append(
            {"frame": f, "dets": len(Den), "dets_x20": int((Den[:, 0] < 20).sum())}
        )
    T = pd.DataFrame(rows)
    g = m.groupby("frame")
    T["ab"] = (
        g.apply(lambda d: d.equipo_s.isin(["A", "B"]).sum()).reindex(T.frame).to_numpy()
    )
    T["arb_en_eq"] = (
        g.apply(lambda d: (d.equipo_s.isin(["A", "B"]) & d.arbitro).sum())
        .reindex(T.frame)
        .to_numpy()
    )
    T["ab"] = T.ab.fillna(0)
    T["arb_en_eq"] = T.arb_en_eq.fillna(0)
    T = T.merge(
        m.drop_duplicates("frame")[["frame", "tiempo_s"]], on="frame", how="left"
    )
    T["deficit"] = T.dets - T.ab - T.arb_en_eq
    T["bin"] = (T.tiempo_s // BIN_S).astype(int)
    B = T.groupby("bin").agg(
        t0=("tiempo_s", "min"),
        dets=("dets", "mean"),
        dets_x20=("dets_x20", "mean"),
        ab=("ab", "mean"),
        arb_en_eq=("arb_en_eq", "mean"),
        deficit=("deficit", "mean"),
    )
    _ = esta_en_equipo  # solo documental
    return B


def proxy_tasa_saltos(filas: pd.DataFrame) -> pd.DataFrame:
    """Fracción de tramos reales consecutivos con velocidad entre 3 y 8,5 m/s."""
    r = filas.sort_values(["id_jugador", "frame"]).copy()
    r["dt"] = r.groupby("id_jugador").tiempo_s.diff()
    r["dx"] = r.groupby("id_jugador").x_m.diff()
    r["dy"] = r.groupby("id_jugador").y_m.diff()
    r["v"] = np.hypot(r.dx, r.dy) / r.dt
    r = r[r.dt < 1.0]  # solo consecutivas de verdad (sin hueco de por medio)
    r["salto"] = (r.v >= 3.0) & (r.v < 8.5)
    r["bin"] = (r.tiempo_s // BIN_S).astype(int)
    B = r.groupby("bin").agg(n=("v", "size"), saltos=("salto", "sum"))
    B["tasa_saltos"] = B.saltos / B.n
    return B


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v3.csv")
    p.add_argument(
        "--dets", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument(
        "--colores", default="data/tracking_benja/cache_colores_benja_p1.pkl"
    )
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()

    filas = pd.read_csv(args.csv).query("es_real == 1").reset_index(drop=True)
    with open(args.dets, "rb") as f:
        dets = {
            e["frame_idx"]: np.array(e["dets"]).reshape(-1, 7)
            for e in pickle.load(f)["cache"]
        }
    with open(args.colores, "rb") as f:
        colores = pickle.load(f)
    masa = masa_de_ventana(filas, {k: v.tolist() for k, v in dets.items()}, colores)[
        ["frame", "id_jugador", "masa"]
    ]

    Bd = proxy_deficit(filas, dets, masa)
    Bt = proxy_tasa_saltos(filas)
    J = Bd.join(Bt[["tasa_saltos"]], how="inner")
    J["z_deficit"] = (J.deficit - J.deficit.mean()) / J.deficit.std()
    J["z_tasa"] = (J.tasa_saltos - J.tasa_saltos.mean()) / J.tasa_saltos.std()
    J["score"] = J.z_deficit + J.z_tasa
    J["t"] = [f"{int(t // 60)}:{int(t % 60):02d}" for t in J.t0]

    print(
        f"1. CONTROL: ¿destaca el propio tercio 3 del GT (bin {BIN_TERCIO3}, t≈5:45)?"
    )
    fila3 = J.loc[BIN_TERCIO3]
    pct_score = (J.score < fila3.score).mean()
    pct_tasa = (J.tasa_saltos < fila3.tasa_saltos).mean()
    print(
        f"   score {fila3.score:+.2f} (percentil {pct_score:.0%})"
        f" · tasa_saltos {fila3.tasa_saltos:.3f} (percentil {pct_tasa:.0%})"
    )
    if pct_score < 0.85:
        print(
            "   ⚠️ NO destaca claramente: los proxies son un ECO DÉBIL del fenómeno del"
            " tercio 3, no una detección fiable. Lo de abajo es 'dónde mirar', no 'qué hay'."
        )

    sin_encuadre_ni_arbitro = (J.dets_x20 < 1.5) & (J.arb_en_eq < 0.15)
    cand = J[sin_encuadre_ni_arbitro].sort_values("score", ascending=False)
    print(
        f"\n2. CANDIDATOS (sin encuadre-cerca de cámara ni árbitro; {len(cand)} de {len(J)} bins)"
    )
    print(
        f"   {'tiempo':>7s} {'dets':>6s} {'deficit':>8s} {'tasa_saltos':>12s} {'score':>7s}"
    )
    for bin_, r in cand.head(args.top).iterrows():
        marca = "  ← tercio 3" if bin_ == BIN_TERCIO3 else ""
        linea = f"   {r.t:>7s} {r.dets:6.1f} {r.deficit:8.2f} {r.tasa_saltos:12.3f}"
        print(f"{linea} {r.score:7.2f}{marca}")

    conocidos = {3, 4, 8, 13, 14}
    solapan = cand.head(args.top)[
        cand.head(args.top).t0.apply(lambda t: int(t // 60) in conocidos)
    ]
    print(f"\n3. De esos, {len(solapan)} caen en un minuto ya señalado como 'malo'")
    print("   (bajo total de detecciones). Los demás son NUEVOS: detecciones normales")
    print("   pero el proxy los marca — igual que el tercio 3.")


if __name__ == "__main__":
    main()
