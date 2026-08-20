#!/usr/bin/env python
"""¿De qué tamaño son los recortes DONDE VA A OPERAR el embedding?

La distribución global de tamaños no sirve para elegir backbone: el
embedding no se consulta en todos los recortes, sino en dos momentos
concretos — el CRUCE (dos cajas solapadas) y la RE-ENTRADA (un track que
vuelve tras perderse). Si esos momentos tienen una distribución distinta
de la global, elegir por la global es elegir mal.

Además responde a la pregunta del esquema por zonas (siglip para
pequeños, dinov2 para grandes) con el dato que de verdad la decide: en
una re-entrada se compara el recorte de AHORA con los de ANTES, así que
lo que importa no es el tamaño de cada uno sino si los dos caen en el
mismo bin. Si no caen, sus embeddings viven en espacios distintos y no se
pueden comparar.

Uso:
    python scripts/tamano_en_el_cruce.py
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
from src.tracking.perfiles import correr_perfil  # noqa: E402

BINS = [("<20 px", 0, 20), ("20-30 px", 20, 30), (">30 px", 30, 1e9)]
VENTANA_FIRMA = 8  # el mismo que usa la puerta de re-entrada


def bin_de(alto):
    for nombre, lo, hi in BINS:
        if lo <= alto < hi:
            return nombre
    return BINS[-1][0]


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def reparto(alturas):
    n = len(alturas)
    if not n:
        return {b: 0.0 for b, _l, _h in BINS}, 0
    c = {b: 0 for b, _l, _h in BINS}
    for a in alturas:
        c[bin_de(a)] += 1
    return {b: v / n for b, v in c.items()}, n


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    p.add_argument("--hueco-min-s", type=float, default=0.5)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    cajas = {e["frame_idx"]: [d[2:6] for d in e["dets"]] for e in banco.datos["cache"]}
    alto_de = {
        (e["frame_idx"], i): float(d[5] - d[3])
        for e in banco.datos["cache"]
        for i, d in enumerate(e["dets"])
    }

    identidades = correr_perfil(
        banco.datos["cache"],
        banco.datos["fps"],
        banco.datos["sample"],
        banco.cfg_tracking,
        perfil="bytetrack",
        colores=banco.colores,
    )
    dt = banco.dt
    hueco_frames = max(1, int(round(args.hueco_min_s / dt))) * 1.5

    todas, en_cruce, en_reentrada = [], [], []
    mismo_bin, distinto_bin = 0, 0

    for ident in identidades:
        obs = sorted([par for tr in ident for par in tr.det_idxs], key=lambda p: p[0])
        for f, di in obs:
            todas.append(alto_de.get((f, di), 0.0))
        # Cruces: alguna caja vecina con IoU > 0.1
        for f, di in obs:
            lista = cajas.get(f, [])
            if di >= len(lista):
                continue
            propia = lista[di]
            if any(iou(propia, o) > 0.1 for j, o in enumerate(lista) if j != di):
                en_cruce.append(alto_de.get((f, di), 0.0))
        # Re-entradas: primera observación tras un hueco real
        for k in range(1, len(obs)):
            if obs[k][0] - obs[k - 1][0] < hueco_frames:
                continue
            alto_despues = alto_de.get(obs[k], 0.0)
            en_reentrada.append(alto_despues)
            # ¿La ventana de ANTES cae en el mismo bin que la de DESPUÉS?
            ini = max(0, k - VENTANA_FIRMA)
            antes = [alto_de.get(o, 0.0) for o in obs[ini:k]]
            fin = k + VENTANA_FIRMA
            desp = [alto_de.get(o, 0.0) for o in obs[k:fin]]
            if not antes or not desp:
                continue
            if bin_de(float(np.median(antes))) == bin_de(float(np.median(desp))):
                mismo_bin += 1
            else:
                distinto_bin += 1

    print("\n── ¿DÓNDE OPERA EL EMBEDDING? ──\n")
    cab = f"{'momento':<24}{'n':>8}" + "".join(f"{b:>11}" for b, _l, _h in BINS)
    print(cab)
    print("-" * len(cab))
    for nombre, datos in (
        ("todos los recortes", todas),
        ("EN EL CRUCE", en_cruce),
        ("EN LA RE-ENTRADA", en_reentrada),
    ):
        r, n = reparto(datos)
        print(f"{nombre:<24}{n:>8}" + "".join(f"{r[b]:>10.1%}" for b, _l, _h in BINS))

    print("\n── ¿COMPENSA UN ESQUEMA POR ZONAS? ──\n")
    total = mismo_bin + distinto_bin
    if total:
        print(f"  Re-entradas analizadas: {total}")
        print(
            f"  El ANTES y el DESPUÉS caen en el MISMO bin de tamaño: "
            f"{mismo_bin} ({mismo_bin / total:.1%})"
        )
        print(f"  Caen en bins DISTINTOS: {distinto_bin} ({distinto_bin / total:.1%})")
        print(
            "\n  En una re-entrada se compara el recorte de AHORA con los de\n"
            "  ANTES. Si cada bin usa un backbone distinto, esas parejas viven\n"
            "  en espacios vectoriales distintos y NO SE PUEDEN COMPARAR."
        )
        if distinto_bin / total > 0.15:
            print(
                f"\n  → {distinto_bin / total:.0%} de las re-entradas quedarían "
                "sin poder compararse.\n    El esquema por zonas se rompe justo "
                "en el caso al que sirve."
            )
        else:
            print(
                f"\n  → Solo {distinto_bin / total:.0%} cruzaría de bin: el "
                "esquema por zonas es viable\n    si el coste lo justifica."
            )


if __name__ == "__main__":
    main()
