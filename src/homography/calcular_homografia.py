"""
Calcula la homografía a partir de los puntos marcados a mano,
la valida dibujando el campo proyectado sobre la imagen,
y guarda la matriz H.
"""

import cv2
import json
import numpy as np

IMAGEN = "data/calibracion/frame_corregido.png"
PUNTOS = "data/calibracion/puntos_marcados.json"
SALIDA_H = "data/calibracion/homografia.npy"

# ── Cargar los puntos marcados ──
with open(PUNTOS) as f:
    puntos = json.load(f)

src_pts = np.array([p["pixel"] for p in puntos], dtype=np.float32)  # píxeles
dst_pts = np.array([p["metros"] for p in puntos], dtype=np.float32)  # metros

print(f"Puntos cargados: {len(puntos)}")

# ── Calcular la homografía ──
H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

print("\nMatriz H:")
print(H)
print(f"\nPuntos aceptados por RANSAC: {int(mask.sum())} de {len(puntos)}")
for i, p in enumerate(puntos):
    estado = "✓" if mask[i] else "✗ descartado"
    print(f"  {estado}  {p['nombre']}")

# ── Guardar la matriz ──
np.save(SALIDA_H, H)
print(f"\nMatriz guardada en {SALIDA_H}")

# ── Validación visual: dibujar el campo proyectado ──
H_inv = np.linalg.inv(H)


def metros_a_pixel(x_m, y_m):
    punto = np.array([x_m, y_m, 1.0])
    proy = H_inv @ punto
    proy = proy / proy[2]
    return int(proy[0]), int(proy[1])


img = cv2.imread(IMAGEN)

lineas_campo = [
    [(0, 0), (100, 0)],
    [(100, 0), (100, 64)],
    [(100, 64), (0, 64)],
    [(0, 64), (0, 0)],
    [(50, 0), (50, 64)],
    [(0, 11.84), (16.5, 11.84)],
    [(16.5, 11.84), (16.5, 52.16)],
    [(16.5, 52.16), (0, 52.16)],
    [(100, 11.84), (83.5, 11.84)],
    [(83.5, 11.84), (83.5, 52.16)],
    [(83.5, 52.16), (100, 52.16)],
]

for p1, p2 in lineas_campo:
    cv2.line(img, metros_a_pixel(*p1), metros_a_pixel(*p2), (0, 0, 255), 3)

# Círculo central
circulo = [
    metros_a_pixel(50 + 9.15 * np.cos(a), 32 + 9.15 * np.sin(a))
    for a in np.linspace(0, 2 * np.pi, 40)
]
for i in range(len(circulo) - 1):
    cv2.line(img, circulo[i], circulo[i + 1], (0, 0, 255), 3)

cv2.namedWindow("Validacion", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Validacion", 1600, 700)
cv2.imshow("Validacion", img)
print("\nCierra la ventana o pulsa una tecla para terminar.")
cv2.waitKey(0)
cv2.destroyAllWindows()
