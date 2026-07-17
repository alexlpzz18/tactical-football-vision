"""Regla de porteros por POSICIÓN (independiente del color).

El clasificador de color no puede asignar equipo a los porteros (visten
distinto que su equipo), pero su posición los delata: una identidad cuya
posición MEDIANA vive dentro de un área de penalti es el portero del
equipo que defiende ese lado. La mediana (no la media) hace la regla
robusta a observaciones sueltas fuera del área.

Verificado sobre el GT del tramo de validación: portero_A (defiende el
lado de mx alto) tiene mediana mx=90.9 [85.1-95.5]; portero_B (mx bajo)
mediana mx=15.4 [11.9-17.9]; ningún jugador de campo tiene su mediana
dentro de esas zonas. Qué equipo defiende cada lado se indica en config
(en un partido real cambia al descanso; la automatización de ese mapeo
queda para la integración end-to-end).
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ReglaPorteros:
    """Áreas de penalti en metros (ejes de la homografía del partido)."""

    # Rango mx del área del lado bajo (portería izquierda en esta cámara)
    area_mx_bajo: tuple[float, float] = (0.0, 19.0)
    # Rango mx del área del lado alto
    area_mx_alto: tuple[float, float] = (86.0, 110.0)
    # Rango my común (ancho del área, generoso alrededor de la portería)
    area_my: tuple[float, float] = (20.0, 55.0)
    # Qué equipo defiende cada lado en este tramo
    equipo_mx_alto: str = "A"
    equipo_mx_bajo: str = "B"

    @classmethod
    def desde_dict(cls, d: dict) -> "ReglaPorteros":
        d = dict(d)
        for clave in ("area_mx_bajo", "area_mx_alto", "area_my"):
            if clave in d:
                d[clave] = tuple(d[clave])
        return cls(**d)


def aplicar_regla_porteros(
    equipos: dict[int, str],
    identidades: list[list[Tracklet]],
    regla: ReglaPorteros,
) -> dict[int, str]:
    """Reetiqueta como portero_X las identidades que viven en un área.

    Args:
        equipos: {id_identidad (1..N): 'A'/'B'/'otro'} del clasificador de
            color. La regla SOBRESCRIBE la etiqueta de color (los porteros
            visten distinto y el color no es fiable para ellos).
        identidades: las identidades cosidas, en el mismo orden 1..N.
        regla: áreas y mapeo lado→equipo.

    Returns:
        Copia de `equipos` con las identidades de área reetiquetadas como
        'portero_A' / 'portero_B'.
    """
    resultado = dict(equipos)
    n_reetiquetadas = 0
    for id_identidad, identidad in enumerate(identidades, start=1):
        posiciones = np.array([pos for tr in identidad for pos in tr.pos])
        mediana = np.median(posiciones, axis=0)
        mx, my = float(mediana[0]), float(mediana[1])
        if not (regla.area_my[0] <= my <= regla.area_my[1]):
            continue
        if regla.area_mx_bajo[0] <= mx <= regla.area_mx_bajo[1]:
            resultado[id_identidad] = f"portero_{regla.equipo_mx_bajo}"
            n_reetiquetadas += 1
        elif regla.area_mx_alto[0] <= mx <= regla.area_mx_alto[1]:
            resultado[id_identidad] = f"portero_{regla.equipo_mx_alto}"
            n_reetiquetadas += 1
    logger.info("Regla de porteros: %d identidades reetiquetadas", n_reetiquetadas)
    return resultado
