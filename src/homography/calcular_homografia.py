"""
Calcula la homografía a partir de los puntos marcados a mano,
la valida dibujando el campo proyectado sobre la imagen,
y guarda la matriz H.

Las líneas de validación se dibujan del MODELO de campo
(src/campo_modelo.py), así que vale igual para F11 que para F7.

Uso:
    # F11 de Villaviciosa (comportamiento y rutas de siempre)
    python -m src.homography.calcular_homografia

    # Fútbol 7 del benjamín, con sus rutas
    python -m src.homography.calcular_homografia --config configs/campo_benja.yaml

    # Sin ventana (útil en remoto o para repetir la calibración en lote)
    python -m src.homography.calcular_homografia --config ... --sin-ventana
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import yaml

from src.campo_modelo import cargar_modelo

# Rutas por defecto: las del F11 de Villaviciosa (no cambiar)
IMAGEN = "data/calibracion/frame_corregido.png"
PUNTOS = "data/calibracion/puntos_marcados.json"
SALIDA_H = "data/calibracion/homografia.npy"


def calcular_homografia(puntos: list[dict], umbral_ransac: float = 5.0):
    """H (píxel→metros) por RANSAC + la máscara de puntos aceptados."""
    if len(puntos) < 4:
        raise ValueError(
            f"Hacen falta al menos 4 puntos para una homografía (hay {len(puntos)})."
        )
    src = np.array([p["pixel"] for p in puntos], dtype=np.float32)
    dst = np.array([p["metros"] for p in puntos], dtype=np.float32)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, umbral_ransac)
    if H is None:
        raise ValueError(
            "findHomography no encontró solución: revisa que los clics no "
            "estén alineados ni repetidos."
        )
    return H, mask


def error_reproyeccion(puntos: list[dict], H: np.ndarray) -> np.ndarray:
    """Error en METROS de cada punto al proyectarlo con H."""
    src = np.array([p["pixel"] for p in puntos], dtype=np.float64).reshape(-1, 1, 2)
    dst = np.array([p["metros"] for p in puntos], dtype=np.float64)
    proy = cv2.perspectiveTransform(src, H).reshape(-1, 2)
    return np.linalg.norm(proy - dst, axis=1)


def dibujar_validacion(img, modelo, H):
    """Dibuja el campo del modelo proyectado sobre la imagen."""
    H_inv = np.linalg.inv(H)

    def a_pixel(x_m, y_m):
        proy = H_inv @ np.array([x_m, y_m, 1.0])
        proy = proy / proy[2]
        return int(proy[0]), int(proy[1])

    for p1, p2 in modelo.lineas():
        cv2.line(img, a_pixel(*p1), a_pixel(*p2), (0, 0, 255), 3)
    circulo = [a_pixel(x, y) for x, y in modelo.circulo()]
    for i in range(len(circulo) - 1):
        cv2.line(img, circulo[i], circulo[i + 1], (0, 0, 255), 3)
    return img


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campo", default="f11", help="f11 (defecto) o f7")
    parser.add_argument("--config", default=None, help="YAML del campo y rutas")
    parser.add_argument("--imagen", default=None)
    parser.add_argument("--puntos", default=None)
    parser.add_argument("--salida", default=None)
    parser.add_argument("--ransac", type=float, default=5.0)
    parser.add_argument("--sin-ventana", action="store_true")
    args = parser.parse_args()

    modelo = cargar_modelo(
        nombre=None if args.config else args.campo, config=args.config
    )
    rutas = {}
    if args.config:
        with open(args.config) as f:
            rutas = yaml.safe_load(f).get("rutas", {})
    ruta_imagen = args.imagen or rutas.get("imagen", IMAGEN)
    ruta_puntos = args.puntos or rutas.get("puntos", PUNTOS)
    ruta_salida = args.salida or rutas.get("homografia", SALIDA_H)

    with open(ruta_puntos) as f:
        puntos = json.load(f)
    print(f"Campo: {modelo.nombre} ({modelo.largo:.1f} x {modelo.ancho:.1f} m)")
    print(f"Puntos cargados: {len(puntos)}  ({ruta_puntos})")

    H, mask = calcular_homografia(puntos, args.ransac)
    print("\nMatriz H:")
    print(H)
    print(f"\nPuntos aceptados por RANSAC: {int(mask.sum())} de {len(puntos)}")
    errores = error_reproyeccion(puntos, H)
    for i, p in enumerate(puntos):
        estado = "✓" if mask[i] else "✗ descartado"
        print(f"  {estado:<13} {p['nombre']:<24} error {errores[i]:>6.2f} m")
    aceptados = errores[mask.ravel().astype(bool)]
    if len(aceptados):
        print(
            f"\nError de reproyección (aceptados): mediana {np.median(aceptados):.2f} m, "
            f"máximo {aceptados.max():.2f} m"
        )

    Path(ruta_salida).parent.mkdir(parents=True, exist_ok=True)
    np.save(ruta_salida, H)
    print(f"\nMatriz guardada en {ruta_salida}")

    if args.sin_ventana:
        return
    img = cv2.imread(ruta_imagen)
    if img is None:
        print(f"(sin validación visual: no se encuentra {ruta_imagen})")
        return
    img = dibujar_validacion(img, modelo, H)
    cv2.namedWindow("Validacion", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Validacion", 1600, 700)
    cv2.imshow("Validacion", img)
    print("\nCierra la ventana o pulsa una tecla para terminar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
