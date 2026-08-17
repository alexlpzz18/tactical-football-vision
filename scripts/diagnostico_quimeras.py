#!/usr/bin/env python
"""Paso 0 del diseño de apariencia: ¿dónde NACEN las quimeras?

La hipótesis a validar antes de construir nada (docs/apariencia_en_asociacion.md):
la quimera nace en el instante en que dos cajas se solapan y ByteTrack,
que solo mira IoU en píxeles, se queda sin criterio para distinguirlas.

Si la mayoría de los cambios de persona NO ocurren con una caja
solapada al lado, la hipótesis es falsa y el camino A no sirve.

El control es lo que da valor a la cifra: se compara el solape en los
frames de CAMBIO contra el solape en los frames normales de las mismas
identidades. Sin ese control, "el 70 % tenía una caja cerca" no dice
nada — puede ser que SIEMPRE haya una caja cerca.
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco  # noqa: E402
from src.tracking.cosido_pureza import (  # noqa: E402
    ParametrosCosidoPureza,
    coser_por_pureza,
)


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
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking.yaml")
    p.add_argument("--conf", type=float, default=0.45)
    p.add_argument("--umbral-solape", type=float, default=0.1)
    p.add_argument(
        "--ventana",
        type=int,
        default=3,
        help="Muestras previas en las que buscar el solape",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    from barrido_v4 import filtrar_por_confianza

    banco = Banco(args.config, args.config_tracking)
    filtrar_por_confianza(banco, args.conf)
    ids = banco.bytetrack(
        buffer_perdido_s=1.5, umbral_emparejamiento=0.995, min_frames_consecutivos=2
    )
    ids = coser_por_pureza(
        ids,
        banco.colores,
        ParametrosCosidoPureza(max_hueco=4.0, color_max_dist=0.9),
        dt=banco.dt,
    )

    # Cajas por frame, para poder medir el solape en cualquier instante
    cajas = {e["frame_idx"]: [d[2:6] for d in e["dets"]] for e in banco.datos["cache"]}

    # Equipo de cada id del GT, para saber si la quimera mezcla dos
    # jugadores del MISMO equipo — esas la puerta de color no las ve.
    equipo_gt = {}
    for g in banco.gt.values():
        for o in g:
            equipo_gt.setdefault(o.obj_id, o.team)

    # A quién pertenece cada observación según el GT (el más cercano en metros)
    cambios, normales, n_quimeras = [], [], 0
    quim_mismo_equipo = quim_distinto = 0
    huecos_cam, huecos_nor = [], []
    for ident in ids:
        obs = []
        for tr in ident:
            for pos, (f, di) in zip(tr.pos, tr.det_idxs):
                g = banco.gt.get(f)
                if not g:
                    continue
                mejor, dmin = None, banco.umbral.para(float(pos[1]))
                for o in g:
                    d = float(np.linalg.norm(np.asarray(o.pos) - np.asarray(pos)))
                    if d < dmin:
                        mejor, dmin = o.obj_id, d
                if mejor is not None:
                    obs.append((f, di, mejor))
        obs.sort()
        personas = {o[2] for o in obs}
        if len(personas) > 1:
            n_quimeras += 1
            equipos = {equipo_gt.get(i) for i in personas}
            # Normalizamos portero_A → A: un portero y un jugador de campo
            # del mismo equipo visten distinto, así que cuentan como
            # colores distintos aunque el GT los agrupe.
            if len(equipos) == 1:
                quim_mismo_equipo += 1
            else:
                quim_distinto += 1
        for k in range(1, len(obs)):
            # La oclusión EMPIEZA antes del salto: el track se pierde
            # mientras dos cuerpos se tapan y se recupera ya sobre el
            # otro. Mirar solo el frame del cambio subestima el solape,
            # así que se toma el máximo de la ventana previa.
            vecino = 0.0
            for j in range(max(0, k - args.ventana), k + 1):
                f, di, _ = obs[j]
                lista = cajas.get(f, [])
                if di >= len(lista):
                    continue
                vecino = max(
                    [vecino]
                    + [iou(lista[di], otra) for m, otra in enumerate(lista) if m != di]
                )
            hueco = obs[k][0] - obs[k - 1][0]
            if obs[k][2] != obs[k - 1][2]:
                cambios.append(vecino)
                huecos_cam.append(hueco)
            else:
                normales.append(vecino)
                huecos_nor.append(hueco)

    cam, nor = np.array(cambios), np.array(normales)
    u = args.umbral_solape
    print(f"\nIdentidades con más de una persona del GT: {n_quimeras}")
    if n_quimeras:
        pct = 100 * quim_mismo_equipo / n_quimeras
        print(
            f"  del MISMO equipo: {quim_mismo_equipo} ({pct:.0f} %)  |  "
            f"de equipos distintos: {quim_distinto}"
        )
        print(
            "  ← las del mismo equipo son INVISIBLES para una puerta de color:\n"
            "    los dos jugadores visten igual, así que la firma casa."
        )
    print(f"Observaciones: {len(cam)} de CAMBIO, {len(nor)} normales\n")
    cab = f"{'':<12}{'n':>7}{'IoU medio':>11}{'mediana':>10}{f'  % con IoU>{u}':>16}"
    print(cab)
    print("-" * len(cab))
    for nombre, v in (("CAMBIO", cam), ("normal", nor)):
        if len(v):
            print(
                f"{nombre:<12}{len(v):>7}{v.mean():>11.3f}{np.median(v):>10.3f}"
                f"{(v > u).mean() * 100:>15.1f}%"
            )
    # La otra explicación posible: el salto no ocurre al solaparse, sino
    # al RECUPERAR una identidad que se había perdido. Si los cambios
    # llegan tras huecos largos y las observaciones normales no, el
    # problema está en la re-entrada, no en el instante del cruce.
    hc, hn = np.array(huecos_cam), np.array(huecos_nor)
    if len(hc) and len(hn):
        print(
            f"\nHueco temporal previo (frames): CAMBIO mediana {np.median(hc):.0f}, "
            f"media {hc.mean():.1f}  |  normal mediana {np.median(hn):.0f}, "
            f"media {hn.mean():.1f}"
        )
        print(
            # OJO con el umbral: aquí solo hay observaciones en frames
            # con GT (1 de cada 15), así que DOS consecutivas distan 15
            # por construcción. Preguntar por "> 9" daba 100 % en ambos
            # grupos, que no es un hallazgo sino el paso del GT.
            f"  cambios tras hueco > 15 frames (o sea, con pérdida real): "
            f"{(hc > 15).mean() * 100:.1f}%  (normales: {(hn > 15).mean() * 100:.1f}%)"
        )
    if len(cam) and len(nor):
        r = (cam > u).mean() / max((nor > u).mean(), 1e-9)
        print(f"\nUn cambio de persona tiene {r:.1f}× más probabilidad de")
        print(f"ocurrir con una caja solapada (IoU>{u}) que una observación normal.")
        print(
            "\n→ HIPÓTESIS "
            + (
                "CONFIRMADA: el solape es donde nacen. Camino A tiene sentido."
                if r >= 2
                else "NO CONFIRMADA: el solape no explica los cambios. "
                "Camino A se construiría sobre arena."
            )
        )


if __name__ == "__main__":
    main()
