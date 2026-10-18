#!/usr/bin/env python
"""¿Puntúan las marcas fijas más que el balón real en el mismo instante?

Parte de la verificación del mecanismo de GREEDYNMM (docs/sahi_balon.md,
corrección del 1-oct-2026): si un candidato intruso (una marca pintada)
tiene MÁS confianza que el balón real en el mismo frame o uno cercano, el
postproceso heredaría esa confianza alta en vez de la "intacta" del
balón — el caso peor que el documentado. Esto mide si eso pasa EN LA
PRÁCTICA sobre la parte entera, o si es solo teórico.

Reutiliza el pipeline real (src.balon.carga, seleccionar_balon_activo)
para que "el balón real de ese frame" sea exactamente el que usa
producción, no una redefinición ad hoc.

Uso:
    python scripts/marcas_vs_balon_score.py \\
        --cache data/tracking_benja/cache_balon_p1.pkl \\
        --csv-jugadores data/tracking_benja/posiciones_benja_p1_v3.csv \\
        --campo configs/campo_benja.yaml \\
        --ventana-s 1.0
"""

import argparse
import bisect
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.carga import cargar_detecciones_limpias  # noqa: E402
from src.balon.carga import contexto_del_selector  # noqa: E402
from src.balon.marcas_estaticas import encontrar_marcas_estaticas  # noqa: E402
from src.balon.tracking_balon import ParametrosBalon  # noqa: E402
from src.balon.tracking_balon import filtrar_balon_plausible  # noqa: E402
from src.balon.tracking_balon import seleccionar_balon_activo  # noqa: E402
from src.campo_modelo import cargar_modelo  # noqa: E402

logger = logging.getLogger("marcas_vs_balon")


def _centro_px(det):
    return (det[2] + det[4]) / 2.0, (det[3] + det[5]) / 2.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default="data/tracking_benja/cache_balon_p1.pkl")
    parser.add_argument(
        "--csv-jugadores", default="data/tracking_benja/posiciones_benja_p1_v3.csv"
    )
    parser.add_argument("--campo", default="configs/campo_benja.yaml")
    parser.add_argument(
        "--ventana-s",
        type=float,
        default=1.0,
        help="Máxima distancia temporal (s) entre el candidato de marca y "
        "el balón real para considerarlos 'el mismo instante'.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    import pickle

    with open(args.cache, "rb") as f:
        crudo = pickle.load(f)
    tiempos = {e["frame_idx"]: e["t"] for e in crudo["cache"]}
    dets_crudas = {e["frame_idx"]: e["dets"] for e in crudo["cache"] if e["dets"]}

    modelo_campo = cargar_modelo(config=args.campo)

    # Las marcas se buscan sobre el caché TRAS plausibilidad (mismo orden
    # que src.balon.carga), para no mezclar basura imposible con marcas.
    dets_plausibles = filtrar_balon_plausible(dets_crudas, modelo_campo)
    marcas = encontrar_marcas_estaticas(dets_plausibles, tiempos)
    print(f"Marcas fijas localizadas: {len(marcas)} celdas")

    # El balón REAL de cada frame: el pipeline de producción completo
    # (filtros + desempate por cercanía a jugador), para no inventar un
    # criterio nuevo de "cuál es el balón bueno".
    detecciones, tiempos_limpias, meta = cargar_detecciones_limpias(
        args.cache, modelo_campo
    )
    jug_de_frame, ctx = contexto_del_selector(
        args.csv_jugadores,
        tiempos_limpias,
        detecciones,
        args.campo,
        modelo_campo,
        meta["fuera_de_campo"],
    )
    pos_jug = {f: [(j[0], j[1]) for j in jug_de_frame.get(f, [])] for f in detecciones}
    params = ParametrosBalon()
    activo = seleccionar_balon_activo(
        detecciones,
        pos_jug,
        params,
        **ctx,
    )
    print(f"Balón activo seleccionado: {len(activo)} frames")

    # Candidatos CRUDOS (antes de quitar marcas) que caen dentro de una
    # celda de marca, con su score y su tiempo.
    candidatos_marca = []  # (t, score, celda)
    for frame, dets in dets_plausibles.items():
        t = tiempos.get(frame)
        if t is None:
            continue
        for det in dets:
            px, py = _centro_px(det)
            celda = (int(px // 12), int(py // 12))
            if celda in marcas:
                candidatos_marca.append((t, float(det[6]), celda))
    candidatos_marca.sort()

    # Balón real: (t, score) ordenado.
    balon_real = sorted(
        (tiempos_limpias[f], float(det[6])) for f, det in activo.items()
    )
    tiempos_balon = [b[0] for b in balon_real]

    # Para cada candidato de marca, el balón real MÁS CERCANO en el
    # tiempo, dentro de la ventana.
    casos_invertidos = []
    comparaciones = 0
    for t_marca, score_marca, celda in candidatos_marca:
        i = bisect.bisect_left(tiempos_balon, t_marca)
        vecinos = [j for j in (i - 1, i) if 0 <= j < len(tiempos_balon)]
        if not vecinos:
            continue
        j = min(vecinos, key=lambda k: abs(tiempos_balon[k] - t_marca))
        dt = abs(tiempos_balon[j] - t_marca)
        if dt > args.ventana_s:
            continue
        comparaciones += 1
        t_balon, score_balon = balon_real[j]
        if score_marca > score_balon:
            casos_invertidos.append(
                (t_marca, celda, score_marca, t_balon, score_balon, dt)
            )

    print(
        f"\nComparaciones dentro de ±{args.ventana_s:.1f} s: {comparaciones} "
        f"(de {len(candidatos_marca)} candidatos de marca)"
    )
    print(
        f"Casos donde la MARCA puntúa más que el balón real cercano: {len(casos_invertidos)}"
    )
    if casos_invertidos:
        print("\nEjemplos (t_marca, celda, score_marca, t_balón, score_balón, Δt):")
        for caso in casos_invertidos[:15]:
            print(
                f"  t={caso[0]:7.2f}s celda={caso[1]} marca={caso[2]:.3f}  "
                f"vs  t={caso[3]:7.2f}s balón={caso[4]:.3f}  (Δt={caso[5]:.2f}s)"
            )
    else:
        print("Ninguno: en esta parte entera el caso invertido no se observa.")


if __name__ == "__main__":
    main()
