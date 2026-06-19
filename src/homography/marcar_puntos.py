"""
Herramienta de clic para marcar puntos del campo sobre una imagen.
Marca cada punto en orden; permite saltar los que no se vean y deshacer.
Guarda las coordenadas exactas (píxeles) en un JSON.
"""

import cv2
import json

IMAGEN = "data/calibracion/frame_corregido.png"
SALIDA = "data/calibracion/puntos_marcados.json"

# Puntos a marcar, en orden, con su coordenada real en metros.
# El círculo central tiene radio 9.15m; cruza la línea de medio campo
# en (50, 32+9.15)=(50, 41.15) arriba y (50, 32-9.15)=(50, 22.85) abajo.
PUNTOS_A_MARCAR = [
    ("center", (50.0, 32.0)),
    ("circulo_top", (50.0, 41.15)),  # corte círculo con medio campo (arriba)
    ("circulo_bottom", (50.0, 22.85)),  # corte círculo con medio campo (abajo)
    ("halfway_top", (50.0, 64.0)),  # medio campo toca banda de arriba
    ("halfway_bottom", (50.0, 0.0)),  # medio campo toca banda de abajo
    ("box_left_top", (16.5, 52.16)),
    ("box_left_bottom", (16.5, 11.84)),
    ("box_right_top", (83.5, 52.16)),
    ("box_right_bottom", (83.5, 11.84)),
    ("penalty_left", (11.0, 32.0)),
    ("penalty_right", (89.0, 32.0)),
    ("corner_top_left", (0.0, 64.0)),
    ("corner_bottom_left", (0.0, 0.0)),
    ("corner_top_right", (100.0, 64.0)),
    ("corner_bottom_right", (100.0, 0.0)),
]

puntos_marcados = []
idx_actual = 0


def dibujar_instruccion(img):
    overlay = img.copy()
    if idx_actual < len(PUNTOS_A_MARCAR):
        nombre, metros = PUNTOS_A_MARCAR[idx_actual]
        texto = (
            f"[{idx_actual+1}/{len(PUNTOS_A_MARCAR)}] Marca: {nombre}  "
            f"{metros}m   (n=saltar, z=deshacer)"
        )
    else:
        texto = "TERMINADO - pulsa 's' para guardar, 'q' para salir"
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1], 40), (0, 0, 0), -1)
    cv2.putText(overlay, texto, (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return overlay


def callback(event, x, y, flags, param):
    global idx_actual
    if event == cv2.EVENT_LBUTTONDOWN and idx_actual < len(PUNTOS_A_MARCAR):
        nombre, metros = PUNTOS_A_MARCAR[idx_actual]
        puntos_marcados.append(
            {
                "nombre": nombre,
                "pixel": [x, y],
                "metros": list(metros),
            }
        )
        print(f"  ✓ {nombre}: pixel ({x}, {y}) -> metros {metros}")
        idx_actual += 1


def main():
    global idx_actual
    img = cv2.imread(IMAGEN)
    if img is None:
        print(f"ERROR: no se encuentra {IMAGEN}")
        return

    cv2.namedWindow("Marcar puntos", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Marcar puntos", 1600, 700)
    cv2.setMouseCallback("Marcar puntos", callback)

    print("\n=== INSTRUCCIONES ===")
    print("Clic = marcar el punto que pide arriba.")
    print("n = saltar este punto (si no se ve).")
    print("z = deshacer el último marcado.")
    print("s = guardar y salir.   q = salir sin guardar.\n")

    while True:
        vista = img.copy()
        for i, p in enumerate(puntos_marcados):
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
        vista = dibujar_instruccion(vista)
        cv2.imshow("Marcar puntos", vista)

        tecla = cv2.waitKey(20) & 0xFF
        if tecla == ord("n") and idx_actual < len(PUNTOS_A_MARCAR):  # saltar
            nombre = PUNTOS_A_MARCAR[idx_actual][0]
            print(f"  ⤳ saltado: {nombre}")
            idx_actual += 1
        elif tecla == ord("z") and puntos_marcados:  # deshacer
            quitado = puntos_marcados.pop()
            # retrocede al índice del punto deshecho
            idx_actual = PUNTOS_A_MARCAR.index(
                next(p for p in PUNTOS_A_MARCAR if p[0] == quitado["nombre"])
            )
            print(f"  ↶ deshecho: {quitado['nombre']}")
        elif tecla == ord("s"):  # guardar
            with open(SALIDA, "w") as f:
                json.dump(puntos_marcados, f, indent=2)
            print(f"\n✓ Guardados {len(puntos_marcados)} puntos en {SALIDA}")
            break
        elif tecla == ord("q"):  # salir
            print("\nSalido sin guardar.")
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
