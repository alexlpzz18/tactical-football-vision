#!/usr/bin/env python
"""¿Adoptamos la etiqueta POR OBSERVACIÓN? Medida contra el producto.

Alex, viendo el vídeo del acumulado: *"el vídeo sigue confundiendo
naranjas con blancos, ¿ya no debería pasar con el nuevo pipeline o no lo
has aplicado todavía?"*. No está aplicado: lo que se adoptó esta semana
—staff lento, portero por último hombre, n_init 50— **no toca la etiqueta
de equipo**, que se sigue decidiendo por voto sobre toda la identidad.

Medido sobre el caché de producción del benjamín:

    voto por identidad (hoy) : 116 de 747 observaciones con el equipo
                               equivocado = 15,5 %, y 11 identidades
                               mezclan los dos equipos
    por observación          : 24 de 747 = 3,2 %

Cinco veces menos. Pero eso es accuracy de etiqueta, no producto, y ya
nos pasó una vez que la métrica que decidía no medía lo que creíamos. Así
que aquí se mide contra centroide, anchura y ocupación, en las dos patas.

⚠️ Las reglas posicionales SIGUEN SIENDO POR IDENTIDAD y mandan: un
portero es portero en todas sus observaciones, y el staff no juega en
ninguna. Lo que pasa a decidirse por observación es solo el A/B del
color, que es donde el voto arrastra.

Uso:
    python scripts/etiqueta_por_observacion_producto.py
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

from oraculos import metricas_producto  # noqa: E402
from portero_identidades import cargar_todo  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("por_obs")


def bloques(
    ids, equipos, colores, clf, gt_m, por_observacion, forzar_ab=False, ventana_s=0.0
):
    """Con `ventana_s` > 0 la etiqueta sale del color MEDIO de los últimos
    N segundos, no de una sola observación ni de toda la identidad.

    Es el punto medio: conserva parte de la robustez del promedio y deja
    de arrastrar la identidad entera cuando cambia de persona.
    """
    """{(frame, equipo): [posiciones]} con una u otra estrategia."""
    from src.team_classification.oclusion import color_medio_limpio

    pf = {}
    for k, ident in enumerate(ids, start=1):
        etiqueta = str(equipos.get(k, "otro"))
        # Las reglas posicionales mandan sobre toda la identidad
        if etiqueta == "staff" or etiqueta == "otro":
            continue
        fijo = (
            etiqueta.replace("portero_", "") if etiqueta.startswith("portero") else None
        )
        obs = sorted(
            (
                (t, tuple(par), pos)
                for tr in ident
                for t, par, pos in zip(tr.ts, tr.det_idxs, tr.pos)
            ),
            key=lambda o: o[0],
        )
        for t_actual, par, pos in obs:
            if par[0] not in gt_m:
                continue
            if True:
                if fijo is not None:
                    eq = fijo
                elif ventana_s > 0:
                    cerca = [
                        (p, colores[p])
                        for t2, p, _q in obs
                        if abs(t2 - t_actual) <= ventana_s / 2 and p in colores
                    ]
                    media = color_medio_limpio(cerca, None) if cerca else None
                    eq = (
                        clf.predict_color(media, solo_equipos=forzar_ab)
                        if media is not None
                        else etiqueta
                    )
                elif por_observacion and tuple(par) in colores:
                    # `solo_equipos` fuerza a elegir entre A y B. Hace falta
                    # para que la comparación sea justa: en Villaviciosa el
                    # fit SÍ produce prototipo 'otro' y la etiqueta por
                    # observación mandaba allí 219 puntos al tercer cajón,
                    # así que el bloque encogía y las métricas cambiaban de
                    # significado. En el benjamín no hay 'otro' y da igual.
                    eq = clf.predict_color(colores[tuple(par)], solo_equipos=forzar_ab)
                else:
                    eq = etiqueta
                if eq in ("A", "B"):
                    pf.setdefault((par[0], eq), []).append(
                        (float(pos[0]), float(pos[1]))
                    )
    return pf


def medir(pf, pf_gt, modelo):
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])
    m = (
        metricas_producto(pf)
        .set_index(["frame", "equipo"])
        .join(verdad, rsuffix="_gt", how="inner")
    )
    e = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt)
    largo, ancho = modelo.largo, modelo.ancho

    def ocupacion(p):
        z = {}
        for (_f, eq), pts in p.items():
            for x, y in pts:
                k = (eq, min(int(x / largo * 3), 2), min(int(y / ancho * 3), 2))
                z[k] = z.get(k, 0) + 1
        tot = sum(z.values()) or 1
        return {k: v / tot for k, v in z.items()}

    oc, oc_g = ocupacion(pf), ocupacion(pf_gt)
    dif = sum(abs(oc.get(k, 0) - oc_g.get(k, 0)) for k in set(oc) | set(oc_g)) / 2
    return (
        e.median(),
        e.mean(),
        e.quantile(0.9),
        (m.ancho - m.ancho_gt).abs().median(),
        dif,
        sum(len(v) for v in pf.values()),
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_acumulado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg, cfg_tr, cfg_eq, datos, cache, colores, gt_m, gt_px = cargar_todo(
        args.config,
        args.gt,
        args.offset,
        args.paso,
        recortar=False,
        sin_porteros=False,
    )
    modelo, _prof = _profundidad_configurada(cfg_eq)
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
    )
    equipos = clasificar_identidades(ids, colores, clf, cfg_eq)
    pf_gt = {}
    for f, obs in gt_m.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))

    print(f"\n{args.config}")
    cab = (
        f"  {'estrategia':<26}{'mediana':>9}{'media':>9}{'p90':>9}"
        f"{'anchura':>9}{'ocup':>8}{'pts':>7}"
    )
    print(cab)
    print("  " + "-" * (len(cab) - 2))
    for nombre, por_obs, forzar, ventana in (
        ("voto por identidad (hoy)", False, False, 0.0),
        ("por observación", True, True, 0.0),
        ("ventana 1,0 s", False, True, 1.0),
        ("ventana 2,0 s", False, True, 2.0),
        ("ventana 4,0 s", False, True, 4.0),
        ("ventana 8,0 s", False, True, 8.0),
    ):
        pf = bloques(ids, equipos, colores, clf, gt_m, por_obs, forzar, ventana)
        med, mea, p90, anc, oc, pts = medir(pf, pf_gt, modelo)
        print(
            f"  {nombre:<26}{med:>8.2f}m{mea:>8.2f}m{p90:>8.2f}m"
            f"{anc:>8.2f}m{oc:>7.1%}{pts:>7}"
        )


if __name__ == "__main__":
    main()
