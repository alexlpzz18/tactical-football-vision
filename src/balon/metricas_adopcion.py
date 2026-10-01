"""Dos métricas de adopción que "huecos cerrados" no ve (1-oct-2026).

Pedido de Alex al revisar el mecanismo de GREEDYNMM: "huecos cerrados" es
CIEGO a un sistema que se engancha 300 frames seguidos a una marca sin
soltarla — técnicamente CERO huecos, pero está completamente equivocado.
Es justo el fallo que tuvo el esquema mixto cuando se adoptó solo mirando
huecos cerrados y resultó que el 56 % del caché era el punto central del
campo (`src/balon/marcas_estaticas.py`).

⚠️ LA MITAD QUE FALTA, y por qué. El `static-lock ratio` que pidió Alex
tiene dos partes: "cae cerca de una marca" Y "MIENTRAS el balón real está
en otra zona". La segunda parte necesita saber dónde está el balón real,
y **no hay GT de posición de balón en el proyecto** (confirmado:
`scripts/oraculo_balon.py` ya lo dice en su docstring, y ni
`data/annotations/gt_benja/` ni `data/annotations/ground_truth_tracking/`
anotan balón, solo `player` y `referee`). Por eso aquí solo se mide la
PRIMERA mitad, `fraccion_en_marcas`: cuánto del tiempo de salida cae en
una celda de marca conocida. Es una cota superior del problema, no la
métrica completa — un frame en una celda de marca puede ser el balón real
posado justo ahí (el coste aceptado que ya documenta
`marcas_estaticas.py`), así que un valor alto no prueba el fallo, pero un
valor bajo sí lo descarta.
"""

from __future__ import annotations

import numpy as np


def fraccion_en_marcas(
    trayectoria: list[tuple[int, np.ndarray]],
    marcas: set[tuple[int, int]],
    celda_px: int = 12,
) -> float:
    """Fracción de observaciones de SALIDA que caen en una celda de marca.

    Args:
        trayectoria: [(frame_idx, (px, py))] en PÍXELES — el centro de la
            caja que el sistema entregó como balón en ese frame.
        marcas: celdas (cx, cy) ya localizadas por
            `marcas_estaticas.encontrar_marcas_estaticas`.
        celda_px: debe coincidir con el que se usó para encontrar `marcas`.

    Returns:
        0.0 si no hay observaciones. No distingue "balón real posado en
        la marca" de "fallo enganchado a la marca" — ver el docstring del
        módulo.
    """
    if not trayectoria:
        return 0.0
    en_marca = 0
    for _frame, (px, py) in trayectoria:
        celda = (int(px // celda_px), int(py // celda_px))
        if celda in marcas:
            en_marca += 1
    return en_marca / len(trayectoria)


def duracion_maxima_anclada(
    trayectoria: list[tuple[int, np.ndarray]],
    tiempos: dict[int, float],
    radio_m: float = 1.0,
    max_hueco_s: float = 1.0,
) -> float:
    """Duración (s) del tramo continuo más largo sin salir de una zona pequeña.

    No necesita GT: es una propiedad de la trayectoria de SALIDA en sí
    misma. Un balón en juego se mueve; un fallo enganchado a una marca
    (o a cualquier objeto fijo) no. Un tramo se corta si el balón sale
    del radio O si hay un hueco de detección mayor que `max_hueco_s`
    (para no fundir dos paradas de juego distintas en una sola racha).

    Args:
        trayectoria: [(frame_idx, (x_m, y_m))] en METROS, ordenada por
            frame — cualquier huecos ya están fuera de esta lista.
        tiempos: {frame_idx: t en segundos}.
        radio_m: cuánto puede moverse el balón y seguir contando como
            "la misma zona". 1,0 m es generoso para un balón parado.
        max_hueco_s: hueco de detección máximo dentro del mismo tramo.

    Returns:
        Segundos del tramo más largo. 0.0 si la trayectoria está vacía.
    """
    if not trayectoria:
        return 0.0

    mejor = 0.0
    inicio_frame, inicio_pos = trayectoria[0]
    t_inicio = tiempos[inicio_frame]
    t_anterior = t_inicio
    centro = np.array(inicio_pos, dtype=float)
    n_tramo = 1

    def cerrar_tramo(t_fin):
        nonlocal mejor
        mejor = max(mejor, t_fin - t_inicio)

    for frame, pos in trayectoria[1:]:
        t = tiempos[frame]
        pos = np.array(pos, dtype=float)
        hueco = t - t_anterior
        # Centro móvil (media del tramo) para no castigar una deriva lenta
        # real como si fuera un "salto" fuera de zona.
        dist = float(np.linalg.norm(pos - centro))
        if hueco > max_hueco_s or dist > radio_m:
            cerrar_tramo(t_anterior)
            inicio_frame, t_inicio = frame, t
            centro = pos.copy()
            n_tramo = 1
        else:
            centro = (centro * n_tramo + pos) / (n_tramo + 1)
            n_tramo += 1
        t_anterior = t

    cerrar_tramo(t_anterior)
    return mejor
