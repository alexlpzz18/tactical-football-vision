#!/usr/bin/env python
"""¿Sustituye el portero por ÚLTIMO HOMBRE a la regla de área?

La regla de área tiene dos defectos medidos: se come a los jugadores de
campo que pasan el rato ahí (el caso del `id 55`, que la exclusividad
tapa a medias) y no puede encontrar al portero cuando el catálogo
arbitral lo manda al cajón 'otro' por su equipación.

La regla nueva (`docs/portero.md`) corona por comportamiento y **sabe
abstenerse**: 8 de 8 en las dos patas, con el caso negativo incluido.
Aquí se decide la adopción con el criterio de siempre: métricas de
producto en las DOS patas, y nada se adopta si degrada alguna.

Además:
- **El caso del id 55**: quién corona cada método y si es una persona
  real del GT.
- **El orden de las reglas**: el catálogo arbitral corre ANTES y puede
  mandar al portero a 'otro'; las dos reglas de portero corren DESPUÉS y
  lo sobrescriben, así que la posición manda sobre el color. Se comprueba
  que ningún portero acabe como 'otro' ni como 'staff'.

Uso:
    python scripts/adoptar_portero.py
    python scripts/adoptar_portero.py --config configs/processor_villa_v4_cache.yaml \
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

from oraculos import metricas_producto  # noqa: E402
from portero_identidades import cargar_todo, porteros_del_gt  # noqa: E402
from fugas_en_el_campo import casar_con_gt  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("adoptar")


def medir(cfg_eq, cache, colores, datos, cfg_tr, gt_m, gt_px, modelo):
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
    pf = {}
    for k, ident in enumerate(ids, start=1):
        eq = str(equipos.get(k, "otro")).replace("portero_", "")
        if eq not in ("A", "B"):
            continue
        for tr in ident:
            for pos, par in zip(tr.pos, tr.det_idxs):
                if par[0] in gt_m:
                    pf.setdefault((par[0], eq), []).append(
                        (float(pos[0]), float(pos[1]))
                    )
    pf_gt = {}
    for f, obs in gt_m.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))
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
        for (_f, eq_), pts in p.items():
            for x, y in pts:
                key = (eq_, min(int(x / largo * 3), 2), min(int(y / ancho * 3), 2))
                z[key] = z.get(key, 0) + 1
        tot = sum(z.values()) or 1
        return {k_: v / tot for k_, v in z.items()}

    oc, oc_g = ocupacion(pf), ocupacion(pf_gt)
    dif = sum(abs(oc.get(k_, 0) - oc_g.get(k_, 0)) for k_ in set(oc) | set(oc_g)) / 2
    return dict(
        med=e.median(),
        mea=e.mean(),
        p90=e.quantile(0.9),
        anc=(m.ancho - m.ancho_gt).abs().median(),
        oc=dif,
        pts=sum(len(v) for v in pf.values()),
        ids=ids,
        equipos=equipos,
        duenos=duenos,
    )


def dueno(ident, duenos):
    gs = [duenos.get(tuple(par)) for tr in ident for par in tr.det_idxs]
    gs = [g for g in gs if g is not None]
    return Counter(gs).most_common(1)[0][0] if gs else None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    p.add_argument(
        "--recortar",
        action="store_true",
        help="recortar el caché al rango del GT (menos datos)",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg, cfg_tr, cfg_eq0, datos, cache, colores, gt_m, gt_px = cargar_todo(
        args.config, args.gt, args.offset, args.paso, recortar=args.recortar
    )
    modelo, _prof = _profundidad_configurada(cfg_eq0)
    porteros_gt = porteros_del_gt(gt_m)
    print(f"\n{args.config} · porteros del GT: {porteros_gt}")
    print(
        f"  {len(cache)} frames, {sum(len(e['dets']) for e in cache)} detecciones"
        f"{' (recortado al GT)' if args.recortar else ' (tramo completo)'}"
    )

    variantes = {
        "regla de ÁREA (hoy)": {"activo": True, "metodo": "area"},
        "ÚLTIMO HOMBRE (nueva)": {"activo": True, "metodo": "ultimo_hombre"},
    }
    resultados = {}
    for nombre, cfg_p in variantes.items():
        cfg_eq = {
            **cfg_eq0,
            "porteros": {**cfg_eq0.get("porteros", {}), **cfg_p},
        }
        resultados[nombre] = medir(
            cfg_eq, cache, colores, datos, cfg_tr, gt_m, gt_px, modelo
        )

    cab = (
        f"  {'variante':<24}{'mediana':>9}{'media':>9}{'p90':>9}"
        f"{'anchura':>9}{'ocup':>8}{'pts':>7}"
    )
    print("\n" + cab)
    print("  " + "-" * (len(cab) - 2))
    for nombre, r in resultados.items():
        print(
            f"  {nombre:<24}{r['med']:>8.2f}m{r['mea']:>8.2f}m{r['p90']:>8.2f}m"
            f"{r['anc']:>8.2f}m{r['oc']:>7.1%}{r['pts']:>7}"
        )

    print("\n  ¿A QUIÉN CORONA CADA MÉTODO? (el caso del id 55 y compañía)")
    cab2 = (
        f"    {'variante':<24}{'id':>5}{'obs':>7}{'mediana (m)':>16}"
        f"{'etiqueta':>12}{'del GT':>9}{'¿es portero?':>14}"
    )
    print(cab2)
    print("    " + "-" * (len(cab2) - 4))
    for nombre, r in resultados.items():
        coronados = [k for k, v in r["equipos"].items() if str(v).startswith("portero")]
        if not coronados:
            print(f"    {nombre:<24}{'—':>5}   (no corona a nadie)")
        for k in coronados:
            ident = r["ids"][k - 1]
            pos = np.array([p for tr in ident for p in tr.pos])
            d = dueno(ident, r["duenos"])
            ok = (
                "SÍ" if d in porteros_gt else ("NO ES PORTERO" if d else "no es del GT")
            )
            print(
                f"    {nombre:<24}{k:>5}"
                f"{sum(len(t.det_idxs) for t in ident):>7}"
                f"{f'({np.median(pos[:,0]):.1f},{np.median(pos[:,1]):.1f})':>16}"
                f"{str(r['equipos'][k]):>12}{str(d):>9}{ok:>14}"
            )

    print("\n  ORDEN DE LAS REGLAS: ¿acaba algún portero como 'otro' o 'staff'?")
    for nombre, r in resultados.items():
        malos = []
        for k, ident in enumerate(r["ids"], start=1):
            d = dueno(ident, r["duenos"])
            if d in porteros_gt and str(r["equipos"].get(k)) in ("otro", "staff"):
                malos.append(
                    (k, d, r["equipos"][k], sum(len(t.det_idxs) for t in ident))
                )
        if malos:
            for k, d, et, n in malos:
                print(
                    f"    {nombre:<24} ⚠️ identidad {k} (portero {d}, {n} obs) "
                    f"acaba como '{et}'"
                )
        else:
            print(f"    {nombre:<24} ✔ ningún portero acaba en 'otro' ni 'staff'")


if __name__ == "__main__":
    main()
