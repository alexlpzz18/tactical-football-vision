#!/usr/bin/env python
"""Parte un partido en tramos y escribe un config por tramo.

Cada config se lanza en UNA sesión de Colab en modo `full` y deja su
caché parcial en Drive; luego `scripts/fusionar_caches.py` los une.

Los tramos se solapan a propósito unos segundos: si una sesión muere a
mitad, el solape evita que quede un agujero justo en la costura, y la
fusión descarta los frames repetidos.

Uso:
    python scripts/planificar_tramos.py --config configs/processor_benja.yaml \\
        --duracion-min 20 --tramo-min 4 --salida configs/tramos_benja
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("planificar")


def planificar(duracion_min, tramo_min, solape_seg):
    """[(min_ini, dur_seg)] que cubren el partido con solape."""
    tramos, inicio = [], 0.0
    while inicio < duracion_min:
        dur = min(tramo_min * 60.0, (duracion_min - inicio) * 60.0) + solape_seg
        tramos.append((round(inicio, 3), round(dur, 1)))
        inicio += tramo_min
    return tramos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Config base del partido")
    parser.add_argument("--duracion-min", type=float, required=True)
    parser.add_argument(
        "--tramo-min",
        type=float,
        default=4.0,
        help="Minutos de partido por sesión de Colab (4 es prudente con SAHI)",
    )
    parser.add_argument("--solape-seg", type=float, default=5.0)
    parser.add_argument("--salida", required=True, help="Carpeta de los configs")
    parser.add_argument(
        "--drive",
        default="/content/drive/MyDrive/tactical/tramos",
        help="Carpeta de Drive donde cada sesión deja su caché parcial",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with open(args.config) as f:
        base = yaml.safe_load(f)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)

    tramos = planificar(args.duracion_min, args.tramo_min, args.solape_seg)
    nombres = []
    for i, (min_ini, dur_seg) in enumerate(tramos, start=1):
        cfg = yaml.safe_load(yaml.safe_dump(base))  # copia profunda
        cfg["modo"] = "full"
        cfg["muestreo"]["tramo"] = {"min_ini": min_ini, "dur_seg": dur_seg}
        cfg["rutas"]["cache"] = f"{args.drive}/cache_t{i:02d}.pkl"
        cfg["rutas"]["cache_colores"] = f"{args.drive}/colores_t{i:02d}.pkl"
        # El CSV de un tramo suelto no interesa: el bueno sale del caché
        # fusionado. Se le da un nombre propio para no pisar el real.
        cfg["rutas"]["salida_csv"] = f"{args.drive}/parcial_t{i:02d}.csv"
        cfg["rutas"]["salida_meta"] = f"{args.drive}/parcial_t{i:02d}_meta.json"
        ruta = salida / f"tramo_{i:02d}.yaml"
        with open(ruta, "w") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        nombres.append(ruta)
        print(f"  {ruta}  →  min {min_ini:.1f} + {dur_seg:.0f} s")

    guion = salida / "COMO_CORRERLO.md"
    guion.write_text(
        f"""# {len(tramos)} tramos de {args.tramo_min:g} min

Cada tramo es UNA sesión de Colab. Se solapan {args.solape_seg:g} s para que
una sesión caída no deje un agujero en la costura; la fusión descarta los
frames repetidos.

## En cada sesión de Colab

```python
from google.colab import drive; drive.mount('/content/drive')
%cd /content/tactical-football-vision
!python scripts/procesar_partido.py --config {salida}/tramo_01.yaml
```

cambiando `tramo_01` por el que toque. Los cachés parciales van a
`{args.drive}`.

## Cuando estén todos

```bash
python scripts/fusionar_caches.py \\
    --detecciones {args.drive}/cache_t*.pkl \\
    --colores {args.drive}/colores_t*.pkl \\
    --salida-detecciones {base["rutas"]["cache"]} \\
    --salida-colores {base["rutas"]["cache_colores"]}
```

Avisa si queda algún hueco temporal, que es la forma de darse cuenta de
que una sesión murió sin que nadie lo notara. A partir de ahí, todo el
trabajo local es el de siempre:

```bash
python scripts/procesar_partido.py --config {args.config} --modo desde_cache
```
""",
        encoding="utf-8",
    )
    print(f"\n✓ {len(tramos)} configs en {salida}\n  Guía: {guion}")


if __name__ == "__main__":
    main()
