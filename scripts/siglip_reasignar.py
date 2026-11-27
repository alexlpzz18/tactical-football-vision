#!/usr/bin/env python
"""Reasigna las etiquetas de SigLIP de un caché de detecciones a OTRO del mismo vídeo, por caja.

Las etiquetas de SigLIP (`lit_siglip_etiquetar.py`) van indexadas por (frame, posición) del caché
sobre el que se calcularon. Al regenerar el caché (p. ej. la opción 1, con las detecciones débiles
añadidas: `docs/plan_opcion1_dos_etapas.md`), las cajas de producción se reproducen casi iguales
(99,9 % con IoU ≥ 0,9 en el alevín A) pero NO idénticas, y las posiciones cambian: usar el fichero
viejo con el caché nuevo pegaría cada etiqueta a otra caja sin avisar.

Aquí cada detección del caché nuevo hereda la etiqueta de la detección del viejo, en el mismo
fotograma, con la que más solapa, si el IoU es ≥ `iou_min`. Las que no tienen pareja (las débiles
nuevas) se quedan sin etiqueta y el voto por ventana las decide con el color, que es exactamente lo
que se midió en el alevín A (anchura 3,82 m, centroide 3,57 m).

Uso:
    python scripts/siglip_reasignar.py --cache-viejo data/tracking_alevinb/cache_alevinb_p1.pkl \\
        --etiquetas data/embeddings_equipos/etiquetas_siglip_alevinb_p1.npz \\
        --cache-nuevo data/tracking_alevinb/cache_alevinb_p1_conf010.pkl \\
        --salida data/embeddings_equipos/etiquetas_siglip_alevinb_p1_conf010.npz
"""

import argparse
import json
import pickle
from pathlib import Path

import numpy as np


def iou_matriz(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU entre las cajas (x1, y1, x2, y2) de `a` (N×4) y `b` (M×4)."""
    iw = np.clip(
        np.minimum(a[:, None, 2], b[None, :, 2])
        - np.maximum(a[:, None, 0], b[None, :, 0]),
        0,
        None,
    )
    ih = np.clip(
        np.minimum(a[:, None, 3], b[None, :, 3])
        - np.maximum(a[:, None, 1], b[None, :, 1]),
        0,
        None,
    )
    inter = iw * ih
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-9)


def reasignar(viejo: list, etiquetas: dict, nuevo: list, iou_min: float = 0.9) -> dict:
    """{(frame, j del caché nuevo): etiqueta}."""
    cajas_viejas = {
        e["frame_idx"]: np.array([d[2:6] for d in e["dets"]], float) for e in viejo
    }
    salida = {}
    for e in nuevo:
        f = e["frame_idx"]
        cv = cajas_viejas.get(f)
        if cv is None or not len(cv) or not e["dets"]:
            continue
        m = iou_matriz(
            np.array([d[2:6] for d in e["dets"]], float).reshape(-1, 4),
            cv.reshape(-1, 4),
        )
        for j, fila in enumerate(m):
            k = int(np.argmax(fila))
            if fila[k] >= iou_min and (f, k) in etiquetas:
                salida[(f, j)] = etiquetas[(f, k)]
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-viejo", type=Path, required=True)
    ap.add_argument("--etiquetas", type=Path, required=True)
    ap.add_argument("--cache-nuevo", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--iou-min", type=float, default=0.9)
    a = ap.parse_args()
    z = np.load(a.etiquetas, allow_pickle=True)
    etq = {(int(f), int(j)): int(e) for (f, j), e in zip(z["claves"], z["etiqueta"])}
    viejo = pickle.load(open(a.cache_viejo, "rb"))["cache"]
    nuevo = pickle.load(open(a.cache_nuevo, "rb"))["cache"]
    r = reasignar(viejo, etq, nuevo, a.iou_min)
    claves = np.array(sorted(r), dtype=int).reshape(-1, 2)
    np.savez(
        a.salida,
        claves=claves,
        etiqueta=np.array([r[tuple(c)] for c in claves], dtype=int),
    )
    n_nuevo = sum(len(e["dets"]) for e in nuevo)
    conf = {(e["frame_idx"], j): d[6] for e in nuevo for j, d in enumerate(e["dets"])}
    fuertes = sum(1 for c in conf.values() if c >= 0.3)
    print(
        json.dumps(
            {
                "detecciones_nuevas": n_nuevo,
                "con_etiqueta": len(r),
                "fuertes_con_etiqueta_pct": round(
                    100 * sum(1 for k in r if conf[k] >= 0.3) / max(fuertes, 1), 1
                ),
                "salida": str(a.salida),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
