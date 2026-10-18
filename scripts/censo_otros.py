#!/usr/bin/env python
"""¿QUÉ HAY exactamente en el grupo "ni A ni B" dentro del campo?

Cambio de enfoque de Alex (26-ago-2026), y es mejor: al árbitro no hay
que IDENTIFICARLO entre 23 candidatos, hay que **descartar**. Dentro del
campo hay tres grupos —los dos colores del partido y "otros"—, y en
"otros" debería haber tres personas: los dos porteros, que ya se
identifican con 8 de 8, y el árbitro. Por eliminación, sin que ninguna
señal de comportamiento tenga que distinguirlo. Es el mismo principio que
la exclusividad un-portero-por-área: **contar y descartar en vez de
identificar**.

La pega está en el paso previo: el grupo "otros" no está limpio. Ahí caen
el público, los árboles proyectados a 176 m, los entrenadores y los
fragmentos de jugadores cuyo recorte es ruido.

Este script hace la foto, que es lo que decide si la vía es viable:

- **una o dos identidades tras filtrar** → el árbitro sale solo y gratis;
- **quince** → el problema no es el árbitro, es limpiar el grupo, y ahí
  es donde hay que meter el esfuerzo (que además es lo que hace falta
  para el staff, que sí paga).

Se enseña como un EMBUDO: cuántas quedan tras cada filtro, y qué son
según el GT.

Uso:
    python scripts/censo_otros.py
    python scripts/censo_otros.py --config configs/processor_villa_v4_cache.yaml \
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
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.team_classification.staff import velocidad_media  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("censo")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja.yaml")
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
        sin_porteros=False,  # el censo quiere el pipeline de PRODUCCIÓN entero
    )
    modelo, _prof = _profundidad_configurada(cfg_eq)
    clf = entrenar_clasificador(colores, cfg_eq, cache)

    print(f"\n{args.config}")
    # ⚠️ Lo primero, porque puede tumbar la vía entera: ¿existe siquiera un
    # tercer cajón de color? El fit se queda con los DOS meta-grupos más
    # grandes y llama 'otro' al resto — pero si la fusión deja solo dos
    # meta-grupos, no hay prototipo 'otro' y el color NO PUEDE mandar a
    # nadie ahí. Entonces el "tercer grupo" no existe por color y lo único
    # que llena ese cajón es el catálogo arbitral.
    if clf._prototipos.otro is None:
        print(
            "  ⚠️ El fit NO produce prototipo 'otro': el color no puede "
            "mandar a nadie al tercer grupo."
        )
        print("     Lo único que llena ese cajón es el catálogo arbitral.")
    else:
        d_a = float(np.linalg.norm(clf._prototipos.otro - clf._prototipos.a))
        d_b = float(np.linalg.norm(clf._prototipos.otro - clf._prototipos.b))
        print(
            f"  El fit SÍ produce prototipo 'otro' (a {d_a:.2f} de A y "
            f"{d_b:.2f} de B)"
        )

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
    tipo_gt = {}
    for _f, obs in gt_m.items():
        for o in obs:
            et = str(o.team)
            tipo_gt[o.obj_id] = (
                "arbitro"
                if o.label == "referee"
                else "portero" if et.startswith("portero") else "jugador"
            )

    filas = []
    for k, ident in enumerate(ids, start=1):
        pos = np.array([p for tr in ident for p in tr.pos])
        pares = [tuple(par) for tr in ident for par in tr.det_idxs]
        gs = [duenos[par] for par in pares if par in duenos]
        dueno = Counter(gs).most_common(1)[0][0] if gs else None
        # ⚠️ Cuántas observaciones sostienen ese "dueño". El GT solo cubre
        # 1 de cada 5 frames del caché, así que una identidad de 493
        # observaciones puede tener 5 casadas — y entonces su dueño
        # mayoritario es ruido, no un hecho.
        n_gt = len(gs)
        mx, my = float(np.median(pos[:, 0])), float(np.median(pos[:, 1]))
        filas.append(
            dict(
                k=k,
                n=len(pares),
                mx=mx,
                my=my,
                dentro=(0 <= mx <= modelo.largo and 0 <= my <= modelo.ancho),
                etiqueta=str(equipos.get(k, "otro")),
                dueno=dueno,
                tipo=tipo_gt.get(dueno, "no es del GT"),
                n_gt=n_gt,
                vel=velocidad_media(ident),
            )
        )

    print(
        f"\n  {len(filas)} identidades en total. Reparto de etiquetas: "
        f"{dict(Counter(f['etiqueta'] for f in filas))}"
    )

    # ── EL EMBUDO ─────────────────────────────────────────────────────
    print("\n  EL EMBUDO: cuántas quedan tras cada filtro")
    pasos = [
        ("todas las identidades", lambda f: True),
        ("ni A ni B", lambda f: f["etiqueta"] not in ("A", "B")),
        ("  + dentro del campo (geométrico)", lambda f: f["dentro"]),
        (
            "  + quitando los porteros",
            lambda f: not f["etiqueta"].startswith("portero"),
        ),
        ("  + quitando el staff", lambda f: f["etiqueta"] != "staff"),
        ("  + con al menos 25 observaciones", lambda f: f["n"] >= 25),
    ]
    quedan = filas
    cab = f"    {'filtro':<36}{'quedan':>8}{'observaciones':>15}"
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    for nombre, cond in pasos:
        quedan = [f for f in quedan if cond(f)]
        print(f"    {nombre:<36}{len(quedan):>8}" f"{sum(f['n'] for f in quedan):>15}")

    print("\n  QUÉ SON las que quedan, según el GT:")
    if not quedan:
        print("    (ninguna)")
    cab2 = (
        f"    {'id':>5}{'obs':>7}{'mediana (m)':>16}{'vel':>8}"
        f"{'etiqueta':>10}{'dueño GT':>10}{'qué es':>16}"
    )
    print(cab2)
    print("    " + "-" * (len(cab2) - 4))
    for f in sorted(quedan, key=lambda x: -x["n"]):
        v = f["vel"]
        pos_txt = f"({f['mx']:.1f},{f['my']:.1f})"
        print(
            f"    {f['k']:>5}{f['n']:>7}{f['n_gt']:>9}"
            f"{pos_txt:>16}"
            f"{(f'{v:.2f}' if v is not None else '—'):>8}"
            f"{f['etiqueta']:>10}{str(f['dueno']):>10}{f['tipo']:>16}"
        )

    # ── ¿Y si se activa el margen del catálogo arbitral? ─────────────
    # Las dos que quedan son el árbitro y UN JUGADOR que el catálogo
    # robó. Y ese caso ya estaba diagnosticado y con el arreglo escrito
    # pero APAGADO: `arbitro.margen_equipo` exige que el color de la
    # identidad esté a más de X·d(A,B) del prototipo más cercano antes de
    # dejar que el catálogo mande. Si eso quita al jugador y respeta al
    # árbitro, la eliminación sale gratis.
    print("\n  ¿LO ARREGLA EL MARGEN DEL CATÁLOGO ARBITRAL? (arbitro.margen_equipo)")
    cab3 = (
        f"    {'margen':>8}{'marcadas árbitro':>19}{'quedan tras el embudo':>24}"
        f"{'quiénes':>28}"
    )
    print(cab3)
    print("    " + "-" * (len(cab3) - 4))
    for margen in (0.60, 0.62, 0.68, 0.75, 0.78):
        cfg2 = {
            **cfg_eq,
            "arbitro": {**cfg_eq.get("arbitro", {}), "margen_equipo": margen},
        }
        eq2 = clasificar_identidades(ids, colores, clf, cfg2)
        n_arb = sum(1 for v in eq2.values() if v == "otro")
        restan = []
        for f in filas:
            et = str(eq2.get(f["k"], "otro"))
            if et in ("A", "B") or et.startswith("portero") or et == "staff":
                continue
            if not f["dentro"] or f["n"] < 25:
                continue
            restan.append((f["k"], f["tipo"], f["n_gt"]))
        quienes = ", ".join(f"{k}:{t[:8]}({g})" for k, t, g in restan) or "ninguna"
        print(f"    {margen:>8.2f}{n_arb:>10}{len(restan):>9}{quienes:>44}")

    print("\n  VEREDICTO")
    n = len(quedan)
    if n <= 2:
        print(f"    {n} identidades: el árbitro sale por eliminación y GRATIS.")
    elif n <= 5:
        print(f"    {n} identidades: casi. Falta un filtro más para que salga solo.")
    else:
        print(f"    {n} identidades: la vía de eliminación NO es viable todavía.")
        print("    El problema no es identificar al árbitro, es LIMPIAR el grupo.")


if __name__ == "__main__":
    main()
