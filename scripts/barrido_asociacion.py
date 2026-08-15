#!/usr/bin/env python
"""Barrido COMBINADO de la asociación: ByteTrack × cosido por pureza.

El barrido anterior movía un parámetro cada vez, que es lo correcto para
entender, pero se pierde las interacciones: un buffer más largo fragmenta
menos y deja al cosido menos trabajo, así que el óptimo del cosido puede
no ser el mismo con cada buffer.

Criterio de adopción (estricto, el de siempre): la cobertura sube,
quimeras ≤ 5, IDF1 no baja y la concurrencia se queda en ~23.

Uso:
    python scripts/barrido_asociacion.py
    python scripts/barrido_asociacion.py --config configs/evaluation_v4pre_v2color.yaml
"""

import argparse
import itertools
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")


from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.evaluation.adaptador import trayectorias_a_por_frame  # noqa: E402
from src.evaluation.metricas import calcular_metricas_tracking  # noqa: E402
from src.tracking.cosido_pureza import (  # noqa: E402
    ParametrosCosidoPureza,
    coser_por_pureza,
)
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)

# Referencia: la configuración adoptada hoy.
REFERENCIA = {"cobertura": 0.575, "idf1": 0.444, "quimeras": 5, "conc": 23}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/evaluation_v4pre.yaml")
    parser.add_argument("--config-tracking", default="configs/tracking.yaml")
    parser.add_argument("--max-combinaciones", type=int, default=30)
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)

    buffers = [1.5, 2.0, 3.0]
    emparejamientos = [0.98, 0.995]
    cosidos = [
        ("hueco 3 / ambig 0.15", dict(max_hueco=3.0, margen_ambiguedad=0.15)),
        ("hueco 4 / ambig 0.15", dict(max_hueco=4.0, margen_ambiguedad=0.15)),
        ("hueco 4 / ambig 0.30", dict(max_hueco=4.0, margen_ambiguedad=0.30)),
        ("hueco 6 / ambig 0.30", dict(max_hueco=6.0, margen_ambiguedad=0.30)),
        ("hueco 4 / color 0.9", dict(max_hueco=4.0, color_max_dist=0.9)),
    ]

    combinaciones = list(itertools.product(buffers, emparejamientos, cosidos))
    if len(combinaciones) > args.max_combinaciones:
        combinaciones = combinaciones[: args.max_combinaciones]
        print(f"⚠ Truncado a {args.max_combinaciones} combinaciones")

    cab = (
        f"{'buffer':>7}{'empar':>8}  {'cosido':<24}"
        f"{'nIds':>6}{'cob.':>7}{'conc':>6}{'IDF1':>7}{'tasa':>7}{'quim':>6}"
    )
    print("\n" + cab)
    print("-" * len(cab))

    filas = []
    cache_bt = {}
    for buf, emp, (nombre, kw) in combinaciones:
        clave = (buf, emp)
        if clave not in cache_bt:
            cache_bt[clave] = banco.bytetrack(
                buffer_perdido_s=buf, umbral_emparejamiento=emp
            )
        base = cache_bt[clave]
        cosidas = coser_por_pureza(
            base, banco.colores, ParametrosCosidoPureza(**kw), dt=banco.dt
        )
        eq = banco.clasificar(cosidas)
        tr = interpolar_trayectorias(
            identidades_a_trayectorias(cosidas), banco.frames_ts, max_hueco=6.0
        )
        f = medir("x", tr, eq, banco.gt, banco.comunes, banco.tiempos, banco.umbral)
        m = calcular_metricas_tracking(
            banco.gt, trayectorias_a_por_frame(tr, eq), banco.comunes, banco.umbral
        )
        f.update(buffer=buf, empar=emp, cosido=nombre, frag=m.fragmentaciones)
        filas.append(f)
        print(
            f"{buf:>7.1f}{emp:>8.3f}  {nombre:<24}{f['nids']:>6}"
            f"{f['cobertura']:>7.3f}{f['conc']:>6.0f}{f['idf1']:>7.3f}"
            f"{f['tasa']:>7.3f}{f['quimeras']:>4}/{f['con10']:<2}"
        )

    print("-" * len(cab))
    print(
        f"{'REFERENCIA (adoptado hoy)':<39}{'115':>6}"
        f"{REFERENCIA['cobertura']:>7.3f}{REFERENCIA['conc']:>6}"
        f"{REFERENCIA['idf1']:>7.3f}{'0.147':>7}{REFERENCIA['quimeras']:>4}/37"
    )

    # Criterio ESTRICTO: mejora la cobertura sin degradar nada más.
    ganadoras = [
        f
        for f in filas
        if f["cobertura"] > REFERENCIA["cobertura"]
        and f["quimeras"] <= REFERENCIA["quimeras"]
        and f["idf1"] >= REFERENCIA["idf1"]
        and f["conc"] <= REFERENCIA["conc"] + 2
    ]
    print(f"\nCombinaciones que superan el criterio estricto: {len(ganadoras)}")
    for f in sorted(ganadoras, key=lambda x: -x["cobertura"]):
        print(
            f"  buffer {f['buffer']} · empar {f['empar']} · {f['cosido']}  →  "
            f"cob {f['cobertura']:.3f} (+{f['cobertura'] - REFERENCIA['cobertura']:.3f}), "
            f"IDF1 {f['idf1']:.3f}, {f['quimeras']} quimeras"
        )
    if not ganadoras:
        print("  (ninguna: el punto adoptado sigue siendo el mejor compromiso)")
    mejor_cob = max(filas, key=lambda f: f["cobertura"])
    print(
        f"\nMáxima cobertura del barrido: {mejor_cob['cobertura']:.3f} "
        f"(buffer {mejor_cob['buffer']}, empar {mejor_cob['empar']}, "
        f"{mejor_cob['cosido']}) con {mejor_cob['quimeras']} quimeras e "
        f"IDF1 {mejor_cob['idf1']:.3f}"
    )


if __name__ == "__main__":
    main()
