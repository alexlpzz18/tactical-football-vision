"""Diagnóstico de una calibración: ¿dónde es fiable y dónde no?

Sale de `docs/homografia_zona_cercana.md`. Se persiguió durante una sesión
un error de 1,29 m "cerca de la cámara" suponiendo que la homografía
extrapolaba mal en la franja sin puntos de calibración. **No era eso** — y
las dos medidas de aquí son las que lo demostraron, así que se quedan para
el próximo campo, que es lo que el producto va a pedir: cada cliente trae
el suyo y hay que decirle dónde puede fiarse del informe.

Dos funciones, dos preguntas distintas:

- `clics_en_el_borde` — ¿algún punto se marcó pegado al filo de la imagen?
  Si es así, el punto REAL estaba fuera de plano y se clicó el borde. En
  el benjamín pasó con los dos corners del área cercana (píxel x=0 y
  x=1919 sobre 1920), y el síntoma fue silencioso: la auditoría de escala
  medía esa área en 23,99 m contra 26 reglamentarios, mientras la de
  enfrente daba 25,82. Un clic así no se distingue de uno bueno mirando el
  JSON.

- `estabilidad` — cuánto se mueve cada punto del campo cuando los clics se
  perturban con el ruido de una mano humana. Es la respuesta honesta a
  "¿dónde es fiable esta calibración?", y no coincide con la intuición:
  en el benjamín la zona MÁS estable es la cercana (0,09 m) y la peor es
  el fondo (0,29-0,41 m), aunque el fondo tenga cinco puntos marcados y la
  franja cercana ninguno.

  ⚠️ Lo que mide NO es el error de la calibración, sino su SENSIBILIDAD al
  ruido de clic. Una calibración puede ser estable y estar mal (si todos
  los clics comparten un sesgo), así que esto no sustituye a
  `auditar_escala.py`, que la contrasta contra las marcas del reglamento.
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Margen en píxeles para considerar que un clic está "pegado al borde".
# 2 px: por debajo del propio ruido de la mano, así que solo caza los clics
# que de verdad tocaron el filo, no los que quedaron simplemente cerca.
MARGEN_BORDE_PX = 2.0


def clics_en_el_borde(
    puntos: list[dict],
    ancho_imagen: int,
    alto_imagen: int,
    margen_px: float = MARGEN_BORDE_PX,
) -> list[dict]:
    """Devuelve los puntos marcados a menos de `margen_px` del filo.

    Un clic ahí casi siempre significa que el punto real caía FUERA del
    encuadre y se marcó el borde en su lugar: el píxel es válido pero los
    metros que se le asignaron no son los de ese píxel.
    """
    sospechosos = []
    for punto in puntos:
        x, y = punto["pixel"]
        if (
            x <= margen_px
            or y <= margen_px
            or x >= ancho_imagen - 1 - margen_px
            or y >= alto_imagen - 1 - margen_px
        ):
            sospechosos.append(punto)
    if sospechosos:
        logger.warning(
            "%d clic(s) pegados al borde de la imagen: %s. El punto real "
            "podría estar fuera de plano.",
            len(sospechosos),
            ", ".join(p.get("nombre", "?") for p in sospechosos),
        )
    return sospechosos


def estabilidad(
    puntos: list[dict],
    consultas: list[tuple[float, float]],
    ruido_px: float = 2.0,
    repeticiones: int = 300,
    semilla: int = 0,
) -> list[float]:
    """Desplazamiento mediano, en metros, de cada punto de `consultas`.

    Se perturban los clics con ruido gaussiano de `ruido_px`, se reajusta la
    homografía y se mira cuánto se mueve la posición que esa homografía
    asigna al mismo píxel. Devuelve una lista paralela a `consultas`.

    `consultas` va en METROS (coordenadas de campo): cada una se lleva a su
    píxel con la homografía sin perturbar y es ese píxel el que se
    reproyecta, que es lo que le pasa de verdad a una detección.
    """
    if len(puntos) < 4:
        raise ValueError(
            f"Hacen falta al menos 4 puntos para una homografía (hay {len(puntos)})."
        )
    if not consultas:
        return []

    pixeles = np.array([p["pixel"] for p in puntos], dtype=np.float64)
    metros = np.array([p["metros"] for p in puntos], dtype=np.float32)
    base, _ = cv2.findHomography(pixeles.astype(np.float32), metros, cv2.RANSAC, 5.0)
    if base is None:
        raise ValueError("findHomography no encontró solución con los puntos dados.")

    objetivo = np.array(consultas, dtype=np.float32).reshape(-1, 1, 2)
    en_pixel = cv2.perspectiveTransform(objetivo, np.linalg.inv(base))

    rng = np.random.default_rng(semilla)
    desplazamientos = []
    for _ in range(repeticiones):
        ruidosos = (pixeles + rng.normal(0.0, ruido_px, pixeles.shape)).astype(
            np.float32
        )
        perturbada, _ = cv2.findHomography(ruidosos, metros, cv2.RANSAC, 5.0)
        if perturbada is None:
            continue
        movido = cv2.perspectiveTransform(en_pixel, perturbada).reshape(-1, 2)
        desplazamientos.append(movido)

    if not desplazamientos:
        raise ValueError("Ninguna de las repeticiones dio una homografía válida.")

    muestras = np.array(desplazamientos)
    # Contra la MEDIA de las perturbadas, no contra la original: así se mide
    # la dispersión que mete el ruido y no el sesgo del ajuste de partida.
    centro = muestras.mean(axis=0)
    distancias = np.linalg.norm(muestras - centro, axis=2)
    return [float(v) for v in np.median(distancias, axis=0)]
