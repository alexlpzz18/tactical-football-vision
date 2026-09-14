#!/usr/bin/env python
"""Compara DOS cachés de balón con el mismo filtro y las mismas métricas.

Encargo de Alex (29-ago-2026): *"ahora estaríamos comparando un número
medido contra uno recordado"*. El caché del esquema `entero` se
sobrescribió cuando se lanzó el mixto, así que la comparación
`entero` ↔ `mixto` que sostenía la adopción no se puede rehacer de
memoria. Este script la hace bien: **mismo filtro, mismas métricas, los
tres números que deciden.**

⚠️ EL FILTRO ES EL MISMO PARA LOS DOS, y eso es la mitad del valor. El
mixto metió marcas pintadas del campo (el 56 % de su caché), pero el
frame entero también puede tener las suyas — el caché viejo daba 8.137
"con balón" SIN pasar por el filtro de marcas, y nunca se comprobó
cuántas eran el punto central. Comparar uno filtrado con otro sin filtrar
volvería a ser una comparación tramposa, solo que en la otra dirección.

Los tres números:

1. **Frames con balón REAL**: tras plausibilidad Y marcas.
2. **Cobertura de la posesión**: qué fracción del partido acaba con un
   dueño asignado. Es lo que de verdad limita el informe, más que el
   porcentaje de detección.
3. **Coste**: se pasa a mano con `--minutos`, porque lo sabe quien lanzó
   la pasada.

Uso:
    python scripts/comparar_caches_balon.py \\
        --cache-a data/tracking_benja/cache_balon_p1_entero.pkl --minutos-a 6 \\
        --cache-b data/tracking_benja/cache_balon_p1.pkl --minutos-b 29
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("comparar_balon")

RADIOS = (2.0, 3.0, 5.0)


def _metricas(ruta, modelo, jug, ts, radios=RADIOS):
    from src.balon.carga import cargar_detecciones_limpias

    dets, tiempos, meta = cargar_detecciones_limpias(ruta, modelo)
    n = meta["n_frames"]
    fila = {
        "esquema": (meta.get("firma") or {}).get("esquema", "desconocido"),
        "frames": n,
        "con_balon": len(dets),
        "pct_balon": 100 * len(dets) / max(n, 1),
        "celdas_marcas": len(meta["celdas_marcas"]),
    }
    for radio in radios:
        duenos = []
        for f, ds in dets.items():
            t = tiempos[f]
            k = int(np.argmin(np.abs(ts - t)))
            if abs(ts[k] - t) > 0.2:
                continue
            P = jug[ts[k]]
            d = np.hypot(
                P[:, 0].astype(float) - ds[0][0], P[:, 1].astype(float) - ds[0][1]
            )
            j = int(np.argmin(d))
            if d[j] <= radio:
                duenos.append(P[j, 2])
        fila[f"cobertura_{radio:.0f}"] = 100 * len(duenos) / max(n, 1)
        fila[f"posesion_A_{radio:.0f}"] = (
            100 * np.mean([x == "A" for x in duenos]) if duenos else float("nan")
        )
    return fila


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache-a", required=True, help="normalmente el de frame entero")
    p.add_argument("--cache-b", required=True, help="normalmente el mixto")
    p.add_argument("--minutos-a", type=float, default=float("nan"))
    p.add_argument("--minutos-b", type=float, default=float("nan"))
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v2.csv")
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    for ruta in (args.cache_a, args.cache_b):
        if not Path(ruta).exists():
            raise SystemExit(f"\nERROR: no existe {ruta}")

    from src.campo_modelo import cargar_modelo

    modelo = cargar_modelo(config=args.campo)
    df = pd.read_csv(args.csv)
    df = df[(df.es_real == 1) & df.etiqueta.isin(["A", "B", "portero_A", "portero_B"])]
    df = df.assign(base=df.etiqueta.str.replace("portero_", "", regex=False))
    jug = {t: g[["x_m", "y_m", "base"]].to_numpy() for t, g in df.groupby("tiempo_s")}
    ts = np.array(sorted(jug))

    a = _metricas(args.cache_a, modelo, jug, ts)
    b = _metricas(args.cache_b, modelo, jug, ts)

    if a["frames"] != b["frames"]:
        print(
            f"\n⚠️  LOS DOS CACHÉS NO CUBREN LO MISMO ({a['frames']} contra "
            f"{b['frames']} frames). La comparación NO es justa; revisa que "
            f"sean del mismo vídeo y el mismo sample_every."
        )

    linea = "=" * 72
    print(f"\n{linea}\nCOMPARACIÓN JUSTA · mismo filtro, mismas métricas\n{linea}")
    print(f"\n{'':<28} {'A: ' + a['esquema']:>20} {'B: ' + b['esquema']:>20}")
    print(f"{'-' * 72}")

    def linea_num(nombre, clave, fmt="{:.1f}", sufijo=""):
        va, vb = a[clave], b[clave]
        print(
            f"{nombre:<28} {fmt.format(va) + sufijo:>20} {fmt.format(vb) + sufijo:>20}"
        )

    print("  1) FRAMES CON BALÓN REAL")
    linea_num("     tras los dos filtros", "pct_balon", "{:.1f}", " %")
    linea_num("     celdas de marcas", "celdas_marcas", "{:.0f}")
    print("\n  2) COBERTURA DE LA POSESIÓN (% del partido con dueño)")
    for radio in RADIOS:
        linea_num(f"     radio {radio:.0f} m", f"cobertura_{radio:.0f}", "{:.1f}", " %")
    print("\n     posesión de A, de control (no debería moverse mucho):")
    for radio in RADIOS:
        linea_num(
            f"     radio {radio:.0f} m", f"posesion_A_{radio:.0f}", "{:.1f}", " %"
        )
    print("\n  3) COSTE")
    print(
        f"{'     minutos de GPU':<28} {args.minutos_a:>19.0f}m {args.minutos_b:>19.0f}m"
    )

    print(f"\n{linea}")
    d_balon = b["pct_balon"] - a["pct_balon"]
    d_cob = b["cobertura_3"] - a["cobertura_3"]
    d_coste = args.minutos_b - args.minutos_a
    print(
        f"  B gana {d_balon:+.1f} puntos de balón y {d_cob:+.1f} de cobertura, "
        f"por {d_coste:+.0f} min"
    )
    if np.isfinite(d_coste) and d_coste > 0 and d_balon < 5:
        print("  ⚠️  Menos de 5 puntos por más tiempo de GPU: probablemente NO")
        print("      compensa. La decisión es de Alex.")
    print(f"{linea}\n")


if __name__ == "__main__":
    main()
