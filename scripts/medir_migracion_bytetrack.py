#!/usr/bin/env python
"""Banco de la migración a ByteTrack: cada variante contra el GT.

Objetivo declarado del encargo: superar la cobertura de ByteTrack pelado
(0,516 crudo / 0,533 con interpolación) SIN degradar su pureza (5-6
quimeras, tasa de IDSW ~0,17, concurrencia 20-23 con GT 22).

Uso:
    python scripts/medir_migracion_bytetrack.py
    python scripts/medir_migracion_bytetrack.py --barrido ambiguedad
"""

import argparse
import logging
import pickle
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

warnings.filterwarnings("ignore")

from src.evaluation.adaptador import trayectorias_a_por_frame  # noqa: E402
from src.evaluation.alineacion import frames_comunes  # noqa: E402
from src.evaluation.asociacion import UmbralProfundidad, asociar_todos  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.evaluation.metricas import (  # noqa: E402
    accuracy_equipos,
    calcular_metricas_tracking,
    cobertura_colectiva,
    resumen_equipos,
)
from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.cosido_pureza import (  # noqa: E402
    ParametrosCosidoPureza,
    coser_por_pureza,
)
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)

logger = logging.getLogger("migracion")


def medir(nombre, trayectorias, equipos, gt, comunes, tiempos, umbral):
    """Todas las métricas del banco para un conjunto de trayectorias."""
    pred = trayectorias_a_por_frame(trayectorias, equipos)
    m = calcular_metricas_tracking(gt, pred, comunes, umbral)
    cob = cobertura_colectiva(gt, pred, comunes, umbral)
    n_por_frame = np.array([len(pred.get(f, [])) for f in sorted(tiempos)], dtype=float)
    res = resumen_equipos(accuracy_equipos(gt, pred, comunes, umbral).detalle)

    votos = defaultdict(Counter)
    for _f, emparejados in asociar_todos(gt, pred, comunes, umbral).items():
        for id_gt, id_pred in emparejados:
            votos[id_pred][id_gt] += 1
    quimeras = con10 = 0
    for cuenta in votos.values():
        total = sum(cuenta.values())
        if total >= 10:
            con10 += 1
            if cuenta.most_common(1)[0][1] / total < 0.60:
                quimeras += 1

    emparejadas = int(round(m.recall * m.n_gt))
    return {
        "nombre": nombre,
        "nids": len(trayectorias),
        "cobertura": cob.cobertura,
        "conc": float(np.median(n_por_frame)),
        "idf1": m.idf1,
        "idsw": m.id_switches,
        "tasa": m.id_switches / emparejadas if emparejadas else 0.0,
        "quimeras": quimeras,
        "con10": con10,
        "acc": res.accuracy_campo,
    }


def imprimir(filas, gt_conc):
    cab = (
        f"{'variante':<42} {'nIds':>5} {'cob.':>6} {'conc':>5} {'IDF1':>6} "
        f"{'IDSW':>5} {'tasa':>6} {'quim':>7} {'equipos':>8}"
    )
    print("\n" + "=" * len(cab))
    print(cab)
    print("-" * len(cab))
    for f in filas:
        acc = f"{f['acc']:.3f}" if f["acc"] is not None else "  N/D"
        print(
            f"{f['nombre']:<42} {f['nids']:>5} {f['cobertura']:>6.3f} "
            f"{f['conc']:>5.0f} {f['idf1']:>6.3f} {f['idsw']:>5} "
            f"{f['tasa']:>6.3f} {f['quimeras']:>3}/{f['con10']:<3} {acc:>8}"
        )
    print("-" * len(cab))
    print(f"{'referencia GT':<42} {23:>5} {1.0:>6.3f} {gt_conc:>5.0f}")
    print("=" * len(cab))


