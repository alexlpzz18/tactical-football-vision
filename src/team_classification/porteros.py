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

    @classmethod
    def desde_modelo(
        cls,
        modelo,
        margen: float = 2.0,
        equipo_mx_alto: str = "A",
        equipo_mx_bajo: str = "B",
    ) -> "ReglaPorteros":
        """Deriva las áreas del MODELO de campo en vez de hardcodearlas.

        Los valores por defecto de esta clase son los del F11 de
        Villaviciosa, ajustados a mano contra su ground truth. En un campo
        de otra medida no significan nada: un corte en mx=88,5 no existe
        en un campo de 62 m de largo. Con esto, la regla sale del
        reglamento de la modalidad y de las dimensiones reales del campo.
        """
        areas = modelo.areas_porteria(margen=margen)
        return cls(
            area_mx_bajo=areas["bajo"][0],
            area_mx_alto=areas["alto"][0],
            area_my=areas["bajo"][1],
            equipo_mx_alto=equipo_mx_alto,
            equipo_mx_bajo=equipo_mx_bajo,
        )


def _mediana(identidad: list[Tracklet]) -> tuple[float, float]:
    """Posición mediana de la identidad (mx, my)."""
    posiciones = np.array([pos for tr in identidad for pos in tr.pos])
    mediana = np.median(posiciones, axis=0)
    return float(mediana[0]), float(mediana[1])


def _en_area(mx: float, my: float, regla: "ReglaPorteros") -> str | None:
    """'bajo', 'alto' o None según en qué área de portería vive."""
    if not (regla.area_my[0] <= my <= regla.area_my[1]):
        return None
    if regla.area_mx_bajo[0] <= mx <= regla.area_mx_bajo[1]:
        return "bajo"
    if regla.area_mx_alto[0] <= mx <= regla.area_mx_alto[1]:
        return "alto"
    return None


def deducir_lados(
    equipos: dict[int, str],
    identidades: list[list[Tracklet]],
    largo: float,
    regla: "ReglaPorteros | None" = None,
    ancho: float | None = None,
    separacion_min_frac: float = 0.02,
) -> tuple[str, str] | None:
    """Qué equipo defiende cada portería, DEDUCIDO de las posiciones.

    Antes esto era un par de claves de config que había que "ajustar al
    partido" a mano. No funciona: nadie puede verificarlo a ojo sobre un
    replay, y en el benjamín estaba al revés — los porteros salían
    cruzados (el portero_A era en realidad el del equipo B).

    La señal que sí decide: el equipo que defiende la portería x=0 tiene
    a sus jugadores, en promedio, más cerca de ella que el rival, porque
    sus defensas viven ahí. Medido en el benjamín: A 30,0 m vs B 34,1 m
    sobre un campo de 62, una separación de 4,2 m que no deja duda y que
    da el lado CORRECTO (el contrario del que estaba configurado).

    Se usa el eje LARGO (pos[0]), que es donde están las porterías, sea
    cual sea el eje de profundidad de la cámara.

    ⚠️ Los propios porteros NO pueden votar, y por eso hace falta `regla`.
    El motivo no es que "voten al equipo contrario", sino que su etiqueta
    de color es basura: un portero viste distinto a sus compañeros, así
    que el clasificador le asigna un equipo prácticamente al azar. Y como
    además vive en un extremo del campo, ese voto aleatorio arrastra la
    media de quien le toque. Medido en el benjamín: dejándolos votar sale
    A 42,4 vs B 34,2 (invertido); excluyéndolos, A 30,0 vs B 34,1
    (correcto, y coincide con la verificación visual).

    Args:
        equipos: {id: etiqueta} del clasificador de color.
        identidades: las identidades, en el mismo orden 1..N.
        largo: largo del campo en metros.
        regla: si se pasa, las identidades que viven en un área de
            portería quedan EXCLUIDAS del voto (ver arriba).
        ancho: ancho del campo. Con él solo votan las posiciones DENTRO
            del campo — imprescindible, porque esta deducción corre antes
            que la regla de staff y en el fondo de la imagen hay público
            y suplentes proyectados a x=71, 80 y hasta 95 m sobre un
            campo de 62. Con ellos dentro, la media de su equipo se
            dispara y el signo vuelve a salir invertido.
        separacion_min_frac: separación mínima entre las medias, como
            fracción del largo, para fiarse. Por debajo se devuelve None
            y manda la config.

    Returns:
        (equipo_bajo, equipo_alto) o None si la señal no es concluyente.
    """
    posiciones: dict[str, list[float]] = {"A": [], "B": []}
    for indice, identidad in enumerate(identidades, start=1):
        etiqueta = equipos.get(indice)
        if etiqueta not in posiciones:
            continue  # porteros ya marcados, staff, 'otro': no votan
        if regla is not None and _en_area(*_mediana(identidad), regla) is not None:
            continue  # vive en un área: es portero, y su voto invierte el signo
        for tracklet in identidad:
            for pos in tracklet.pos:
                mx, my = float(pos[0]), float(pos[1])
                if not 0.0 <= mx <= largo:
                    continue
                if ancho is not None and not 0.0 <= my <= ancho:
                    continue
                posiciones[etiqueta].append(mx)

    if not posiciones["A"] or not posiciones["B"]:
        return None
    media_a = float(np.mean(posiciones["A"]))
    media_b = float(np.mean(posiciones["B"]))
    if abs(media_a - media_b) < separacion_min_frac * largo:
        logger.warning(
            "Lados de portería no concluyentes (A %.1f m vs B %.1f m, "
            "separación < %.0f %% del campo): se usa lo configurado",
            media_a,
            media_b,
            100 * separacion_min_frac,
        )
        return None

    bajo, alto = ("A", "B") if media_a < media_b else ("B", "A")
    logger.info(
        "Lados deducidos de las posiciones: %s defiende x=0 y %s x=%.0f "
        "(x media: A %.1f m, B %.1f m)",
        bajo,
        alto,
        largo,
        media_a,
        media_b,
    )
    return bajo, alto


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
        lado = _en_area(*_mediana(identidad), regla)
        if lado is None:
            continue
        equipo = regla.equipo_mx_bajo if lado == "bajo" else regla.equipo_mx_alto
        resultado[id_identidad] = f"portero_{equipo}"
        n_reetiquetadas += 1
    logger.info("Regla de porteros: %d identidades reetiquetadas", n_reetiquetadas)
    return resultado
