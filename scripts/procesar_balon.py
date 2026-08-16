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
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.tracking_balon import (  # noqa: E402
    ParametrosBalon,
    preparar_para_replay,
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
        default="angulo",
        help="Cómo detectar los contactos. 'angulo' (el de siempre) solo ve "
        "pases, tiros y rebotes; 'velocidad' ve además la conducción. "
        "Medido contra el GT del clip: recall 0.25 → 0.75, precisión "
        "0.71 → 0.43. Provisional hasta que Alex decida.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with open(args.cache_balon, "rb") as f:
        datos = pickle.load(f)
    cache = datos["cache"]
    tiempos = {e["frame_idx"]: e["t"] for e in cache}
    detecciones = {e["frame_idx"]: e["dets"] for e in cache if e["dets"]}

    jug = pd.read_csv(args.csv_jugadores)
    reales = jug[jug.es_real == 1]
    # Los jugadores van a otra frecuencia: se indexan por tiempo para
    # poder emparejar con el balón, que se muestrea más denso.
    por_tiempo, equipo_de = {}, {}
    for t, g in reales.groupby("tiempo_s"):
        por_tiempo[round(float(t), 2)] = [
            (float(r.x_m), float(r.y_m), int(r.id_jugador)) for r in g.itertuples()
        ]
        for r in g.itertuples():
            equipo_de[int(r.id_jugador)] = str(r.etiqueta)

    def jugadores_en(frame):
        t = round(tiempos.get(frame, 0.0), 2)
        if t in por_tiempo:
            return por_tiempo[t]
        # El instante más cercano dentro de medio paso de jugadores
        cercano = min(por_tiempo, key=lambda x: abs(x - t), default=None)
        if cercano is None or abs(cercano - t) > 0.08:
            return []
        return por_tiempo[cercano]

    params = ParametrosBalon()
    pos_jug = {f: [(j[0], j[1]) for j in jugadores_en(f)] for f in detecciones}
    activo = seleccionar_balon_activo(detecciones, pos_jug, params)
    logger.info(
        "Balón activo: %d frames de %d con detección (%d frames en total)",
        len(activo),
        len(detecciones),
        len(cache),
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
    preparadas = preparar_para_replay(trayectoria, aereo, tiempos, params)

    filas = []
    for f, pos, es_aereo, es_real in preparadas:
        # El balón es UNA identidad continua (-1). Durante el vuelo su
        # posición queda congelada en la última fiable, así que la serie
        # no da saltos; el aéreo se marca además con una ficha propia
        # (-2) en el mismo sitio, que es la que el replay atenúa.
        filas.append(
            {
                "frame": f,
                "tiempo_s": round(tiempos[f], 2),
                # Convenio: el balón no es un jugador, y el aéreo va con
                # id propio porque el replay asigna UNA etiqueta por
                # identidad — mezclarlos perdía la marca de "no fiable".
                "id_jugador": -1,
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
                    "id_jugador": -2,
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
    print(f"  frames del tramo            : {len(cache)}")
    print(
        f"  con balón detectado         : {len(detecciones)} "
        f"({100 * len(detecciones) / len(cache):.0f} %)"
    )
    print(
        f"  tras seleccionar el activo  : {n_con} "
        f"({100 * n_con / len(cache):.0f} % del tramo)"
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
