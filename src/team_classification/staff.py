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
    # ── Tolerancia SEGUNDA, para quien además se mueve poco ──────────
    #
    # Por qué hace falta (medido en el benjamín, 25-ago-2026): el
    # entrenador del chándal vive a 0,23 m fuera de la banda y mete la
    # mitad de las fugas del sistema. Bajar `tolerancia_m` para cogerlo
    # NO se puede: un jugador real tiene su mediana a 0,22 m fuera de la
    # banda contraria. **Un centímetro.** Ninguna tolerancia los separa
    # mirando solo la posición.
    #
    # Y la velocidad sola tampoco: el más lento del partido no es el
    # entrenador (0,67 m/s) sino EL PORTERO (0,60 m/s), así que una regla
    # de "se mueve poco" a secas se lleva al portero por delante.
    #
    # Las dos juntas sí, porque el portero está DENTRO y el entrenador
    # FUERA. Es la doctrina de siempre: no aplicar un criterio ruidoso a
    # todo el mundo, solo decidir mejor donde ya hay riesgo. La velocidad
    # solo se mira en quien ya está fuera de las líneas.
    #
    # Margen medido: la identidad-persona más lenta después del portero va
    # a 2,06 m/s, así que 1,5 m/s cae en un hueco ancho.
    # ⚠️ Margen de proyección: 0,15 m, no 0. Con 0 exacto, un portero cuya
    # mediana caiga UN CENTÍMETRO por detrás de la línea de fondo —cosa
    # normalísima, ahí es donde vive— se marcaría staff, y eso cuesta más
    # de lo que la regla gana. Medido: 0,15 m sigue cogiendo al entrenador
    # (0,23 m fuera) y no cambia ninguna cifra.
    tolerancia_lento_m: float = 0.15
    vel_max_lento: float = 0.0  # 0 = desactivado
    # Observaciones mínimas para juzgar una VELOCIDAD, que no es lo mismo
    # que juzgar una mediana de posición: `min_observaciones` (5) se eligió
    # para lo segundo. Con 5 muestras en medio segundo, "se mueve poco" no
    # significa nada — le pasaba a la identidad 53 del benjamín, de 6
    # observaciones.
    min_obs_lento: int = 25

    @classmethod
    def desde_dict(cls, d: dict) -> "ReglaStaff":
        regla = cls(**d)
        # `_distancia_fuera` está acotada con max(0, ...), así que una
        # tolerancia NEGATIVA no significa "dentro por ese margen": la
        # comparación `0 > -1` es cierta para todo el mundo y marcaría
        # staff al campo entero. Ya pasó en un barrido. Se rechaza en vez
        # de dejar la trampa abierta en el YAML.
        for nombre in ("tolerancia_m", "tolerancia_lento_m"):
            if getattr(regla, nombre) < 0:
                raise ValueError(
                    f"{nombre} no puede ser negativa ({getattr(regla, nombre)}): "
                    "la distancia al campo está acotada a 0 y una tolerancia "
                    "negativa marcaría staff a TODAS las identidades."
                )
        return regla


def _distancia_fuera(mx: float, my: float, largo: float, ancho: float) -> float:
    """Metros que el punto (mx, my) queda fuera del rectángulo del campo."""
    fuera_x = max(0.0, -mx, mx - largo)
    fuera_y = max(0.0, -my, my - ancho)
    return max(fuera_x, fuera_y)


def velocidad_media(identidad: list[Tracklet]) -> float | None:
    """Metros por segundo a lo largo de la identidad, o None si no se sabe.

    Se divide por el tiempo REAL transcurrido y no por el número de
    observaciones: una identidad con huecos no debe parecer más lenta solo
    por tenerlos.

    ⚠️ Devuelve **None**, no 0.0, cuando no hay con qué calcularla (una
    sola observación, o todas con la misma marca de tiempo). Codificar
    "no lo sé" como 0 la mandaba justo al lado que DISPARA la regla: una
    identidad de 5 muestras con el mismo instante y 12 m recorridos salía
    a 0 m/s y se marcaba staff.
    """
    obs = sorted(
        ((t, p) for tr in identidad for t, p in zip(tr.ts, tr.pos)),
        key=lambda o: o[0],
    )
    if len(obs) < 2:
        return None
    duracion = obs[-1][0] - obs[0][0]
    if duracion <= 0:
        return None
    recorrido = sum(
        float(np.linalg.norm(np.asarray(obs[i][1]) - np.asarray(obs[i - 1][1])))
        for i in range(1, len(obs))
    )
    return recorrido / duracion


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
        motivo = None
        if fuera > regla.tolerancia_m:
            motivo = "fuera del campo"
        elif (
            regla.vel_max_lento > 0
            and fuera > regla.tolerancia_lento_m
            and len(posiciones) >= regla.min_obs_lento
            # ⚠️ La rama lenta NO puede sobrescribir a un portero. Es el
            # único jugador del campo que puede estar quieto Y sobre la
            # línea de fondo a la vez, y la etiqueta de portero la ha
            # puesto la regla de área, que sabe más que esta. Sin esta
            # guarda, un portero un centímetro por detrás de su línea sale
            # de staff y el centroide del benjamín se va de 1,27 a 2,04 m.
            and not str(equipos.get(id_identidad, "")).startswith("portero")
        ):
            velocidad = velocidad_media(identidad)
            if velocidad is not None and velocidad < regla.vel_max_lento:
                motivo = "fuera de la línea y casi quieto"
        if motivo:
            resultado[id_identidad] = ETIQUETA_STAFF
            n_staff += 1
            logger.debug(
                "Identidad %d marcada staff (%s): mediana (%.1f, %.1f), %.1f m fuera",
                id_identidad,
                motivo,
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
