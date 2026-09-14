"""Dónde hay que trocear la imagen para encontrar el balón del fondo.

El esquema de detección adoptado (`docs/sahi_balon.md`) es MIXTO: frame
entero en toda la imagen y tiles SOLO en una franja horizontal. La franja
existe porque con la cámara elevada la distancia se traduce en altura en
la imagen —la correlación entre `y` y el tamaño del balón es +0,924, es
perspectiva pura—, así que el balón pequeño vive en una banda estrecha y
trocear el resto es gastar GPU en césped donde no falla nadie.

⚠️ POR QUÉ ESTO NO PUEDE SER UN PAR DE NÚMEROS FIJOS. La primera versión
llevaba `BANDA_LEJOS = (540, 720)`, medido sobre la cámara del benjamín.
Es exactamente el tipo de número que NO viaja entre partidos, y ya nos ha
mordido dos veces (`arbitro.margen_equipo`, las franjas de profundidad).
Aquí además el fallo sería SILENCIOSO: una banda heredada de otro encuadre
trocearía césped vacío y dejaría el fondo sin trocear, y el informe diría
tan tranquilo que el esquema mixto no cierra huecos. Un negativo falso
sobre una idea buena es peor que no medirla.

⚠️ Y POR QUÉ NO SE DERIVA DEL TAMAÑO DEL BALÓN, que era lo primero que
parecía natural. Se probó: con el jacobiano de la homografía se predice el
diámetro en píxeles de un balón de 0,22 m, y **no reproduce lo medido**.
Predice 4,8 px donde el caché mide 10,7, y el sesgo ni siquiera es
constante (×2,2 arriba, ×1,6 abajo). La caja del detector no es el balón:
la inflan el desenfoque de movimiento y el tamaño mínimo práctico de caja.
Un umbral en píxeles derivado así estaría mal calibrado en cada cámara de
una forma distinta.

Lo que sí es geometría pura, sin ninguna constante empírica, es **qué
parte de la imagen ocupa una franja del CAMPO**. De ahí este módulo.
"""

import logging

import numpy as np

from src.tracking.plausibilidad_fisica import escalas_locales

logger = logging.getLogger(__name__)


def banda_a_trocear(
    homografia: np.ndarray,
    largo: float,
    ancho: float,
    zona_min: float,
    alto_imagen: int,
    ancho_imagen: int,
    margen_campo_m: float = 20.0,
    altura_aerea_m: float = 3.0,
) -> tuple[int, int]:
    """Franja (y0, y1) de la imagen que hay que trocear, en píxeles.

    Se construye proyectando a la imagen la franja de campo que va de
    `zona_min - margen_campo_m` hasta el fondo, y subiendo el borde
    superior lo que ocupa un balón a `altura_aerea_m` de altura.

    Los dos márgenes tienen sentido futbolístico, que es lo que hace que
    viajen a otra cámara:

    - **`margen_campo_m`**: durante un hueco el balón se mueve, y a veces
      viene HACIA la cámara. Medido sobre los 47 huecos del fondo del
      benjamín, tres se pierden a y≈600 y reaparecen a y=786, 761 y 755:
      con la franja pegada a `zona_min` esos tres quedan fuera. Con 20 m
      de margen entran los 47.
    - **`altura_aerea_m`**: un balón por el aire aparece MÁS ARRIBA en la
      imagen que su proyección de suelo. Tres metros es un despeje normal,
      y se convierte a píxeles con la escala local de la homografía en el
      borde de la banda, así que se adapta sola a la perspectiva de cada
      campo.

    Args:
        homografia: H de píxeles a metros (la del caché).
        largo, ancho: dimensiones del campo en metros.
        zona_min: metros desde los que el balón se considera "del fondo".
        alto_imagen, ancho_imagen: tamaño del frame, para recortar.
        margen_campo_m: cuánto campo se coge por delante de `zona_min`.
        altura_aerea_m: altura de balón que se cubre por arriba.

    Returns:
        (y0, y1) en píxeles, ya recortado a la imagen.
    """
    inversa = np.linalg.inv(homografia)

    def a_pixel(x_m, y_m):
        v = inversa @ np.array([x_m, y_m, 1.0])
        if abs(v[2]) < 1e-12:
            return np.nan, np.nan
        return v[0] / v[2], v[1] / v[2]

    x_desde = max(0.0, zona_min - margen_campo_m)
    filas = [
        a_pixel(x, y)[1]
        for x in np.linspace(x_desde, largo, 25)
        for y in np.linspace(0.0, ancho, 25)
    ]
    filas = [f for f in filas if np.isfinite(f)]
    if not filas:
        raise ValueError(
            "La homografía no proyecta el campo a la imagen: no se puede "
            "derivar la franja. ¿Es la homografía de este partido?"
        )
    y0, y1 = min(filas), max(filas)

    # Margen aéreo: cuántos píxeles ocupa `altura_aerea_m` justo en el
    # borde superior. La escala LATERAL (el menor valor singular del
    # jacobiano) es la que sirve para medir alturas.
    centro_u = ancho_imagen / 2.0
    lateral_m_por_px, _prof = escalas_locales(homografia, centro_u, float(y0))
    if np.isfinite(lateral_m_por_px) and lateral_m_por_px > 0:
        y0 -= altura_aerea_m / lateral_m_por_px

    y0 = int(max(0, np.floor(y0)))
    y1 = int(min(alto_imagen, np.ceil(y1)))
    if y1 - y0 < 2:
        raise ValueError(
            f"La franja derivada es degenerada ({y0}-{y1}). Revisa la "
            f"homografía y las dimensiones del campo."
        )
    # ⚠️ Si la franja se come casi toda la imagen, la derivación ha
    # fallado (homografía o medidas equivocadas) o la cámara es tan baja
    # que el fondo ocupa todo el encuadre. En los dos casos el esquema
    # mixto NO aplica, y devolver la imagen entera sería trocearlo todo
    # creyendo que se está ahorrando: el peor final posible, porque nadie
    # se enteraría hasta ver la factura de GPU.
    if (y1 - y0) > 0.8 * alto_imagen:
        raise ValueError(
            f"La franja derivada ocupa el {100 * (y1 - y0) / alto_imagen:.0f} % "
            f"del alto ({y0}-{y1}): el esquema mixto no ahorra nada aquí.\n"
            f"  O la homografía / las medidas del campo no son de este "
            f"partido, o la cámara está tan baja que el fondo ocupa todo el "
            f"encuadre.\n"
            f"  Comprueba la homografía; si es correcta, usa "
            f"`balon.esquema: sahi`."
        )
    logger.info(
        "Franja a trocear: y %d-%d (%.0f %% del alto), de x >= %.0f m con "
        "%.0f m de margen y %.0f m de aire.",
        y0,
        y1,
        100 * (y1 - y0) / alto_imagen,
        x_desde,
        margen_campo_m,
        altura_aerea_m,
    )
    return y0, y1
