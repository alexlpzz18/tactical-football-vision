#!/usr/bin/env python
"""PARTE 2: ¿existe el tercer grupo, y se define por COLOR o no?

El diseño de Alex tiene dos mitades:

1. el tercer grupo se define de forma RELATIVA — "todo recorte cuyo color
   esté lejos de los DOS prototipos que el fit encontró en ESTE partido",
   con el umbral derivado de SU distribución;
2. dentro del tercer grupo se separa por COMPORTAMIENTO (portero,
   árbitro, staff), que es donde está medido que está el valor.

⚠️ La mitad 1 lleva **dos intentos fallidos** anotados en
`configs/team_classification_benja.yaml`: umbral absoluto (no viaja:
hundía Villaviciosa de 0,718 a 0,482) y umbral relativo (a 1,2 no cambia
nada; a 1,0 cuesta accuracy). La conclusión que quedó escrita es que el
problema no es el umbral sino los DATOS: "el amarillo del árbitro no está
lejos de los dos prototipos en un histograma HS de un torso de 15-40 px".

Lo nuevo que propone Alex es derivar el umbral de la distribución en vez
de barrerlo. Pero si las distribuciones se SOLAPAN, ninguna forma de
elegir el umbral lo arregla. Así que eso es lo primero que se mide, y se
mide antes de construir nada:

**¿Se separan las distribuciones de distancia al prototipo más cercano
entre las personas que juegan y las que no?**

Si no se separan, la puerta de color no existe, y el tercer grupo hay que
definirlo solo por comportamiento — que es lo que ya hace la regla del
portero, que ignora el color por completo y funciona.

Uso:
    python scripts/tercer_grupo.py
    python scripts/tercer_grupo.py --config configs/processor_villa_v4_cache.yaml \
        --gt data/annotations/ground_truth_tracking/annotations.xml --offset 7500
"""

import argparse
import logging
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from fugas_en_el_campo import casar_con_gt  # noqa: E402
from portero_identidades import cargar_todo  # noqa: E402
from src.team_classification.color_classifier import _solo_hs  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("tercer_grupo")


def separacion(a, b):
    """Cuánto se separan dos muestras, en unidades de su propia dispersión.

    Es la d de Cohen. Se usa en vez de "mirar los percentiles" porque hay
    que poder comparar la separación ENTRE PATAS, y cada partido tiene su
    escala de color.
    """
    a, b = np.asarray(a), np.asarray(b)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    s = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    return abs(a.mean() - b.mean()) / s if s > 0 else float("nan")


def solape(a, b):
    """Fracción de la muestra 'a' que cae dentro del rango central de 'b'."""
    a, b = np.asarray(a), np.asarray(b)
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    lo, hi = np.percentile(b, [5, 95])
    return float(np.mean((a >= lo) & (a <= hi)))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg, cfg_tr, cfg_eq, datos, cache, colores, gt_m, gt_px = cargar_todo(
        args.config, args.gt, args.offset, args.paso, recortar=False
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
    por_frame = {e["frame_idx"]: e for e in cache}
    duenos = {}
    for f in sorted(set(por_frame) & set(gt_px)):
        casado, _ = casar_con_gt(por_frame[f]["dets"], gt_px[f])
        for i, o in casado.items():
            duenos[(f, i)] = o["id"]
    # Quién es quién según el GT: jugadores de campo, porteros, árbitro
    tipo_gt = {}
    for _f, obs in gt_m.items():
        for o in obs:
            et = str(o.team)
            if o.label == "referee":
                tipo_gt[o.obj_id] = "arbitro"
            elif et.startswith("portero"):
                tipo_gt[o.obj_id] = "portero"
            elif et in ("A", "B"):
                tipo_gt[o.obj_id] = "jugador"

    a, b = clf._prototipos.a, clf._prototipos.b
    sep_ab = float(np.linalg.norm(a - b)) or 1.0

    def dist_relativa(feats):
        if not feats:
            return None
        media = np.mean([_solo_hs(f) for f in feats], axis=0)
        return (
            min(float(np.linalg.norm(media - a)), float(np.linalg.norm(media - b)))
            / sep_ab
        )

    filas = []
    for k, ident in enumerate(ids, start=1):
        pares = [tuple(par) for tr in ident for par in tr.det_idxs]
        feats = [colores[par] for par in pares if par in colores]
        d = dist_relativa(feats)
        if d is None:
            continue
        gs = [duenos[par] for par in pares if par in duenos]
        dueno = Counter(gs).most_common(1)[0][0] if gs else None
        tipo = tipo_gt.get(dueno, "NO es del GT")
        pos = np.array([p for tr in ident for p in tr.pos])
        filas.append(
            dict(
                k=k,
                d=d,
                tipo=tipo,
                n=len(pares),
                mx=float(np.median(pos[:, 0])),
                my=float(np.median(pos[:, 1])),
                etiqueta=str(equipos.get(k, "otro")),
            )
        )

    print(f"\n{args.config}")
    print(
        f"  {len(ids)} identidades · separación entre prototipos "
        f"d(A,B) = {sep_ab:.3f}"
    )
    print(
        "\n  ¿SE SEPARAN LAS DISTRIBUCIONES? (distancia al prototipo más "
        "cercano, en unidades de d(A,B))"
    )
    cab = (
        f"    {'grupo':<22}{'n ids':>7}{'obs':>8}{'p5':>8}{'mediana':>9}" f"{'p95':>8}"
    )
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    grupos = {}
    for tipo in ("jugador", "portero", "arbitro", "NO es del GT"):
        sel = [f for f in filas if f["tipo"] == tipo and f["n"] >= 25]
        if not sel:
            continue
        ds = [f["d"] for f in sel]
        grupos[tipo] = ds
        print(
            f"    {tipo:<22}{len(sel):>7}{sum(f['n'] for f in sel):>8}"
            f"{np.percentile(ds,5):>8.2f}{np.median(ds):>9.2f}"
            f"{np.percentile(ds,95):>8.2f}"
        )

    if "jugador" in grupos:
        print("\n    Contra los JUGADORES de campo:")
        for tipo, ds in grupos.items():
            if tipo == "jugador":
                continue
            print(
                f"      {tipo:<20} d de Cohen {separacion(ds, grupos['jugador']):>5.2f}"
                f"  ·  solape {solape(ds, grupos['jugador']):>5.0%}"
            )
        print("      (d de Cohen: <0,8 se considera solape grande; el solape es")
        print("       la fracción de ese grupo que cae dentro del p5-p95 de los")
        print("       jugadores, o sea indistinguible por color)")

    print(
        "\n  Las identidades que NO son del GT, una a una "
        "(las que el tercer grupo tendría que cazar):"
    )
    cab2 = (
        f"    {'id':>5}{'obs':>7}{'mediana (m)':>16}{'dist. relativa':>16}"
        f"{'etiqueta de hoy':>18}"
    )
    print(cab2)
    print("    " + "-" * (len(cab2) - 4))
    for f in sorted(
        [x for x in filas if x["tipo"] == "NO es del GT" and x["n"] >= 25],
        key=lambda x: -x["n"],
    )[:10]:
        pos_txt = f"({f['mx']:.1f},{f['my']:.1f})"
        print(
            f"    {f['k']:>5}{f['n']:>7}"
            f"{pos_txt:>16}"
            f"{f['d']:>16.2f}{f['etiqueta']:>18}"
        )


if __name__ == "__main__":
    main()
