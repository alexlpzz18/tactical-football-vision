"""Tests del modelo de campo parametrizable (F11 / F7) y su calibración.

Lo crítico aquí es doble: que el F7 salga con las medidas del reglamento
de Madrid, y que el F11 de Villaviciosa NO cambie ni un decimal — su
homografía está calibrada contra esos puntos exactos.
"""

import json

import numpy as np
import pytest

from src.campo_modelo import (
    MARCAS_F7,
    MARCAS_F11,
    MODELO_F7,
    MODELO_F11,
    cargar_modelo,
)
from src.homography.calcular_homografia import (
    calcular_homografia,
    error_reproyeccion,
)

# Los 15 puntos que la herramienta pedía cuando estaban hardcodeados para
# el F11. La homografía de Villaviciosa se calibró con estas coordenadas.
PUNTOS_F11_LEGADO = {
    "center": (50.0, 32.0),
    "circulo_top": (50.0, 41.15),
    "circulo_bottom": (50.0, 22.85),
    "halfway_top": (50.0, 64.0),
    "halfway_bottom": (50.0, 0.0),
    "box_left_top": (16.5, 52.16),
    "box_left_bottom": (16.5, 11.84),
    "box_right_top": (83.5, 52.16),
    "box_right_bottom": (83.5, 11.84),
    "penalty_left": (11.0, 32.0),
    "penalty_right": (89.0, 32.0),
    "corner_top_left": (0.0, 64.0),
    "corner_bottom_left": (0.0, 0.0),
    "corner_top_right": (100.0, 64.0),
    "corner_bottom_right": (100.0, 0.0),
}


# ── el F11 no se toca ─────────────────────────────────────────────────


def test_f11_reproduce_exactamente_los_puntos_historicos():
    """Cada punto del F11 sale con la MISMA coordenada de siempre."""
    generados = dict(MODELO_F11.puntos_clicables())
    for nombre, (x, y) in PUNTOS_F11_LEGADO.items():
        assert nombre in generados, f"falta el punto histórico {nombre}"
        assert generados[nombre] == pytest.approx((x, y), abs=1e-9), nombre


def test_f11_conserva_dimensiones_y_marcas():
    assert (MODELO_F11.largo, MODELO_F11.ancho) == (100.0, 64.0)
    assert MODELO_F11.marcas is MARCAS_F11
    assert MARCAS_F11.penalti == 11.0
    assert MARCAS_F11.circulo_radio == 9.15
    assert MARCAS_F11.area_ancho == 40.32


def test_el_json_de_villaviciosa_sigue_encajando_en_el_modelo():
    """Los clics guardados coinciden con lo que el modelo pide hoy."""
    with open("data/calibracion/puntos_marcados.json") as f:
        guardados = json.load(f)
    generados = dict(MODELO_F11.puntos_clicables())
    for punto in guardados:
        assert punto["nombre"] in generados
        assert generados[punto["nombre"]] == pytest.approx(
            tuple(punto["metros"]), abs=1e-6
        ), punto["nombre"]


# ── modelo F7 ─────────────────────────────────────────────────────────


def test_f7_usa_el_reglamento_de_madrid():
    assert MARCAS_F7.area_ancho == 26.0
    assert MARCAS_F7.area_profundidad == 12.0
    assert MARCAS_F7.penalti == 9.0
    assert MARCAS_F7.circulo_radio == 6.0
    assert MARCAS_F7.porteria_ancho == 6.0
    assert (MODELO_F7.largo, MODELO_F7.ancho) == (62.0, 40.0)


def test_f7_genera_las_familias_de_puntos_del_encargo():
    """Esquinas, cortes de área con fondo, esquinas interiores, penaltis,
    círculo (4), centro y medios de banda."""
    p = dict(MODELO_F7.puntos_clicables())
    # Esquinas
    assert p["corner_bottom_left"] == (0.0, 0.0)
    assert p["corner_top_right"] == (62.0, 40.0)
    # Cortes del área con la línea de fondo (26 m de ancho → 20±13)
    assert p["box_left_top_line"] == (0.0, 33.0)
    assert p["box_left_bottom_line"] == (0.0, 7.0)
    # Esquinas interiores del área (12 m de profundidad)
    assert p["box_left_top"] == (12.0, 33.0)
    assert p["box_right_bottom"] == (50.0, 7.0)
    # Penaltis a 9 m de cada fondo
    assert p["penalty_left"] == (9.0, 20.0)
    assert p["penalty_right"] == (53.0, 20.0)
    # Círculo con 4 puntos, radio 6
    assert p["circulo_top"] == (31.0, 26.0)
    assert p["circulo_left"] == (25.0, 20.0)
    # Centro y medios de banda
    assert p["center"] == (31.0, 20.0)
    assert p["halfway_bottom"] == (31.0, 0.0)
    # Portería de 6 m
    assert p["goal_left_top"] == (0.0, 23.0)
    assert p["goal_left_bottom"] == (0.0, 17.0)


