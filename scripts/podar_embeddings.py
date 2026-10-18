#!/usr/bin/env python
"""Deja en el caché de embeddings solo lo que la puerta va a consultar.

La estrategia adoptada (docs/embedding_unico.md): **una sola pasada** —
embeber todo durante la detección, cuando el vídeo ya está decodificado— y
**tirar después** lo que no cae en ninguna ventana de re-entrada.

La alternativa "embeber solo las ventanas" parecía más barata y no lo es:
para saber dónde están las re-entradas hay que haber trackeado, y para
trackear hacen falta las detecciones, así que obliga a decodificar el
vídeo DOS veces. Decodificar 90 minutos domina el coste; la inferencia
sobre recortes de 224×224 es marginal al lado de SAHI.

Medido: la puerta usa el 11,3 % de los recortes. Con PCA a 128 dims el
caché de un partido baja de ~1,4 GB a unos 26 MB.

Uso:
    python scripts/podar_embeddings.py \\
        --config configs/processor_benja_emb.yaml --pca 128
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.puerta_reentrada import _observaciones  # noqa: E402

logger = logging.getLogger("podar")
VENTANA = 8


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--pca", type=int, default=0, help="0 = sin PCA")
    p.add_argument("--salida", default=None)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    conf_min = float(cfg_tr.get("confianza_min", 0) or 0)
    cache, _c = filtrar_por_confianza(datos["cache"], colores, conf_min)

    ruta_emb = cfg["rutas"]["cache_embeddings"]
    with open(ruta_emb, "rb") as f:
        d = pickle.load(f)
    V = np.asarray(d["embeddings"], dtype=np.float32)
    claves = [tuple(c) for c in d["claves"]]

    # Reindexar igual que el filtro de confianza, o los det_idx mentirían
    mapa = {}
    for e in datos["cache"]:
        fr, j = e["frame_idx"], 0
        for i, det in enumerate(e["dets"]):
            if det[6] < conf_min:
                continue
            mapa[(fr, i)] = (fr, j)
            j += 1
    pos = {c: i for i, c in enumerate(claves)}

    ids = asociar_con_bytetrack(
        cache,
        datos["fps"],
        datos["sample"],
        ParametrosByteTrack.desde_dict(cfg_tr.get("bytetrack")),
    )
    dt = datos["sample"] / datos["fps"]
    hueco = float(cfg_tr.get("puerta_reentrada", {}).get("hueco_min_s", 0.5))
    hueco_frames = max(1, int(round(hueco / dt))) * 1.5

    necesarios = set()
    for ident in ids:
        obs = _observaciones(ident)
        for k in range(1, len(obs)):
            if obs[k][0] - obs[k - 1][0] < hueco_frames:
                continue
            ini, fin = max(0, k - VENTANA), k + VENTANA
            for _f, par in obs[ini:fin]:
                necesarios.add(par)

    inverso = {v: k for k, v in mapa.items()}
    filtradas, vectores = [], []
    for par in sorted(necesarios):
        crudo = inverso.get(par, par)
        if crudo in pos:
            filtradas.append(crudo)
            vectores.append(V[pos[crudo]])
    if not vectores:
        raise SystemExit("No quedó ningún embedding: revisa la reindexación")
    M = np.stack(vectores)

    nota_pca = ""
    if args.pca and args.pca < M.shape[1]:
        # PCA sin sklearn: SVD sobre los datos centrados.
        media = M.mean(axis=0)
        _u, _s, vt = np.linalg.svd(M - media, full_matrices=False)
        base = vt[: args.pca]
        M = (M - media) @ base.T
        nota_pca = f", PCA a {args.pca} dims"

    salida = args.salida or ruta_emb.replace(".pkl", "_podado.pkl")
    nuevo = {
        **d,
        "claves": filtradas,
        "embeddings": M.astype(np.float16),
        "dims": int(M.shape[1]),
        "podado": True,
        "ventana_obs": VENTANA,
    }
    with open(salida, "wb") as f:
        pickle.dump(nuevo, f, protocol=4)

    antes = Path(ruta_emb).stat().st_size / 1e6
    despues = Path(salida).stat().st_size / 1e6
    print(f"\n✓ {salida}")
    print(
        f"  {len(claves)} → {len(filtradas)} vectores "
        f"({len(filtradas)/max(len(claves),1):.1%}){nota_pca}"
    )
    print(
        f"  {antes:.0f} MB → {despues:.0f} MB  ({antes/max(despues,1e-9):.0f}× menos)"
    )


if __name__ == "__main__":
    main()
