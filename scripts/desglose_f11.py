#!/usr/bin/env python
"""Desglose del error de producto en F11 (comprobación #1 de la segunda opinión, 26-nov-2026).

La escalera de oráculos y el reparto de Shapley de `desglose_del_error.py` (hechos para el benjamín)
sobre el GT del alevín A («Villaviciosa», 30 s), con lo que pide Alex para F11:
- el peso de **faltan** (MIS) en el centroide, la anchura y la profundidad, y dónde están los que
  faltan (tercio de profundidad);
- el peso de **sobran** (EXT), separado en: el ÁRBITRO (fila A/B a ≤ 2 m del árbitro del GT; en F11
  no corre la pista Viterbi del árbitro), fuera del campo, y el resto.
Criterio (fijado antes): si quitar «faltan» reduce el error de anchura más de un 30 %, la presencia
lejana pasa a prioridad.

Solo lee: el CSV de una pasada de producción con los configs de `main`.

Uso:
    python scripts/desglose_f11.py --csv outputs/literatura/banco/villa/posiciones_actual.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

from desglose_del_error import (  # noqa: E402
    _valor_por_subconjunto,
    construir_frames,
    control_base,
    escalera,
    imprimir_escalera,
    imprimir_shapley,
)
from src.evaluation.desglose_error import EQUIPOS, shapley  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument(
        "--gt", default="data/annotations/ground_truth_tracking/annotations.xml"
    )
    ap.add_argument("--homografia", default="data/calibracion/homografia.npy")
    ap.add_argument("--offset", type=int, default=7500)
    ap.add_argument("--paso", type=int, default=15)
    ap.add_argument("--largo", type=float, default=105.0)
    ap.add_argument("--ancho", type=float, default=68.0)
    ap.add_argument("--radio", type=float, default=2.0)
    a = ap.parse_args()
    H = np.load(R / a.homografia)
    gt_m = gt_a_por_frame(parsear_cvat(R / a.gt), H, a.offset, a.paso)
    todas = pd.read_csv(a.csv)
    reales = todas[todas.es_real == 1].reset_index(drop=True)
    print(f"GT: {len(gt_m)} frames · CSV {a.csv}")
    frames = construir_frames(gt_m, reales, a.radio)
    control_base(frames)
    Rr = escalera(frames)
    imprimir_escalera(Rr)
    sh = imprimir_shapley(Rr, a.radio)

    # ── el criterio: ¿cuánto baja la anchura al quitar «faltan»? ──
    base = _valor_por_subconjunto(Rr, "ancho", "media")
    solo_mis = base[frozenset({"MIS"})]
    print("\n3. CRITERIO (anchura, media)")
    print(
        f"   sistema {base[frozenset()]:.2f} m · arreglando SOLO «faltan» {solo_mis:.2f} m "
        f"({1 - solo_mis / base[frozenset()]:.0%} menos) · parte de Shapley de «faltan» "
        f"{sh[('ancho', 'media')]['MIS']:.2f} m "
        f"({sh[('ancho', 'media')]['MIS'] / base[frozenset()]:.0%})"
    )

    # ── dónde están los que faltan (tercio de profundidad: el eje y en este campo) ──
    tercio = lambda y: min(int(y / a.ancho * 3), 2)  # noqa: E731
    personas = pd.DataFrame(
        [
            (fc.frame, p.equipo, tercio(p.y), p.fila is None)
            for fc in frames
            for p in fc.personas
        ],
        columns=["frame", "equipo", "tercio", "falta"],
    )
    print("\n4. FALTAN, por tercio de profundidad (0 = cerca de la cámara, 2 = fondo)")
    for t, g in personas.groupby("tercio"):
        print(
            f"   tercio {t}: {len(g)} personas del GT · faltan {g.falta.sum()} "
            f"({g.falta.mean():.0%}) · {g.falta.sum() / max(personas.falta.sum(), 1):.0%} "
            "de todas las que faltan"
        )

    # ── sobran: árbitro, fuera del campo, resto ──
    arbitro = {
        f: [np.asarray(o.pos, float) for o in obs if str(o.label) == "referee"]
        for f, obs in gt_m.items()
    }
    tipos = {"arbitro": 0, "fuera_del_campo": 0, "desplazada_2_5m": 0, "resto": 0}
    for fc in frames:
        for i in range(len(fc.x)):
            if i in fc.persona_de_fila or fc.etiqueta[i] not in EQUIPOS:
                continue
            p = np.array([fc.x[i], fc.y[i]])
            if any(np.linalg.norm(p - q) <= a.radio for q in arbitro.get(fc.frame, [])):
                tipos["arbitro"] += 1
            elif not (0 <= p[0] <= a.largo and 0 <= p[1] <= a.ancho):
                tipos["fuera_del_campo"] += 1
            elif i in fc.pareja_de_fila:
                tipos["desplazada_2_5m"] += 1
            else:
                tipos["resto"] += 1
    total = max(sum(tipos.values()), 1)
    print(f"\n5. SOBRAN (filas A/B que no casan con ningún jugador del GT): {total}")
    for k, v in tipos.items():
        print(f"   {k}: {v} ({v / total:.0%}) · {v / len(frames):.2f} por frame")
    print(
        f"   ¿el GT anota al árbitro? {sum(len(v) for v in arbitro.values())} observaciones "
        f"de árbitro en {len(frames)} frames"
    )
    # Shapley del árbitro dentro de EXT: no es separable con este núcleo; se da la parte de EXT
    for metrica in ("centroide", "ancho", "prof"):
        v = _valor_por_subconjunto(Rr, metrica, "media")
        s = shapley(v)
        print(
            f"   {metrica}: parte de «sobran» {s['EXT']:.2f} m de {v[frozenset()]:.2f} "
            f"({s['EXT'] / v[frozenset()]:.0%}); de «faltan» {s['MIS']:.2f} "
            f"({s['MIS'] / v[frozenset()]:.0%})"
        )


if __name__ == "__main__":
    main()
