"""Quita del caché de balón lo que no se mueve nunca: las marcas del campo.

29-ago-2026. El esquema mixto subió el balón detectado del 53 % al 81 %
anunciado, y al medir la posesión salió que los instantes sin dueño
estaban a **12,4 m** del jugador más cercano. Tirando de ahí:
**11.982 detecciones —el 56 % del total— caen en 10 celdas de 12×12 px**,
cada una con dispersión de 0,6 a 3,2 px y presencia repartida por los 20
minutos.

Mirando los recortes, la respuesta: **son marcas pintadas y manchas fijas
del campo**. El punto central, el de penalti, una marca oscura junto al
muro del fondo. Tienen el tamaño y el color de un balón, y el troceado de
la franja las presenta a la red lo bastante grandes como para que dispare.

⚠️ POR QUÉ NO VALEN OTRAS DOS SEÑALES, medidas y descartadas:

1. **Coexistencia** ("el balón no está en dos sitios a la vez"). Parecía
   la señal limpia y está contaminada: los propios fantasmas coexisten
   ENTRE SÍ, así que el balón de verdad sale "fijo" por coincidir con
   ellos. Daba 10 de 10 objetos fijos, incluido el balón bueno.
2. **Racha continua**. Un objeto del fondo debería estar siempre, pero se
   detecta de forma intermitente: las rachas más largas son de 14-19 s,
   indistinguibles de un balón parado en una falta.

Lo que sí separa es lo trivial: **acumular cientos de detecciones en la
MISMA celda a lo largo del partido**. La celda mediana del caché tiene 2
detecciones y la marca fija más pequeña tiene 108.

⚠️ COSTE ACEPTADO, y hay que decirlo: cuando el balón se posa
EXACTAMENTE sobre una marca pintada —el saque de centro sobre el punto
central, un penalti— esta función también lo quita. Es asumible porque
son paradas de juego, no fútbol: nadie tiene la posesión en ese instante.
Lo que NO sería asumible es lo contrario, dejar una marca haciéndose
pasar por balón durante 20 minutos.
"""

import logging
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)

# Umbrales, con el margen que los justifica medido sobre la parte entera:
#   - celda de 12 px: un balón en juego recorre el campo y reparte sus
#     detecciones por 2.552 celdas distintas.
#   - 100 detecciones: las marcas fijas van de 108 a 4.973; la celda que
#     más acumula sin ser una marca tiene 94. El hueco es real y el
#     umbral cae en su centro.
#   - 120 s: una marca aparece a lo largo de todo el partido; un balón
#     parado en una falta dura segundos.
#   - 4 px de dispersión: las marcas van de 0,6 a 3,2 px.
CELDA_PX = 12
MIN_DETECCIONES = 100
MIN_DURACION_S = 120.0
MAX_DISPERSION_PX = 4.0


def _centro_px(det):
    return (det[2] + det[4]) / 2.0, (det[3] + det[5]) / 2.0


def encontrar_marcas_estaticas(
    detecciones: dict,
    tiempos: dict,
    celda_px: int = CELDA_PX,
    min_detecciones: int = MIN_DETECCIONES,
    min_duracion_s: float = MIN_DURACION_S,
    max_dispersion_px: float = MAX_DISPERSION_PX,
) -> set:
    """Celdas (cx, cy) que contienen una marca fija, no el balón.

    Args:
        detecciones: {frame_idx: [(mx, my, x1, y1, x2, y2, conf), ...]}.
        tiempos: {frame_idx: t en segundos}.

    Returns:
        El conjunto de celdas sospechosas, en unidades de `celda_px`.

        ⚠️ Son CELDAS, no objetos: una marca justo sobre el borde de la
        rejilla cae en dos celdas contiguas. En la parte entera salen 10
        celdas para unos 5-6 objetos reales. Para contar objetos habría
        que fusionar las contiguas; para FILTRAR da igual, y por eso no
        se hace.
    """
    por_celda = defaultdict(list)
    for frame, dets in detecciones.items():
        t = tiempos.get(frame)
        if t is None:
            continue
        for det in dets:
            px, py = _centro_px(det)
            por_celda[(int(px // celda_px), int(py // celda_px))].append((t, px, py))

    marcas = set()
    for celda, puntos in por_celda.items():
        if len(puntos) < min_detecciones:
            continue
        ts = [p[0] for p in puntos]
        if max(ts) - min(ts) < min_duracion_s:
            continue
        disp = float(
            np.hypot(np.std([p[1] for p in puntos]), np.std([p[2] for p in puntos]))
        )
        if disp <= max_dispersion_px:
            marcas.add(celda)
    return marcas


def filtrar_marcas_estaticas(
    detecciones: dict, tiempos: dict, **umbrales
) -> tuple[dict, set]:
    """Quita las detecciones que caen en una marca fija del campo.

    Returns:
        (detecciones sin las marcas, conjunto de celdas descartadas).
    """
    marcas = encontrar_marcas_estaticas(detecciones, tiempos, **umbrales)
    if not marcas:
        return dict(detecciones), marcas

    celda = umbrales.get("celda_px", CELDA_PX)
    limpio, quitadas = {}, 0
    for frame, dets in detecciones.items():
        buenas = []
        for det in dets:
            px, py = _centro_px(det)
            if (int(px // celda), int(py // celda)) in marcas:
                quitadas += 1
            else:
                buenas.append(det)
        if buenas:
            limpio[frame] = buenas

    total = sum(len(v) for v in detecciones.values())
    logger.info(
        "Marcas fijas del campo: %d celdas, %d detecciones quitadas de %d "
        "(%.1f %%). Los frames con balón pasan de %d a %d.",
        len(marcas),
        quitadas,
        total,
        100 * quitadas / max(total, 1),
        len(detecciones),
        len(limpio),
    )
    return limpio, marcas