class Banco:
    """Carga una vez lo caro y mide variantes."""

    def __init__(self, cfg_path, cfg_tracking_path):
        with open(cfg_path) as f:
            self.cfg = yaml.safe_load(f)
        with open(cfg_tracking_path) as f:
            self.cfg_tracking = yaml.safe_load(f)

        self.datos = cargar_cache(self.cfg["rutas"]["cache"])
        with open(self.cfg["rutas"]["cache_colores"], "rb") as f:
            self.colores = pickle.load(f)
        homografia = np.load(self.cfg["rutas"]["homografia"])
        self.gt = gt_a_por_frame(
            parsear_cvat(self.cfg["rutas"]["ground_truth"]),
            homografia,
            frame_offset=self.cfg["alineacion"]["frame_offset"],
            paso_gt=self.cfg["alineacion"]["paso_gt"],
        )
        self.umbral = UmbralProfundidad.desde_dict(
            self.cfg["asociacion"]["umbral_profundidad"]
        )
        self.frames_ts = [(e["frame_idx"], e["t"]) for e in self.datos["cache"]]
        self.tiempos = dict(self.frames_ts)
        self.comunes = frames_comunes(self.gt, [f for f, _ in self.frames_ts])
        self.cfg_equipos = cargar_config_equipos()
        self.clasificador = entrenar_clasificador(
            self.colores, self.cfg_equipos, self.datos["cache"]
        )
        self.dt = self.datos["sample"] / self.datos["fps"]

    def clasificar(self, identidades):
        return clasificar_identidades(
            identidades, self.colores, self.clasificador, self.cfg_equipos
        )

    def medir_identidades(self, nombre, identidades, interpolar=False):
        equipos = self.clasificar(identidades)
        trayectorias = identidades_a_trayectorias(identidades)
        if interpolar:
            cfg_int = self.cfg_tracking.get("interpolacion", {})
            trayectorias = interpolar_trayectorias(
                trayectorias,
                self.frames_ts,
                max_hueco=cfg_int.get("max_hueco", 6.0),
            )
        return medir(
            nombre,
            trayectorias,
            equipos,
            self.gt,
            self.comunes,
            self.tiempos,
            self.umbral,
        )

    def bytetrack(self, **kwargs):
        return asociar_con_bytetrack(
            self.datos["cache"],
            self.datos["fps"],
            self.datos["sample"],
            ParametrosByteTrack(**kwargs),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/evaluation_v4pre.yaml")
    parser.add_argument("--config-tracking", default="configs/tracking.yaml")
    parser.add_argument(
        "--barrido",
        default=None,
        choices=["ambiguedad", "hueco", "color"],
        help="Barre un parámetro del cosido por pureza en vez de la tabla base",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    banco = Banco(args.config, args.config_tracking)
    base = banco.bytetrack()
    filas = [
        banco.medir_identidades("1. ByteTrack pelado", base),
        banco.medir_identidades("2. ByteTrack + interpolación", base, interpolar=True),
    ]

    if args.barrido is None:
        cosidas = coser_por_pureza(
            base, banco.colores, ParametrosCosidoPureza(), dt=banco.dt
        )
        filas.append(banco.medir_identidades("3. + cosido por pureza", cosidas))
        filas.append(
            banco.medir_identidades(
                "4. + cosido + interpolación", cosidas, interpolar=True
            )
        )
    else:
        valores = {
            "ambiguedad": [0.0, 0.15, 0.35, 0.6, 1.0],
            "hueco": [1.0, 2.0, 4.0, 6.0, 10.0],
            "color": [0.6, 0.9, 1.2, 1.6, 99.0],
        }[args.barrido]
        clave = {
            "ambiguedad": "margen_ambiguedad",
            "hueco": "max_hueco",
            "color": "color_max_dist",
        }[args.barrido]
        for v in valores:
            cosidas = coser_por_pureza(
                base,
                banco.colores,
                ParametrosCosidoPureza(**{clave: v}),
                dt=banco.dt,
            )
            filas.append(
                banco.medir_identidades(f"cosido {clave}={v}", cosidas, interpolar=True)
            )

    gt_conc = np.median([len(banco.gt.get(f, [])) for f in banco.comunes])
    imprimir(filas, gt_conc)
    print(
        "\nObjetivo: cobertura > 0,533 SIN empeorar quimeras (≤6), "
        "tasa de IDSW (≤0,18) ni concurrencia (≤25).\n"
    )


if __name__ == "__main__":
    main()
