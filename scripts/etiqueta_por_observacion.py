#!/usr/bin/env python
"""¿Etiquetar el equipo por OBSERVACIÓN, por IDENTIDAD, o por VENTANA?

La corrección del centroide dejó claro que la palanca del producto es
**la etiqueta de equipo por observación**, no la asociación. Hoy la
etiqueta se decide por voto mayoritario sobre TODA la identidad, y eso
tiene un problema y una virtud:

- **Problema**: una identidad contaminada arrastra a todas sus
  observaciones a la etiqueta de la persona dominante. Si mezcla dos
  equipos, la mitad sale mal por construcción.
- **Virtud**: el voto es robusto. Un recorte ocluido o borroso no cambia
  el veredicto.

Se miden tres estrategias, y el punto medio puede ser lo mejor de ambas:

- **identidad**: mayoría sobre toda la vida (lo de hoy).
- **observación**: cada recorte decide por sí mismo.
- **ventana**: mayoría sobre los últimos N segundos. Conserva parte de la
  robustez y deja de arrastrar la identidad entera cuando cambia de
  persona.

Y se desglosa el resultado en las DOS columnas que importan: cuánto se
gana en las identidades CONTAMINADAS y cuánto se pierde en las PURAS.

Uso:
    python scripts/etiqueta_por_observacion.py
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

from oraculos import metricas_producto  # noqa: E402
from pureza_sin_reentrada import duenos  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    entrenar_clasificador,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("etiqueta")
FRANJAS = [("10-20 m", 10, 20), ("20-30 m", 20, 30), ("30+ m", 30, 1e9)]


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
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    gt = gt_a_por_frame(parsear_cvat(args.gt), H, frame_offset=9750, paso_gt=15)
    mapa = duenos(cache, gt)

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

    eq_gt, pf_gt = {}, {}
    for f, obs in gt.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            eq_gt.setdefault(o.obj_id, eq)
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])

    # OJO: el sistema PROMEDIA LAS FEATURES y luego clasifica; no
    # clasifica cada recorte y vota. La primera versión votaba etiquetas y
    # daba un centroide de 7,89 m frente a los 1,55 m reales — implausible,
    # que es lo que delató el fallo. Aquí se replica el promedio de
    # features, que es lo que hace `color_medio_limpio`.
    from src.team_classification.oclusion import (
        color_medio_limpio,
        detecciones_ocluidas,
    )

    cfg_oc = cfg_eq.get("oclusion", {})
    try:
        ocluidas = detecciones_ocluidas(
            cache, **{k: v for k, v in cfg_oc.items() if k != "activo"}
        )
    except Exception:
        ocluidas = set()

    def clasifica_feats(pares):
        feats = [(p, colores[p]) for p in pares if p in colores]
        if not feats:
            return None
        media = color_medio_limpio(feats, ocluidas)
        return clf.predict_color(media) if media is not None else None

    def etiquetar(modo, ventana_s=1.5):
        """{(frame, det_idx): equipo} según la estrategia."""
        salida = {}
        for ident in ids:
            obs = sorted(
                (
                    (par, p, t)
                    for tr in ident
                    for p, par, t in zip(tr.pos, tr.det_idxs, tr.ts)
                ),
                key=lambda o: o[2],
            )
            pares = [tuple(o[0]) for o in obs]
            if modo == "identidad":
                eq = clasifica_feats(pares) or "otro"
                for par in pares:
                    salida[par] = eq
            elif modo == "observacion":
                for par in pares:
                    salida[par] = clasifica_feats([par]) or "otro"
            else:  # ventana: promedio de features de los últimos N segundos
                for i, o in enumerate(obs):
                    t0 = o[2]
                    ventana = [
                        pares[j]
                        for j in range(len(obs))
                        if abs(obs[j][2] - t0) <= ventana_s / 2
                    ]
                    salida[pares[i]] = clasifica_feats(ventana) or "otro"
        return salida

    pos = {}
    for ident in ids:
        for tr in ident:
            for pp, par in zip(tr.pos, tr.det_idxs):
                pos[tuple(par)] = (float(pp[0]), float(pp[1]))
    # Identidades puras vs contaminadas, para desglosar ganancia y pérdida
    contaminada = {}
    for ident in ids:
        gs = [mapa.get(tuple(par)) for tr in ident for par in tr.det_idxs]
        gs = [x for x in gs if x is not None]
        for tr in ident:
            for par in tr.det_idxs:
                contaminada[tuple(par)] = len(set(gs)) > 1

    def evalua(etiquetas, nombre):
        pf = {}
        for par, eq in etiquetas.items():
            eqn = str(eq).replace("portero_", "")
            if eqn in ("A", "B") and par in pos:
                pf.setdefault((par[0], eqn), []).append(pos[par])
        m = (
            metricas_producto(pf)
            .set_index(["frame", "equipo"])
            .join(verdad, rsuffix="_gt", how="inner")
        )
        cen = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt).median() if len(m) else np.nan
        anc = (m.ancho - m.ancho_gt).abs().median() if len(m) else np.nan
        # Aciertos por observación, desglosados
        bien = {"puras": [0, 0], "contaminadas": [0, 0]}
        por_franja = {n: [0, 0] for n, _l, _h in FRANJAS}
        for par, eq in etiquetas.items():
            g = mapa.get(par)
            if g is None:
                continue
            real = eq_gt.get(g)
            ok = str(eq).replace("portero_", "") == real
            cubo = "contaminadas" if contaminada.get(par) else "puras"
            bien[cubo][0] += ok
            bien[cubo][1] += 1
            y = pos.get(par, (0, 0))[1]
            for n, lo, hi in FRANJAS:
                if lo <= y < hi:
                    por_franja[n][0] += ok
                    por_franja[n][1] += 1
        return cen, anc, bien, por_franja

    from src.team_classification.pipeline_equipos import clasificar_identidades

    eq_sistema = dict(clasificar_identidades(ids, colores, clf, cfg_eq))
    et_sistema = {}
    for k, ident in enumerate(ids, start=1):
        for tr in ident:
            for par in tr.det_idxs:
                et_sistema[tuple(par)] = str(eq_sistema.get(k, "otro"))

    estrategias = [
        ("SISTEMA REAL (referencia)", et_sistema),
        ("identidad, solo color", etiquetar("identidad")),
        ("observación", etiquetar("observacion")),
        ("ventana 1,0 s", etiquetar("ventana", 1.0)),
        ("ventana 2,0 s", etiquetar("ventana", 2.0)),
        ("ventana 4,0 s", etiquetar("ventana", 4.0)),
    ]

    cab = (
        f"{'estrategia':<24}{'centroide':>11}{'anchura':>9}"
        f"{'acierto PURAS':>15}{'acierto CONTAM.':>17}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    guardado = {}
    for nombre, et in estrategias:
        cen, anc, bien, franjas = evalua(et, nombre)
        guardado[nombre] = franjas
        pp = bien["puras"][0] / max(bien["puras"][1], 1)
        pc = bien["contaminadas"][0] / max(bien["contaminadas"][1], 1)
        print(f"{nombre:<24}{cen:>10.2f}m{anc:>8.2f}m{pp:>14.1%}{pc:>16.1%}")
    print("-" * len(cab))
    print(
        f"  observaciones en identidades puras: {bien['puras'][1]} · "
        f"en contaminadas: {bien['contaminadas'][1]}"
    )

    print("\n── ACIERTO POR FRANJA DE PROFUNDIDAD ──\n")
    cab2 = f"{'estrategia':<24}" + "".join(f"{n:>12}" for n, _l, _h in FRANJAS)
    print(cab2)
    print("-" * len(cab2))
    for nombre, _et in estrategias:
        fila = f"{nombre:<24}"
        for n, _l, _h in FRANJAS:
            ok, tot = guardado[nombre][n]
            fila += f"{ok/max(tot,1):>11.1%}" if tot else f"{'—':>12}"
        print(fila)


if __name__ == "__main__":
    main()
