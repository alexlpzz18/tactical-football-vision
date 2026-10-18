#!/usr/bin/env python
"""Puerta de ambigüedad en METROS: beneficio Y coste, juntos.

El diagnóstico dice que la contaminación nace por **proximidad física**
(2,42× de enriquecimiento) en el **fondo del campo** (1,65×), sin solape
de cajas ni hueco temporal. ByteTrack asocia por IoU en píxeles y es
ciego a dos jugadores separados 1,7 m en el fondo.

Esta puerta mira la señal correcta. Y se mide con el listón que exige la
historia del proyecto: **tres cortes adoptados por buenos que bajaban
quimeras hundiendo la cobertura**. Aquí el coste va en la misma tabla que
el beneficio.

Tres formas de actuar, que NO son lo mismo:

- **cortar**: parte la identidad en el momento de riesgo. Lo más agresivo.
- **apariencia**: solo corta si además la firma no casa. Usa el momento
  de riesgo como *puerta*, no como sentencia.
- **marcar**: no corta nada, solo cuenta cuánto se señalaría como dudoso.
  Es la medida del plan B.

Uso:
    python scripts/puerta_proximidad.py
"""

import argparse
import logging
import pickle
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from oraculos import metricas_producto  # noqa: E402
from pureza_sin_reentrada import analizar, duenos  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.field_tracker import Tracklet  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402

logger = logging.getLogger("proximidad")
VENTANA = 8


def coseno(a, b):
    na = float(np.linalg.norm(a)) + 1e-9
    nb = float(np.linalg.norm(b)) + 1e-9
    return float(1.0 - float(a @ b) / (na * nb))


def firma(emb, pares):
    v = [emb[p] for p in pares if p in emb]
    return np.mean(v, axis=0) if v else None


def aplicar(identidades, emb, dist_m, modo, y_min, umbral_emb=0.08):
    """Devuelve (identidades nuevas, nº de momentos de riesgo, nº de cortes)."""
    # Posición de cada observación, por frame, para buscar vecinos
    pos = {}
    for k, ident in enumerate(identidades):
        for tr in ident:
            for p, par in zip(tr.pos, tr.det_idxs):
                pos.setdefault(par[0], []).append((k, np.asarray(p), par))

    salida, n_riesgo, n_cortes = [], 0, 0
    for k, ident in enumerate(identidades):
        obs = sorted(
            ((par, p) for tr in ident for p, par in zip(tr.pos, tr.det_idxs)),
            key=lambda o: o[0][0],
        )
        mapa_tr = {}
        for tr in ident:
            for i, par in enumerate(tr.det_idxs):
                mapa_tr[tuple(par)] = (tr, i)

        cortes = []
        for i in range(1, len(obs)):
            par, p = obs[i]
            if p[1] < y_min:  # fuera de la franja de riesgo
                continue
            vecinos = [
                float(np.linalg.norm(q - p))
                for j, q, _pp in pos.get(par[0], [])
                if j != k
            ]
            if not vecinos or min(vecinos) > dist_m:
                continue
            n_riesgo += 1
            if modo == "marcar":
                continue
            if modo == "apariencia":
                ini = max(0, i - VENTANA)
                fin = i + VENTANA
                a = firma(emb, [o[0] for o in obs[ini:i]])
                b = firma(emb, [o[0] for o in obs[i:fin]])
                if a is None or b is None or coseno(a, b) <= umbral_emb:
                    continue
            cortes.append(par[0])
            n_cortes += 1

        if not cortes:
            salida.append(ident)
            continue
        trozos = [[] for _ in range(len(cortes) + 1)]
        for par, _p in obs:
            destino = sum(1 for c in cortes if par[0] >= c)
            trozos[destino].append(par)
        for trozo in trozos:
            nuevo, lista = None, []
            for par in trozo:
                tr, i = mapa_tr[tuple(par)]
                if nuevo is None:
                    nuevo = Tracklet(tr.id, tr.ts[i], tr.pos[i], par[1], par[0])
                    lista.append(nuevo)
                else:
                    nuevo.anadir(tr.ts[i], tr.pos[i], par[1], par[0])
            if lista:
                salida.append(lista)
    return salida, n_riesgo, n_cortes


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

    eq_gt, pf_gt = {}, {}
    for f, obs in gt.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            eq_gt.setdefault(o.obj_id, eq)
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])

    base = asociar_con_bytetrack(
        cache,
        datos["fps"],
        datos["sample"],
        ParametrosByteTrack.desde_dict(cfg_tr.get("bytetrack")),
    )

    def evalua(identidades):
        r = analizar(identidades, mapa)
        grupos = {}
        for ident in identidades:
            g = [mapa.get(tuple(par)) for tr in ident for par in tr.det_idxs]
            g = [x for x in g if x is not None]
            if g:
                grupos.setdefault(Counter(g).most_common(1)[0][0], []).append(ident)
        pf = {}
        for gid, lista in grupos.items():
            eq = eq_gt.get(gid)
            if eq not in ("A", "B"):
                continue
            for ident in lista:
                for tr in ident:
                    for p, (f, _dd) in zip(tr.pos, tr.det_idxs):
                        pf.setdefault((f, eq), []).append((p[0], p[1]))
        m = (
            metricas_producto(pf)
            .set_index(["frame", "equipo"])
            .join(verdad, rsuffix="_gt", how="inner")
        )
        cen = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt).median() if len(m) else np.nan
        # COSTE: identidades PURAS que la puerta ha troceado
        puras_rotas = sum(1 for lista in grupos.values() if len(lista) > 1)
        return r, cen, puras_rotas

    r0, cen0, _ = evalua(base)
    cab = (
        f"{'variante':<34}{'tracklets':>10}{'pureza':>9}{'%puros':>8}"
        f"{'frag':>6}{'centroide':>11}{'riesgos':>9}{'cortes':>8}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    print(
        f"{'BASE (sin puerta)':<34}{r0['tracklets']:>10}{r0['pureza_obs']:>8.1%}"
        f"{r0['pct_puros']:>8.0%}{r0['frag']:>6.1f}{cen0:>10.2f}m{'—':>9}{'—':>8}"
    )

    for y_min, etiqueta in ((0.0, "todo el campo"), (30.0, "solo fondo 30+ m")):
        print(f"\n── {etiqueta} ──")
        for modo in ("cortar", "apariencia", "marcar"):
            for dist in (1.5, 2.0, 2.5, 3.0):
                ids, n_r, n_c = aplicar(base, emb, dist, modo, y_min)
                r, cen, rotas = evalua(ids)
                nombre = f"{modo} {dist} m"
                print(
                    f"{nombre:<34}{r['tracklets']:>10}{r['pureza_obs']:>8.1%}"
                    f"{r['pct_puros']:>8.0%}{r['frag']:>6.1f}{cen:>10.2f}m"
                    f"{n_r:>9}{n_c:>8}"
                )
    print("\n  techo del oráculo de asociación: centroide 0.42 m")
    print("  'riesgos' = momentos que la puerta examina · 'cortes' = los que parte")


if __name__ == "__main__":
    main()
