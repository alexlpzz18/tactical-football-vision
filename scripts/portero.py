#!/usr/bin/env python
"""¿Se puede identificar al PORTERO por comportamiento? Los dos criterios.

El portero lleva TRES intentos rompiendo cosas: destrozó el doble pase
por colores (su equipación es distinta a propósito, así que partir el
caché por color lo trocea y el trozo del pase equivocado se convierte en
un jugador fantasma dentro del área), casi rompe la regla de staff lento
(es el más lento del partido, 0,60 m/s) y su exclusividad de área se come
jugadores de campo. Es la pieza que decide si el diseño de tres grupos
aguanta, así que se mide ANTES de construir nada.

Alex corrige de entrada dos reglas que parecían obvias y son FALSAS: un
portero bien entrenado juega ADELANTADO —si el balón está en campo rival
sube casi al centro, para cortar los pelotazos a la espalda de la
defensa— así que ni "vive en su tercio" ni "se mueve poco
longitudinalmente" valen. Lo invariante es otra cosa:

1. **ÚLTIMO HOMBRE**: adelantado o no, está casi siempre por detrás de
   todos los jugadores de su equipo.
2. **NO CRUZA EL MEDIO CAMPO**: sube hasta el círculo, pero no lo pasa.

Se miden los dos contra el GT, en las DOS patas, y —esto es lo que decide
si sirven— **con su línea base**: si un defensa central es último hombre
el 40 % del tiempo, el criterio no separa. Un criterio solo vale por lo
que lo distingue del siguiente candidato.

⚠️ El GT es la verdad de POSICIÓN, no del sistema: aquí se mide si los
criterios son ciertos EN EL FÚTBOL, no si nuestro tracker los detecta.
Si fallan aquí, no hay nada que construir encima.

Uso:
    python scripts/portero.py
    python scripts/portero.py --config configs/processor_villa_v4_cache.yaml \
        --gt data/annotations/ground_truth_tracking/annotations.xml --offset 7500
"""

import argparse
import logging
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    cargar_config_equipos,
)

logger = logging.getLogger("portero")


def cargar(ruta_cfg, ruta_gt, offset, paso):
    cfg = yaml.safe_load(open(ruta_cfg))
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    modelo, _prof = _profundidad_configurada(cfg_eq)
    H = np.load(cfg["rutas"]["homografia"])
    gt = gt_a_por_frame(parsear_cvat(ruta_gt), H, frame_offset=offset, paso_gt=paso)
    return cfg_eq, modelo, gt


def por_persona(gt):
    """{obj_id: (equipo, es_portero, [(frame, x, y), ...])}."""
    datos = defaultdict(lambda: {"equipo": None, "portero": False, "pos": []})
    for f, obs in gt.items():
        for o in obs:
            etiqueta = str(o.team)
            if o.label == "referee" or etiqueta in ("None", "?"):
                equipo, portero = "arbitro", False
            else:
                portero = etiqueta.startswith("portero")
                equipo = etiqueta.replace("portero_", "")
            d = datos[o.obj_id]
            d["equipo"] = equipo
            d["portero"] = portero
            d["pos"].append((f, float(o.pos[0]), float(o.pos[1])))
    return datos


