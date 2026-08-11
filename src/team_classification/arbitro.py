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

⚠️ LIMITACIÓN CONOCIDA — el arquetipo NEGRO no se puede evaluar con el
caché actual. La feature de color es un histograma HS (`extraer_color_torso`
descarta V a propósito, para ser robusta a la iluminación), y sin V el
negro es indistinguible del blanco y del gris: los tres tienen saturación
baja. Los arquetipos flúor sí funcionan, porque lo que los define es
precisamente una saturación altísima en una franja concreta de tono.
Habilitar el negro exige añadir un estadístico de V al caché, lo que
implica regenerarlos en Colab.

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
    # Los arquetipos que necesitan V (el negro) quedan declarados pero
    # inactivos hasta que el caché lo guarde.
    necesita_v: bool = False

    def contiene(self, h: float, s: float) -> bool:
        return self.h_min <= h <= self.h_max and s >= self.s_min


# El conjunto cerrado. Los rangos de H salen de los colores flúor
# estándar de equipación arbitral, en unidades OpenCV (grados / 2).
ARQUETIPOS = (
    Arquetipo("amarillo_fluor", 20.0, 35.0, 170.0),
    Arquetipo("verde_fluor", 35.0, 85.0, 170.0),
    Arquetipo("naranja_fluor", 5.0, 20.0, 200.0),
    Arquetipo("azul_electrico", 100.0, 128.0, 180.0),
    # Sin V en el caché no se puede evaluar (ver docstring del módulo).
    Arquetipo("negro", 0.0, 180.0, 0.0, necesita_v=True),
)


def tono_dominante(feature: np.ndarray) -> tuple[float, float] | None:
    """(H, S) del bin dominante del histograma, en unidades OpenCV."""
    feature = np.asarray(feature)
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
    tonos = [t for t in (tono_dominante(p) for p in prototipos_equipo) if t]
    activos = []
    for arq in arquetipos:
        if arq.necesita_v:
            continue  # el caché no guarda V (ver docstring del módulo)
        choca = next((t for t in tonos if arq.contiene(*t)), None)
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
) -> dict[int, str]:
    """{id_identidad: nombre del arquetipo} de quienes visten de árbitro.

    Args:
        identidades: identidades ya cosidas (orden 1..N).
        colores: caché {(frame_idx, det_idx): feature}.
        prototipos_equipo: prototipos A y B, para la regla de conflicto.
        min_observaciones: recortes mínimos para juzgar (con menos, el
            tono dominante es demasiado inestable).

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
        tono = tono_dominante(np.mean(feats, axis=0))
        if tono is None:
            continue
        for arq in activos:
            if arq.contiene(*tono):
                encontrados[indice] = arq.nombre
                logger.info(
                    "Identidad %d viste de árbitro (%s: H=%.0f, S=%.0f, "
                    "%d recortes)",
                    indice,
                    arq.nombre,
                    tono[0],
                    tono[1],
                    len(feats),
                )
                break
    return encontrados
