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


def lados_por_equipo(datos, modelo, usar_etiqueta=False):
    """{equipo: -1 si defiende x=0, +1 si defiende x=largo}.

    ⚠️ ESTO ERA CIRCULAR y lo cazó la verificación adversarial. La primera
    versión sacaba el lado de la posición del PORTERO, buscándolo por su
    etiqueta del GT: o sea que el banco le daba al criterio la mitad de la
    respuesta. Con el lado invertido, la regla corona a un jugador de
    campo al 85-91 % sin enterarse de nada.

    Ahora sale de donde sale en producción (`porteros.deducir_lados`): de
    la posición media de los jugadores de cada equipo, porque el equipo
    que defiende x=0 tiene a sus defensas ahí. Y se excluye del voto a
    quien viva dentro de un área de penalti —criterio GEOMÉTRICO, no la
    etiqueta—, igual que hace producción.

    `usar_etiqueta=True` reproduce el cálculo viejo, solo para poder
    comprobar que el nuevo da lo mismo.
    """
    largo = modelo.largo
    if usar_etiqueta:
        lados = {}
        for _oid, d in datos.items():
            if not d["portero"]:
                continue
            mx = float(np.median([x for _f, x, _y in d["pos"]]))
            lados[d["equipo"]] = -1 if mx < largo / 2 else +1
        return lados

    areas = modelo.areas_porteria(margen=2.0)
    medias = {}
    for _oid, d in datos.items():
        if d["equipo"] not in ("A", "B"):
            continue
        mx = float(np.median([x for _f, x, _y in d["pos"]]))
        my = float(np.median([y for _f, _x, y in d["pos"]]))
        en_area = any(
            r[0][0] <= mx <= r[0][1] and r[1][0] <= my <= r[1][1]
            for r in areas.values()
        )
        if en_area:
            continue  # vive en un área: no vota (es el portero, y su voto invierte)
        medias.setdefault(d["equipo"], []).append(mx)
    if len(medias) < 2:
        return {}
    ma = float(np.mean(medias["A"]))
    mb = float(np.mean(medias["B"]))
    bajo = "A" if ma < mb else "B"
    return {bajo: -1, ("B" if bajo == "A" else "A"): +1}


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
    lados = lados_por_equipo(datos, modelo)
    lados_viejo = lados_por_equipo(datos, modelo, usar_etiqueta=True)
    print(f"\n{args.config}")
    print(
        f"  campo {largo:.1f} x {modelo.ancho:.1f} m · {len(gt)} frames de GT · "
        f"{len(datos)} personas"
    )
    porteros = [o for o, d in datos.items() if d["portero"]]
    print(f"  porteros en el GT: {porteros}")
    print(f"  lado DEDUCIDO de las posiciones (sin usar la etiqueta): {lados}")
    print(f"  lado que daba el cálculo CIRCULAR viejo:                {lados_viejo}")
    if lados != lados_viejo:
        print("  ⚠️ NO COINCIDEN. Se mide con el deducido, que es el honesto.")
    else:
        print("  → coinciden: el criterio se mide sin verle la respuesta al GT.")

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
        lado = lados.get(equipo)
        if lado is None:
            continue
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
    cab = (
        f"  {'persona':<10}{'equipo':<9}{'¿portero?':<11}{'frames':>8}"
        f"{'último hombre':>16}{'puntuación':>13}"
    )
    print(cab)
    print("  " + "-" * (len(cab) - 2))
    filas = sorted(
        veces_presente,
        key=lambda o: -puntuacion(veces_ultimo[o], veces_presente[o]),
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
            gente, key=lambda o: -puntuacion(veces_ultimo[o], veces_presente[o])
        )
        primero, segundo = orden[0], orden[1] if len(orden) > 1 else None
        r1 = puntuacion(veces_ultimo[primero], veces_presente[primero])
        # OJO: `if segundo` es FALSO cuando el segundo es el obj_id 0, que
        # existe. El script llegó a imprimir "el segundo es 0 (0%)" cuando
        # esa persona era último hombre el 2 % — margen 98 disfrazado de
        # 100. Con un central de obj_id 0 al 40 % habría dicho 60 en vez
        # de 20, que es justo la cifra de la que depende la decisión.
        r2 = (
            puntuacion(veces_ultimo[segundo], veces_presente[segundo])
            if segundo is not None
            else 0.0
        )
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
        lado = lados.get(d["equipo"])
        if lado is None:
            continue
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

    robustez(datos, por_frame, porteros, lados, largo)


def puntuacion(veces: int, presente: int) -> float:
    """Cota inferior de Wilson al 95 % para veces/presente.

    Por qué no el ratio a secas, y lo cazó la verificación adversarial:
    un rival con UNA SOLA observación en la que resulta ser último hombre
    puntúa 1/1 = 100 % y le gana al portero real con 55/60 = 92 %. Con el
    GT no muerde —todo el mundo está en casi todos los frames— pero con
    NUESTRAS identidades, repartidas en una mediana de 6 fragmentos por
    jugador, es exactamente lo que va a pasar.

    Y filtrar por un mínimo de presencia tampoco vale: vacía el ranking,
    porque los fragmentos son cortos por definición. Hay que PONDERAR por
    presencia, no filtrar por ella, y para eso está esta cota: penaliza
    la muestra pequeña sin descartarla.

        1/1   -> 0,21      (el impostor de una observación se hunde)
        55/60 -> 0,82      (el portero real aguanta)
        59/59 -> 0,94
    """
    if presente <= 0:
        return 0.0
    z = 1.96
    p = veces / presente
    n = presente
    centro = p + z * z / (2 * n)
    margen = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return max((centro - margen) / (1 + z * z / n), 0.0)


