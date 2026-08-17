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

import numpy as np
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


def _identidades_y_etiquetas(ruta_cache, ruta_colores):
    """(identidades, etiquetas) del benjamín con el caché que se le dé."""
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
    return ids, {i: EQUIV.get(str(v), str(v)) for i, v in eq2.items()}


def _traspasar_etiquetas(ids_origen, ids_destino):
    """{id_destino: id_origen} emparejando por solape ESPACIO-TEMPORAL.

    Imprescindible, y es un fallo que costó una medición: el mini-GT de
    equipos está etiquetado sobre los ids del v4pre, y esos ids NO
    sobreviven a un cambio de detector. Medido: 27 de las 30 identidades
    del mini-GT caen a más de 5 m de donde estaba la misma id con el v4
    (mediana 38 m) — el id 8 era el portero lejano y pasa a estar en la
    portería contraria.

    Comparar por número de id es comparar personas distintas. Lo que sí
    sobrevive es DÓNDE y CUÁNDO estuvo cada identidad, así que la
    correspondencia se hace por ahí.
    """

    def por_frame(identidades):
        indice = {}
        for i, ident in enumerate(identidades, start=1):
            for tr in ident:
                for pos, (f, _d) in zip(tr.pos, tr.det_idxs):
                    indice.setdefault(f, []).append((i, np.asarray(pos)))
        return indice

    origen, destino = por_frame(ids_origen), por_frame(ids_destino)
    votos: dict[int, Counter] = {}
    for f, lista_d in destino.items():
        for i_d, pos_d in lista_d:
            mejor, dmin = None, 2.0  # 2 m: la misma persona en el mismo frame
            for i_o, pos_o in origen.get(f, []):
                dist = float(np.linalg.norm(pos_o - pos_d))
                if dist < dmin:
                    mejor, dmin = i_o, dist
            if mejor is not None:
                votos.setdefault(i_d, Counter())[mejor] += 1
    return {i_d: c.most_common(1)[0][0] for i_d, c in votos.items() if c}


def evaluar_benja(ruta_cache, ruta_colores, ruta_cache_ref=None, ruta_colores_ref=None):
    """Mini-GT de equipos + los casos con nombre.

    `ruta_cache_ref` son los cachés SOBRE LOS QUE se etiquetó el mini-GT.
    Se necesitan porque los ids no sobreviven a un cambio de detector
    (ver _traspasar_etiquetas): sin ellos se compararían personas
    distintas y el resultado no significaría nada.
    """
    ids, pred_por_id = _identidades_y_etiquetas(ruta_cache, ruta_colores)
    if ruta_cache_ref:
        ids_ref, _ = _identidades_y_etiquetas(ruta_cache_ref, ruta_colores_ref)
        mapa = _traspasar_etiquetas(ids_ref, ids)
        pred = {}
        for i_nuevo, etiqueta in pred_por_id.items():
            i_viejo = mapa.get(i_nuevo)
            if i_viejo is not None:
                pred[i_viejo] = etiqueta
        print(
            f"  (etiquetas trasladadas por posición: {len(pred)} de "
            f"{len(pred_por_id)} identidades encontraron su equivalente)"
        )
    else:
        pred = pred_por_id

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
        b4 = evaluar_benja(
            args.cache_benja_v4,
            args.colores_benja_v4,
            ruta_cache_ref="data/tracking_benja/cache_detecciones_benja.pkl",
            ruta_colores_ref="data/tracking_benja/cache_colores_benja.pkl",
        )
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
