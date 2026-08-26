#!/usr/bin/env python
"""El ÁRBITRO: los tres criterios de Alex, medidos contra el GT.

Se ataca antes que el staff por dos razones suyas: el catálogo de
equipaciones ya lo caza a veces (hay de dónde partir) y, sobre todo, **un
árbitro colado en un equipo mueve el centroide**, mientras que el staff
lento ya está medio resuelto.

Los tres criterios:

1. **Máxima dispersión longitudinal**: recorre todo el campo de área a
   área, cosa que ningún jugador hace tanto.
2. **Mediana cerca del centro** del campo.
3. **Vive ENTRE los dos porteros**, sin quedar nunca por detrás de
   ninguno. Es el que más convence a Alex, y ahora se puede calcular
   porque los porteros están identificados con 8 de 8
   (`docs/portero.md`).

⚠️ **El GT del benjamín NO anota al árbitro** (14 tracks: 12 jugadores y
2 porteros). Solo el de Villaviciosa lo tiene (track 22). Así que la
medición limpia contra verdad de posición solo se puede hacer en una
pata, y en el benjamín hay que identificarlo por exclusión —la persona
que no es ninguna de las 14, vive dentro del campo y persiste—. Se dice
en vez de disimularlo.

Como siempre: cada criterio con su LÍNEA BASE. Un criterio solo vale por
lo que lo separa del siguiente candidato.

Uso:
    python scripts/arbitro_criterios.py
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

logger = logging.getLogger("arbitro")


def cargar(ruta_cfg, ruta_gt, offset, paso):
    cfg = yaml.safe_load(open(ruta_cfg))
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    modelo, _prof = _profundidad_configurada(cfg_eq)
    H = np.load(cfg["rutas"]["homografia"])
    tracks = parsear_cvat(ruta_gt)
    gt = gt_a_por_frame(tracks, H, frame_offset=offset, paso_gt=paso)
    return modelo, gt


def por_persona(gt):
    d = defaultdict(lambda: {"tipo": None, "equipo": None, "pos": []})
    for f, obs in gt.items():
        for o in obs:
            et = str(o.team)
            if o.label == "referee":
                tipo, equipo = "arbitro", None
            elif et.startswith("portero"):
                tipo, equipo = "portero", et.replace("portero_", "")
            else:
                tipo, equipo = "jugador", et
            d[o.obj_id]["tipo"] = tipo
            d[o.obj_id]["equipo"] = equipo
            d[o.obj_id]["pos"].append((f, float(o.pos[0]), float(o.pos[1])))
    return d


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_villa_v4_cache.yaml")
    p.add_argument(
        "--gt", default="data/annotations/ground_truth_tracking/annotations.xml"
    )
    p.add_argument("--offset", type=int, default=7500)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    modelo, gt = cargar(args.config, args.gt, args.offset, args.paso)
    datos = por_persona(gt)
    largo = modelo.largo
    arbitros = [o for o, d in datos.items() if d["tipo"] == "arbitro"]
    porteros = [o for o, d in datos.items() if d["tipo"] == "portero"]
    print(f"\n{args.config} · campo {largo:.0f} m · {len(gt)} frames de GT")
    print(f"  árbitro(s) en el GT: {arbitros or 'NINGUNO'} · porteros: {porteros}")
    if not arbitros:
        print(
            "  ⚠️ Sin árbitro anotado: en esta pata no se puede medir "
            "contra verdad de posición."
        )
        return

    # ── Criterio 1: dispersión longitudinal ───────────────────────────
    # ── Criterio 2: mediana cerca del centro ──────────────────────────
    filas = []
    for oid, d in datos.items():
        xs = np.array([x for _f, x, _y in d["pos"]])
        filas.append(
            dict(
                oid=oid,
                tipo=d["tipo"],
                equipo=d["equipo"],
                n=len(xs),
                recorrido_x=float(xs.max() - xs.min()),
                std_x=float(xs.std()),
                dist_centro=abs(float(np.median(xs)) - largo / 2),
            )
        )

    def tabla(clave, titulo, mayor_es_mejor=True):
        print(f"\n  ── {titulo} ──")
        orden = sorted(filas, key=lambda f: -f[clave] if mayor_es_mejor else f[clave])
        cab = f"    {'#':>3}{'persona':>9}{'tipo':>10}{'n':>6}{clave:>16}"
        print(cab)
        print("    " + "-" * (len(cab) - 4))
        for i, f in enumerate(orden[:5], start=1):
            marca = "  <== EL ÁRBITRO" if f["tipo"] == "arbitro" else ""
            print(
                f"    {i:>3}{f['oid']:>9}{f['tipo']:>10}{f['n']:>6}"
                f"{f[clave]:>16.1f}{marca}"
            )
        puesto = next(i for i, f in enumerate(orden, start=1) if f["tipo"] == "arbitro")
        arb = next(f for f in orden if f["tipo"] == "arbitro")
        segundo = next(f for f in orden if f["tipo"] != "arbitro")
        print(
            f"    → el árbitro va el {puesto}º de {len(orden)}. "
            f"Él {arb[clave]:.1f}, el mejor no-árbitro {segundo[clave]:.1f} "
            f"(margen {abs(arb[clave]-segundo[clave]):.1f})"
        )

    tabla("recorrido_x", "CRITERIO 1: dispersión longitudinal (max−min de x)")
    tabla("std_x", "CRITERIO 1b: desviación típica de x")
    tabla(
        "dist_centro",
        "CRITERIO 2: distancia de la mediana al centro",
        mayor_es_mejor=False,
    )

    # ── Criterio 3: ENTRE los dos porteros ────────────────────────────
    print("\n  ── CRITERIO 3: ¿vive ENTRE los dos porteros? ──")
    pos_por_frame = defaultdict(dict)
    for oid, d in datos.items():
        for f, x, _y in d["pos"]:
            pos_por_frame[f][oid] = x
    if len(porteros) < 2:
        print("    (hacen falta los dos porteros)")
        return
    p0, p1 = porteros
    entre, total = defaultdict(int), defaultdict(int)
    for f, gente in pos_por_frame.items():
        if p0 not in gente or p1 not in gente:
            continue
        lo, hi = sorted((gente[p0], gente[p1]))
        for oid, x in gente.items():
            if oid in (p0, p1):
                continue
            total[oid] += 1
            if lo < x < hi:
                entre[oid] += 1
    cab = f"    {'persona':>9}{'tipo':>10}{'frames':>8}{'entre los porteros':>21}"
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    orden = sorted(total, key=lambda o: entre[o] / max(total[o], 1))
    for oid in orden[:4] + ["..."] + orden[-3:]:
        if oid == "...":
            print("    " + " " * 9 + "...")
            continue
        marca = "  <== EL ÁRBITRO" if datos[oid]["tipo"] == "arbitro" else ""
        print(
            f"    {oid:>9}{datos[oid]['tipo']:>10}{total[oid]:>8}"
            f"{f'{entre[oid]}/{total[oid]} = {entre[oid]/max(total[oid],1):.0%}':>21}"
            f"{marca}"
        )
    arb = arbitros[0]
    r_arb = entre[arb] / max(total[arb], 1)
    otros = sorted(
        (entre[o] / max(total[o], 1) for o in total if o != arb), reverse=True
    )
    print(f"\n    → el árbitro está entre los porteros el {r_arb:.0%} del tiempo.")
    print(
        f"      El jugador que más, el {otros[0]:.0%}; la mediana de los "
        f"jugadores, el {np.median(otros):.0%}."
    )
    if r_arb > otros[0]:
        print("      SEPARA: ningún jugador llega.")
    else:
        n_superan = sum(1 for x in otros if x >= r_arb)
        print(f"      NO separa solo: {n_superan} jugadores igualan o superan.")

    criterios_alternativos(datos, modelo, arbitros)


def criterios_alternativos(datos, modelo, arbitros):
    """Si los tres criterios fallan, ¿qué señal SÍ distingue a un árbitro?

    La hipótesis de por qué fallan: los tres hablan de un PARTIDO ENTERO
    ("recorre el campo de área a área") y la ventana medida son 50
    segundos. En 50 s el árbitro no cruza el campo: sigue al balón, que se
    queda en una zona, mientras un lateral sí hace una carrera larga.

    Así que se buscan señales que no necesiten una ventana larga. La idea
    de fondo: un árbitro **no pertenece a ningún bloque**. Un jugador está
    rodeado de compañeros y cerca del centroide de SU equipo; el árbitro
    está más o menos equidistante de los dos y más solo.
    """
    print("\n  ── SEÑALES ALTERNATIVAS (no necesitan ventana larga) ──")
    pos_por_frame = defaultdict(dict)
    for oid, d in datos.items():
        for f, x, y in d["pos"]:
            pos_por_frame[f][oid] = (x, y)
    equipo_de = {o: d["equipo"] for o, d in datos.items()}

    asimetria, soledad = defaultdict(list), defaultdict(list)
    for _f, gente in pos_por_frame.items():
        cent = {}
        for eq in ("A", "B"):
            pts = [p for o, p in gente.items() if equipo_de.get(o) == eq]
            if pts:
                cent[eq] = np.mean(pts, axis=0)
        if len(cent) < 2:
            continue
        for oid, p in gente.items():
            da = float(np.linalg.norm(np.array(p) - cent["A"]))
            db = float(np.linalg.norm(np.array(p) - cent["B"]))
            if da + db > 0:
                asimetria[oid].append(abs(da - db) / (da + db))
            otros = [
                float(np.linalg.norm(np.array(p) - np.array(q)))
                for o2, q in gente.items()
                if o2 != oid
            ]
            if otros:
                soledad[oid].append(min(otros))

    for clave, datos_m, titulo, mayor in (
        (
            "asim",
            asimetria,
            "¿de qué bloque es? |d(centroide A) - d(centroide B)| / suma",
            False,
        ),
        ("solo", soledad, "distancia al vecino MÁS CERCANO (m)", True),
    ):
        vals = {o: float(np.median(v)) for o, v in datos_m.items() if v}
        orden = sorted(vals, key=lambda o: -vals[o] if mayor else vals[o])
        arb = arbitros[0]
        puesto = orden.index(arb) + 1
        print(f"\n    {titulo}")
        cab = f"      {'#':>3}{'persona':>9}{'tipo':>10}{'valor':>10}"
        print(cab)
        for i, o in enumerate(orden[:4], start=1):
            marca = "  <== EL ÁRBITRO" if datos[o]["tipo"] == "arbitro" else ""
            print(f"      {i:>3}{o:>9}{datos[o]['tipo']:>10}{vals[o]:>10.2f}{marca}")
        mejor_otro = next(vals[o] for o in orden if o != arb)
        print(
            f"      → el árbitro va el {puesto}º de {len(orden)}: "
            f"{vals[arb]:.2f} contra {mejor_otro:.2f} del mejor no-árbitro"
        )


if __name__ == "__main__":
    main()
