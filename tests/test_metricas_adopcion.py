import pytest

from src.balon.metricas_adopcion import duracion_maxima_anclada, fraccion_en_marcas


def test_fraccion_en_marcas_vacia_da_cero():
    assert fraccion_en_marcas([], {(0, 0)}) == 0.0


def test_fraccion_en_marcas_cuenta_solo_las_celdas_de_marca():
    marcas = {(5, 5)}
    trayectoria = [
        (0, (12 * 5 + 1, 12 * 5 + 1)),  # celda (5,5): marca
        (1, (12 * 5 + 1, 12 * 5 + 1)),  # celda (5,5): marca
        (2, (0, 0)),  # celda (0,0): no es marca
        (3, (0, 0)),  # celda (0,0): no es marca
    ]
    assert fraccion_en_marcas(trayectoria, marcas) == pytest.approx(0.5)


def test_fraccion_en_marcas_sin_marcas_conocidas_da_cero():
    trayectoria = [(0, (60, 60))]
    assert fraccion_en_marcas(trayectoria, set()) == 0.0


def test_duracion_maxima_anclada_vacia_da_cero():
    assert duracion_maxima_anclada([], {}) == 0.0


def test_un_balon_parado_mucho_tiempo_da_toda_la_duracion():
    tiempos = {f: f * 0.1 for f in range(50)}
    trayectoria = [(f, (10.0, 10.0)) for f in range(50)]
    dur = duracion_maxima_anclada(trayectoria, tiempos, radio_m=1.0)
    assert dur == pytest.approx(4.9, abs=0.01)


def test_un_balon_que_se_mueve_corta_el_tramo():
    tiempos = {f: f * 0.1 for f in range(20)}
    # Quieto 10 frames, luego se va lejos y se queda quieto otros 10.
    trayectoria = [(f, (10.0, 10.0)) for f in range(10)] + [
        (f, (50.0, 50.0)) for f in range(10, 20)
    ]
    dur = duracion_maxima_anclada(trayectoria, tiempos, radio_m=1.0)
    # Cada tramo dura 9 pasos de 0.1s = 0.9s, no los 1.9s del total.
    assert dur == pytest.approx(0.9, abs=0.01)


def test_un_hueco_largo_corta_el_tramo_aunque_no_se_mueva():
    tiempos = {0: 0.0, 1: 0.1, 2: 5.0, 3: 5.1}
    trayectoria = [
        (0, (10.0, 10.0)),
        (1, (10.0, 10.0)),
        (2, (10.0, 10.0)),
        (3, (10.0, 10.0)),
    ]
    dur = duracion_maxima_anclada(trayectoria, tiempos, radio_m=1.0, max_hueco_s=1.0)
    assert dur == pytest.approx(0.1, abs=0.01)


def test_un_balon_en_juego_normal_da_una_duracion_corta():
    # Recorre 1 m por paso: nunca se queda dentro del radio más de 2 pasos.
    tiempos = {f: f * 0.1 for f in range(30)}
    trayectoria = [(f, (float(f), 0.0)) for f in range(30)]
    dur = duracion_maxima_anclada(trayectoria, tiempos, radio_m=1.0)
    assert dur < 0.5
