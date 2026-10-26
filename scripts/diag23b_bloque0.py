#!/usr/bin/env python
"""Diagnóstico 23-oct (b), bloque 0: otro ≥ 2 y huecos > 2,5 s como % del tiempo-jugador.

Sobre los CSV del 23-oct (a) (hoy y B2, las dos patas). Criterio en `docs/diagnostico_23oct_b.md`.

Uso:
    python scripts/diag23b_bloque0.py --entrada outputs/diagnostico_23oct_a
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
DIM = {"benja": (62.0, 40.0, 7), "villa": (100.0, 64.0, 11)}


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def huecos_pct(filas) -> dict:
    """Huecos > 2,5 s entre filas consecutivas de una identidad, en % del tiempo-jugador."""
    vida = hueco = 0.0
    for _i, g in filas.groupby("id_jugador"):
        t = np.sort(g.tiempo_s.to_numpy())
        if len(t) < 2:
            continue
        vida += t[-1] - t[0]
        dt = np.diff(t)
        hueco += float(dt[dt > 2.5].sum())
    return {
        "tiempo_jugador_s": round(vida, 1),
        "huecos_s": round(hueco, 1),
        "huecos_pct": round(100 * hueco / max(vida, 1e-9), 2),
    }


def main() -> None:
    import pandas as pd

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entrada", required=True)
    args = ap.parse_args()
    inv = _mod("diag22e_invariantes")
    ent = Path(args.entrada)
    res = {}
    for pata in ("benja", "villa"):
        largo, ancho, tope = DIM[pata]
        for nombre, sufijo in (("hoy", "hoy"), ("b2", "color")):
            filas = pd.read_csv(ent / f"corte_cruces_{pata}_{sufijo}.csv")
            i = inv.invariantes(inv.recuento_por_frame(filas, largo, ancho), tope)
            res[f"{pata}_{nombre}"] = {
                "otro_2_pct": i["pct_otro_2_o_mas"],
                **huecos_pct(filas),
            }
    texto = json.dumps(res, indent=1, ensure_ascii=False)
    (ent.parent / "diagnostico_23oct_b").mkdir(exist_ok=True)
    (ent.parent / "diagnostico_23oct_b" / "bloque0.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