def lado_de_cada_portero(datos, largo):
    """{obj_id del portero: -1 si defiende x=0, +1 si defiende x=largo}."""
    lados = {}
    for oid, d in datos.items():
        if not d["portero"]:
            continue
        mx = float(np.median([x for _f, x, _y in d["pos"]]))
        lados[oid] = -1 if mx < largo / 2 else +1
    return lados


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg_eq, modelo, gt = cargar(args.config, args.gt, args.offset, args.paso)
    datos = por_persona(gt)
    largo = modelo.largo
    lados = lado_de_cada_portero(datos, largo)
    print(f"\n{args.config}")
    print(
        f"  campo {largo:.1f} x {modelo.ancho:.1f} m · {len(gt)} frames de GT · "
        f"{len(datos)} personas"
    )
    porteros = [o for o, d in datos.items() if d["portero"]]
    print(
        f"  porteros en el GT: {porteros} "
        f"({', '.join(f'{o}: defiende x={0 if lados[o] < 0 else largo:.0f}' for o in porteros)})"
    )

    # Posiciones por (frame, equipo)
    por_frame = defaultdict(list)
    for oid, d in datos.items():
        if d["equipo"] not in ("A", "B"):
            continue
        for f, x, y in d["pos"]:
            por_frame[(f, d["equipo"])].append((oid, x, y))

    # ── CRITERIO 1: ÚLTIMO HOMBRE ────────────────────────────────────
    print("\n" + "=" * 74)
    print("CRITERIO 1: ¿es el portero el ÚLTIMO HOMBRE de su equipo?")
    print("=" * 74)
    veces_ultimo = defaultdict(int)
    veces_presente = defaultdict(int)
    for (f, equipo), gente in por_frame.items():
        # de qué lado defiende este equipo: el de su portero
        suyo = [o for o in porteros if datos[o]["equipo"] == equipo]
        if not suyo:
            continue
        lado = lados[suyo[0]]
        # "detrás" = hacia su propia portería. OJO CON EL SIGNO: si el
        # equipo defiende x=0 (lado -1), el último hombre es el de x MÁS
        # PEQUEÑA. `min(key=lado*x)` con lado=-1 minimiza -x, o sea coge
        # la x mayor: justo el contrario. Lo delató que los dos porteros
        # salieran a 0 % en un criterio que Alex dice que se cumple casi
        # siempre — un número imposible es más fiable que releer el signo.
        extremo = min(gente, key=lambda g: -lado * g[1])
        for oid, _x, _y in gente:
            veces_presente[oid] += 1
        veces_ultimo[extremo[0]] += 1
    cab = f"  {'persona':<10}{'equipo':<9}{'¿portero?':<11}{'frames':>8}{'último hombre':>16}"
    print(cab)
    print("  " + "-" * (len(cab) - 2))
    filas = sorted(
        veces_presente,
        key=lambda o: -veces_ultimo[o] / max(veces_presente[o], 1),
    )
    for oid in filas:
        n, u = veces_presente[oid], veces_ultimo[oid]
        marca = "SÍ" if datos[oid]["portero"] else "no"
        print(
            f"  {oid:<10}{datos[oid]['equipo']:<9}{marca:<11}{n:>8}"
            f"{f'{u}/{n} = {u/max(n,1):.0%}':>16}"
        )

    # Lo que decide: ¿el que MÁS veces es último hombre es el portero?
    print("\n  Lo que decide si el criterio SEPARA:")
    for equipo in ("A", "B"):
        gente = [o for o in veces_presente if datos[o]["equipo"] == equipo]
        if not gente:
            continue
        orden = sorted(
            gente, key=lambda o: -veces_ultimo[o] / max(veces_presente[o], 1)
        )
        primero, segundo = orden[0], orden[1] if len(orden) > 1 else None
        r1 = veces_ultimo[primero] / max(veces_presente[primero], 1)
        r2 = veces_ultimo[segundo] / max(veces_presente[segundo], 1) if segundo else 0.0
        ok = "✔ es el portero" if datos[primero]["portero"] else "✘ NO es el portero"
        print(
            f"    equipo {equipo}: el más 'último hombre' es la persona "
            f"{primero} ({r1:.0%})  {ok}"
        )
        print(
            f"               el segundo es {segundo} ({r2:.0%})  "
            f"→ margen de {r1 - r2:.0%} puntos"
        )

    # ── CRITERIO 2: NO CRUZA EL MEDIO CAMPO ──────────────────────────
    print("\n" + "=" * 74)
    print("CRITERIO 2: ¿cruza el medio campo?")
    print("=" * 74)
    print(f"  (medio campo en x = {largo/2:.1f} m)")
    cab2 = (
        f"  {'persona':<10}{'equipo':<9}{'¿portero?':<11}{'frames':>8}"
        f"{'cruza el medio':>16}{'x más lejos':>13}"
    )
    print(cab2)
    print("  " + "-" * (len(cab2) - 2))
    resumen = []
    for oid, d in sorted(datos.items()):
        if d["equipo"] not in ("A", "B"):
            continue
        suyo = [o for o in porteros if datos[o]["equipo"] == d["equipo"]]
        if not suyo:
            continue
        lado = lados[suyo[0]]
        xs = np.array([x for _f, x, _y in d["pos"]])
        # distancia RECORRIDA hacia campo contrario desde su portería
        avance = (xs - largo / 2) * (-lado)
        cruza = int((avance > 0).sum())
        resumen.append((oid, d, len(xs), cruza, float(avance.max())))
    for oid, d, n, cruza, maximo in sorted(resumen, key=lambda r: r[3] / max(r[2], 1)):
        marca = "SÍ" if d["portero"] else "no"
        print(
            f"  {oid:<10}{d['equipo']:<9}{marca:<11}{n:>8}"
            f"{f'{cruza}/{n} = {cruza/max(n,1):.0%}':>16}"
            f"{maximo:>12.1f}m"
        )
    print("\n  ('x más lejos' = metros que pasó del medio campo hacia el campo")
    print("   contrario; negativo significa que nunca lo cruzó)")


if __name__ == "__main__":
    main()
