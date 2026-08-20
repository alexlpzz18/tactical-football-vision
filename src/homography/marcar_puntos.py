"""
Herramienta de clic para marcar puntos del campo sobre una imagen.
Marca cada punto en orden; permite saltar los que no se vean y deshacer.
Guarda las coordenadas exactas (píxeles) en un JSON.

Los puntos NO están hardcodeados: se generan del modelo de campo
(src/campo_modelo.py), así que sirve para F11, para F7 o para cualquier
campo descrito en un YAML.

Uso:
    # F11 de Villaviciosa (comportamiento y rutas de siempre)
    python -m src.homography.marcar_puntos

    # Fútbol 7 con las medidas por defecto
    python -m src.homography.marcar_puntos --campo f7 \
        --imagen data/calibracion_benja/frame.png \
        --salida data/calibracion_benja/puntos_marcados_benja.json

    # Campo descrito en un config (rutas incluidas)
    python -m src.homography.marcar_puntos --config configs/campo_benja.yaml
"""

import argparse
import json
from pathlib import Path

import cv2
import yaml

from src.campo_modelo import cargar_modelo

# Rutas por defecto: las del F11 de Villaviciosa (no cambiar)
IMAGEN = "data/calibracion/frame_corregido.png"
SALIDA = "data/calibracion/puntos_marcados.json"


def _rutas_desde_config(config: str | None) -> dict:
    if config is None:
        return {}
    with open(config) as f:
        return yaml.safe_load(f).get("rutas", {})


class Marcador:
    """Estado de la sesión de marcado (puntos hechos e índice actual)."""

    def __init__(self, puntos_a_marcar):
        self.puntos_a_marcar = puntos_a_marcar
        self.marcados = []
        self.idx = 0

    def clic(self, x: int, y: int) -> None:
        if self.idx >= len(self.puntos_a_marcar):
            return
        nombre, metros = self.puntos_a_marcar[self.idx]
        self.marcados.append(
            {"nombre": nombre, "pixel": [x, y], "metros": list(metros)}
        )
        print(f"  ✓ {nombre}: pixel ({x}, {y}) -> metros {metros}")
        self.idx += 1

    def saltar(self) -> None:
        if self.idx < len(self.puntos_a_marcar):
            print(f"  ⤳ saltado: {self.puntos_a_marcar[self.idx][0]}")
            self.idx += 1

    def deshacer(self) -> None:
        if not self.marcados:
            return
        quitado = self.marcados.pop()
        nombres = [n for n, _ in self.puntos_a_marcar]
        self.idx = nombres.index(quitado["nombre"])
        print(f"  ↶ deshecho: {quitado['nombre']}")

    def texto(self) -> str:
        if self.idx >= len(self.puntos_a_marcar):
            return "TERMINADO - pulsa 's' para guardar, 'q' para salir"
        nombre, metros = self.puntos_a_marcar[self.idx]
        return (
            f"[{self.idx + 1}/{len(self.puntos_a_marcar)}] Marca: {nombre}  "
            f"({metros[0]:.2f}, {metros[1]:.2f}) m   (n=saltar, z=deshacer)"
        )


def dibujar_instruccion(img, texto):
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1], 40), (0, 0, 0), -1)
    cv2.putText(overlay, texto, (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return overlay


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campo",
        default="f11",
        help="Modelo de campo: f11 (por defecto) o f7. Ignorado si hay --config.",
    )
    parser.add_argument("--config", default=None, help="YAML con el campo y sus rutas.")
    parser.add_argument("--imagen", default=None)
    parser.add_argument("--salida", default=None)
    args = parser.parse_args()

    modelo = cargar_modelo(
        nombre=None if args.config else args.campo, config=args.config
    )
    rutas = _rutas_desde_config(args.config)
    ruta_imagen = args.imagen or rutas.get("imagen", IMAGEN)
    ruta_salida = args.salida or rutas.get("puntos", SALIDA)

    puntos_a_marcar = modelo.puntos_clicables()
    img = cv2.imread(ruta_imagen)
    if img is None:
        print(f"ERROR: no se encuentra {ruta_imagen}")
        return

    marcador = Marcador(puntos_a_marcar)
    cv2.namedWindow("Marcar puntos", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Marcar puntos", 1600, 700)
    cv2.setMouseCallback(
        "Marcar puntos",
        lambda evento, x, y, flags, param: (
            marcador.clic(x, y) if evento == cv2.EVENT_LBUTTONDOWN else None
        ),
    )

    print(
        f"\n=== CAMPO: {modelo.nombre} ({modelo.largo:.1f} x {modelo.ancho:.1f} m) ==="
    )
    print(
        f"Marcas del reglamento: área {modelo.marcas.area_ancho:.1f}x"
        f"{modelo.marcas.area_profundidad:.1f}, penalti {modelo.marcas.penalti:.1f}, "
        f"círculo r={modelo.marcas.circulo_radio:.1f}, "
        f"portería {modelo.marcas.porteria_ancho:.1f}"
    )
    print(f"Puntos a marcar: {len(puntos_a_marcar)}")
    for nombre, metros in puntos_a_marcar:
        print(f"   {nombre:<24} ({metros[0]:>6.2f}, {metros[1]:>6.2f}) m")
    print("\n=== INSTRUCCIONES ===")
    print("Clic = marcar el punto que pide arriba.")
    print("n = saltar este punto (si no se ve o no se distingue bien).")
    print("z = deshacer el último marcado.")
    print("s = guardar y salir.   q = salir sin guardar.")
    print("\nConsejo: salta los puntos del fondo lejano si no los ves con")
    print("claridad — un clic a ojo ahí contamina toda la calibración.\n")

    while True:
        vista = img.copy()
        for p in marcador.marcados:
            x, y = p["pixel"]
            cv2.circle(vista, (x, y), 6, (0, 0, 255), -1)
            cv2.putText(
                vista,
                p["nombre"],
                (x + 8, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                1,
            )
        cv2.imshow("Marcar puntos", dibujar_instruccion(vista, marcador.texto()))

        tecla = cv2.waitKey(20) & 0xFF
        if tecla == ord("n"):
            marcador.saltar()
        elif tecla == ord("z"):
            marcador.deshacer()
        elif tecla == ord("s"):
            Path(ruta_salida).parent.mkdir(parents=True, exist_ok=True)
            with open(ruta_salida, "w") as f:
                json.dump(marcador.marcados, f, indent=2)
            print(f"\n✓ Guardados {len(marcador.marcados)} puntos en {ruta_salida}")
            break
        elif tecla == ord("q"):
            print("\nSalido sin guardar.")
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