def _mas_ultimo_hombre(
    por_frame, datos, porteros, lados, equipo, frames=None, ocultar=None
):
    """(persona con más votos de último hombre, su ratio, ratio del segundo).

    `ocultar` es un conjunto de (frame, persona) que se quita antes de
    votar: sirve para simular que el detector no vio a alguien.
    """
    veces, presente = {}, {}
    for (f, eq), gente in por_frame.items():
        if eq != equipo or (frames is not None and f not in frames):
            continue
        lado = lados.get(eq)
        if lado is None:
            continue
        visibles = [g for g in gente if not (ocultar and (f, g[0]) in ocultar)]
        if not visibles:
            continue
        extremo = min(visibles, key=lambda g: -lado * g[1])
        for oid, _x, _y in visibles:
            presente[oid] = presente.get(oid, 0) + 1
        veces[extremo[0]] = veces.get(extremo[0], 0) + 1
    if not presente:
        return None, 0.0, 0.0
    orden = sorted(presente, key=lambda o: -veces.get(o, 0) / max(presente[o], 1))
    r1 = veces.get(orden[0], 0) / max(presente[orden[0]], 1)
    r2 = veces.get(orden[1], 0) / max(presente[orden[1]], 1) if len(orden) > 1 else 0.0
    return orden[0], r1, r2


def robustez(datos, por_frame, porteros, lados, largo):
    """¿Aguanta el criterio 1 lo que le va a pasar en producción?

    Se mide contra las dos cosas que el GT esconde: que el tramo sea corto
    y que el detector se deje gente. Si el criterio necesita 60 frames y
    que estén todos, no sirve.
    """
    import random

    print("\n" + "=" * 74)
    print("ROBUSTEZ DEL CRITERIO 1 (es de lo que depende la Parte 2)")
    print("=" * 74)
    frames = sorted({f for f, _eq in por_frame})

    print("\n  a) ¿Cuántos frames hace falta? (ventanas desde el principio)")
    cab = f"    {'ventana':<10}{'equipo A':<28}{'equipo B':<28}"
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    for n in (5, 10, 20, 30, len(frames)):
        celdas = []
        for equipo in ("A", "B"):
            oid, r1, r2 = _mas_ultimo_hombre(
                por_frame, datos, porteros, lados, equipo, frames=set(frames[:n])
            )
            ok = "✔" if oid is not None and datos[oid]["portero"] else "✘"
            celdas.append(f"{ok} persona {oid} ({r1:.0%}, 2º {r2:.0%})")
        print(f"    {f'{n} frames':<10}{celdas[0]:<28}{celdas[1]:<28}")

    print("\n  b) ¿Y si el detector NO ve al portero en parte de los frames?")
    cab2 = f"    {'portero oculto':<16}{'equipo A':<28}{'equipo B':<28}"
    print(cab2)
    print("    " + "-" * (len(cab2) - 4))
    for frac in (0.0, 0.2, 0.5, 0.8, 1.0):
        rnd = random.Random(7)
        ocultar = {(f, o) for o in porteros for f in frames if rnd.random() < frac}
        celdas = []
        for equipo in ("A", "B"):
            oid, r1, r2 = _mas_ultimo_hombre(
                por_frame, datos, porteros, lados, equipo, ocultar=ocultar
            )
            ok = "✔" if oid is not None and datos[oid]["portero"] else "✘"
            celdas.append(f"{ok} persona {oid} ({r1:.0%}, 2º {r2:.0%})")
        print(f"    {f'{frac:.0%}':<16}{celdas[0]:<28}{celdas[1]:<28}")
    print("\n    (al 100 % el portero no existe para el criterio: lo que salga")
    print("     ahí es el falso positivo que habría que descartar por el veto)")

    print("\n  c) ¿Sigue siendo último hombre cuando MÁS adelantado está?")
    for oid in porteros:
        d = datos[oid]
        lado = lados[d["equipo"]]
        pos = sorted(d["pos"], key=lambda p: -lado * p[1], reverse=True)
        adelantados = {f for f, _x, _y in pos[: max(len(pos) // 5, 1)]}
        _o, r1, _r2 = _mas_ultimo_hombre(
            por_frame, datos, porteros, lados, d["equipo"], frames=adelantados
        )
        veces = 0
        for (f, eq), gente in por_frame.items():
            if eq != d["equipo"] or f not in adelantados:
                continue
            if min(gente, key=lambda g: -lado * g[1])[0] == oid:
                veces += 1
        print(
            f"    portero {oid} (equipo {d['equipo']}), en el 20 % de frames en que "
            f"más sube: último hombre {veces}/{len(adelantados)} = "
            f"{veces/max(len(adelantados),1):.0%}"
        )


if __name__ == "__main__":
    main()
