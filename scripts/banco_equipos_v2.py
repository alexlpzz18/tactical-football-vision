#!/usr/bin/env python
"""Banco del brillo y el pantalón en la decisión de equipo, en las TRES patas. Plan y criterios en
docs/plan_equipos_v2.md (escritos antes de medir).

Para cada pareja (peso_v_pecho, peso_pantalon) corre el `desde_cache` de producción con la feature
v2 y mide:
- benjamín y Villaviciosa, contra su GT (`foto_de_estado.medir`): equipo equivocado (1-a-1, 2 m),
  recuento correcto por equipo, centroide;
- alevín B, sin GT: equilibrio A/B por fotograma y jugadores por equipo en el campo, en el tramo
  10-15 min y por bloques de 5 min de la parte (control de luz y sombra).

Uso:
    python scripts/banco_equipos_v2.py --pesos-v 0 0.25 0.5 1 --pesos-pantalon 0 0.5
"""

import argparse
import copy
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

SALIDA = R / "outputs/banco_equipos_v2"
PATAS = {
    "benja": {
        "config": "configs/processor_benja_v2color.yaml",
        # las cajas del caché v2 son las de producción (600/600 frames idénticos): vale su chaleco
        "cache_chaleco": "data/tracking_benja/cache_chaleco_benja.pkl",
        "gt": "data/annotations/gt_benja/annotations.xml",
        "homografia": "data/calibracion_benja/homografia_benja.npy",
        "offset": 9750,
        "campo": (62.0, 40.0),
    },
    "villa": {
        "config": "configs/processor_v2color.yaml",
        "cache": "data/tracking/cache_detecciones_v4pre_v2color_tramo.pkl",
        "cache_colores": "data/tracking/cache_colores_v4pre_v2color_tramo.pkl",
        "gt": "data/annotations/ground_truth_tracking/annotations.xml",
        "homografia": "data/calibracion/homografia.npy",
        "offset": 7500,
        "campo": (105.0, 68.0),
    },
    "alevinb": {
        "config": "data/tracking_alevinb/config_alevinb_p1.yaml",
        "cache_colores": "data/tracking_alevinb/colores_v2_alevinb_p1.pkl",
        "campo": (100.0, 64.0),
    },
}


def correr(pata: str, pv: float, pp: float) -> Path:
    """`desde_cache` de producción con los pesos dados. Devuelve el CSV."""
    from src.tracking_data.processor import procesar_desde_cache

    d = PATAS[pata]
    cfg = yaml.safe_load(open(R / d["config"]))
    cfg["modo"] = "desde_cache"
    for clave in ("cache", "cache_colores", "cache_chaleco"):
        if clave in d:
            cfg["rutas"][clave] = str(R / d[clave])
    ruta_eq = R / cfg.get("config_equipos", "configs/team_classification.yaml")
    eq = yaml.safe_load(open(ruta_eq))
    eq = copy.deepcopy(eq)
    eq.setdefault("clasificador_color", {}).update(peso_v_pecho=pv, peso_pantalon=pp)
    carpeta = SALIDA / pata
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"v{pv:g}_p{pp:g}"
    (carpeta / f"equipos_{nombre}.yaml").write_text(
        yaml.safe_dump(eq, allow_unicode=True)
    )
    cfg["config_equipos"] = str(carpeta / f"equipos_{nombre}.yaml")
    csv = carpeta / f"posiciones_{nombre}.csv"
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(carpeta / f"meta_{nombre}.json")
    procesar_desde_cache(cfg)
    return csv


def medir_con_gt(pata: str, csv: Path) -> dict:
    from foto_de_estado import medir

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    d = PATAS[pata]
    gt_m = gt_a_por_frame(
        parsear_cvat(R / d["gt"]), np.load(R / d["homografia"]), d["offset"], 15
    )
    # ⚠️ Los nombres A/B son ARBITRARIOS (el fit llama A al grupo más grande) y `medir` busca el
    # mejor emparejamiento para el equipo equivocado pero NO para el centroide. Con el brillo 0,5
    # el benjamín cambió de nombres y el centroide salió 10,98 m: era la distancia entre los dos
    # equipos, no un fallo. Se mide con los dos nombres y vale el emparejamiento bueno.
    df = pd.read_csv(csv)
    cambio = {"A": "B", "B": "A", "portero_A": "portero_B", "portero_B": "portero_A"}
    invertido = csv.with_name(csv.stem + "_AB_invertido.csv")
    df.assign(etiqueta=df.etiqueta.replace(cambio)).to_csv(invertido, index=False)
    r = min(
        (medir(c, gt_m, None, *d["campo"]) for c in (csv, invertido)),
        key=lambda x: x["centroide"],
    )
    r["nombres_invertidos"] = float(
        r["centroide"] < medir(csv, gt_m, None, *d["campo"])["centroide"]
    )
    return {k: round(float(v), 3) for k, v in r.items()}


def medir_sin_gt(csv: Path, largo: float, ancho: float) -> dict:
    """Equilibrio A/B y jugadores de campo por equipo, en el campo (porteros aparte)."""
    df = pd.read_csv(csv)
    df = df[(df.es_real == 1) & df.x_m.between(0, largo) & df.y_m.between(0, ancho)]
    df = df[df.etiqueta.isin(["A", "B"])]

    def resumen(sub):
        c = sub.groupby(["frame", "etiqueta"]).size().unstack(fill_value=0)
        for e in ("A", "B"):
            if e not in c:
                c[e] = 0
        eq = (
            c[["A", "B"]].min(axis=1) / c[["A", "B"]].max(axis=1).clip(lower=1)
        ).median()
        return {
            "equilibrio": round(float(eq), 3),
            "A": float(c.A.median()),
            "B": float(c.B.median()),
        }

    salida = {"tramo_10_15": resumen(df[df.tiempo_s.between(600, 900)])}
    bloques = {}
    for ini in range(0, int(df.tiempo_s.max()) + 1, 300):
        sub = df[df.tiempo_s.between(ini, ini + 300)]
        if len(sub):
            bloques[f"{ini // 60:02d}-{(ini + 300) // 60:02d}"] = resumen(sub)[
                "equilibrio"
            ]
    salida["equilibrio_por_5min"] = bloques
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pesos-v", type=float, nargs="+", default=[0, 0.25, 0.5, 1])
    ap.add_argument("--pesos-pantalon", type=float, nargs="+", default=[0, 0.5])
    ap.add_argument("--patas", nargs="+", default=list(PATAS))
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / "resultados.json"
    res = json.loads(ruta.read_text()) if ruta.exists() else {}
    for pv in a.pesos_v:
        for pp in a.pesos_pantalon:
            clave = f"v{pv:g}_p{pp:g}"
            for pata in a.patas:
                if clave in res.get(pata, {}):
                    continue
                csv = SALIDA / pata / f"posiciones_{clave}.csv"
                if not csv.exists():  # la medida se puede repetir sin volver a correr
                    csv = correr(pata, pv, pp)
                r = (
                    medir_sin_gt(csv, *PATAS[pata]["campo"])
                    if pata == "alevinb"
                    else medir_con_gt(pata, csv)
                )
                res.setdefault(pata, {})[clave] = r
                ruta.write_text(json.dumps(res, indent=1, ensure_ascii=False))
                print(pata, clave, json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
