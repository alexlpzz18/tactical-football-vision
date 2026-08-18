#!/usr/bin/env python
"""Instantes concretos donde una identidad PUEDE haber cambiado de persona.

Sin GT posicional no se puede afirmar que una identidad sea quimera —el
benjamín no lo tiene—, pero sí se puede señalar DÓNDE mirar: los puntos
en que la firma de apariencia de una identidad da un salto, ordenados por
tamaño del salto.

Sirve para que la verificación visual vaya a instantes concretos en vez
de a ojo sobre seis minutos de vídeo. Incluye los saltos que la puerta
NO cortó (por debajo del umbral), que son justo los candidatos a quimera
superviviente.

Uso:
    python scripts/sospechosas_de_quimera.py --config configs/processor_benja_emb.yaml
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

warnings.filterwarnings("ignore")

from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    entrenar_clasificador,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402

VENTANA = 8


def coseno(a, b):
    na = float(np.linalg.norm(a)) + 1e-9
    nb = float(np.linalg.norm(b)) + 1e-9
    return float(1.0 - float(a @ b) / (na * nb))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--top", type=int, default=12)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    conf_min = float(cfg_tr.get("confianza_min", 0) or 0)
    cache, colores = filtrar_por_confianza(datos["cache"], colores, conf_min)

    with open(cfg["rutas"]["cache_embeddings"], "rb") as f:
        d_emb = pickle.load(f)
    V = np.asarray(d_emb["embeddings"], dtype=np.float32)
    crudo = {tuple(c): V[i] for i, c in enumerate(d_emb["claves"])}
    emb = {}
    for e in datos["cache"]:
        fr, j = e["frame_idx"], 0
        for i, det in enumerate(e["dets"]):
            if det[6] < conf_min:
                continue
            if (fr, i) in crudo:
                emb[(fr, j)] = crudo[(fr, i)]
            j += 1

    clf = entrenar_clasificador(colores, cfg_eq, cache)
    ids = correr_perfil(
        cache,
        datos["fps"],
        datos["sample"],
        cfg_tr,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=cfg_eq,
        embeddings=emb,
    )
    fps = float(datos["fps"])
    cfg_p = cfg_tr.get("puerta_reentrada", {})
    umbral = float(cfg_p.get("emb_max_dist", 0.08))
    # La puerta SOLO mira re-entradas: saltos con hueco por encima de
    # esto. Un salto de apariencia con hueco corto es un CRUCE, y la
    # puerta ni lo examina — decirlo mal mandaría a mirar donde no es.
    hueco_min = float(cfg_p.get("hueco_min_s", 0.5)) * 1.5

    sospechas = []
    for k, ident in enumerate(ids, start=1):
        obs = sorted([par for tr in ident for par in tr.det_idxs], key=lambda x: x[0])
        for i in range(1, len(obs)):
            ini = max(0, i - VENTANA)
            fin = i + VENTANA
            a = [emb[o] for o in obs[ini:i] if o in emb]
            b = [emb[o] for o in obs[i:fin] if o in emb]
            if len(a) < 3 or len(b) < 3:
                continue
            d = coseno(np.mean(a, axis=0), np.mean(b, axis=0))
            hueco = (obs[i][0] - obs[i - 1][0]) / fps
            sospechas.append((d, k, obs[i][0], hueco, len(obs)))

    sospechas.sort(reverse=True)
    print(f"\nIdentidades: {len(ids)}. Umbral de corte de la puerta: {umbral}\n")
    cab = (
        f"{'dist':>7}{'id':>5}{'frame':>8}{'minuto':>9}"
        f"{'hueco s':>9}{'obs id':>8}   ¿la puerta cortó?"
    )
    print(cab)
    print("-" * len(cab))
    for d, k, frame, hueco, n in sospechas[: args.top]:
        m, s = divmod(frame / fps, 60)
        if hueco < hueco_min:
            corto = f"NO la mira (cruce, hueco < {hueco_min:.2f} s)"
        elif d > umbral:
            corto = "sí, cortada"
        else:
            corto = "NO corta — candidata a quimera viva"
        print(
            f"{d:>7.3f}{k:>5}{frame:>8}{int(m):>6}:{s:04.1f}"
            f"{hueco:>9.2f}{n:>8}   {corto}"
        )
    n_cruce = sum(1 for d, _k, _f, h, _n in sospechas if h < hueco_min and d > umbral)
    n_viva = sum(1 for d, _k, _f, h, _n in sospechas if h >= hueco_min and d <= umbral)
    print(
        f"\nSaltos de apariencia por encima de {umbral} que la puerta NO mira\n"
        f"por ser cruces y no re-entradas: {n_cruce}.\n"
        f"Re-entradas con salto por debajo del umbral (candidatas vivas): {n_viva}."
    )
    print(
        "\nLos 'NO la mira' son el techo de la puerta tal como está: el\n"
        "diseño la puso en la re-entrada porque ahí la señal era 3,0× y en\n"
        "el solape 1,8×, pero en el F7 los saltos gordos salen en cruces."
    )


if __name__ == "__main__":
    main()
