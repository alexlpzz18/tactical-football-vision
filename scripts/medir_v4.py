#!/usr/bin/env python
"""Compara v4pre contra v4 en las DOS patas del banco y en los casos con nombre.

Ver docs/remedir_v4.md. No necesita GPU: consume los cachés que genere
Colab.

Uso:
    python scripts/medir_v4.py --cache-v4 data/tracking/cache_detecciones_v4.pkl \
        --colores-v4 data/tracking/cache_colores_v4.pkl
"""

import argparse
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
from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.perfiles import correr_perfil, postprocesar  # noqa: E402

EQUIV = {"arbitro": "otro", "staff": "otro"}
# Los casos que motivan el salto (ver docs/remedir_v4.md)
CASOS = {4: "A", 32: "B"}


def evaluar_benja(ruta_cache, ruta_colores):
    """Mini-GT de equipos + los casos con nombre."""
    cfg = yaml.safe_load(open("configs/processor_benja.yaml"))
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    datos = cargar_cache(ruta_cache)
    with open(ruta_colores, "rb") as f:
        colores = pickle.load(f)
    clf = entrenar_clasificador(colores, cfg_eq, datos["cache"])
    ids = correr_perfil(
        datos["cache"],
        datos["fps"],
        datos["sample"],
        cfg_tr,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=cfg_eq,
    )
    eq = clasificar_identidades(ids, colores, clf, cfg_eq)
    frames_ts = [(e["frame_idx"], e["t"]) for e in datos["cache"]]
    _tr, eq2 = postprocesar(ids, dict(eq), frames_ts, cfg_tr, perfil="bytetrack")
    pred = {i: EQUIV.get(str(v), str(v)) for i, v in eq2.items()}

    gt = pd.read_csv("data/tracking_benja/gt_equipos_benja.csv")
    gt = gt[gt.equipo_real.notna() & (gt.equipo_real != "")]
    gt["real"] = gt.equipo_real.map(lambda x: EQUIV.get(str(x), str(x)))
    aciertos = pesos = 0.0
    for id_j, g in gt.groupby("id_jugador"):
        cuenta = Counter(g.real)
        dom, n = cuenta.most_common(1)[0]
        peso = float(g.n_obs.iloc[0]) * (n / len(g))
        aciertos += peso * (pred.get(int(id_j)) == dom)
        pesos += peso
    return {
        "acc": aciertos / pesos if pesos else 0.0,
        "n_ids": len(ids),
        "casos": {i: pred.get(i) for i in CASOS},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-v4", required=True)
    parser.add_argument("--colores-v4", required=True)
    parser.add_argument("--cache-benja-v4", default=None)
    parser.add_argument("--colores-benja-v4", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    print("\n── PATA 1: Villaviciosa (GT de tracking) ──")
    cab = (
        f"{'modelo':<10}{'nIds':>6}{'cob.':>8}{'conc':>6}{'IDF1':>8}"
        f"{'tasa':>7}{'quim':>7}{'equipos':>9}"
    )
    print(cab)
    print("-" * len(cab))
    filas = {}
    for nombre, cfg_banco in (
        ("v4pre", "configs/evaluation_v4pre.yaml"),
        ("v4", None),
    ):
        if cfg_banco is None:
            cfg = yaml.safe_load(open("configs/evaluation_v4pre.yaml"))
            cfg["rutas"]["cache"] = args.cache_v4
            cfg["rutas"]["cache_colores"] = args.colores_v4
            ruta = "/tmp/eval_v4.yaml"
            yaml.safe_dump(cfg, open(ruta, "w"), allow_unicode=True)
            cfg_banco = ruta
        b = Banco(cfg_banco, "configs/tracking.yaml")
        ids = correr_perfil(
            b.datos["cache"],
            b.datos["fps"],
            b.datos["sample"],
            b.cfg_tracking,
            perfil="bytetrack",
            colores=b.colores,
            clasificador=b.clasificador,
            cfg_equipos=b.cfg_equipos,
        )
        eq = b.clasificar(ids)
        tr, eq2 = postprocesar(
            ids, dict(eq), b.frames_ts, b.cfg_tracking, perfil="bytetrack"
        )
        m = medir(nombre, tr, eq2, b.gt, b.comunes, b.tiempos, b.umbral)
        filas[nombre] = m
        print(
            f"{nombre:<10}{m['nids']:>6}{m['cobertura']:>8.3f}{m['conc']:>6.0f}"
            f"{m['idf1']:>8.3f}{m['tasa']:>7.3f}"
            f"{m['quimeras']:>4}/{m['con10']:<2}{m['acc'] or 0:>9.3f}"
        )

    if args.cache_benja_v4:
        print("\n── PATA 2: benjamín (mini-GT de equipos) ──")
        b4 = evaluar_benja(args.cache_benja_v4, args.colores_benja_v4)
        print(f"  accuracy por observación: {b4['acc']:.3f}  (v4pre: 0.883)")
        print(f"  identidades: {b4['n_ids']}  (v4pre: 67)")
        print("\n── CASOS CON NOMBRE ──")
        for id_j, esperado in CASOS.items():
            sale = b4["casos"].get(id_j)
            ok = "✓ ARREGLADO" if sale == esperado else f"✗ sigue saliendo {sale}"
            print(f"  id {id_j}: debería ser {esperado} → {ok}")

    a, v = filas.get("v4pre"), filas.get("v4")
    if a and v:
        mejora_todo = (
            v["cobertura"] >= a["cobertura"]
            and v["idf1"] >= a["idf1"]
            and v["quimeras"] <= a["quimeras"]
            and abs(v["conc"] - 22) <= abs(a["conc"] - 22)
        )
        print(
            "\n→ "
            + (
                "MEJORA TODO sin degradar nada: se adopta directamente "
                "(excepción vigente)."
                if mejora_todo
                else "NO mejora todas las métricas: la decisión es de Alex, "
                "con la tabla delante."
            )
        )


if __name__ == "__main__":
    main()
