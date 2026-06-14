import cv2
import numpy as np


class LineDetector:
    """
    Detecta las líneas del campo de fútbol en un frame.
    Estrategia : aislar el campo por su color verde,
    detectar bordes y líneas rectas por su forma (no por su color),
    y descartar las que caen sobre jugadores.
    """

    def __init__(self):
        # Rango de color verde del césped en espacio HSV.
        # H (tono): 35-85 cubre desde verde-amarillento a verde-azulado
        # S (saturación): 40-255 evita grises desaturados
        # V (brillo): 40-255 evita zonas demasiado oscuras
        self.green_lower = np.array([35, 40, 40])
        self.green_upper = np.array([85, 255, 255])

    def _get_field_mask(self, frame: np.ndarray) -> np.ndarray:
        """
        Etapa 1: aísla la zona del campo detectando el césped verde.

        Args:
            frame: imagen en formato BGR (como la lee OpenCV)

        Returns:
            máscara binaria: 255 (blanco) donde hay campo, 0 (negro) fuera
        """
        # 1.1 — Convertimos de BGR a HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # 1.2 — Creamos la máscara de píxeles verdes
        green_mask = cv2.inRange(hsv, self.green_lower, self.green_upper)

        # 1.3 — Limpiamos la máscara con operaciones morfológicas
        # Kernel: la "brocha" con la que limpiamos, 7x7 píxeles
        kernel = np.ones((7, 7), np.uint8)

        # CLOSE rellena huecos pequeños (las líneas blancas dentro del campo)
        green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel)

        # OPEN elimina manchas pequeñas de ruido fuera del campo
        green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)

        return green_mask
