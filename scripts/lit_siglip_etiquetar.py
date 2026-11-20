#!/usr/bin/env python
"""Etiqueta con UMAP 3D + K-means de 2 unos embeddings SigLIP ya calculados.

docs/plan_siglip_por_partido.md. Entrada: el caché de la celda de GPU
(`colab_embeddings_equipos.py --modelo siglip`: claves (frame, det) del caché de detecciones de
producción y un embedding por detección). El ajuste se hace solo con las detecciones DENTRO del
campo (como en el intento 1) y, si hay muchas, con una submuestra; luego se aplica a todas.
Salida: un .npz con el mismo formato que `lit_siglip_equipos.py` (claves, etiqueta, dentro), que
leen `lit_seleccion_siglip.py` y `lit_evaluar_equipos.py`.

Necesita umap-learn: se corre con `~/.venvs/detector-cpu`.

Uso:
    ~/.venvs/detector-cpu/bin/python scripts/lit_siglip_etiquetar.py \\
        --embeddings data/embeddings_equipos/cache_sig_alevinb_p1.pkl \\
        --cache data/tracking_alevinb/cache_alevinb_p1.pkl --largo 100 --ancho 64 \\
        --salida outputs/literatura/siglip/alevinb.npz
"""

import argparse
import pickle
import time
from pathlib import Path

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--embeddings", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--largo", type=float, required=True)
    ap.add_argument("--ancho", type=float, required=True)
    ap.add_argument("--max-ajuste", type=int, default=30000)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    import umap
    from sklearn.cluster import KMeans

    t0 = time.time()
    emb = pickle.load(open(a.embeddings, "rb"))
    claves = [tuple(c) for c in emb["claves"]]
    X = np.asarray(emb["embeddings"], dtype=np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    pos = {
        (e["frame_idx"], j): d[:2]
        for e in pickle.load(open(a.cache, "rb"))["cache"]
        for j, d in enumerate(e["dets"])
    }
    dentro = np.array(
        [
            c in pos and 0 <= pos[c][0] <= a.largo and 0 <= pos[c][1] <= a.ancho
            for c in claves
        ]
    )
    rng = np.random.default_rng(a.semilla)
    idx = np.flatnonzero(dentro)
    if len(idx) > a.max_ajuste:
        idx = rng.choice(idx, a.max_ajuste, replace=False)
    red = umap.UMAP(n_components=3, random_state=a.semilla).fit(X[idx])
    km = KMeans(n_clusters=2, n_init=10, random_state=a.semilla).fit(red.embedding_)
    trozos = []
    for k in range(0, len(X), 20000):
        hasta = k + 20000
        trozos.append(km.predict(red.transform(X[k:hasta])))
    etiqueta = np.concatenate(trozos)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        a.salida,
        claves=np.array(claves),
        etiqueta=etiqueta,
        dentro=dentro,
        modelo=emb["backbone"],
    )
    print(
        f"✓ {a.salida}: {len(claves)} detecciones, grupos {np.bincount(etiqueta).tolist()}, "
        f"ajuste con {len(idx)}, {time.time() - t0:.0f} s"
    )


if __name__ == "__main__":
    main()
