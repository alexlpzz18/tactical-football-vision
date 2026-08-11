"""Feature de color v2: añade V y separa camiseta de pantalón.

Qué desbloquea, y por qué se hace ahora:

1. **Canal V.** La feature v1 es un histograma HS y descarta V a
   propósito, por robustez a la iluminación. El precio es que el negro no
   se distingue del blanco ni del gris (los tres tienen saturación baja),
   y por eso el arquetipo NEGRO del catálogo arbitral está declarado pero
   inactivo. Con V pasa a ser evaluable.
2. **Camiseta vs pantalón.** v1 mira solo la banda del pecho. Muchas
   equipaciones se distinguen mejor abajo (camiseta blanca con pantalón
   negro frente a camiseta blanca con pantalón blanco), y el pantalón se
   ocluye menos en los amontonamientos, donde precisamente falla la
   clasificación.

## Compatibilidad, que es la parte delicada

TODOS los umbrales calibrados del sistema viven en la escala de la v1: el
barrido de fusión del fit (0,5-1,3), el veto de color del cosido (1,2,
con mediana de pares legítimos 0,90) y las firmas de la salvaguarda.
Cambiar la feature sin más los invalidaría en silencio.

Por eso la v2 **empieza por la v1 bit a bit**: los primeros 256 valores
son exactamente el histograma HS del pecho normalizado en L2 que produce
`extraer_color_torso`. Cualquier código que compare solo ese bloque
obtiene distancias IDÉNTICAS a las de hoy. Los bloques nuevos van detrás
y se consultan aparte.

La versión viaja en el meta del caché (`version_feature`), y
`parte_camiseta_hs()` acepta las dos longitudes, así que los cachés
viejos siguen funcionando sin tocar nada.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

VERSION_FEATURE = 2

# Disposición del vector v2 (por bloques, cada uno normalizado en L2):
#   [0:256]   histograma HS 16x16 del PECHO   ← idéntico a la v1
#   [256:272] histograma V de 16 bins del pecho
#   [272:336] histograma HS 8x8 del PANTALÓN
LONGITUD_V1 = 256
LONGITUD_V_PECHO = 16
LONGITUD_HS_PANTALON = 64
LONGITUD_V2 = LONGITUD_V1 + LONGITUD_V_PECHO + LONGITUD_HS_PANTALON

_INI_V = LONGITUD_V1
_FIN_V = _INI_V + LONGITUD_V_PECHO
_INI_PANTALON = _FIN_V


def _normalizar(vector: np.ndarray) -> np.ndarray:
    """L2, como la v1 (ver la advertencia de extraer_color_torso)."""
    norma = np.linalg.norm(vector)
    return vector / norma if norma > 0 else vector


def extraer_color_torso_v2(crop: np.ndarray, params=None) -> np.ndarray:
    """Feature v2 de un recorte BGR de jugador.

    Args:
        crop: recorte BGR del jugador.
        params: ParametrosClasificadorColor (mismos que la v1).

    Returns:
        Vector de LONGITUD_V2 floats. Sus primeros 256 valores son
        EXACTAMENTE la feature v1.
    """
    import cv2

    from src.team_classification.color_classifier import (
        ParametrosClasificadorColor,
        extraer_color_torso,
    )

    p = params or ParametrosClasificadorColor()
    # Bloque 1: la v1 tal cual, sin reimplementarla (que se desviaría en
    # cuanto alguien tocara una de las dos).
    hs_pecho = extraer_color_torso(crop, p)

    alto, ancho = crop.shape[:2]
    x0, x1 = int(ancho * p.torso_ancho[0]), int(ancho * p.torso_ancho[1])

    # Bloque 2: V del pecho. Se aplica la MISMA máscara anti-verde que la
    # v1, para que hable de la persona y no del césped del fondo.
    y0, y1 = int(alto * p.torso_alto[0]), int(alto * p.torso_alto[1])
    v_pecho = _histograma_v(crop[y0:y1, x0:x1], p, cv2)

    # Bloque 3: HS del PANTALÓN, en la banda inmediatamente inferior al
    # pecho. Se queda por encima de las espinillas (mucho césped y mucha
    # media) usando la mitad de la altura restante.
    y2 = min(alto, y1 + int((alto - y1) * 0.5))
    hs_pantalon = _histograma_hs(crop[y1:y2, x0:x1], p, cv2, bins=8)

    return np.concatenate([hs_pecho, v_pecho, hs_pantalon])


def _mascara_verde(hsv, p):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (
        (h >= p.verde_h[0])
        & (h <= p.verde_h[1])
        & (s >= p.verde_s_min)
        & (v >= p.verde_v_min)
    )


def _histograma_v(banda, p, cv2, bins=LONGITUD_V_PECHO):
    if banda.size == 0:
        return np.zeros(bins)
    hsv = cv2.cvtColor(banda, cv2.COLOR_BGR2HSV)
    validos = hsv[~_mascara_verde(hsv, p)]
    if len(validos) == 0:
        return np.zeros(bins)
    hist, _ = np.histogram(validos[:, 2], bins=bins, range=(0, 256))
    return _normalizar(hist.astype(float))


def _histograma_hs(banda, p, cv2, bins=8):
    if banda.size == 0:
        return np.zeros(bins * bins)
    hsv = cv2.cvtColor(banda, cv2.COLOR_BGR2HSV)
    validos = hsv[~_mascara_verde(hsv, p)]
    if len(validos) == 0:
        return np.zeros(bins * bins)
    hist, _, _ = np.histogram2d(
        validos[:, 0], validos[:, 1], bins=[bins, bins], range=[[0, 180], [0, 256]]
    )
    return _normalizar(hist.flatten().astype(float))


# ── accesores, que son los que dan la compatibilidad ─────────────────


def es_v2(feature: np.ndarray) -> bool:
    return len(feature) == LONGITUD_V2


def parte_camiseta_hs(feature: np.ndarray) -> np.ndarray:
    """El bloque HS del pecho: idéntico a la v1 en ambas versiones.

    Es la función que hace que los cachés viejos sigan valiendo: todo el
    código calibrado en la escala v1 puede llamar a esto sin saber con
    qué versión de caché está trabajando.
    """
    return feature[:LONGITUD_V1]


def parte_v(feature: np.ndarray) -> np.ndarray | None:
    """Histograma de V del pecho, o None si la feature es v1."""
    return feature[_INI_V:_FIN_V] if es_v2(feature) else None


def parte_pantalon(feature: np.ndarray) -> np.ndarray | None:
    """Histograma HS del pantalón, o None si la feature es v1."""
    return feature[_INI_PANTALON:] if es_v2(feature) else None


def brillo_medio(feature: np.ndarray) -> float | None:
    """Brillo medio (0-255) del pecho, o None si la feature es v1.

    Es lo que hace evaluable el arquetipo NEGRO: un torso negro tiene el
    peso del histograma de V concentrado en los bins bajos.
    """
    v = parte_v(feature)
    if v is None or not np.any(v):
        return None
    centros = (np.arange(LONGITUD_V_PECHO) + 0.5) * 256.0 / LONGITUD_V_PECHO
    return float(np.sum(v * centros) / np.sum(v))
