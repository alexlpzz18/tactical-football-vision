"""
Modelo geométrico del campo de fútbol 11.
Define las coordenadas reales (en metros) de cada punto clave del campo,
usando las medidas reglamentarias oficiales (IFAB / RFEF).

Sistema de coordenadas:
  - Origen (0, 0) en la esquina inferior izquierda del campo.
  - Eje X a lo largo del campo (línea de banda), de 0 a LARGO.
  - Eje Y a lo ancho del campo (línea de meta), de 0 a ANCHO.
"""

# ── Dimensiones totales del campo (las que varían entre campos) ──
FIELD_LENGTH = 100.0  # largo en metros (estimación campo municipal)
FIELD_WIDTH = 64.0  # ancho en metros

# ── Medidas reglamentarias fijas (iguales en todos los campos F11) ──
BOX_LENGTH = 16.5  # profundidad del área grande
BOX_WIDTH = 40.32  # ancho del área grande
SMALL_BOX_LENGTH = 5.5  # profundidad del área pequeña
SMALL_BOX_WIDTH = 18.32  # ancho del área pequeña (5.5 + 7.32 + 5.5)
GOAL_WIDTH = 7.32  # ancho de la portería
PENALTY_DIST = 11.0  # distancia del punto de penalti a la línea de meta
CENTER_RADIUS = 9.15  # radio del círculo central


def get_field_points():
    """
    Devuelve un diccionario con las coordenadas reales (en metros)
    de los puntos clave del campo.

    Returns:
        dict: nombre del punto -> (x, y) en metros
    """
    cx = FIELD_LENGTH / 2  # centro del campo en X (50)
    cy = FIELD_WIDTH / 2  # centro del campo en Y (32)

    points = {
        # Esquinas del campo
        "corner_bottom_left": (0.0, 0.0),
        "corner_top_left": (0.0, FIELD_WIDTH),
        "corner_bottom_right": (FIELD_LENGTH, 0.0),
        "corner_top_right": (FIELD_LENGTH, FIELD_WIDTH),
        # Centro del campo
        "center": (cx, cy),
        # Línea de medio campo (donde corta las bandas)
        "halfway_bottom": (cx, 0.0),
        "halfway_top": (cx, FIELD_WIDTH),
        # Área grande IZQUIERDA (las dos esquinas que se adentran en el campo)
        "box_left_top": (BOX_LENGTH, cy + BOX_WIDTH / 2),
        "box_left_bottom": (BOX_LENGTH, cy - BOX_WIDTH / 2),
        # Área grande DERECHA
        "box_right_top": (FIELD_LENGTH - BOX_LENGTH, cy + BOX_WIDTH / 2),
        "box_right_bottom": (FIELD_LENGTH - BOX_LENGTH, cy - BOX_WIDTH / 2),
        # Puntos de penalti
        "penalty_left": (PENALTY_DIST, cy),
        "penalty_right": (FIELD_LENGTH - PENALTY_DIST, cy),
    }
    return points


if __name__ == "__main__":
    # Pequeña comprobación: imprimir todos los puntos
    pts = get_field_points()
    print(f"Campo de {FIELD_LENGTH}m x {FIELD_WIDTH}m")
    print(f"Total de puntos definidos: {len(pts)}\n")
    for name, (x, y) in pts.items():
        print(f"  {name:25s} -> ({x:.2f}, {y:.2f})")