def test_las_marcas_no_dependen_del_tamano_del_campo():
    """Cambiar largo/ancho mueve el marco pero no las medidas de reglamento."""
    grande = MODELO_F7.con_dimensiones(70.0, 46.0)
    p = dict(grande.puntos_clicables())
    assert p["penalty_left"][0] == 9.0  # sigue a 9 m del fondo
    assert p["box_left_top"][0] == 12.0  # el área sigue entrando 12 m
    ancho_area = p["box_left_top"][1] - p["box_left_bottom"][1]
    assert ancho_area == pytest.approx(26.0)
    diametro = p["circulo_top"][1] - p["circulo_bottom"][1]
    assert diametro == pytest.approx(12.0)
    # pero el campo sí crece
    assert p["corner_top_right"] == (70.0, 46.0)


# ── carga desde config ────────────────────────────────────────────────


def test_cargar_modelo_por_nombre():
    assert cargar_modelo("f7") is MODELO_F7
    assert cargar_modelo("f11") is MODELO_F11
    with pytest.raises(ValueError, match="desconocido"):
        cargar_modelo("f5")


def test_cargar_modelo_desde_config_del_benja():
    modelo = cargar_modelo(config="configs/campo_benja.yaml")
    assert modelo.nombre == "benjamines"
    assert (modelo.largo, modelo.ancho) == (62.0, 40.0)
    assert modelo.marcas == MARCAS_F7  # hereda el reglamento F7


def test_config_puede_ajustar_medidas_y_marcas(tmp_path):
    ruta = tmp_path / "campo.yaml"
    ruta.write_text(
        "campo:\n  nombre: raro\n  tipo: f7\n  largo: 55.0\n  ancho: 35.0\n"
        "  marcas:\n    area_ancho: 22.0\n"
    )
    modelo = cargar_modelo(config=ruta)
    assert (modelo.largo, modelo.ancho) == (55.0, 35.0)
    assert modelo.marcas.area_ancho == 22.0  # sobrescrito
    assert modelo.marcas.penalti == 9.0  # el resto sigue siendo F7


# ── geometría de dibujo ───────────────────────────────────────────────


def test_lineas_y_circulo_dentro_del_campo():
    for modelo in (MODELO_F11, MODELO_F7):
        for p1, p2 in modelo.lineas():
            for x, y in (p1, p2):
                assert -1e-9 <= x <= modelo.largo + 1e-9
                assert -1e-9 <= y <= modelo.ancho + 1e-9
        puntos = np.array(modelo.circulo(20))
        centro = np.array(modelo.centro)
        radios = np.linalg.norm(puntos - centro, axis=1)
        assert radios == pytest.approx(modelo.marcas.circulo_radio, abs=1e-6)


# ── homografía sobre el modelo ────────────────────────────────────────


def _camara_sintetica(modelo, altura=3.0, retroceso=12.0):
    """Cámara BAJA detrás de la portería izquierda mirando al campo.

    Devuelve una función metros→píxel con un modelo pinhole simple: es la
    geometría del caso benjamín (cámara normal tras portería), con el eje
    largo alejándose del objetivo.
    """

    def proyectar(x_m, y_m):
        # Cámara en (-retroceso, ancho/2, altura) mirando a +x
        dx = x_m + retroceso  # profundidad desde la cámara
        dy = y_m - modelo.ancho / 2  # lateral
        f = 1200.0
        u = 1280 + f * dy / dx
        v = 540 + f * altura / dx
        return u, v

    return proyectar


def test_homografia_recupera_el_modelo_con_camara_tras_porteria():
    """Chain completo con datos sintéticos: puntos → H → error < 1 cm."""
    modelo = MODELO_F7
    proyectar = _camara_sintetica(modelo)
    puntos = [
        {"nombre": n, "pixel": list(proyectar(x, y)), "metros": [x, y]}
        for n, (x, y) in modelo.puntos_clicables()
    ]
    H, mask = calcular_homografia(puntos)
    assert int(mask.sum()) == len(puntos)  # sin clics ruidosos, todos valen
    errores = error_reproyeccion(puntos, H)
    assert errores.max() < 0.01


def test_homografia_falla_claro_con_pocos_puntos():
    with pytest.raises(ValueError, match="al menos 4 puntos"):
        calcular_homografia([{"pixel": [0, 0], "metros": [0.0, 0.0]}])


def test_el_error_metrico_crece_con_la_profundidad():
    """Física del caso: cámara baja tras portería → el fondo se comprime.

    Con 1 píxel de error de caja, los metros de error en la mitad lejana
    son MUCHO mayores que cerca de la cámara. No es un fallo: es la
    proyección, y por eso los umbrales por profundidad hay que
    recalibrarlos para este campo.
    """
    modelo = MODELO_F7
    proyectar = _camara_sintetica(modelo)
    puntos = [
        {"nombre": n, "pixel": list(proyectar(x, y)), "metros": [x, y]}
        for n, (x, y) in modelo.puntos_clicables()
    ]
    H, _ = calcular_homografia(puntos)

    import cv2

    def metros_por_pixel(x_m):
        u, v = proyectar(x_m, modelo.ancho / 2)
        par = np.array([[[u, v]], [[u, v + 1.0]]], dtype=np.float64)
        met = cv2.perspectiveTransform(par, H).reshape(2, 2)
        return float(np.linalg.norm(met[1] - met[0]))

    cerca = metros_por_pixel(modelo.largo * 0.1)
    lejos = metros_por_pixel(modelo.largo * 0.9)
    assert lejos > cerca * 5, (cerca, lejos)
