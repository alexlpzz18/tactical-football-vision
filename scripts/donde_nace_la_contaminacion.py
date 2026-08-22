#!/usr/bin/env python
"""¿DÓNDE cambia de persona una identidad contaminada? Diagnóstico puro.

El hueco que quedó abierto: 15 de 24 identidades contienen más de una
persona, y las dos vías investigadas —re-entrada y cruces— no lo
explican. Saltar a "admitir incertidumbre" sin saber dónde nace sería
resignarse sin diagnóstico.

Este script no construye nada. Localiza el instante exacto de cada cambio
de persona y lo caracteriza: quién había cerca, si estaba ocluido,
cortado por el borde, en qué profundidad, si venía de un hueco, y si el
intercambio es entre compañeros o entre rivales.

Si sale un patrón, se ataca. Si sale "en sitios distintos sin nada en
común", es irreducible con una cámara y el plan B queda justificado.

Limitación que hay que tener presente: la identidad del GT solo existe 1
de cada 15 fotogramas, así que el instante del cambio se localiza con
±0,5 s de resolución. Todo lo demás (cajas, solapes, huecos) sí es a
cadencia nativa.

Uso:
    python scripts/donde_nace_la_contaminacion.py
"""

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from pureza_sin_reentrada import duenos  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402

logger = logging.getLogger("contaminacion")
MARGEN_BORDE = 60  # px del borde del encuadre para considerarlo "cortado"
ANCHO, ALTO = 1920, 1080


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    H = np.load(cfg["rutas"]["homografia"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    conf = float(cfg_tr.get("confianza_min", 0) or 0)
    cache, colores = filtrar_por_confianza(datos["cache"], colores, conf)
    gt = gt_a_por_frame(parsear_cvat(args.gt), H, frame_offset=9750, paso_gt=15)
    mapa = duenos(cache, gt)
    cajas = {
        (e["frame_idx"], i): d[2:6] for e in cache for i, d in enumerate(e["dets"])
    }
    por_frame_cajas = {e["frame_idx"]: [d[2:6] for d in e["dets"]] for e in cache}

    equipo, pos_gt = {}, {}
    for f, obs in gt.items():
        for o in obs:
            equipo.setdefault(o.obj_id, str(o.team).replace("portero_", ""))
            pos_gt.setdefault(f, {})[o.obj_id] = np.array(
                [float(o.pos[0]), float(o.pos[1])]
            )

    ids = asociar_con_bytetrack(
        cache,
        datos["fps"],
        datos["sample"],
        ParametrosByteTrack.desde_dict(cfg_tr.get("bytetrack")),
    )

    eventos = []
    for k, ident in enumerate(ids, start=1):
        obs = sorted((par for tr in ident for par in tr.det_idxs), key=lambda p: p[0])
        etiquetadas = [(par, mapa.get(tuple(par))) for par in obs]
        marcadas = [(par, g) for par, g in etiquetadas if g is not None]
        if len({g for _p, g in marcadas}) < 2:
            continue
        for i in range(1, len(marcadas)):
            ga = marcadas[i - 1][1]
            par_b, gb = marcadas[i]
            if ga == gb:
                continue
            f = par_b[0]
            caja = cajas.get(tuple(par_b))
            # ¿quién había cerca, en metros?
            otros = [
                float(np.linalg.norm(pos_gt[f][g] - pos_gt[f][gb]))
                for g in pos_gt.get(f, {})
                if g != gb
            ]
            # ¿solape con otra caja?
            vecinas = por_frame_cajas.get(f, [])
            solape = (
                max(
                    (iou(caja, c) for c in vecinas if tuple(c) != tuple(caja)),
                    default=0.0,
                )
                if caja is not None
                else 0.0
            )
            # hueco de detección: fotogramas desde la observación anterior
            idx = obs.index(par_b)
            hueco = (par_b[0] - obs[idx - 1][0]) / datos["fps"] if idx else 0.0
            cortada = caja is not None and (
                caja[0] < MARGEN_BORDE
                or caja[2] > ANCHO - MARGEN_BORDE
                or caja[1] < MARGEN_BORDE
            )
            eventos.append(
                {
                    "id": k,
                    "frame": f,
                    "t": f / datos["fps"],
                    "de": ga,
                    "a": gb,
                    "mismo_eq": equipo.get(ga) == equipo.get(gb),
                    "d_min": min(otros) if otros else np.nan,
                    "solape": solape,
                    "cortada": bool(cortada),
                    "alto": float(caja[3] - caja[1]) if caja is not None else np.nan,
                    "y_m": float(pos_gt[f][gb][1]) if f in pos_gt else np.nan,
                    "hueco_s": hueco,
                }
            )

    import pandas as pd

    e = pd.DataFrame(eventos)
    print(
        f"\nIdentidades contaminadas: "
        f"{e.id.nunique()} · cambios de persona localizados: {len(e)}\n"
    )

    print("── QUÉ PASA EN EL INSTANTE DEL CAMBIO ──\n")
    print(f"  del MISMO equipo: {e.mismo_eq.sum()} ({e.mismo_eq.mean():.0%})")
    print(
        f"  distancia a la persona más cercana: mediana "
        f"{e.d_min.median():.2f} m · p25 {e.d_min.quantile(.25):.2f} · "
        f"p75 {e.d_min.quantile(.75):.2f}"
    )
    print(
        f"    a menos de 2,5 m (lo que llamábamos 'cruce'): "
        f"{(e.d_min < 2.5).sum()} ({(e.d_min < 2.5).mean():.0%})"
    )
    print(
        f"  solape con otra caja > 0,1: {(e.solape > 0.1).sum()} "
        f"({(e.solape > 0.1).mean():.0%})"
    )
    print(f"  caja CORTADA por el borde: {e.cortada.sum()} ({e.cortada.mean():.0%})")
    print(
        f"  hueco de detección previo > 0,3 s: {(e.hueco_s > 0.3).sum()} "
        f"({(e.hueco_s > 0.3).mean():.0%})"
    )
    print(f"  altura de caja: mediana {e.alto.median():.0f} px")

    print("\n── POR FRANJA DE PROFUNDIDAD ──\n")
    cab = f"{'franja':<12}{'cambios':>9}{'% del total':>13}{'d_min medio':>14}"
    print(cab)
    print("-" * len(cab))
    for nombre, lo, hi in (("10-20 m", 10, 20), ("20-30 m", 20, 30), ("30+ m", 30, 99)):
        s = e[(e.y_m >= lo) & (e.y_m < hi)]
        if len(s):
            print(
                f"{nombre:<12}{len(s):>9}{len(s)/len(e):>12.0%}"
                f"{s.d_min.mean():>13.2f}m"
            )

    print("\n── ¿HAY PATRÓN? ──\n")
    condiciones = {
        "alguien a menos de 2,5 m": (e.d_min < 2.5),
        "alguien a menos de 5 m": (e.d_min < 5.0),
        "solape de cajas > 0,1": (e.solape > 0.1),
        "caja cortada por el borde": e.cortada,
        "hueco previo > 0,3 s": (e.hueco_s > 0.3),
    }
    for nombre, cond in condiciones.items():
        print(f"  {nombre:<30}{cond.sum():>4} de {len(e)} ({cond.mean():>4.0%})")
    ninguna = ~(
        condiciones["alguien a menos de 5 m"]
        | condiciones["solape de cajas > 0,1"]
        | condiciones["caja cortada por el borde"]
        | condiciones["hueco previo > 0,3 s"]
    )
    print(
        f"\n  SIN ninguna de las anteriores: {ninguna.sum()} " f"({ninguna.mean():.0%})"
    )

    print("\n── LOS 8 CASOS MÁS GORDOS (para mirarlos a ojo) ──\n")
    for r in e.nlargest(8, "alto").itertuples():
        m, s = divmod(r.t, 60)
        print(
            f"  id {r.id:>3} · {int(m)}:{s:04.1f} · persona {r.de}→{r.a}"
            f" {'(mismo equipo)' if r.mismo_eq else ''} · "
            f"vecino a {r.d_min:.1f} m · solape {r.solape:.2f} · "
            f"{'CORTADA' if r.cortada else ''} hueco {r.hueco_s:.1f}s"
        )


if __name__ == "__main__":
    main()
