#!/usr/bin/env python
"""Calibra sigma_apariencia y v_incert del coste mixto contra el banco.

Criterio de adopción, el de siempre y sin excepciones: gana si BAJA
QUIMERAS sin degradar cobertura, IDF1 ni concurrencia. Bajar quimeras
hundiendo la cobertura es el error que este proyecto ya ha cometido tres
veces (velocidad, post-proceso completo, color).

`v_incert` entra en el barrido porque el 1,5 m/s por defecto hace caer α
a 0,31 con un solo segundo de hueco INCLUSO cerca de la cámara, donde la
geometría es precisa (±0,11 m). Si es demasiado agresivo estaríamos
tirando la geometría buena justo donde vale.

Uso:
    python scripts/calibrar_coste_mixto.py
"""

import argparse
import itertools
import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.tracking.asociacion_apariencia import (  # noqa: E402
    ParametrosAsociacionApariencia,
    asociar_con_apariencia,
)
from src.tracking.coste_asociacion import ParametrosCosteMixto  # noqa: E402
from src.tracking.cosido_pureza import (  # noqa: E402
    ParametrosCosidoPureza,
    coser_por_pureza,
)
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)

# El punto adoptado hoy (ByteTrack + puerta), por el pipeline real.
REFERENCIA = {"nids": 64, "cobertura": 0.619, "conc": 21, "idf1": 0.546, "quim": 3}


def cargar_embeddings(ruta):
    with open(ruta, "rb") as f:
        d = pickle.load(f)
    V = np.asarray(d["embeddings"], dtype=np.float32)
    return {tuple(c): V[i] for i, c in enumerate(d["claves"])}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    p.add_argument("--emb", default="data/tracking/emb_villa_siglip.pkl")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    emb = cargar_embeddings(args.emb)
    pa = ParametrosAsociacionApariencia()

    cab = (
        f"{'sigma_app':>10}{'v_incert':>10}{'nIds':>6}{'cob.':>8}"
        f"{'conc':>6}{'IDF1':>8}{'tasa':>7}{'quim':>6}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    filas = []
    for s_app, v_inc in itertools.product((0.5, 1.0, 2.0), (0.5, 1.5, 3.0)):
        pc = ParametrosCosteMixto(sigma_apariencia=s_app, v_incert=v_inc)
        ids = asociar_con_apariencia(
            banco.datos["cache"],
            banco.datos["fps"],
            banco.datos["sample"],
            emb,
            pa,
            pc,
        )
        ids = coser_por_pureza(
            ids,
            banco.colores,
            ParametrosCosidoPureza(max_hueco=4.0, color_max_dist=0.9),
            dt=banco.dt,
        )
        eq = banco.clasificar(ids)
        tr = interpolar_trayectorias(
            identidades_a_trayectorias(ids), banco.frames_ts, max_hueco=6.0
        )
        m = medir("x", tr, eq, banco.gt, banco.comunes, banco.tiempos, banco.umbral)
        m.update(s_app=s_app, v_inc=v_inc)
        filas.append(m)
        print(
            f"{s_app:>10.1f}{v_inc:>10.1f}{m['nids']:>6}{m['cobertura']:>8.3f}"
            f"{m['conc']:>6.0f}{m['idf1']:>8.3f}{m['tasa']:>7.3f}{m['quimeras']:>6}"
        )

    print("-" * len(cab))
    r = REFERENCIA
    print(
        f"{'REFERENCIA (ByteTrack+puerta)':<20}{r['nids']:>6}{r['cobertura']:>8.3f}"
        f"{r['conc']:>6}{r['idf1']:>8.3f}{'—':>7}{r['quim']:>6}"
    )

    print("\n── CRITERIO: baja quimeras SIN degradar nada ──\n")
    ganan = [
        f
        for f in filas
        if f["quimeras"] < r["quim"]
        and f["cobertura"] >= r["cobertura"]
        and f["idf1"] >= r["idf1"]
        and abs(f["conc"] - 22) <= abs(r["conc"] - 22)
    ]
    if ganan:
        for f in sorted(ganan, key=lambda x: x["quimeras"]):
            print(
                f"  ✓ sigma_app {f['s_app']} · v_incert {f['v_inc']}: "
                f"{f['quimeras']} quimeras, cob {f['cobertura']:.3f}, "
                f"IDF1 {f['idf1']:.3f}"
            )
    else:
        print("  Ninguna combinación cumple el criterio.")
        mejor = min(filas, key=lambda f: f["quimeras"])
        print(
            f"\n  La de menos quimeras: sigma_app {mejor['s_app']} · "
            f"v_incert {mejor['v_inc']} → {mejor['quimeras']} quimeras, "
            f"pero cob {mejor['cobertura']:.3f} (ref {r['cobertura']:.3f}) "
            f"e IDF1 {mejor['idf1']:.3f} (ref {r['idf1']:.3f})."
        )


if __name__ == "__main__":
    main()
