"""Plausibilidad FÍSICA de una detección, derivada de la homografía.

La idea: una caja de detección no es solo un rectángulo con una
confianza. Está sobre un plano cuya escala conocemos, así que se puede
preguntar **cuánto mide en metros la cosa que hay dentro**. Una persona a
21 m no puede medir 8 píxeles de ancho, y esa pregunta no la responde el
umbral de confianza (medido: subirlo de 0,45 a 0,80 mata 20 fugas y
cuesta 34 personas reales, porque la confianza de las líneas del campo
—hasta 0,80— se solapa con la de los niños).

## De dónde sale la escala, sin calibrar la cámara

La homografía H manda píxeles al suelo en metros. Su **jacobiano** en un
píxel da las dos escalas locales del suelo ahí: el valor singular MENOR
es la escala LATERAL (perpendicular al rayo de visión) y el MAYOR la
escala en PROFUNDIDAD, que se dispara con la distancia.

Para una cámara estenopeica a altura h, un objeto vertical de altura real
Hr a distancia d ocupa `alto_px ≈ f·Hr/d`, mientras que la escala lateral
del suelo es `s_lat ≈ d/f`. Multiplicando:

    alto_px · s_lat ≈ Hr

y **la distancia y la focal se cancelan**. O sea que `alto_px · s_lat` es
la altura real del objeto, sin saber dónde está la cámara ni su focal.

Verificado sobre las 748 detecciones que casan con una persona del GT del
benjamín — la altura implícita se mantiene plana en todo el campo:

| franja | p1 | mediana | p99 |
|---|---|---|---|
| 0-20 m | 0,80 | 1,40 | 1,75 |
| 20-30 m | 0,90 | 1,43 | 2,02 |
| 30-40 m | 0,97 | 1,49 | 2,02 |
| 40-50 m | 1,31 | 1,57 | 1,76 |
| 50-65 m | 1,00 | 1,57 | 1,79 |

Tres veces más lejos y la mediana se mueve un 12 %. Eso es lo que hace
que la regla sea un umbral y no un barrido por franjas.

## Por qué los umbrales son RELATIVOS a la mediana del partido

En el benjamín juegan niños de 8-9 años; en Villaviciosa, adultos. Un
umbral absoluto en metros no viaja, y este proyecto ya pagó ese error dos
veces (el rechazo por distancia al prototipo, y el 0.35 copiado en vez de
derivado). Así que la banda se expresa como **factor de la mediana de las
alturas implícitas del propio partido**, que es una escala natural del
problema: "la mitad de alto que una persona típica de ESTE partido".
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Índices en la tupla del caché: (mx, my, x1, y1, x2, y2, conf)
_X1, _Y1, _X2, _Y2 = 2, 3, 4, 5


def escalas_locales(H: np.ndarray, u: float, v: float) -> tuple[float, float]:
    """(escala lateral, escala en profundidad) en m/px en el píxel (u, v).

    Son los valores singulares del jacobiano de la homografía píxel→metros.
    El menor es el lateral: es el que sirve para medir alturas (ver el
    docstring del módulo).
    """
    n = H[2, 0] * u + H[2, 1] * v + H[2, 2]
    if abs(n) < 1e-12:
        return float("nan"), float("nan")
    p = H[0, 0] * u + H[0, 1] * v + H[0, 2]
    q = H[1, 0] * u + H[1, 1] * v + H[1, 2]
    jac = np.array(
        [
            [(H[0, 0] * n - p * H[2, 0]) / n**2, (H[0, 1] * n - p * H[2, 1]) / n**2],
            [(H[1, 0] * n - q * H[2, 0]) / n**2, (H[1, 1] * n - q * H[2, 1]) / n**2],
        ]
    )
    s = np.linalg.svd(jac, compute_uv=False)
    return float(s[1]), float(s[0])


def medidas_implicadas(cache: list[dict], H: np.ndarray) -> dict:
    """{(frame_idx, det_idx): (alto_m, ancho_m)} de cada detección.

    El píxel de referencia es el PIE de la caja (centro del borde
    inferior), que es el punto que toca el plano del suelo y el único
    donde la escala del suelo significa algo.
    """
    salida = {}
    for entrada in cache:
        f = entrada["frame_idx"]
        for i, det in enumerate(entrada["dets"]):
            u = (det[_X1] + det[_X2]) / 2.0
            v = det[_Y2]
            s_lat, _s_prof = escalas_locales(H, u, v)
            if not np.isfinite(s_lat):
                continue
            salida[(f, i)] = (
                float((det[_Y2] - det[_Y1]) * s_lat),
                float((det[_X2] - det[_X1]) * s_lat),
            )
    return salida


def referencia_del_partido(medidas: dict) -> float:
    """Altura implícita MEDIANA del partido: la escala de "una persona aquí".

    Se usa la mediana y no la media porque el fondo lejano produce alturas
    implícitas absurdas (medido: p99 de 17,9 m en las detecciones que no
    son ninguna de las 14 personas) y una media se iría con ellas.
    """
    alturas = [a for a, _w in medidas.values() if a > 0]
    return float(np.median(alturas)) if alturas else 0.0


def filtrar_por_plausibilidad(
    cache: list[dict],
    colores: dict | None,
    H: np.ndarray,
    alto_min_frac: float = 0.0,
    alto_max_frac: float = 0.0,
    ancho_min_frac: float = 0.0,
    ancho_max_frac: float = 0.0,
) -> tuple[list[dict], dict | None, int]:
    """Quita las detecciones cuyo tamaño implícito no puede ser una persona.

    Los cuatro umbrales van como FRACCIÓN de la altura implícita mediana
    del partido (0 = desactivado). Se aplican sobre la misma referencia a
    propósito: el ancho de una persona también escala con su altura, y así
    hay un solo número que calibrar por partido.

    ⚠️ El índice de detección es la POSICIÓN dentro de la lista del frame.
    Al tirar entradas, todos los índices posteriores se desplazan y el
    caché de colores quedaría emparejado con otra persona **sin fallar**
    (el bug que documenta src/tracking/filtro_confianza.py). Aquí se
    remapean las dos cosas a la vez.

    Returns:
        (caché filtrado, colores reindexados, nº de detecciones quitadas).
    """
    if not any((alto_min_frac, alto_max_frac, ancho_min_frac, ancho_max_frac)):
        return cache, colores, 0

    medidas = medidas_implicadas(cache, H)
    ref = referencia_del_partido(medidas)
    if ref <= 0:
        logger.warning("Sin referencia de altura: el filtro físico se salta.")
        return cache, colores, 0

    lim_alto = (alto_min_frac * ref, alto_max_frac * ref if alto_max_frac else 1e9)
    lim_ancho = (ancho_min_frac * ref, ancho_max_frac * ref if ancho_max_frac else 1e9)

    nuevo_cache, nuevos_colores, quitadas = [], {}, 0
    for entrada in cache:
        f = entrada["frame_idx"]
        dets = []
        for idx_viejo, det in enumerate(entrada["dets"]):
            alto, ancho = medidas.get((f, idx_viejo), (None, None))
            if alto is not None and (
                alto < lim_alto[0]
                or alto > lim_alto[1]
                or ancho < lim_ancho[0]
                or ancho > lim_ancho[1]
            ):
                quitadas += 1
                continue
            idx_nuevo = len(dets)
            dets.append(det)
            if colores is not None and (f, idx_viejo) in colores:
                nuevos_colores[(f, idx_nuevo)] = colores[(f, idx_viejo)]
        nuevo_cache.append({**entrada, "dets": dets})

    logger.info(
        "Filtro físico (altura mediana del partido %.2f m): %d detecciones "
        "quitadas por tamaño implícito imposible",
        ref,
        quitadas,
    )
    return nuevo_cache, (nuevos_colores if colores is not None else None), quitadas
