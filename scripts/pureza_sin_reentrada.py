#!/usr/bin/env python
"""¿Cuánta contaminación mete NUESTRA propia puerta de re-entrada?

El experimento barato que nunca se había hecho. Se desactiva la
re-entrada por completo —buffer a cero, así que cada reaparición abre un
tracklet nuevo— y se mide la PUREZA de lo que sale.

Lo que decide:

- **Si sin re-entrada la pureza es alta**, la contaminación la mete el
  mecanismo de recuperación, y el grafo global tiene material limpio con
  el que trabajar: solo hay que unir bien.
- **Si sin re-entrada la pureza ya es baja**, la mezcla ocurre DENTRO del
  seguimiento continuo (en los cruces), y ningún método de unión posterior
  lo arregla — habría que atacar la asociación por frame.

Es la pregunta que hay que responder antes de construir nada encima.

Uso:
    python scripts/pureza_sin_reentrada.py
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

from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402

logger = logging.getLogger("pureza")
RADIO_BASE, RADIO_POR_METRO, RADIO_MAX = 1.5, 0.09, 6.0


def radio(y):
    return float(np.clip(RADIO_BASE + RADIO_POR_METRO * y, RADIO_BASE, RADIO_MAX))


def duenos(cache, gt):
    """{(frame, det_idx): obj_id} — a quién pertenece cada detección."""
    mapa = {}
    for entrada in cache:
        f = entrada["frame_idx"]
        obs = gt.get(f)
        if not obs:
            continue
        usados = set()
        for o in obs:
            gx, gy = float(o.pos[0]), float(o.pos[1])
            mejor, dmin = None, radio(gy)
            for i, d in enumerate(entrada["dets"]):
                if i in usados:
                    continue
                dist = float(np.hypot(d[0] - gx, d[1] - gy))
                if dist < dmin:
                    mejor, dmin = i, dist
            if mejor is not None:
                usados.add(mejor)
                mapa[(f, mejor)] = o.obj_id
    return mapa


def analizar(identidades, mapa):
    """Pureza de los tracklets y fragmentación de las personas."""
    puros = impuros = 0
    obs_puras = obs_totales = 0
    por_persona = {}
    for k, ident in enumerate(identidades, start=1):
        gids = []
        for tr in ident:
            for par in tr.det_idxs:
                g = mapa.get(tuple(par))
                if g is not None:
                    gids.append(g)
        if not gids:
            continue
        cuenta = {}
        for g in gids:
            cuenta[g] = cuenta.get(g, 0) + 1
        dominante = max(cuenta, key=cuenta.get)
        obs_totales += len(gids)
        obs_puras += cuenta[dominante]
        if len(cuenta) == 1:
            puros += 1
        else:
            impuros += 1
        por_persona.setdefault(dominante, []).append(len(gids))
    n = puros + impuros
    return {
        "tracklets": n,
        "puros": puros,
        "impuros": impuros,
        "pct_puros": puros / max(n, 1),
        "pureza_obs": obs_puras / max(obs_totales, 1),
        "personas": len(por_persona),
        "frag": n / max(len(por_persona), 1),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--frame-ini", type=int, default=9750)
    p.add_argument("--paso-gt", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    H = np.load(cfg["rutas"]["homografia"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    cache, colores = filtrar_por_confianza(
        datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    gt = gt_a_por_frame(
        parsear_cvat(args.gt), H, frame_offset=args.frame_ini, paso_gt=args.paso_gt
    )
    mapa = duenos(cache, gt)
    print(f"\nDetecciones casadas con el GT: {len(mapa)}")

    base = dict(cfg_tr.get("bytetrack") or {})
    cab = (
        f"{'buffer de re-entrada':<26}{'tracklets':>11}{'puros':>8}"
        f"{'% puros':>9}{'pureza obs':>12}{'frag.':>8}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    for nombre, buf in (
        ("0,0 s (SIN re-entrada)", 0.001),
        ("0,5 s", 0.5),
        ("1,5 s (el adoptado)", 1.5),
        ("3,0 s", 3.0),
    ):
        ids = asociar_con_bytetrack(
            cache,
            datos["fps"],
            datos["sample"],
            ParametrosByteTrack.desde_dict({**base, "buffer_perdido_s": buf}),
        )
        r = analizar(ids, mapa)
        print(
            f"{nombre:<26}{r['tracklets']:>11}{r['puros']:>8}{r['pct_puros']:>8.0%}"
            f"{r['pureza_obs']:>12.1%}{r['frag']:>8.1f}"
        )
    print("-" * len(cab))
    print(f"  personas reales en el GT: {len(set(mapa.values()))}")
    print(
        "\n  'pureza obs' = fracción de observaciones que pertenecen a la\n"
        "  persona dominante de su tracklet. Es la que importa: un tracklet\n"
        "  impuro con una sola observación ajena no es lo mismo que uno\n"
        "  mitad y mitad.\n"
        "  'frag.' = tracklets por persona real."
    )


if __name__ == "__main__":
    main()
