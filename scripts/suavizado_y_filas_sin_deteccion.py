#!/usr/bin/env python
"""¿Por qué hay filas `es_real=1` a más de 1 m de toda detección? (BACKLOG 31)

Alex (21-sep-2026): *«la pista de las filas es_real=1 a más de 1 m de toda detección:
mídela, es sospechosa y barata de mirar.»* Es el análogo de las «alas» del balón
(`docs/balon_sin_alas.md`): una fila marcada real tiene que coincidir con una
detección.

Vuelve a correr el procesador DESDE EL CACHÉ (CPU, ~1 min por pasada) dos veces con
el mismo config de producción: con el suavizado de 0,5 s y SIN él, y compara:

1. **Control**: la pasada con suavizado tiene que reproducir el CSV de producción
   (`--csv-produccion`). Si no, todo lo demás no vale.
2. Distancia de cada fila real a la detección cruda más cercana, por zona.
3. Error contra el GT de cada versión (mismo protocolo que `desglose_del_error.py`).

No toca producción: las salidas van a `--salida-dir`.

Uso:
    python scripts/suavizado_y_filas_sin_deteccion.py --salida-dir /tmp/suavizado
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from desglose_del_error import (  # noqa: E402
    _valor_por_subconjunto,
    construir_frames,
)
from src.evaluation.desglose_error import (  # noqa: E402
    FACTORES,
    escalera_por_frame_equipo,
    shapley,
)
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking_data.processor import procesar_partido  # noqa: E402


def preparar_configs(args, salida: Path) -> dict:
    """Dos configs idénticos salvo `suavizado.activo` (y rutas de salida)."""
    with open(args.config_tracking) as f:
        tracking = yaml.safe_load(f)
    sin = dict(tracking)
    sin["suavizado"] = {**tracking["suavizado"], "activo": False}
    ruta_sin = salida / "tracking_sin_suavizado.yaml"
    ruta_sin.write_text(yaml.safe_dump(sin))
    with open(args.config) as f:
        base = yaml.safe_load(f)
    base["modo"] = "desde_cache"
    base["checkpoint"] = {"reanudar": False, "cada_frames": 500}
    configs = {}
    for nombre, ruta_tracking in (
        ("con", args.config_tracking),
        ("sin", str(ruta_sin)),
    ):
        cfg = dict(base)
        cfg["config_tracking"] = ruta_tracking
        cfg["rutas"] = {
            **base["rutas"],
            "salida_csv": str(salida / f"posiciones_{nombre}.csv"),
            "salida_meta": str(salida / f"posiciones_{nombre}_meta.json"),
        }
        ruta_cfg = salida / f"processor_{nombre}.yaml"
        ruta_cfg.write_text(yaml.safe_dump(cfg))
        configs[nombre] = ruta_cfg
    return configs


def distancia_a_deteccion(filas: pd.DataFrame, dets: dict) -> np.ndarray:
    dist = np.full(len(filas), np.inf)
    for frame, g in filas.groupby("frame"):
        D = dets.get(frame)
        if D is not None and len(D):
            d = np.hypot(
                g.x_m.to_numpy()[:, None] - D[None, :, 0],
                g.y_m.to_numpy()[:, None] - D[None, :, 1],
            )
            dist[filas.index.get_indexer(g.index)] = d.min(1)
    return dist


def comparacion_pareada(gt_m: dict, con: pd.DataFrame, sin: pd.DataFrame) -> None:
    """Diferencia pareada por (frame, equipo) con IC95 % por remuestreo de bloques de 5 s.

    Un solo GT de 30 s: la comparación pareada es lo único que dice si el signo aguanta.
    """
    errores = {}
    for nombre, m in (("con", con), ("sin", sin)):
        r = m[m.es_real == 1].reset_index(drop=True)
        R = pd.DataFrame(escalera_por_frame_equipo(construir_frames(gt_m, r, 2.0))[0])
        errores[nombre] = R[R.arreglos == frozenset()].set_index(["frame", "equipo"])
    J = (
        errores["con"]
        .join(errores["sin"], lsuffix="_c", rsuffix="_s", how="inner")
        .reset_index()
    )
    J["bloque"] = (J.frame - J.frame.min()) // 150  # 150 frames = 5 s
    rng = np.random.default_rng(0)
    print(
        "\n3. DIFERENCIA PAREADA CON − SIN suavizado (positivo = el suavizado es PEOR)"
    )
    for metrica in ("centroide", "ancho", "prof"):
        d = J[metrica + "_c"] - J[metrica + "_s"]
        bl = J.assign(d=d).groupby("bloque").d.agg(["sum", "size"])
        sumas, tam = bl["sum"].to_numpy(), bl["size"].to_numpy()
        boot = []
        for _ in range(4000):
            k = rng.integers(0, len(bl), len(bl))
            boot.append(sumas[k].sum() / tam[k].sum())
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(
            f"   {metrica:10s} {d.mean():+.3f} m · IC95 % [{lo:+.3f}, {hi:+.3f}] ({len(J)} pares)"
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_parte_entera.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_benja.yaml")
    p.add_argument(
        "--csv-produccion", default="data/tracking_benja/posiciones_benja_p1_v3.csv"
    )
    p.add_argument(
        "--dets", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument("--salida-dir", required=True)
    p.add_argument(
        "--reusar", action="store_true", help="no vuelve a correr si ya existen"
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    salida = Path(args.salida_dir)
    salida.mkdir(parents=True, exist_ok=True)
    configs = preparar_configs(args, salida)
    for nombre, cfg in configs.items():
        destino = salida / f"posiciones_{nombre}.csv"
        if not (args.reusar and destino.exists()):
            procesar_partido(str(cfg), modo="desde_cache")

    con = pd.read_csv(salida / "posiciones_con.csv")
    sin = pd.read_csv(salida / "posiciones_sin.csv")
    prod = pd.read_csv(args.csv_produccion)
    identico = len(prod) == len(con) and np.allclose(prod.x_m, con.x_m)
    print(f"0. CONTROL: la pasada CON suavizado reproduce producción: {identico}")
    assert identico, "el control falla: no se puede comparar"

    with open(args.dets, "rb") as f:
        dets = {
            e["frame_idx"]: np.array(e["dets"]).reshape(-1, 7)
            for e in pickle.load(f)["cache"]
        }
    gt_m = gt_a_por_frame(parsear_cvat(args.gt), np.load(args.homografia), 9750, 15)

    print("\n1. DISTANCIA DE LAS FILAS es_real=1 A LA DETECCIÓN CRUDA MÁS CERCANA")
    for nombre, m in (("CON suavizado", con), ("SIN suavizado", sin)):
        r = m[m.es_real == 1].reset_index(drop=True)
        r["d"] = distancia_a_deteccion(r, dets)
        r["zona"] = pd.cut(r.x_m, [-99, 20, 40, 99], labels=["x<20", "20-40", "x>40"])
        print(
            f"   {nombre}: {len(r)} filas · mediana {r.d.median():.3f} m"
            f" · p99 {r.d.quantile(.99):.2f} m · >1 m: {(r.d > 1).mean():.1%}"
            f" · >2 m: {(r.d > 2).mean():.1%}"
        )
        z = r.groupby("zona", observed=True).d.agg(lambda s: (s > 1).mean())
        print(
            "      >1 m por zona: " + " · ".join(f"{k} {v:.1%}" for k, v in z.items())
        )

    print("\n2. ERROR CONTRA EL GT (radio 2 m; media por equipo y frame)")
    print(
        f"   {'':14s} {'centroide':>10s} {'casadas':>8s} {'equipo mal':>11s} "
        + " ".join(f"{f:>5s}" for f in FACTORES)
    )
    for nombre, m in (("CON suavizado", con), ("SIN suavizado", sin)):
        r = m[m.es_real == 1].reset_index(drop=True)
        frames = construir_frames(gt_m, r, 2.0)
        R = pd.DataFrame(escalera_por_frame_equipo(frames)[0])
        v = _valor_por_subconjunto(R, "centroide", "media")
        sh = shapley(v)
        casadas = sum(p.fila is not None for fc in frames for p in fc.personas)
        mal = sum(
            1
            for fc in frames
            for p in fc.personas
            if p.fila is not None
            and fc.etiqueta[p.fila] in ("A", "B")
            and fc.etiqueta[p.fila] != p.equipo
        )
        print(
            f"   {nombre:14s} {v[frozenset()]:10.2f} {casadas:8d} {mal:11d} "
            + " ".join(f"{sh[f]:5.2f}" for f in FACTORES)
        )
    comparacion_pareada(gt_m, con, sin)


if __name__ == "__main__":
    main()
