#!/usr/bin/env python
"""Los dos bugs del clasificador, medidos POR SEPARADO.

El diagnóstico del punto 1 dejó el clasificador en el 8,6 % de los fallos
(el 85-90 % es asociación), y dentro de ese 8,6 % hay dos causas
concretas, ninguna de las cuales era la que yo supuse al principio:

1. **Catálogo arbitral goloso**: marca como árbitro a un jugador real del
   equipo A (id 40, 110 observaciones en el centro del campo). La regla
   de conflicto protege al PROTOTIPO del equipo pero no a la dispersión
   alrededor. Arreglo: `margen_equipo` — el catálogo solo manda cuando el
   color no se parece a NINGÚN equipo.
2. **El cajón 'otro' absorbe identidades cortas**: 1, 7, 14 y 16
   observaciones. Con una sola, la media de color es ruido puro. Arreglo:
   `min_obs_para_otro` — por debajo, se fuerza A/B.

Se miden por separado, y cada uno contra las dos patas.

Uso:
    python scripts/medir_bugs_clasificador.py
"""

import argparse
import copy
import logging
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    clasificar_identidades,
)
from src.tracking.perfiles import correr_perfil, postprocesar  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    ids = correr_perfil(
        banco.datos["cache"],
        banco.datos["fps"],
        banco.datos["sample"],
        banco.cfg_tracking,
        perfil="bytetrack",
        colores=banco.colores,
        clasificador=banco.clasificador,
        cfg_equipos=banco.cfg_equipos,
    )

    equipo_gt = {}
    for g in banco.gt.values():
        for o in g:
            equipo_gt.setdefault(o.obj_id, "otro" if o.team is None else str(o.team))

    # A quién pertenece cada identidad, para contar el fallo del clasificador
    # SOLO en identidades puras (en las contaminadas no existe respuesta).
    duenos = []
    for ident in ids:
        personas = []
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
                    personas.append(mejor)
        duenos.append(personas)

    variantes = [
        ("base (como está hoy)", {}, {}),
        ("bug 1: margen_equipo 0.5", {"margen_equipo": 0.5}, {}),
        ("bug 1: margen_equipo 0.8", {"margen_equipo": 0.8}, {}),
        ("bug 2: min_obs_otro 10", {}, {"min_obs_para_otro": 10}),
        ("bug 2: min_obs_otro 25", {}, {"min_obs_para_otro": 25}),
        ("los dos (0.8 + 25)", {"margen_equipo": 0.8}, {"min_obs_para_otro": 25}),
    ]

    cab = (
        f"{'variante':<26}{'cob.':>8}{'IDF1':>8}{'quim':>6}"
        f"{'acc eq':>9}{'puras mal':>11}{'obs mal':>9}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    for nombre, kw_arb, kw_agg in variantes:
        cfg_eq = copy.deepcopy(banco.cfg_equipos)
        cfg_eq.setdefault("arbitro", {}).update(kw_arb)
        cfg_eq.setdefault("agregacion", {}).update(kw_agg)
        eq = clasificar_identidades(ids, banco.colores, banco.clasificador, cfg_eq)
        tr, eq2 = postprocesar(
            ids, dict(eq), banco.frames_ts, banco.cfg_tracking, perfil="bytetrack"
        )
        m = medir("x", tr, eq2, banco.gt, banco.comunes, banco.tiempos, banco.umbral)

        puras_mal = obs_mal = 0
        for i, personas in enumerate(duenos, start=1):
            if not personas or len(set(personas)) != 1:
                continue
            real = equipo_gt.get(personas[0])
            pred = str(eq2.get(i, "otro"))
            pred = "otro" if pred in ("arbitro", "staff") else pred
            if real != pred:
                puras_mal += 1
                obs_mal += len(personas)
        print(
            f"{nombre:<26}{m['cobertura']:>8.3f}{m['idf1']:>8.3f}{m['quimeras']:>6}"
            f"{(m['acc'] or 0):>9.3f}{puras_mal:>11}{obs_mal:>9}"
        )

    print(
        "\n'puras mal' = identidades de UNA sola persona con el equipo "
        "equivocado.\nEs donde vive el 8,6 % que puede arreglar el "
        "clasificador; el resto es\nasociación y ningún clasificador lo salva."
    )


if __name__ == "__main__":
    main()
