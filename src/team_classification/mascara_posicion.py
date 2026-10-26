"""Rango de color del césped de UN frame, para la máscara por posición de la feature.

docs/diagnostico_22oct_b.md, bloque 3. La máscara anti-verde de la feature borra una banda FIJA
(H 35-85, S≥40, V≥40) y con ella el chaleco verde flúor del árbitro (H≈46, V≈247): el
histograma ve el 7 % de su torso (docs/diagnostico_22oct.md, bloque 2). Aquí el césped se mide
en el propio frame, en «cajas vacías» del mismo tamaño que las detecciones, desplazadas en
horizontal hasta donde no tocan ninguna, con el pie dentro del campo.
"""

import numpy as np

DESPLAZAMIENTOS = (-6, -3, 3, 6)  # en anchos de caja
PERCENTILES = (1, 99)
MIN_PIXELES = 200  # por debajo, el rango no es fiable: se devuelve None


def _solapan(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def rango_cesped_del_frame(frame_bgr, cajas_px, a_metros, dimensiones, max_cajas=4):
    """(lo, hi) HSV del césped de este frame, o None si no hay bastantes píxeles.

    Args:
        frame_bgr: la imagen.
        cajas_px: [(x1, y1, x2, y2)] de las detecciones del frame.
        a_metros: función (u, v) → (x, y) en metros (la homografía).
        dimensiones: (largo, ancho) del campo en metros.
    """
    import cv2

    h_img, w_img = frame_bgr.shape[:2]
    largo, ancho = dimensiones
    trozos = []
    for x1, y1, x2, y2 in list(cajas_px)[:max_cajas]:
        an = x2 - x1
        for dx in DESPLAZAMIENTOS:
            c = (x1 + dx * an, y1, x2 + dx * an, y2)
            if c[0] < 0 or c[2] >= w_img or any(_solapan(c, b) for b in cajas_px):
                continue
            xm, ym = a_metros((c[0] + c[2]) / 2.0, c[3])
            if not (0 <= xm <= largo and 0 <= ym <= ancho):
                continue
            al = c[3] - c[1]
            ya, yb = int(c[1] + 0.20 * al), int(c[1] + 0.45 * al)
            xa, xb = int(c[0] + 0.35 * an), int(c[0] + 0.65 * an)
            ya, yb, xa, xb = max(ya, 0), min(yb, h_img), max(xa, 0), min(xb, w_img)
            if yb > ya and xb > xa:
                trozos.append(
                    cv2.cvtColor(frame_bgr[ya:yb, xa:xb], cv2.COLOR_BGR2HSV).reshape(
                        -1, 3
                    )
                )
    if not trozos:
        return None
    px = np.vstack(trozos)
    if len(px) < MIN_PIXELES:
        return None
    lo = np.percentile(px, PERCENTILES[0], axis=0)
    hi = np.percentile(px, PERCENTILES[1], axis=0)
    return lo, hi
