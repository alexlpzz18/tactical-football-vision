"""Catálogo ABSOLUTO de equipaciones arbitrales.

El intento anterior —"si el color está lejos de los dos prototipos de
equipo, es otro"— fracasó midiendo (ver docs/experimentos_tracking.md):
el umbral que separaba perfectamente en el benjamín hundía Villaviciosa,
porque una distancia en unidades de histograma no viaja entre partidos.

Este enfoque le da la vuelta: en vez de preguntar "¿está lejos de estos
dos equipos?" (relativo, y por tanto dependiente del partido), pregunta
"¿es esto una equipación de árbitro?" (absoluto, y por tanto universal).
Los árbitros visten un conjunto CERRADO y reconocible: amarillo flúor,
verde flúor, naranja flúor, negro y azul eléctrico. Eso no se calibra por
partido porque no cambia de un partido a otro.

El arquetipo NEGRO depende de la VERSIÓN del caché de color, y se activa
solo. Con la feature v1 —un histograma HS que descarta V a propósito, por
robustez a la iluminación— el negro es indistinguible del blanco y del
gris: los tres tienen saturación baja. Con la v2, que añade V (ver
src/team_classification/feature_v2.py), pasa a ser evaluable, y este
módulo lo detecta mirando si los prototipos traen brillo. Los arquetipos
flúor funcionan con las dos versiones, porque lo que los define es una
saturación altísima en una franja concreta de tono.

REGLA DE CONFLICTO (imprescindible, no un adorno): si una de las dos
equipaciones del partido cae dentro de un arquetipo, ese arquetipo se
DESACTIVA para ese partido. Es un caso real y frecuente: el equipo B del
benjamín viste naranja saturado (H=6, S=248), que es exactamente el
arquetipo "naranja flúor". Sin esta regla, el catálogo etiquetaría a
media plantilla como árbitros.
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.team_classification.feature_v2 import brillo_medio

logger = logging.getLogger(__name__)

# Unidades de OpenCV: H en 0-180 (la mitad de los grados), S en 0-255.
BINS_H, BINS_S = 16, 16


@dataclass(frozen=True)
class Arquetipo:
    """Una equipación arbitral: franja de tono + saturación mínima."""

    nombre: str
    h_min: float
    h_max: float
    s_min: float
    # El NEGRO no se define por el tono sino por brillo bajo y poca
    # saturación, así que tiene su propio criterio. Darle rangos comodín
    # de H y S y reutilizar la regla de los flúor no funciona: `contiene`
    # devolvía True para CUALQUIER color, y entonces la regla de
    # conflicto lo desactivaba siempre (lo cazó un test).
    v_max: float | None = None
    s_max: float = 255.0

    @property
    def necesita_v(self) -> bool:
        return self.v_max is not None

    def contiene(self, h: float, s: float, brillo: float | None = None) -> bool:
        if self.v_max is not None:
            return brillo is not None and brillo < self.v_max and s <= self.s_max
        return self.h_min <= h <= self.h_max and s >= self.s_min


# El conjunto cerrado. Los rangos de H salen de los colores flúor
# estándar de equipación arbitral, en unidades OpenCV (grados / 2).
ARQUETIPOS = (
    Arquetipo("amarillo_fluor", 20.0, 35.0, 170.0),
    Arquetipo("verde_fluor", 35.0, 85.0, 170.0),
    Arquetipo("naranja_fluor", 5.0, 20.0, 200.0),
    Arquetipo("azul_electrico", 100.0, 128.0, 180.0),
    # Brillo bajo Y poca saturación: un granate también es oscuro, pero
    # no es negro. Solo evaluable con features v2 (la v1 no guarda V).
    Arquetipo("negro", 0.0, 180.0, 0.0, v_max=60.0, s_max=90.0),
)


def tono_dominante(feature: np.ndarray) -> tuple[float, float] | None:
    """(H, S) del bin dominante del histograma, en unidades OpenCV."""
    from src.team_classification.feature_v2 import parte_camiseta_hs

    feature = parte_camiseta_hs(np.asarray(feature))
    if feature.size == 0 or not np.any(feature):
        return None
    indice = int(np.argmax(feature))
    ih, is_ = divmod(indice, BINS_S)
    return (ih + 0.5) * 180.0 / BINS_H, (is_ + 0.5) * 256.0 / BINS_S


def arquetipos_activos(
    prototipos_equipo: list[np.ndarray],
    arquetipos=ARQUETIPOS,
) -> tuple[Arquetipo, ...]:
    """Quita los arquetipos que chocan con una equipación del partido.

    Args:
        prototipos_equipo: features de los prototipos A y B.
        arquetipos: catálogo a filtrar.

    Returns:
        Los arquetipos utilizables en ESTE partido.
    """
    equipos = []
    for proto in prototipos_equipo:
        tono = tono_dominante(proto)
        if tono:
            equipos.append((tono[0], tono[1], brillo_medio(np.asarray(proto))))
    hay_v = any(b is not None for _h, _s, b in equipos)
    activos = []
    for arq in arquetipos:
        if arq.necesita_v and not hay_v:
            continue  # caché v1: no guarda V (ver docstring del módulo)
        choca = next((e for e in equipos if arq.contiene(*e)), None)
        if choca:
            logger.info(
                "Arquetipo '%s' DESACTIVADO en este partido: una equipación "
                "cae dentro (H=%.0f, S=%.0f)",
                arq.nombre,
                choca[0],
                choca[1],
            )
            continue
        activos.append(arq)
    return tuple(activos)


def identificar_arbitros(
    identidades,
    colores: dict,
    prototipos_equipo: list[np.ndarray],
    min_observaciones: int = 25,
    margen_equipo: float = 0.0,
) -> dict[int, str]:
    """{id_identidad: nombre del arquetipo} de quienes visten de árbitro.

    Args:
        identidades: identidades ya cosidas (orden 1..N).
        colores: caché {(frame_idx, det_idx): feature}.
        prototipos_equipo: prototipos A y B, para la regla de conflicto.
        min_observaciones: recortes mínimos para juzgar (con menos, el
            tono dominante es demasiado inestable).
        margen_equipo: si es > 0, el catálogo SOLO manda cuando el color
            de la identidad está a más de `margen_equipo × d(A,B)` del
            prototipo más cercano. Sin esto, la regla de conflicto
            protege al PROTOTIPO del equipo pero no a la dispersión
            alrededor: un jugador cuyo color se aparta cae en un
            arquetipo que no choca con la media de su equipo. Medido: le
            pasaba al id 40 de Villaviciosa, un jugador del equipo A con
            110 observaciones en el centro del campo.

    Returns:
        Solo las identidades que caen en un arquetipo activo.
    """
    activos = arquetipos_activos(prototipos_equipo)
    if not activos:
        logger.info("Ningún arquetipo arbitral utilizable en este partido")
        return {}

    encontrados: dict[int, str] = {}
    for indice, identidad in enumerate(identidades, start=1):
        feats = [
            colores[par]
            for tracklet in identidad
            for par in tracklet.det_idxs
            if par in colores
        ]
        if len(feats) < min_observaciones:
            continue
        media = np.mean(feats, axis=0)
        tono = tono_dominante(media)
        if tono is None:
            continue
        brillo = brillo_medio(media)
        if margen_equipo > 0 and len(prototipos_equipo) >= 2:
            from src.team_classification.feature_v2 import parte_camiseta_hs

            hs = parte_camiseta_hs(media)
            a, b = prototipos_equipo[0], prototipos_equipo[1]
            separacion = float(np.linalg.norm(a - b))
            cerca = min(float(np.linalg.norm(hs - a)), float(np.linalg.norm(hs - b)))
            if separacion > 0 and cerca < margen_equipo * separacion:
                # Se parece a un equipo: manda el equipo, no el catálogo.
                #
                # ⚠️ Y se AVISA cuando la identidad vetada es grande. Este
                # margen se adoptó a 0,68 y hubo que revertirlo el mismo
                # día: con otro caché del mismo partido vetaba al ÁRBITRO
                # —583 observaciones en el centro del campo— que se colaba
                # entero en un equipo. La guarda que contaba identidades
                # en el tercer grupo daba el visto bueno, porque no puede
                # saber si la que queda es la correcta. Esta sí lo habría
                # cazado.
                if len(feats) >= 100:
                    logger.warning(
                        "El margen del catálogo VETA a la identidad %d, que "
                        "tiene %d observaciones y casaba un arquetipo "
                        "arbitral (distancia al equipo más cercano %.2f de "
                        "%.2f × %.2f). Si era el árbitro, va a contar para "
                        "un equipo.",
                        indice,
                        len(feats),
                        cerca,
                        margen_equipo,
                        separacion,
                    )
                continue
        for arq in activos:
            if arq.contiene(tono[0], tono[1], brillo):
                encontrados[indice] = arq.nombre
                logger.info(
                    "Identidad %d viste de árbitro (%s: H=%.0f, S=%.0f, "
                    "V=%s, %d recortes)",
                    indice,
                    arq.nombre,
                    tono[0],
                    tono[1],
                    f"{brillo:.0f}" if brillo is not None else "n/d",
                    len(feats),
                )
                break
    return encontrados
