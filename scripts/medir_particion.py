#!/usr/bin/env python
"""4a: pureza antes y despues de partir, con el control de cortes al azar."""

import logging
import pickle
import random
import sys
import warnings
import numpy as np
import yaml

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.CRITICAL)
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.partir_tracklets import (  # noqa: E402
    ParametrosPartir,
    partir_tracklets,
)
from pureza_sin_reentrada import duenos, analizar  # noqa: E402

cfg = yaml.safe_load(open("configs/processor_benja_v4_ajustado.yaml"))
cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
H = np.load(cfg["rutas"]["homografia"])
datos = cargar_cache(cfg["rutas"]["cache"])
colores = pickle.load(open(cfg["rutas"]["cache_colores"], "rb"))
conf = float(cfg_tr.get("confianza_min", 0) or 0)
cache, colores = filtrar_por_confianza(datos["cache"], colores, conf)
gt = gt_a_por_frame(
    parsear_cvat("data/annotations/gt_benja/annotations.xml"),
    H,
    frame_offset=9750,
    paso_gt=15,
)
mapa = duenos(cache, gt)

d = pickle.load(open("data/tracking_benja/emb_benja_siglip.pkl", "rb"))
V = np.asarray(d["embeddings"], dtype=np.float32)
crudo = {tuple(c): V[i] for i, c in enumerate(d["claves"])}
emb = {}
for e in datos["cache"]:
    f, j = e["frame_idx"], 0
    for i, det in enumerate(e["dets"]):
        if det[6] < conf:
            continue
        if (f, i) in crudo:
            emb[(f, j)] = crudo[(f, i)]
        j += 1

base = asociar_con_bytetrack(
    cache,
    datos["fps"],
    datos["sample"],
    ParametrosByteTrack.desde_dict(cfg_tr.get("bytetrack")),
)
print(
    f"{'variante':<26}{'tracklets':>11}{'puros':>8}{'%puros':>8}{'pureza obs':>12}{'frag':>7}"
)
print("-" * 72)
r = analizar(base, mapa)
print(
    f"{'sin partir (base)':<26}{r['tracklets']:>11}{r['puros']:>8}{r['pct_puros']:>7.0%}"
    f"{r['pureza_obs']:>12.1%}{r['frag']:>7.1f}"
)
for u in (0.04, 0.06, 0.08, 0.10, 0.13):
    ids = partir_tracklets(base, emb, ParametrosPartir(activo=True, umbral=u))
    r = analizar(ids, mapa)
    print(
        f"{'partido umbral '+str(u):<26}{r['tracklets']:>11}{r['puros']:>8}"
        f"{r['pct_puros']:>7.0%}{r['pureza_obs']:>12.1%}{r['frag']:>7.1f}"
    )
print(f"\npersonas reales: {len(set(mapa.values()))}")

# ── CONTROL: ¿corta por SEÑAL o por trocear? ──
# La pureza premia fragmentar: un trozo de una observación es 100 % puro.
# Comparamos contra cortar en puntos AL AZAR, el mismo número de veces.
from src.tracking.field_tracker import Tracklet  # noqa: E402


def partir_al_azar(identidades, n_cortes_total, semilla=0):
    rng = random.Random(semilla)
    pesos = [sum(len(t.pos) for t in i) for i in identidades]
    salida = []
    cortes_por = [0] * len(identidades)
    for _ in range(n_cortes_total):
        k = rng.choices(range(len(identidades)), weights=pesos)[0]
        cortes_por[k] += 1
    for k, identidad in enumerate(identidades):
        obs = sorted(
            (par for tr in identidad for par in tr.det_idxs), key=lambda p: p[0]
        )
        pos = {}
        for tr in identidad:
            for p, par in zip(tr.pos, tr.det_idxs):
                pos[tuple(par)] = (p, tr)
        puntos = (
            sorted(
                rng.sample(
                    range(4, max(5, len(obs) - 4)),
                    min(cortes_por[k], max(0, len(obs) - 9)),
                )
            )
            if len(obs) > 9
            else []
        )
        trozos, ant = [], 0
        for c in puntos + [len(obs)]:
            trozos.append(obs[ant:c])
            ant = c
        for trozo in trozos:
            nuevo, lista = None, []
            for par in trozo:
                if par not in pos:
                    continue
                p, tro = pos[par]
                i = tro.det_idxs.index(par)
                if nuevo is None:
                    nuevo = Tracklet(tro.id, tro.ts[i], p, par[1], par[0])
                    lista.append(nuevo)
                else:
                    nuevo.anadir(tro.ts[i], p, par[1], par[0])
            if lista:
                salida.append(lista)
    return salida


print("\n── CONTROL: mismos cortes, pero en puntos AL AZAR ──")
print(f"{'variante':<26}{'tracklets':>11}{'puros':>8}{'%puros':>8}{'pureza obs':>12}")
print("-" * 65)
for u in (0.04, 0.06, 0.08):
    ids = partir_tracklets(base, emb, ParametrosPartir(activo=True, umbral=u))
    r = analizar(ids, mapa)
    n_c = len(ids) - len(base)
    rs = [analizar(partir_al_azar(base, n_c, s), mapa) for s in range(3)]
    pa = float(np.mean([x["pureza_obs"] for x in rs]))
    print(
        f"{'APARIENCIA u='+str(u):<26}{r['tracklets']:>11}{r['puros']:>8}"
        f"{r['pct_puros']:>7.0%}{r['pureza_obs']:>12.1%}"
    )
    print(
        f"{'  azar, mismos cortes':<26}{np.mean([x['tracklets'] for x in rs]):>11.0f}"
        f"{np.mean([x['puros'] for x in rs]):>8.0f}"
        f"{np.mean([x['pct_puros'] for x in rs]):>7.0%}{pa:>12.1%}"
        f"   -> ventaja real: {r['pureza_obs']-pa:+.1%}"
    )
