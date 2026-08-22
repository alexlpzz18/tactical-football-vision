#!/usr/bin/env python
"""Híbrido: identidad cerca, observación en el FONDO si es sospechosa.

Medido CON las reglas posicionales puestas, que es donde vive el 1,55 m.

El sistema decide la etiqueta con `solo_cercanos` —las observaciones
próximas, donde el color funciona— y la **propaga** a las lejanas. Acierta
el 100 % cerca y el 84,1 % en el fondo. Etiquetar por observación invierte
el reparto: 92 % cerca y 91,7 % en el fondo.

La idea es quedarse con lo mejor de cada uno: **mantener la propagación
donde acierta y romperla solo en el fondo, y solo cuando la identidad es
sospechosa.**

Dos definiciones de "sospechosa", las dos medidas:

- **dispersión**: sus propios recortes no se parecen entre sí (la
  identidad mezcla dos aspectos).
- **proximidad**: estuvo a menos de 2,5 m de otra identidad — la señal con
  2,42× de enriquecimiento sobre el azar.

Precisión de diseño: **solo se re-etiquetan las identidades cuya etiqueta
vino del COLOR (A/B)**. Si a un portero lo fijó la regla de área o a un
árbitro el catálogo, el color no debe pisarlo: esas reglas son las que
valen 7 metros de centroide.

Uso:
    python scripts/hibrido_profundidad.py
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
from pureza_sin_reentrada import duenos  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.team_classification.oclusion import (  # noqa: E402
    color_medio_limpio,
    detecciones_ocluidas,
)
from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("hibrido")
FRANJAS = [("10-20 m", 10, 20), ("20-30 m", 20, 30), ("30+ m", 30, 1e9)]
ZONAS = 3


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--y-fondo", type=float, default=30.0)
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
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    gt = gt_a_por_frame(parsear_cvat(args.gt), H, frame_offset=9750, paso_gt=15)
    mapa = duenos(cache, gt)
    cfg_oc = cfg_eq.get("oclusion", {})
    try:
        ocluidas = detecciones_ocluidas(
            cache, **{k: v for k, v in cfg_oc.items() if k != "activo"}
        )
    except Exception:
        ocluidas = set()

    ids = correr_perfil(
        cache,
        datos["fps"],
        datos["sample"],
        cfg_tr,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=cfg_eq,
    )
    eq_id = dict(clasificar_identidades(ids, colores, clf, cfg_eq))

    pos, obs_de = {}, {}
    for k, ident in enumerate(ids, start=1):
        obs_de[k] = []
        for tr in ident:
            for pp, par in zip(tr.pos, tr.det_idxs):
                pos[tuple(par)] = (float(pp[0]), float(pp[1]))
                obs_de[k].append(tuple(par))

    # ── Sospecha por DISPERSIÓN de color dentro de la identidad ──
    from src.team_classification.feature_v2 import parte_camiseta_hs

    dispersion = {}
    for k, pares in obs_de.items():
        feats = [parte_camiseta_hs(colores[p]) for p in pares if p in colores]
        dispersion[k] = (
            float(
                np.median(
                    np.linalg.norm(np.array(feats) - np.mean(feats, axis=0), axis=1)
                )
            )
            if len(feats) >= 3
            else 0.0
        )

    # ── Sospecha por PROXIMIDAD a otra identidad ──
    por_frame = {}
    for k, pares in obs_de.items():
        for par in pares:
            por_frame.setdefault(par[0], []).append((k, np.asarray(pos[par])))
    proxima = Counter()
    for f, lista in por_frame.items():
        for i, (k, p) in enumerate(lista):
            for j, (k2, q) in enumerate(lista):
                if i != j and float(np.linalg.norm(p - q)) < 2.5:
                    proxima[k] += 1
                    break
    frac_prox = {k: proxima[k] / max(len(pares), 1) for k, pares in obs_de.items()}

    eq_gt, pf_gt = {}, {}
    for f, obs in gt.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            eq_gt.setdefault(o.obj_id, eq)
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])
    largo, ancho = cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]

    def etiquetas_hibridas(criterio, umbral):
        et = {}
        for k, pares in obs_de.items():
            base = str(eq_id.get(k, "otro"))
            # Solo se re-etiqueta lo que decidió el COLOR. Las reglas
            # posicionales (portero, staff, árbitro) mandan siempre.
            reetiquetable = base in ("A", "B")
            if criterio == "ninguno":
                sospechosa = False
            elif criterio == "dispersion":
                sospechosa = dispersion.get(k, 0.0) > umbral
            else:
                sospechosa = frac_prox.get(k, 0.0) > umbral
            for par in pares:
                if (
                    reetiquetable
                    and sospechosa
                    and pos[par][1] >= args.y_fondo
                    and par in colores
                ):
                    m = color_medio_limpio([(par, colores[par])], ocluidas)
                    et[par] = clf.predict_color(m) if m is not None else base
                else:
                    et[par] = base
        return et

    def evalua(et):
        pf = {}
        for par, eq in et.items():
            eqn = str(eq).replace("portero_", "")
            if eqn in ("A", "B"):
                pf.setdefault((par[0], eqn), []).append(pos[par])
        m = (
            metricas_producto(pf)
            .set_index(["frame", "equipo"])
            .join(verdad, rsuffix="_gt", how="inner")
        )
        cen = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt).median() if len(m) else np.nan
        anc = (m.ancho - m.ancho_gt).abs().median() if len(m) else np.nan
        franjas = {n: [0, 0] for n, _l, _h in FRANJAS}
        for par, eq in et.items():
            g = mapa.get(par)
            if g is None:
                continue
            ok = str(eq).replace("portero_", "") == eq_gt.get(g)
            y = pos[par][1]
            for n, lo, hi in FRANJAS:
                if lo <= y < hi:
                    franjas[n][0] += ok
                    franjas[n][1] += 1

        def ocupacion(pfx):
            z = Counter()
            for (_f, eq), puntos in pfx.items():
                for x, y2 in puntos:
                    z[
                        (
                            eq,
                            min(int(x / largo * ZONAS), ZONAS - 1),
                            min(int(y2 / ancho * ZONAS), ZONAS - 1),
                        )
                    ] += 1
            t = sum(z.values()) or 1
            return {kk: v / t for kk, v in z.items()}

        oc_s, oc_g = ocupacion(pf), ocupacion(pf_gt)
        dif = (
            sum(abs(oc_s.get(kk, 0) - oc_g.get(kk, 0)) for kk in set(oc_s) | set(oc_g))
            / 2
        )
        return cen, anc, dif, franjas

    cab = f"{'variante':<30}{'centroide':>11}{'anchura':>9}{'ocupación':>11}" + "".join(
        f"{n:>11}" for n, _l, _h in FRANJAS
    )
    print("\n" + cab)
    print("-" * len(cab))
    variantes = [("SISTEMA (referencia)", "ninguno", 0.0)]
    for u in (0.5, 0.7, 0.9):
        variantes.append((f"dispersión > {u}", "dispersion", u))
    for u in (0.1, 0.3, 0.5):
        variantes.append((f"proximidad > {u:.0%} del tiempo", "proximidad", u))

    for nombre, crit, u in variantes:
        cen, anc, oc, fr = evalua(etiquetas_hibridas(crit, u))
        fila = f"{nombre:<30}{cen:>10.2f}m{anc:>8.2f}m{oc:>10.1%}"
        for n, _l, _h in FRANJAS:
            ok, tot = fr[n]
            fila += f"{ok/max(tot,1):>10.1%}" if tot else f"{'—':>11}"
        print(fila)
    print("\n  Criterio: gana si mejora el fondo SIN degradar el 100 % de cerca.")


if __name__ == "__main__":
    main()
