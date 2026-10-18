#!/usr/bin/env python
"""El STAFF: los criterios de Alex, medidos antes de construir nada.

Es el que paga: **vive en el BORDE, y por eso rompe la anchura**. Medido
antes (`docs/reglas_fisicas.md`, `docs/arbitro.md`): sacar del bloque a
quien no juega vale 0,68 m de media de centroide y **el 61 % del error de
anchura**, mientras que el árbitro —que vive en medio del juego— vale
0,41-0,61 m y CERO de anchura. La diferencia no es ser no-jugador: es
estar en el borde.

Los criterios que propuso Alex:

1. **Franja estrecha junto a la banda**, siempre del MISMO lado (los
   banquillos están en un lado concreto del campo).
2. **Recorrido lateral, no de área a área**: se mueve a lo ancho, no a lo
   largo.
3. **PERMANENCIA**: lleva minutos en el mismo sitio, y ningún jugador hace
   eso. Es la señal que él considera más fuerte.

Y dos ideas más suyas, que se miden aquí también:

4. **Permanencia como discriminador universal**: un jugador entra al
   campo al principio y sale al final; un intruso aparece a mitad.
5. **La plantilla como ALARMA, nunca como objetivo** (eso ya falló con la
   cota de plantilla): si hay 9 blancos simultáneos, dos sobran.

Media regla ya existe y está adoptada: el *staff lento* (fuera de la
línea Y velocidad < 1,5 m/s), que caza al entrenador del benjamín. Lo que
se mide aquí es qué AÑADEN los criterios nuevos sobre eso.

⚠️ Ninguna de las dos patas anota al staff en su GT, así que "quién es
staff" se establece por exclusión: identidades que no casan con ninguna
persona del GT. Se dice en vez de disimularlo.

Uso:
    python scripts/staff_criterios.py
    python scripts/staff_criterios.py --config configs/processor_villa_v4_cache.yaml \
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

logger = logging.getLogger("staff")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    p.add_argument("--min-obs", type=int, default=25)
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
    por_frame = {e["frame_idx"]: e for e in cache}
    duenos = {}
    for f in sorted(set(por_frame) & set(gt_px)):
        casado, _ = casar_con_gt(por_frame[f]["dets"], gt_px[f])
        for i, o in casado.items():
            duenos[(f, i)] = o["id"]

    frames_totales = sorted({e["frame_idx"] for e in cache})
    t_de = {e["frame_idx"]: e["t"] for e in cache}
    dur = (t_de[frames_totales[-1]] - t_de[frames_totales[0]]) or 1.0

    filas = []
    for k, ident in enumerate(ids, start=1):
        pos = np.array([p for tr in ident for p in tr.pos])
        pares = [tuple(par) for tr in ident for par in tr.det_idxs]
        frames = sorted({par[0] for par in pares})
        gs = [duenos[par] for par in pares if par in duenos]
        n_gt = len(gs)
        dueno = Counter(gs).most_common(1)[0][0] if gs else None
        mx, my = float(np.median(pos[:, 0])), float(np.median(pos[:, 1]))
        # ¿es una persona del GT? Se exige que MÁS DE LA MITAD de sus
        # observaciones casadas apunten al mismo, y al menos 5: un dueño
        # sobre 1 voto no es un hecho (nos mordió en el censo del árbitro).
        es_jugador = n_gt >= 5 and Counter(gs).most_common(1)[0][1] / n_gt > 0.5
        filas.append(
            dict(
                k=k,
                n=len(pares),
                n_gt=n_gt,
                dueno=dueno if es_jugador else None,
                es_jugador=es_jugador,
                mx=mx,
                my=my,
                etiqueta=str(equipos.get(k, "otro")),
                vel=velocidad_media(ident) or 0.0,
                # 1. distancia a la banda MÁS CERCANA (a lo ancho)
                dist_banda=min(abs(my), abs(modelo.ancho - my)),
                # 2. recorrido lateral contra longitudinal
                span_x=float(pos[:, 0].max() - pos[:, 0].min()),
                span_y=float(pos[:, 1].max() - pos[:, 1].min()),
                # 3/4. permanencia: fracción del tramo que dura, y si
                # empieza al principio o aparece a mitad
                cobertura=(t_de[frames[-1]] - t_de[frames[0]]) / dur,
                empieza=(t_de[frames[0]] - t_de[frames_totales[0]]) / dur,
            )
        )

    campo = [f for f in filas if f["n"] >= args.min_obs]
    jug = [f for f in campo if f["es_jugador"]]
    nojug = [f for f in campo if not f["es_jugador"]]
    print(f"\n{args.config}")
    print(
        f"  {len(campo)} identidades con ≥{args.min_obs} obs: "
        f"{len(jug)} son personas del GT, {len(nojug)} no"
    )
    print(
        "  ⚠️ El GT no anota al staff: 'no es del GT' incluye staff, "
        "público, árbitro y fragmentos."
    )

    def compara(clave, titulo, unidad=""):
        a = np.array([f[clave] for f in jug])
        b = np.array([f[clave] for f in nojug])
        if len(a) < 2 or len(b) < 2:
            return
        # solape: fracción de los NO jugadores dentro del p5-p95 de los jugadores
        lo, hi = np.percentile(a, [5, 95])
        sol = float(np.mean((b >= lo) & (b <= hi)))
        s = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
        d = abs(a.mean() - b.mean()) / s if s > 0 else float("nan")
        print(
            f"    {titulo:<38}{np.median(a):>8.2f}{unidad}"
            f"{np.median(b):>10.2f}{unidad}{d:>8.2f}{sol:>9.0%}"
        )

    print("\n  ¿QUÉ SEÑAL SEPARA? (mediana de cada grupo, d de Cohen y solape)")
    cab = (
        f"    {'señal':<38}{'jugadores':>11}{'no jugadores':>13}"
        f"{'d':>7}{'solape':>9}"
    )
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    compara("dist_banda", "1. distancia a la banda más cercana", "m")
    compara("span_y", "2a. recorrido LATERAL (span y)", "m")
    compara("span_x", "2b. recorrido LONGITUDINAL (span x)", "m")
    compara("vel", "3. velocidad media", "")
    compara("cobertura", "4a. fracción del tramo que dura", "")
    compara("empieza", "4b. cuándo aparece (0=al principio)", "")
    print(
        "\n    (d de Cohen alta y solape bajo = separa; solape alto = "
        "indistinguible)"
    )

    print("\n  Las que NO son del GT, una a una:")
    cab2 = (
        f"    {'id':>5}{'obs':>7}{'mediana (m)':>16}{'a banda':>9}"
        f"{'span x':>8}{'span y':>8}{'vel':>7}{'dura':>7}{'etiqueta':>9}"
    )
    print(cab2)
    print("    " + "-" * (len(cab2) - 4))
    for f in sorted(nojug, key=lambda x: -x["n"])[:12]:
        pos_txt = f"({f['mx']:.1f},{f['my']:.1f})"
        print(
            f"    {f['k']:>5}{f['n']:>7}{pos_txt:>16}{f['dist_banda']:>8.1f}m"
            f"{f['span_x']:>7.1f}m{f['span_y']:>7.1f}m{f['vel']:>7.2f}"
            f"{f['cobertura']:>7.0%}{f['etiqueta']:>9}"
        )


if __name__ == "__main__":
    main()
