"""Regla de STAFF por homografía: quien vive FUERA del campo no juega.

Diagnóstico que la motiva (08-ago-2026, feedback visual del replay v4pre):
en el replay aparecía una ficha con equipo asignado paseando por encima de
la banda superior. Es el juez de línea (o cuerpo técnico): el clasificador
de color no puede descartarlo — y menos aún desde que el fit v4pre no
produce prototipo 'otro' — pero la GEOMETRÍA sí, y gratis: su posición
mediana proyectada cae fuera del rectángulo del campo.

Misma filosofía que la regla de porteros: una decisión posicional, barata
y explicable, que corrige al color en vez de pedirle más de lo que puede
dar. La tolerancia existe porque el error de proyección crece con la
profundidad: un jugador real pisando la banda puede proyectarse un par de
metros fuera.
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)

ETIQUETA_STAFF = "staff"


@dataclass
class ReglaStaff:
    """Parámetros de la regla de staff (valores por defecto conservadores)."""

    largo: float = 105.0
    ancho: float = 68.0
    # Metros que la posición MEDIANA debe estar fuera del rectángulo para
    # considerar que la identidad no juega. 2.0 m deja margen al error de
    # proyección de un jugador que pisa la banda.
    tolerancia_m: float = 2.0
    # Mínimo de observaciones para juzgar: con 2-3 posiciones la mediana no
    # significa nada (y los artefactos de proyección son cortos).
    min_observaciones: int = 5

    @classmethod
    def desde_dict(cls, d: dict) -> "ReglaStaff":
        return cls(**d)


def _distancia_fuera(mx: float, my: float, largo: float, ancho: float) -> float:
    """Metros que el punto (mx, my) queda fuera del rectángulo del campo."""
    fuera_x = max(0.0, -mx, mx - largo)
    fuera_y = max(0.0, -my, my - ancho)
    return max(fuera_x, fuera_y)


def aplicar_regla_staff(
    equipos: dict[int, str],
    identidades: list[list[Tracklet]],
    regla: ReglaStaff,
) -> dict[int, str]:
    """Reetiqueta como 'staff' las identidades que viven fuera del campo.

    Args:
        equipos: {id_identidad (1..N): etiqueta} del clasificador.
        identidades: las identidades en el MISMO orden (id = índice + 1).
        regla: parámetros (dimensiones del campo y tolerancia).

    Returns:
        Diccionario nuevo con las identidades de fuera marcadas 'staff'.
        No se tocan las demás (incluidos los porteros ya reetiquetados).
    """
    resultado = dict(equipos)
    n_staff = 0
    for id_identidad, identidad in enumerate(identidades, start=1):
        posiciones = np.array([pos for tracklet in identidad for pos in tracklet.pos])
        if len(posiciones) < regla.min_observaciones:
            continue
        mx, my = float(np.median(posiciones[:, 0])), float(np.median(posiciones[:, 1]))
        fuera = _distancia_fuera(mx, my, regla.largo, regla.ancho)
        if fuera > regla.tolerancia_m:
            resultado[id_identidad] = ETIQUETA_STAFF
            n_staff += 1
            logger.debug(
                "Identidad %d marcada staff: mediana (%.1f, %.1f), %.1f m fuera",
                id_identidad,
                mx,
                my,
                fuera,
            )
    logger.info(
        "Regla de staff: %d identidades fuera del campo (tolerancia %.1f m)",
        n_staff,
        regla.tolerancia_m,
    )
    return resultado
