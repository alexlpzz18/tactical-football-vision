#!/usr/bin/env python
"""Puerta de re-entrada con EMBEDDING en vez de color: barrido + caso #43.

El color es ciego por definición al caso que más duele: dos compañeros
con la misma equipación (el #43 de Alex — todo naranja, y a mitad de la
tira empieza a seguir a otro naranja). El embedding sí los distingue:
medido, siglip 0,200 frente a 0,018 del HSV en la re-entrada de recortes
pequeños, que es el 42 % de las re-entradas.

Este script barre el umbral y, además de las métricas del banco, cuenta
explícitamente **cuántas quimeras del MISMO equipo** quedan — que es lo
único que el color no podía arreglar.

Uso:
    python scripts/calibrar_puerta_embedding.py
"""

import argparse
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
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cosido_pureza import (  # noqa: E402
    ParametrosCosidoPureza,
    coser_por_pureza,
)
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)
from src.tracking.puerta_reentrada import (  # noqa: E402
    ParametrosPuertaReentrada,
    aplicar_puerta_reentrada,
)

REFERENCIA = {"nids": 64, "cobertura": 0.619, "conc": 21, "idf1": 0.546, "quim": 3}


def cargar_emb(ruta):
    with open(ruta, "rb") as f:
        d = pickle.load(f)
    V = np.asarray(d["embeddings"], dtype=np.float32)
    return {tuple(c): V[i] for i, c in enumerate(d["claves"])}


def quimeras_por_equipo(identidades, banco):
    """(mismo equipo, equipos distintos) entre las identidades impuras."""
    equipo_gt = {}
    for g in banco.gt.values():
        for o in g:
            equipo_gt.setdefault(o.obj_id, str(o.team))
    mismo = distinto = 0
    for ident in identidades:
        personas = set()
        for tr in ident:
            for pos, (f, _d) in zip(tr.pos, tr.det_idxs):
                g = banco.gt.get(f)
                if not g:
                    continue
                mejor, dmin = None, banco.umbral.para(float(pos[1]))
                for o in g:
                    d = float(np.linalg.norm(np.asarray(o.pos) - np.asarray(pos)))
                    if d < dmin:
                        mejor, dmin = o.obj_id, d
                if mejor is not None:
                    personas.add(mejor)
        if len(personas) > 1:
            if len({equipo_gt.get(i) for i in personas}) == 1:
                mismo += 1
            else:
                distinto += 1
    return mismo, distinto


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    p.add_argument("--emb", default="data/tracking/emb_villa_siglip.pkl")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    emb = cargar_emb(args.emb)
    base = asociar_con_bytetrack(
        banco.datos["cache"],
        banco.datos["fps"],
        banco.datos["sample"],
        ParametrosByteTrack.desde_dict(banco.cfg_tracking.get("bytetrack")),
    )

    cab = (
        f"{'puerta':<26}{'nIds':>6}{'cob.':>8}{'conc':>6}{'IDF1':>8}"
        f"{'tasa':>7}{'quim':>6}{'mismo eq':>10}"
    )
    print("\n" + cab)
    print("-" * len(cab))

    variantes = [("color 0.9 (adoptada)", dict(color_max_dist=0.9), None)]
    for u in (0.04, 0.06, 0.08, 0.10, 0.13):
        variantes.append((f"embedding {u}", dict(emb_max_dist=u), emb))

    for nombre, kw, fuente in variantes:
        ids = aplicar_puerta_reentrada(
            base,
            banco.colores,
            banco.dt,
            ParametrosPuertaReentrada(activa=True, hueco_min_s=0.5, **kw),
            embeddings=fuente,
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
        mismo, _dist = quimeras_por_equipo(ids, banco)
        print(
            f"{nombre:<26}{m['nids']:>6}{m['cobertura']:>8.3f}{m['conc']:>6.0f}"
            f"{m['idf1']:>8.3f}{m['tasa']:>7.3f}{m['quimeras']:>6}{mismo:>10}"
        )

    r = REFERENCIA
    print("-" * len(cab))
    print(
        f"{'REFERENCIA':<26}{r['nids']:>6}{r['cobertura']:>8.3f}{r['conc']:>6}"
        f"{r['idf1']:>8.3f}{'—':>7}{r['quim']:>6}"
    )
    print(
        "\n'mismo eq' = quimeras que mezclan a dos jugadores del MISMO equipo.\n"
        "Es el caso #43 y el techo estructural del color: si el embedding\n"
        "sirve, esa columna tiene que bajar."
    )


if __name__ == "__main__":
    main()
