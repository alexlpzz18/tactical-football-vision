"""Cajas ANORMALES para su posición: qué recortes no son de fiar para el color.

Puerta de calidad de caja (docs/diagnostico_28oct_g.md). La forma de una caja depende de dónde está
su pie en la imagen: cerca de la cámara una persona mide más píxeles que en el fondo. Una caja mucho
más alta o más ancha de lo esperado para su posición suele coger a DOS personas (el árbitro con el
jugador de debajo, dos jugadores lado a lado); una mucho más baja es un FRAGMENTO (cabeza, torso).
Su color es una mezcla, o es de un trozo, y no debería votar el equipo.

Como en `oclusion.py`, esto NO quita la detección del tracking ni su posición: solo le quita el voto
de color en la ventana de `etiquetar_por_observacion`. La observación recibe la etiqueta de los
demás recortes de su ventana.

Por qué el tamaño esperado sale de un AJUSTE y no de la homografía: la homografía es del plano del
SUELO. Da la escala horizontal en el pie, pero no la vertical, porque la altura de una persona no
está en ese plano. El ajuste por posición (cuadrático, robusto) es la geometría de ESTA cámara
medida sobre sus propias detecciones; es el mismo f(u, v) del 22-oct, bloque 3
(`scripts/diag22_altura_contador.py`).
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def ajustar_tamano_esperado(u, v, valor, iteraciones: int = 30):
    """f(u, v) = valor esperado (alto o ancho, px): cuadrática en (u, v) con pérdida de Huber.

    Mínimos cuadrados reponderados (IRLS): las cajas raras pesan menos, así que el ajuste describe
    la caja TÍPICA de cada posición aunque haya cajas fundidas y fragmentos en la muestra.
    """
    u, v, valor = (np.asarray(x, float) for x in (u, v, valor))
    u0, v0 = float(np.median(u)), float(np.median(v))

    def diseno(uu, vv):
        a, b = (np.asarray(uu, float) - u0) / 1000.0, (
            np.asarray(vv, float) - v0
        ) / 1000.0
        return np.column_stack([np.ones_like(a), a, b, a * b, a**2, b**2])

    X = diseno(u, v)
    w = np.ones(len(valor))
    beta = np.zeros(X.shape[1])
    for _ in range(iteraciones):
        raiz = np.sqrt(w)
        beta, *_ = np.linalg.lstsq(X * raiz[:, None], valor * raiz, rcond=None)
        r = valor - X @ beta
        s = 1.4826 * np.median(np.abs(r - np.median(r))) or 1.0
        k = 1.345 * s
        w = np.where(np.abs(r) <= k, 1.0, k / np.maximum(np.abs(r), 1e-9))

    def f(uu, vv):
        return diseno(uu, vv) @ beta

    return f


def cajas_anormales(
    cache: list[dict],
    alto_max: float = 1.4,
    ancho_max: float = 1.6,
    alto_min: float = 0.6,
) -> set[tuple[int, int]]:
    """{(frame_idx, índice de detección)} de las cajas anormales para su posición.

    Anormal: alto / alto_esperado > `alto_max`, o ancho / ancho_esperado > `ancho_max`, o
    alto / alto_esperado < `alto_min`. Los esperados se ajustan sobre TODAS las detecciones del
    caché (u = centro de la base, v = borde inferior).
    """
    claves, u, v, alto, ancho = [], [], [], [], []
    for entrada in cache:
        for i, d in enumerate(entrada["dets"]):
            x1, y1, x2, y2 = (float(c) for c in d[2:6])
            claves.append((entrada["frame_idx"], i))
            u.append((x1 + x2) / 2)
            v.append(y2)
            alto.append(y2 - y1)
            ancho.append(x2 - x1)
    if len(claves) < 10:
        return set()
    u, v, alto, ancho = (np.asarray(x, float) for x in (u, v, alto, ancho))
    f_alto = ajustar_tamano_esperado(u, v, alto)
    f_ancho = ajustar_tamano_esperado(u, v, ancho)
    r_alto = alto / np.maximum(f_alto(u, v), 1.0)
    r_ancho = ancho / np.maximum(f_ancho(u, v), 1.0)
    malas = (r_alto > alto_max) | (r_ancho > ancho_max) | (r_alto < alto_min)
    anormales = {c for c, m in zip(claves, malas) if m}
    logger.info(
        "Cajas anormales para su posición: %d de %d (%.1f %%; altas %d, anchas %d, bajas %d)",
        len(anormales),
        len(claves),
        100 * len(anormales) / len(claves),
        int((r_alto > alto_max).sum()),
        int((r_ancho > ancho_max).sum()),
        int((r_alto < alto_min).sum()),
    )
    return anormales
