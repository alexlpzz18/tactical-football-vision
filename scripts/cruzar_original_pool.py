#!/usr/bin/env python
"""¿Hay frames del TEST o de la VALIDACIÓN del pool repetidos en el dataset original de v1?

Lee el JSON que deja `colab_comprobaciones_reentreno.py minutos --json` (los 799 frames del
original, con `con_balon`) y el manifiesto del pool. Un frame del pool cuenta como repetido
si hay uno del original a ≤ `--radio` frames (2 por defecto: a 30 fps, 0,07 s, la misma
imagen a efectos prácticos).

Uso:
    python scripts/cruzar_original_pool.py --original ~/Downloads/frames_original.json
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def cruzar(
    frames_original: list[int], manifiesto: pd.DataFrame, radio: int = 2
) -> pd.DataFrame:
    """Por cada frame de test/val del pool: distancia (frames) al más cercano del original."""
    orig = np.array(sorted(f for f in frames_original if f is not None))
    filas = []
    for r in manifiesto[manifiesto.split.isin(["test", "val"])].itertuples():
        d = int(np.abs(orig - int(r.frame)).min()) if len(orig) else None
        filas.append({"split": r.split, "frame": int(r.frame), "minuto": r.minuto,
                      "dist_frames": d, "repetido": d is not None and d <= radio})  # fmt: skip
    return pd.DataFrame(filas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original", required=True, help="JSON de `minutos --json`")
    ap.add_argument("--manifiesto", default="outputs/pool_balon_pegado/manifiesto.csv")
    ap.add_argument("--radio", type=int, default=2)
    a = ap.parse_args()
    orig = json.load(open(Path(a.original).expanduser()))
    t = cruzar([o["frame"] for o in orig], pd.read_csv(a.manifiesto), a.radio)
    print(
        f"original: {len(orig)} frames ({sum(o['con_balon'] for o in orig)} con balón)"
    )
    for split, g in t.groupby("split"):
        rep = g[g.repetido]
        print(
            f"{split}: {len(rep)} de {len(g)} a ≤ {a.radio} frames de uno del original "
            f"(exactos: {int((g.dist_frames == 0).sum())}) · {sorted(rep.frame)}"
        )
    print(
        "distancia al más cercano (frames), mediana por split:",
        t.groupby("split").dist_frames.median().to_dict(),
    )


if __name__ == "__main__":
    main()
