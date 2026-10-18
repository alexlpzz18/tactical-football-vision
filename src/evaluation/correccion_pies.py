"""Corrige el sesgo de los clics del GT manual: del cuerpo al SUELO.

Alex marcó a propósito la parte de la media más cercana al pie, creyendo
que el detector se guiaba por el blanco de la camiseta. No es así: la caja
envuelve a la persona entera y lo que se proyecta es **su borde inferior**,
o sea el punto donde pisa. De ahí un sesgo sistemático y en una sola
dirección — el clic queda por encima del suelo y la homografía lo manda
más lejos de la cámara.

La corrección se hace **por altura de caja**, no por un número fijo de
píxeles: el desfase escala con la distancia (un jugador cercano ocupa 90
px y uno del fondo 25, y "el tobillo" está a distinta altura en píxeles en
cada caso). Medido sobre 745 clics casados con una detección:

| corrección | desplazamiento mediano | p90 |
|---|---|---|
| ninguna | 1,58 m | 3,14 m |
| píxeles fijos (7,7) | 0,48 m | 1,89 m |
| **por altura (0,129 × alto)** | **0,42 m** | **1,47 m** |

Con 0,42 m el GT baja por debajo del error de la propia calibración
(0,91 m de mediana en sus puntos de referencia), así que deja de ser el
factor limitante: pasa a servir también para medir error de localización,
no solo identidad.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Fracción del alto de caja que hay que bajar el clic. Mediana medida.
FRACCION_ALTO = 0.129


def corregir_clics(
    df,
    cache: list[dict],
    fraccion: float = FRACCION_ALTO,
    max_dist_px: float = 40.0,
):
    """Baja cada clic hasta el suelo, escalando por el alto de su caja.

    Args:
        df: DataFrame con jugador, frame, x_px, y_px.
        cache: caché de detecciones, para saber el alto de la caja.
        fraccion: cuánto bajar, en fracción del alto de la caja.
        max_dist_px: si no hay caja tan cerca, se usa el alto mediano.

    Returns:
        El DataFrame con `y_px` corregido y una columna `corregido_px`.
    """
    cajas = {e["frame_idx"]: [d[2:6] for d in e["dets"]] for e in cache}
    altos_todos = [c[3] - c[1] for lista in cajas.values() for c in lista]
    alto_tipico = float(np.median(altos_todos)) if altos_todos else 40.0

    salida = df.copy()
    correcciones, sin_caja = [], 0
    for fila in df.itertuples():
        lista = cajas.get(int(fila.frame), [])
        mejor, dmin = None, float("inf")
        for c in lista:
            dist = float(np.hypot((c[0] + c[2]) / 2 - fila.x_px, c[3] - fila.y_px))
            if dist < dmin:
                mejor, dmin = c, dist
        if mejor is None or dmin > max_dist_px:
            sin_caja += 1
            alto = alto_tipico
        else:
            alto = mejor[3] - mejor[1]
        correcciones.append(fraccion * alto)

    salida["corregido_px"] = np.round(correcciones, 1)
    salida["y_px"] = np.round(df["y_px"].to_numpy() + np.array(correcciones))
    logger.info(
        "Corrección de pies: %+.1f px de mediana (%d clics sin caja cerca, "
        "corregidos con el alto típico de %.0f px)",
        float(np.median(correcciones)),
        sin_caja,
        alto_tipico,
    )
    return salida
