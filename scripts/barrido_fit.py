#!/usr/bin/env python
"""Barrido del fit del clasificador contra las DOS patas del banco.

Villaviciosa tiene ground truth de tracking; el benjamín tiene el mini-GT
de equipos etiquetado a mano. Medir en una sola no vale: un ajuste puede
enderezar el caso F7 y romper el F11, y hasta ahora no había forma de
verlo en el mismo movimiento.

Objetivo concreto: ¿alguna combinación endereza el **id 4 del benjamín**
(570 observaciones, real A y predicho B) sin degradar Villaviciosa?

Uso:
    python scripts/barrido_fit.py
    python scripts/barrido_fit.py --max 40
"""

import argparse
import copy
import itertools
import logging
import pickle
import sys
import warnings
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.perfiles import correr_perfil, postprocesar  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)

logger = logging.getLogger("barrido_fit")

EQUIV = {"arbitro": "otro", "staff": "otro"}
ID_PROBLEMA = 4  # el id del benjamín que se quiere enderezar


class PataBenja:
    """El benjamín: mini-GT de equipos etiquetado a mano, por recorte."""

    def __init__(self):
        cfg = yaml.safe_load(open("configs/processor_benja.yaml"))
        self.cfg_tracking = yaml.safe_load(open(cfg["config_tracking"]))
        self.cfg_equipos_base = cargar_config_equipos(cfg["config_equipos"])
        self.datos = cargar_cache(cfg["rutas"]["cache"])
        with open(cfg["rutas"]["cache_colores"], "rb") as f:
            self.colores = pickle.load(f)
        # Caché v2 (mismas detecciones), para poder pesar el pantalón
        self.datos_v2 = cargar_cache(
            "data/tracking_benja/cache_detecciones_benja_v2color.pkl"
        )
        with open("data/tracking_benja/cache_colores_benja_v2color.pkl", "rb") as f:
            self.colores_v2 = pickle.load(f)

        gt = pd.read_csv("data/tracking_benja/gt_equipos_benja.csv")
        gt = gt[gt.equipo_real.notna() & (gt.equipo_real != "")]
        gt["real"] = gt.equipo_real.map(lambda x: EQUIV.get(str(x), str(x)))
        self.gt = gt
        self.frames_ts = [(e["frame_idx"], e["t"]) for e in self.datos["cache"]]

    def medir(self, cfg_equipos, usar_v2=False):
        datos = self.datos_v2 if usar_v2 else self.datos
        colores = self.colores_v2 if usar_v2 else self.colores
        clf = entrenar_clasificador(colores, cfg_equipos, datos["cache"])
        ids = correr_perfil(
            datos["cache"],
            datos["fps"],
            datos["sample"],
            self.cfg_tracking,
            perfil="bytetrack",
            colores=colores,
            clasificador=clf,
            cfg_equipos=cfg_equipos,
        )
        eq = clasificar_identidades(ids, colores, clf, cfg_equipos)
        _tr, eq2 = postprocesar(
            ids, dict(eq), self.frames_ts, self.cfg_tracking, perfil="bytetrack"
        )
        pred = {i: EQUIV.get(str(v), str(v)) for i, v in eq2.items()}

        aciertos = pesos = 0.0
        id4_ok = None
        for id_j, g in self.gt.groupby("id_jugador"):
            cuenta = Counter(g.real)
            dominante, n = cuenta.most_common(1)[0]
            pureza = n / len(g)
            peso = float(g.n_obs.iloc[0]) * pureza
            ok = pred.get(int(id_j)) == dominante
            aciertos += peso * ok
            pesos += peso
            if int(id_j) == ID_PROBLEMA:
                id4_ok = bool(ok)
        return {
            "acc_benja": aciertos / pesos if pesos else 0.0,
            "id4": id4_ok,
            "n_ids": len(ids),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=40)
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    villa = Banco("configs/evaluation_v4pre.yaml", "configs/tracking.yaml")
    benja = PataBenja()

    # Diales. El radio de 25 m nunca se había medido.
    radios = [20.0, 25.0, 30.0, 35.0]
    umbrales = [(0.5, 1.3, 0.05), (0.4, 1.6, 0.05), (0.6, 1.1, 0.02)]
    minimos = [100, 300]
    combinaciones = list(itertools.product(radios, umbrales, minimos))[: args.max]

    cab = (
        f"{'radio':>6}{'umbral fusión':>16}{'min':>6}  "
        f"{'VILLA cob.':>11}{'IDF1':>7}{'quim':>6}{'equipos':>9}  "
        f"{'BENJA acc':>10}{'id 4':>6}"
    )
    print("\n" + cab)
    print("-" * len(cab))

    filas = []
    for radio, (u0, u1, paso), minimo in combinaciones:
        cfg_v = copy.deepcopy(villa.cfg_equipos)
        cfg_b = copy.deepcopy(benja.cfg_equipos_base)
        for cfg in (cfg_v, cfg_b):
            cfg.setdefault("agregacion", {})["umbral_profundidad_m"] = radio
            cfg.setdefault("entrenamiento", {})["umbral_profundidad_m"] = radio
            cfg["entrenamiento"]["min_features"] = minimo
            cc = cfg.setdefault("clasificador_color", {})
            cc.update(umbral_min=u0, umbral_max=u1, umbral_paso=paso)

        clf = entrenar_clasificador(villa.colores, cfg_v, villa.datos["cache"])
        ids = correr_perfil(
            villa.datos["cache"],
            villa.datos["fps"],
            villa.datos["sample"],
            villa.cfg_tracking,
            perfil="bytetrack",
            colores=villa.colores,
            clasificador=clf,
            cfg_equipos=cfg_v,
        )
        eq = clasificar_identidades(ids, villa.colores, clf, cfg_v)
        tr, eq2 = postprocesar(
            ids, dict(eq), villa.frames_ts, villa.cfg_tracking, perfil="bytetrack"
        )
        v = medir("x", tr, eq2, villa.gt, villa.comunes, villa.tiempos, villa.umbral)
        b = benja.medir(cfg_b)

        f = dict(radio=radio, umbral=f"{u0}-{u1}/{paso}", minimo=minimo, **v, **b)
        filas.append(f)
        print(
            f"{radio:>6.0f}{f['umbral']:>16}{minimo:>6}  "
            f"{v['cobertura']:>11.3f}{v['idf1']:>7.3f}"
            f"{v['quimeras']:>3}/{v['con10']:<2}{v['acc'] or 0:>9.3f}  "
            f"{b['acc_benja']:>10.3f}{('SÍ' if b['id4'] else 'no'):>6}"
        )

    print("-" * len(cab))
    ref = filas[0] if filas else None
    enderezan = [f for f in filas if f["id4"]]
    print(f"\nCombinaciones que enderezan el id 4: {len(enderezan)} de {len(filas)}")
    for f in enderezan:
        print(
            f"  radio {f['radio']:.0f} · umbral {f['umbral']} · min {f['minimo']}  →  "
            f"Villaviciosa cob {f['cobertura']:.3f} / equipos {f['acc'] or 0:.3f}, "
            f"benja {f['acc_benja']:.3f}"
        )
    if not enderezan:
        print("  (ninguna: el id 4 no es un problema del fit)")
    if ref:
        mejor_b = max(filas, key=lambda x: x["acc_benja"])
        mejor_v = max(filas, key=lambda x: (x["acc"] or 0))
        print(
            f"\nMejor benja : {mejor_b['acc_benja']:.3f} "
            f"(radio {mejor_b['radio']:.0f}, umbral {mejor_b['umbral']}, "
            f"min {mejor_b['minimo']}) · Villaviciosa equipos "
            f"{mejor_b['acc'] or 0:.3f}, cob {mejor_b['cobertura']:.3f}"
        )
        print(
            f"Mejor villa : {mejor_v['acc'] or 0:.3f} "
            f"(radio {mejor_v['radio']:.0f}, umbral {mejor_v['umbral']}, "
            f"min {mejor_v['minimo']}) · benja {mejor_v['acc_benja']:.3f}"
        )


if __name__ == "__main__":
    main()
