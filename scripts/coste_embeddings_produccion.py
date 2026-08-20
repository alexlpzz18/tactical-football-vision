#!/usr/bin/env python
"""¿Cuánto cuesta el embedding en producción si solo se embeben las ventanas?

La puerta de re-entrada NO consulta el embedding en cada detección: solo
en los puntos donde un track reaparece, y allí mira una ventana de 8
observaciones a cada lado. Si hay que embeber el partido entero para
usar el 20 %, el caché de 1,5 GB y el coste de GPU se vuelven un problema
de margen del SaaS.

Este script mide cuántos recortes hacen falta de verdad, y —lo que
importa más— **cuánto cuesta la vía barata en pasadas de vídeo**, que es
donde está el gasto real.

Uso:
    python scripts/coste_embeddings_produccion.py
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.puerta_reentrada import _observaciones  # noqa: E402

VENTANA = 8
DIMS = 768
BYTES = 2  # fp16


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    p.add_argument(
        "--minutos-partido",
        type=float,
        default=90.0,
        help="Para extrapolar del tramo de 1 min al partido completo",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    n_dets = sum(len(e["dets"]) for e in banco.datos["cache"])
    dt = banco.dt
    hueco_min = float(
        banco.cfg_tracking.get("puerta_reentrada", {}).get("hueco_min_s", 0.5)
    )
    hueco_frames = max(1, int(round(hueco_min / dt))) * 1.5

    ids = asociar_con_bytetrack(
        banco.datos["cache"],
        banco.datos["fps"],
        banco.datos["sample"],
        ParametrosByteTrack.desde_dict(banco.cfg_tracking.get("bytetrack")),
    )

    necesarios = set()
    n_reentradas = 0
    for ident in ids:
        obs = _observaciones(ident)
        for k in range(1, len(obs)):
            if obs[k][0] - obs[k - 1][0] < hueco_frames:
                continue
            n_reentradas += 1
            ini, fin = max(0, k - VENTANA), k + VENTANA
            for _f, par in obs[ini:fin]:
                necesarios.add(par)

    frac = len(necesarios) / max(n_dets, 1)
    minutos_tramo = len(banco.datos["cache"]) * dt / 60.0
    escala = args.minutos_partido / minutos_tramo

    print(f"\nTramo medido: {minutos_tramo:.1f} min, {n_dets} detecciones")
    print(f"Re-entradas: {n_reentradas}\n")

    cab = f"{'estrategia':<34}{'recortes':>12}{'caché fp16':>13}{'con PCA128':>12}"
    print(cab)
    print("-" * len(cab))
    for nombre, n in (
        ("partido entero", n_dets),
        (f"solo ventanas (±{VENTANA} obs)", len(necesarios)),
    ):
        n_part = n * escala
        mb = n_part * DIMS * BYTES / 1e6
        mb_pca = n_part * 128 * BYTES / 1e6
        print(f"{nombre:<34}{n_part:>12,.0f}{mb:>11.0f} MB{mb_pca:>10.0f} MB")

    print(
        f"\nLa vía barata necesita el {frac:.1%} de los recortes: "
        f"{1/max(frac, 1e-9):.1f}× menos."
    )

    print("\n── PERO: el gasto real no son los recortes, son las PASADAS ──\n")
    print(
        "  Para saber DÓNDE están las re-entradas hay que haber trackeado ya,\n"
        "  y para trackear hacen falta las detecciones. O sea que la vía\n"
        "  barata es un pipeline de DOS pasadas sobre el vídeo:\n\n"
        "    1ª  detectar (SAHI) → trackear → localizar re-entradas\n"
        "    2ª  volver a decodificar el vídeo y embeber solo esas ventanas\n\n"
        "  Frente a UNA pasada embebiendo todo mientras se detecta.\n"
    )
    print(
        f"  Decodificar un partido de {args.minutos_partido:.0f} min es el coste\n"
        "  fijo que domina: los recortes son de 224x224 y su inferencia es\n"
        "  barata al lado de SAHI (8 tiles a 1280 por frame).\n"
    )
    print(
        "  → La vía barata ahorra ALMACENAMIENTO (el caché baja "
        f"{1/max(frac, 1e-9):.0f}×),\n"
        "    pero AÑADE una decodificación completa del vídeo. Solo compensa\n"
        "    si el cuello de botella es el disco, no la GPU."
    )
    print(
        "\n  Alternativa sin segunda pasada: embeber todo en la pasada de\n"
        "  detección y TIRAR después lo que no se use. Cuesta la GPU de\n"
        f"  embeber {n_dets * escala:,.0f} recortes pero deja el caché final\n"
        f"  en {len(necesarios) * escala * 128 * BYTES / 1e6:.0f} MB con PCA. "
        "Es lo que yo haría."
    )


if __name__ == "__main__":
    main()
