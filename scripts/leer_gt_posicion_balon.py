#!/usr/bin/env python
"""Convierte las respuestas de gt_posicion_balon.py en un GT con coordenadas.

Lee `respuestas.csv` (columna "respuesta" rellenada a mano con un código
de celda tipo "K7", o "fuera"/"tapado"/"no_se"), y escribe un CSV con
posición en píxeles del vídeo original y en metros (vía la homografía),
indexado por frame_idx y tiempo.

INCREMENTAL a propósito: se puede ejecutar con las respuestas a medias
—usa solo las filas que ya tengan algo en "respuesta"— y se puede volver
a ejecutar más veces según Alex vaya añadiendo. Nunca hace falta terminar
las 30-50 imágenes de una sentada.

Uso:
    python scripts/leer_gt_posicion_balon.py \\
        --respuestas outputs/gt_posicion_balon/respuestas.csv \\
        --salida data/tracking_benja/gt_posicion_balon.csv
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.gt_parser import proyectar_punto  # noqa: E402

logger = logging.getLogger("leer_gt_posicion_balon")

LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXY"
ESTADOS_SIN_POSICION = {"fuera", "tapado", "no_se"}
RE_CELDA = re.compile(r"^([A-Ya-y])\s*(\d{1,2})$")
# "M9/M10": el balón está justo entre dos celdas vecinas, se promedia.
RE_DOS_CELDAS = re.compile(r"^([A-Ya-y]\s*\d{1,2})\s*/\s*([A-Ya-y]\s*\d{1,2})$")
# "Tapado en M9": oculto pero con una posición aproximada aprovechable.
RE_TAPADO_CON_CELDA = re.compile(r"^tapado\s+en\s+([A-Ya-y]\s*\d{1,2})$", re.IGNORECASE)


def _celda_a_px(celda: str, origen_x: float, origen_y: float, celda_px: int):
    """'K7' -> (x_px, y_px) del CENTRO de esa celda, en píxeles del vídeo."""
    m = RE_CELDA.match(celda.strip())
    if not m:
        return None
    letra, numero = m.group(1).upper(), int(m.group(2))
    if letra not in LETRAS:
        return None
    col = LETRAS.index(letra)
    fila = numero - 1
    x_px = origen_x + (col + 0.5) * celda_px
    y_px = origen_y + (fila + 0.5) * celda_px
    return x_px, y_px


def _parsear_respuesta(respuesta: str, origen_x: float, origen_y: float, celda_px: int):
    """Devuelve (estado, x_px, y_px). x_px/y_px son None si no hay posición.

    Formatos aceptados, de los más a los menos frecuentes en la práctica:
      - "K7"               -> una celda, visto.
      - "fuera"/"tapado"/"no_se" -> sin posición.
      - "M9/M10"            -> entre dos celdas vecinas: el centro de la
        posición es el PUNTO MEDIO de los dos centros, visto.
      - "Tapado en M9"      -> oculto, pero con la posición aproximada que
        Alex pudo inferir (p.ej. por dónde miran los jugadores). Se guarda
        como "tapado" CON x_px/y_px, a diferencia del "tapado" a secas.
    """
    r = respuesta.strip()
    r_norm = r.lower()
    if r_norm in ESTADOS_SIN_POSICION:
        return r_norm, None, None

    m_tapado = RE_TAPADO_CON_CELDA.match(r)
    if m_tapado:
        punto = _celda_a_px(m_tapado.group(1), origen_x, origen_y, celda_px)
        if punto is None:
            return None, None, None
        return "tapado", punto[0], punto[1]

    m_dos = RE_DOS_CELDAS.match(r)
    if m_dos:
        p1 = _celda_a_px(m_dos.group(1), origen_x, origen_y, celda_px)
        p2 = _celda_a_px(m_dos.group(2), origen_x, origen_y, celda_px)
        if p1 is None or p2 is None:
            return None, None, None
        return "visto", (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2

    punto = _celda_a_px(r, origen_x, origen_y, celda_px)
    if punto is None:
        return None, None, None  # formato no reconocido: se avisa y se salta
    return "visto", punto[0], punto[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--respuestas", default="outputs/gt_posicion_balon/respuestas.csv"
    )
    parser.add_argument("--salida", default="data/tracking_benja/gt_posicion_balon.csv")
    parser.add_argument(
        "--homografia",
        default="data/calibracion_benja/homografia_benja.npy",
        help="Para añadir x_m/y_m. Si no existe, el CSV sale solo en píxeles.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    df = pd.read_csv(args.respuestas)
    df["respuesta"] = df["respuesta"].fillna("").astype(str)
    contestadas = df[df["respuesta"].str.strip() != ""].copy()
    if contestadas.empty:
        print("Ninguna fila contestada todavía en", args.respuestas)
        return

    homografia = None
    ruta_h = Path(args.homografia)
    if ruta_h.exists():
        homografia = np.load(ruta_h)
    else:
        logger.warning(
            "No se encontró %s: el GT saldrá solo en píxeles, sin x_m/y_m", ruta_h
        )

    filas = []
    invalidas = []
    for r in contestadas.itertuples():
        estado, x_px, y_px = _parsear_respuesta(
            r.respuesta, r.origen_x_px, r.origen_y_px, r.celda_px
        )
        if estado is None:
            invalidas.append((r.caso, r.respuesta))
            continue
        x_m = y_m = None
        if x_px is not None and homografia is not None:
            x_m, y_m = proyectar_punto(x_px, y_px, homografia)
        filas.append(
            {
                "caso": r.caso,
                "grupo": r.grupo,
                "frame_idx": r.frame_idx,
                "t": r.t,
                "estado": estado,
                "x_px": x_px,
                "y_px": y_px,
                "x_m": x_m,
                "y_m": y_m,
            }
        )

    if invalidas:
        logger.warning(
            "%d respuestas con formato no reconocido, se omiten: %s",
            len(invalidas),
            invalidas,
        )

    salida = pd.DataFrame(filas).sort_values("frame_idx")
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    salida.to_csv(args.salida, index=False)

    vistos = (salida["estado"] == "visto").sum()
    print(
        f"\n✓ {len(salida)} filas escritas en {args.salida} "
        f"({vistos} con posición, {len(salida) - vistos} sin balón visible) "
        f"de {len(df)} imágenes totales"
    )
    print(salida["grupo"].value_counts().to_string())


if __name__ == "__main__":
    main()
