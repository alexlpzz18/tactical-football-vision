"""
Prueba de proyección: detecta jugadores en un frame, proyecta la posición
de sus pies al campo real (metros) con la homografía, y dibuja el radar 2D.
"""

import cv2
import numpy as np
from ultralytics import YOLO

# ── Rutas ──
IMAGEN = "data/calibracion/frame_corregido.png"
H_PATH = "data/calibracion/homografia.npy"
MODELO = "models/weights/best_v1.pt"  # ajusta si tu modelo se llama distinto

FIELD_LENGTH = 100
FIELD_WIDTH = 64

# ── Cargar homografía y modelo ──
H = np.load(H_PATH)
modelo = YOLO(MODELO)


def pixel_a_metros(x, y):
    punto = np.array([x, y, 1.0])
    proy = H @ punto
    proy = proy / proy[2]
    return proy[0], proy[1]


# ── Detectar jugadores en el frame ──
img = cv2.imread(IMAGEN)
resultados = modelo(img)[0]

posiciones_campo = []
for box in resultados.boxes.xyxy.cpu().numpy():
    x1, y1, x2, y2 = box
    # Punto de los pies: centro horizontal, borde inferior
    pies_x = (x1 + x2) / 2
    pies_y = y2
    # Proyectar a metros
    mx, my = pixel_a_metros(pies_x, pies_y)
    posiciones_campo.append((mx, my))
    # Dibujar la caja y el punto de pies en la imagen
    cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
    cv2.circle(img, (int(pies_x), int(pies_y)), 5, (0, 0, 255), -1)

print(f"Jugadores detectados: {len(posiciones_campo)}")

# ── Dibujar el radar 2D ──
escala = 12  # píxeles por metro
radar = np.zeros((FIELD_WIDTH * escala, FIELD_LENGTH * escala, 3), dtype=np.uint8)
radar[:] = (40, 100, 40)  # verde césped


# Líneas del campo en el radar
def m2r(x, y):
    return int(x * escala), int(y * escala)


cv2.rectangle(radar, m2r(0, 0), m2r(100, 64), (255, 255, 255), 2)
cv2.line(radar, m2r(50, 0), m2r(50, 64), (255, 255, 255), 2)
cv2.circle(radar, m2r(50, 32), int(9.15 * escala), (255, 255, 255), 2)
cv2.rectangle(radar, m2r(0, 11.84), m2r(16.5, 52.16), (255, 255, 255), 2)
cv2.rectangle(radar, m2r(83.5, 11.84), m2r(100, 52.16), (255, 255, 255), 2)

# Jugadores en el radar
for mx, my in posiciones_campo:
    if 0 <= mx <= 100 and 0 <= my <= 64:
        cv2.circle(radar, m2r(mx, my), 8, (0, 200, 255), -1)
        cv2.circle(radar, m2r(mx, my), 8, (0, 0, 0), 2)

# ── Mostrar las dos ventanas ──
cv2.namedWindow("Deteccion", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Deteccion", 1200, 500)
cv2.imshow("Deteccion", img)

cv2.namedWindow("Radar 2D", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Radar 2D", 1000, 640)
cv2.imshow("Radar 2D", radar)

print("Pulsa una tecla sobre una ventana para cerrar.")
cv2.waitKey(0)
cv2.destroyAllWindows()
