#!/usr/bin/env python
"""Replay del GT: el TECHO VISUAL del producto.

Cómo se vería el replay si el tracking fuera perfecto. Sirve para dos
cosas que no se pueden hacer con el replay real:

1. **Ajustar formato y estética sabiendo que ningún fallo es del
   tracking.** Si algo se ve raro aquí, es del replay o de la homografía.
2. **Tener la referencia** contra la que comparar el replay real.

Proyecta los clics del GT con la misma homografía que usa el sistema, así
que cualquier deriva de la calibración aparece igual en los dos.

Uso:
    python scripts/gt_a_replay.py \\
        --clics data/annotations/gt_benja/clics.csv \\
        --equipos "1:A,...,14:B"
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking_data.processor import project_point  # noqa: E402

logger = logging.getLogger("gt_replay")

EQUIPO_A_ENTERO = {"A": 0, "portero_A": 0, "B": 1, "portero_B": 1, "otro": 2}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clics", required=True)
    p.add_argument("--config", default="configs/processor_benja_emb.yaml")
    p.add_argument("--equipos", required=True)
    p.add_argument("--salida-csv", default="data/annotations/gt_benja/gt_replay.csv")
    p.add_argument(
        "--sin-corregir-pies",
        action="store_true",
        help=(
            "No baja los clics al suelo. Con la corrección el "
            "desplazamiento mediano pasa de 1,58 m a 0,42 m."
        ),
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(open(args.config))
    H = np.load(cfg["rutas"]["homografia"])
    equipos = {}
    for par in filter(None, args.equipos.split(",")):
        j, eq = par.split(":")
        equipos[int(j)] = eq

    df = pd.read_csv(args.clics)
    if not args.sin_corregir_pies:
        from src.evaluation.correccion_pies import corregir_clics
        from src.tracking.cache_io import cargar_cache

        ruta_cache = (
            cfg["rutas"]["cache"]
            if "cfg" in dir()
            else "data/tracking_benja/cache_detecciones_benja_v4.pkl"
        )
        df = corregir_clics(df, cargar_cache(ruta_cache)["cache"])
    faltan = set(df.jugador.unique()) - set(equipos)
    if faltan:
        logger.warning("⚠ Sin equipo asignado: %s (irán como 'otro')", sorted(faltan))

    filas = []
    for fila in df.itertuples():
        etiqueta = equipos.get(int(fila.jugador), "otro")
        mx, my = project_point(float(fila.x_px), float(fila.y_px), H)
        filas.append(
            {
                "frame": int(fila.frame),
                "tiempo_s": round(float(fila.t_s), 2),
                "id_jugador": int(fila.jugador),
                "equipo": EQUIPO_A_ENTERO.get(etiqueta, 2),
                "etiqueta": etiqueta,
                "x_m": round(mx, 2),
                "y_m": round(my, 2),
                "es_real": 1,
            }
        )
    salida = pd.DataFrame(filas).sort_values(["frame", "id_jugador"])
    Path(args.salida_csv).parent.mkdir(parents=True, exist_ok=True)
    salida.to_csv(args.salida_csv, index=False)

    # El replay lee los colores reales del meta que acompaña al CSV
    meta_real = Path(cfg["rutas"]["salida_meta"])
    colores = {}
    if meta_real.exists():
        colores = json.load(open(meta_real)).get("colores_equipo", {})
    meta = {
        "colores_equipo": colores,
        "campo_m": cfg["campo_m"]["largo"]
        and [cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]],
        "fuente": "GT MANUAL — techo visual, no salida del sistema",
        "n_identidades": int(salida.id_jugador.nunique()),
    }
    ruta_meta = str(Path(args.salida_csv).with_suffix("")) + "_meta.json"
    json.dump(meta, open(ruta_meta, "w"), indent=2, ensure_ascii=False)

    dentro = (
        (salida.x_m.between(0, cfg["campo_m"]["largo"]))
        & (salida.y_m.between(0, cfg["campo_m"]["ancho"]))
    ).mean()
    print(f"\n✓ {args.salida_csv}")
    print(f"  {len(salida)} posiciones, {salida.id_jugador.nunique()} jugadores")
    print(
        f"  dentro del campo ({cfg['campo_m']['largo']}×{cfg['campo_m']['ancho']} m): "
        f"{dentro:.1%}"
    )
    print(
        f"  rango x [{salida.x_m.min():.1f}, {salida.x_m.max():.1f}] · "
        f"y [{salida.y_m.min():.1f}, {salida.y_m.max():.1f}]"
    )
    print(f"  colores: {colores or '(sin meta del sistema)'}")


if __name__ == "__main__":
    main()
