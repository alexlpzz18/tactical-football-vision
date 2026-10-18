"""Validación automática de un vídeo AL RECIBIRLO, con 10-20 frames sueltos.

Responde dos preguntas antes de gastar GPU en él:

1. **¿Los jugadores son lo bastante grandes?** Mediana de la altura de las cajas del
   DETECTOR en esos frames. Por debajo de 25 px se degrada (umbral medido en el
   diagnóstico de Villaviciosa). Pasar el detector por 10-20 frames cuesta segundos en
   Colab. ⚠️ Se probó a estimarlo SIN detector, con manchas de "lo que no es césped y tiene
   forma de persona", y NO sirve: contra las cajas del detector, en 10 frames del benjamín,
   salía 33 px contra 59 (0,58×), y de 0,22× a 0,96× según el frame. Un vídeo de 40 px
   reales habría dado una falsa alarma. Se quitó (docs/calibracion_automatica.md).
2. **¿Se ve el campo entero?** Solo CPU: si el césped toca el borde izquierdo, el derecho
   o el inferior de la imagen en buena parte, el campo sigue fuera de plano por ese lado.

No la usa el pipeline: es una comprobación previa, para avisar.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

UMBRAL_PX_JUGADOR = 25.0  # diagnóstico de Villaviciosa
CESPED_BAJO, CESPED_ALTO = np.array([35, 40, 40]), np.array([85, 255, 255])
FRACCION_BORDE_CORTADO = 0.20  # césped en > 20 % de un borde lateral/inferior = cortado


def mascara_cesped(img: np.ndarray) -> np.ndarray:
    """Césped (verde) y su mayor región con los agujeros rellenos (jugadores, líneas)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    verde = cv2.inRange(hsv, CESPED_BAJO, CESPED_ALTO)
    # El tono del CÉSPED se calibra en cada vídeo: la mediana de lo verde en la mitad
    # inferior (donde casi seguro está el campo), ±8. Con el rango verde genérico entraba
    # la ladera de hierba de detrás del benjamín, y sus matorrales salían como "jugadores".
    abajo = hsv[hsv.shape[0] // 2 :][verde[verde.shape[0] // 2 :] > 0]  # noqa: E203
    if len(abajo):
        tono = float(np.median(abajo[:, 0]))
        verde &= (np.abs(hsv[:, :, 0].astype(float) - tono) <= 8).astype(np.uint8) * 255
    verde = cv2.morphologyEx(verde, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    # Las líneas blancas parten el césped en trozos: se cierran antes de buscar la región
    # (sin esto la mayor región era un 24 % de la imagen, un solo trozo entre líneas).
    unido = cv2.morphologyEx(verde, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    # Marco de 1 px: findContours no rellena la primera ni la última fila/columna, y el
    # aviso de "campo cortado" mira justo ahí.
    unido = cv2.copyMakeBorder(unido, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    contornos, _ = cv2.findContours(unido, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    region = np.zeros(unido.shape, np.uint8)
    if contornos:
        cv2.drawContours(region, [max(contornos, key=cv2.contourArea)], -1, 255, -1)
    region = region[1:-1, 1:-1] & unido[1:-1, 1:-1]  # sin el marco
    return verde, region


def bordes_cortados(img: np.ndarray) -> list[str]:
    """Bordes (izquierda, derecha, abajo) por los que el campo sigue fuera de plano."""
    _verde, region = mascara_cesped(img)
    bordes = {
        "izquierda": region[:, 0],
        "derecha": region[:, -1],
        "abajo": region[-1, :],
    }
    return [b for b, v in bordes.items() if (v > 0).mean() > FRACCION_BORDE_CORTADO]


@dataclass
class Validacion:
    mediana_px: float | None
    n_cajas: int
    jugadores_pequenos: bool
    bordes_cortados: dict = field(default_factory=dict)  # borde → fracción de frames
    campo_entero: bool = True
    avisos: list = field(default_factory=list)


def validar_video(
    frames: list[np.ndarray],
    alturas_cajas_px: list[float],
    umbral_px: float = UMBRAL_PX_JUGADOR,
) -> Validacion:
    """Valida un vídeo con unos pocos frames (10-20, repartidos).

    Args:
        frames: los frames, en BGR.
        alturas_cajas_px: alturas (y2 − y1) de las cajas de persona del detector en ESOS
            frames (con la confianza de producción).
    """
    cortes: dict = {}
    for img in frames:
        for b in bordes_cortados(img):
            cortes[b] = cortes.get(b, 0) + 1
    mediana = float(np.median(alturas_cajas_px)) if len(alturas_cajas_px) else None
    frac = {b: c / max(len(frames), 1) for b, c in cortes.items()}
    v = Validacion(
        mediana_px=mediana,
        n_cajas=len(alturas_cajas_px),
        jugadores_pequenos=mediana is not None and mediana < umbral_px,
        bordes_cortados=frac,
        campo_entero=not any(f >= 0.5 for f in frac.values()),
    )
    if mediana is None:
        v.avisos.append("el detector no encontró a nadie: ¿es un vídeo de fútbol?")
    elif v.jugadores_pequenos:
        v.avisos.append(
            f"jugadores de {mediana:.0f} px de mediana (< {umbral_px:.0f}): el detector "
            "se degrada; hace falta acercar la cámara o más resolución"
        )
    if not v.campo_entero:
        lados = ", ".join(b for b, f in frac.items() if f >= 0.5)
        v.avisos.append(f"el campo no se ve entero: sigue fuera de plano por {lados}")
    return v
