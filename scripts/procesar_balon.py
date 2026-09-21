#!/usr/bin/env python
"""Balón: caché → trayectoria, fases aéreas, contactos y CSV conjunto.

Une el caché de balón con el CSV de jugadores ya procesado. Los dos van a
frecuencias distintas a propósito (el balón más denso), así que se
mantienen como filas independientes del mismo CSV y se casan por tiempo,
no por frame.

Uso:
    python scripts/procesar_balon.py \\
        --cache-balon data/tracking_benja/cache_balon_piloto.pkl \\
        --csv-jugadores data/tracking_benja/posiciones_benja_piloto5min.csv \\
        --salida data/tracking_benja/posiciones_conjunto.csv
"""

import argparse
import bisect
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.tracking_balon import (  # noqa: E402
    ParametrosBalon,
    id_de_tramo,
    preparar_balon,
    detectar_contactos,
    detectar_contactos_por_velocidad,
    fusionar_contactos,
    detectar_fases_aereas,
    seleccionar_balon_activo,
)

logger = logging.getLogger("balon")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-balon", required=True)
    parser.add_argument("--csv-jugadores", required=True)
    parser.add_argument("--salida", required=True)
    parser.add_argument("--salida-contactos", default=None)
    parser.add_argument(
        "--criterio",
        choices=["angulo", "velocidad", "ambos"],
        default="velocidad",
        help="Cómo detectar los contactos. DEFAULT 'velocidad': ve también "
        "la conducción, que es el 30 % de los toques. Medido contra el GT "
        "del clip, recall 0.25 → 0.75 y en juego continuo 2/11 → 8/11, a "
        "cambio de precisión 0.71 → 0.43. Se adopta porque el uso del "
        "balón es 'por dónde va el juego y quién lo tiene', y ahí perder "
        "dos tercios de los toques es letal mientras que algún falso "
        "positivo se diluye al agregar por zonas y equipos. 'angulo' "
        "queda disponible: es prescindible (lo que ve, lo ve la "
        "velocidad) pero no se borra.",
    )
    parser.add_argument(
        "--campo",
        default="configs/campo_benja.yaml",
        help="config del campo, para el filtro de plausibilidad del balón",
    )
    parser.add_argument(
        "--sin-filtro-marcas",
        action="store_true",
        help="NO quitar las marcas fijas del campo (punto central, de "
        "penalti, manchas). Solo para MEDIR su efecto: en producción van "
        "quitadas, y llegaron a ser el 56 % del caché.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # ⚠️ LOS DOS FILTROS DEL BALÓN VAN JUNTOS Y POR UN SOLO SITIO
    # (`src.balon.carga`), porque tenerlos sueltos significaba cinco
    # consumidores donde olvidar uno — y un consumidor que se olvida no
    # falla: da un número distinto.
    #   1. PLAUSIBILIDAD FÍSICA: entre el 12 % y el 20 % de las
    #      detecciones proyectan FUERA del campo (la x llega a 24.876 m en
    #      un campo de 62). Sin quitarlas la velocidad máxima del balón
    #      sale a 4151 m/s y dos tercios de las FASES AÉREAS son basura.
    #   2. MARCAS FIJAS del campo: el punto central, el de penalti y una
    #      mancha del fondo llegaron a ser el 56 % del caché tras el
    #      esquema mixto (`docs/balon_fantasma.md`).
    from src.balon.carga import cargar_detecciones_limpias
    from src.campo_modelo import cargar_modelo

    modelo_campo = cargar_modelo(config=args.campo)
    detecciones, tiempos, meta = cargar_detecciones_limpias(
        args.cache_balon, modelo_campo, quitar_marcas=not args.sin_filtro_marcas
    )
    n_frames_cache = meta["n_frames"]

    from src.balon.carga import jugadores_por_frame_de_balon

    jug = pd.read_csv(args.csv_jugadores)
    equipo_de = {
        int(r.id_jugador): str(r.etiqueta) for r in jug[jug.es_real == 1].itertuples()
    }
    # Mismo emparejado por tiempo que usa el vídeo de diagnóstico.
    jug_de_frame = jugadores_por_frame_de_balon(
        args.csv_jugadores, tiempos, detecciones
    )

    def jugadores_en(frame):
        return jug_de_frame.get(frame, [])

    params = ParametrosBalon()
    pos_jug = {f: [(j[0], j[1]) for j in jugadores_en(f)] for f in detecciones}
    activo = seleccionar_balon_activo(detecciones, pos_jug, params)
    logger.info(
        "Balón activo: %d frames de %d con detección (%d frames en total)",
        len(activo),
        len(detecciones),
        n_frames_cache,
    )

    trayectoria = [
        (f, np.array(d[:2]), d[5] - d[3], d[6]) for f, d in sorted(activo.items())
    ]
    aereo = detectar_fases_aereas(trayectoria, tiempos, params)
    logger.info(
        "Fases aéreas: %d de %d observaciones (%.0f %%)",
        sum(aereo),
        len(aereo),
        100 * sum(aereo) / len(aereo) if aereo else 0,
    )

    jug_ids = {f: jugadores_en(f) for f, _p, _a, _c in trayectoria}
    # El equipo del jugador al que se atribuye el contacto. Sin esto la
    # columna salía vacía y no se podía medir la atribución.
    equipos_por_frame = {f: equipo_de for f in jug_ids}
    contactos = detectar_contactos(
        trayectoria, tiempos, jug_ids, equipos_por_frame, params, aereo=aereo
    )
    if args.criterio in ("velocidad", "ambos"):
        por_vel = detectar_contactos_por_velocidad(
            trayectoria, tiempos, jug_ids, equipos_por_frame, params, aereo=aereo
        )
        contactos = (
            por_vel
            if args.criterio == "velocidad"
            else fusionar_contactos(contactos, por_vel)
        )

    # Suavizado + fase aérea sin coordenadas inventadas
    # Centros de las cajas en PÍXELES: con ellos, la puerta de continuidad
    # distingue un vuelo de un cambio de balón (docs/balon_sin_alas.md).
    centros_px = {
        f: ((d[2] + d[4]) / 2.0, (d[3] + d[5]) / 2.0) for f, d in activo.items()
    }
    preparadas, cortes = preparar_balon(trayectoria, aereo, tiempos, params, centros_px)
    cortes_ordenados = sorted(cortes)
    logger.info(
        "Puerta de píxeles (> %.0f px/s): %d cortes; el balón se reparte en %d tramos",
        params.vel_max_px_s,
        len(cortes),
        len(cortes) + 1,
    )

    def tramo_de(frame: int) -> int:
        return bisect.bisect_right(cortes_ordenados, frame)

    filas = []
    for f, pos, es_aereo, es_real in preparadas:
        # El balón es UNA identidad continua (-1) POR TRAMO: un corte de la
        # puerta de píxeles abre otra (`id_de_tramo`), para que el replay no
        # una con una recta dos detecciones que no son el mismo balón. El
        # aéreo se marca además con una ficha propia (-2 en el primer tramo)
        # en el mismo sitio, que es la que el replay atenúa.
        filas.append(
            {
                "frame": f,
                "tiempo_s": round(tiempos[f], 2),
                # Convenio: el balón no es un jugador, y el aéreo va con
                # id propio porque el replay asigna UNA etiqueta por
                # identidad — mezclarlos perdía la marca de "no fiable".
                "id_jugador": id_de_tramo(tramo_de(f)),
                "equipo": 3,
                "etiqueta": "balon",
                "x_m": round(float(pos[0]), 2),
                "y_m": round(float(pos[1]), 2),
                "es_real": 1 if es_real else 0,
            }
        )
    # Marcador de "en el aire": misma posición, ficha aparte y atenuada.
    for f, pos, es_aereo, _r in preparadas:
        if es_aereo:
            filas.append(
                {
                    "frame": f,
                    "tiempo_s": round(tiempos[f], 2),
                    "id_jugador": id_de_tramo(tramo_de(f), aereo=True),
                    "equipo": 3,
                    "etiqueta": "balon_aereo",
                    "x_m": round(float(pos[0]), 2),
                    "y_m": round(float(pos[1]), 2),
                    "es_real": 0,
                }
            )
    balon = pd.DataFrame(filas)
    conjunto = pd.concat([jug, balon], ignore_index=True).sort_values(
        ["tiempo_s", "id_jugador"]
    )
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    conjunto.to_csv(args.salida, index=False)

    ruta_c = args.salida_contactos or str(
        Path(args.salida).with_name(Path(args.salida).stem + "_contactos.csv")
    )
    pd.DataFrame(contactos).to_csv(ruta_c, index=False)

    n_con = len(trayectoria)
    print(f"\n✓ CSV conjunto en {args.salida} ({len(conjunto)} filas)")
    print(f"✓ Contactos en {ruta_c}")
    print("\n── NÚMEROS DEL PILOTO ──")
    print(f"  frames del tramo            : {n_frames_cache}")
    print(
        f"  con balón detectado         : {len(detecciones)} "
        f"({100 * len(detecciones) / n_frames_cache:.0f} %)"
    )
    print(
        f"  tras seleccionar el activo  : {n_con} "
        f"({100 * n_con / n_frames_cache:.0f} % del tramo)"
    )
    print(
        f"  en FASE AÉREA               : {sum(aereo)} "
        f"({100 * sum(aereo) / n_con:.0f} % de las observaciones de balón)"
    )
    print(f"  contactos detectados        : {len(contactos)}")
    con_jug = sum(1 for c in contactos if c["id_jugador"] is not None)
    print(
        f"    con jugador atribuido     : {con_jug} "
        f"({100 * con_jug / len(contactos):.0f} %)"
        if contactos
        else ""
    )
    if contactos:
        dur = tiempos[max(tiempos)] - tiempos[min(tiempos)]
        print(
            f"    ritmo                     : {60 * len(contactos) / dur:.0f} por minuto"
        )


if __name__ == "__main__":
    main()
