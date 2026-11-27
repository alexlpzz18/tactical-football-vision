#!/usr/bin/env python
"""¿Cuántas filas FANTASMA hay y cuánto rompen el bloque? (27-nov-2026, petición de Alex)

Fantasma = una fila INTERPOLADA (`es_real` 0) que, en su mismo fotograma, está a ≤ `radio` m de una
fila REAL del mismo equipo o de un portero (la regla de Alex). Caso que lo destapó: en el 3:00.0 del
alevín B, el portero verde real y, a 0,57 m, una pista solo interpolada etiquetada como jugador de
campo, que estira el bloque verde de 29 a 79 m.

Mide, por pata:
- % de fotogramas con algún fantasma y fantasmas por fotograma;
- el LARGO del bloque (extensión en x de los jugadores de campo, sin porteros) con y sin fantasmas:
  % de (fotograma, equipo) que cambian más de 5 m y el cambio medio;
- en el alevín A, que tiene GT: el error de profundidad (x) y de anchura (y) contra el GT con y sin
  fantasmas (oráculo con el radio por profundidad, sin arreglos).

Solo lee CSVs.

Uso:
    python scripts/fantasmas_interpolados.py --salida outputs/fantasmas
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

EQUIPO = {"A": "A", "B": "B", "portero_A": "A", "portero_B": "B"}
PATAS = {
    "alevinb": (
        R / "outputs/f11_staff_dentro/alevinb/posiciones_staff_on.csv",
        100.0,
        64.0,
    ),
    "alevina": (
        R / "outputs/literatura/banco/villa/posiciones_actual.csv",
        100.0,
        64.0,
    ),
}


def marcar_fantasmas(
    df: pd.DataFrame, radio: float, cualquier_equipo: bool = False
) -> pd.Series:
    """True en las filas fantasma: interpolada a ≤ radio de una real del mismo equipo o de un
    portero (V1) o de cualquier equipo (V2, `cualquier_equipo`)."""
    df = df[df.etiqueta.isin(EQUIPO)]
    fantasma = pd.Series(False, index=df.index)
    for _f, g in df.groupby("frame"):
        reales = g[g.es_real == 1]
        interp = g[g.es_real == 0]
        if reales.empty or interp.empty:
            continue
        for i, r in interp.iterrows():
            eq = EQUIPO[r.etiqueta]
            cand = (
                reales
                if cualquier_equipo
                else reales[
                    (reales.etiqueta.map(EQUIPO) == eq)
                    | reales.etiqueta.str.startswith("portero")
                ]
            )
            if (
                len(cand)
                and np.hypot(cand.x_m - r.x_m, cand.y_m - r.y_m).min() <= radio
            ):
                fantasma[i] = True
    return fantasma


def largos(df: pd.DataFrame, largo_campo: float, ancho_campo: float) -> pd.DataFrame:
    d = df[
        df.etiqueta.isin(["A", "B"])
        & df.x_m.between(0, largo_campo)
        & df.y_m.between(0, ancho_campo)
    ]
    return (
        d.groupby(["frame", "etiqueta"])
        .x_m.agg(lambda s: s.max() - s.min())
        .rename("largo")
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--radio", type=float, default=1.5)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    res = {"radio_m": a.radio}
    for pata, (csv, L, W) in PATAS.items():
        df = pd.read_csv(csv)
        f = marcar_fantasmas(df, a.radio)
        df["fantasma"] = f.reindex(df.index, fill_value=False)
        frames = df.frame.nunique()
        con = df[df.fantasma].frame.nunique()
        antes, despues = largos(df, L, W), largos(df[~df.fantasma], L, W)
        j = pd.concat([antes, despues], axis=1, keys=["antes", "despues"]).dropna()
        cambio = (j.antes - j.despues).abs()
        r = {
            "frames": frames,
            "frames_con_fantasma_pct": round(100 * con / frames, 1),
            "fantasmas_por_frame": round(int(df.fantasma.sum()) / frames, 2),
            "filas_interpoladas": int((df.es_real == 0).sum()),
            "fantasmas_de_las_interpoladas_pct": round(
                100 * df.fantasma.sum() / max((df.es_real == 0).sum(), 1), 1
            ),
            "largo_bloque_cambia_mas_de_5m_pct": round(
                100 * float((cambio > 5).mean()), 1
            ),
            "largo_bloque_cambio_medio_m": round(float(cambio.mean()), 2),
            "largo_bloque_cambio_p99_m": round(float(cambio.quantile(0.99)), 1),
        }
        if pata == "alevina":
            import oraculo_f11_radio_profundidad as orc

            H = np.load(orc.HOMOGRAFIA)
            gt = orc.gt_con_pies(H)
            for tag, sub in (
                ("con_fantasmas", df),
                ("sin_fantasmas", df[~df.fantasma]),
            ):
                # el oráculo de siempre usa solo filas reales, y ahí los fantasmas (interpolados) no
                # entran: aquí se mide con TODAS las filas, que es lo que pintan pizarra e informe
                todas = sub.reset_index(drop=True)
                fr = orc.construir(gt, todas, lambda p: max(orc.RADIO, 3.48 * p[4]))
                s = orc.resumen_escalera(fr)
                r[f"gt_{tag}"] = {
                    "profundidad_m": s["prof"]["sistema_m"],
                    "anchura_m": s["ancho"]["sistema_m"],
                    "centroide_m": s["centroide"]["sistema_m"],
                }
        res[pata] = r
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
