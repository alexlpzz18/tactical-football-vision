"""Las marcas pintadas del campo no son el balón.

El esquema mixto presentó a la red, troceada y ampliada, la franja del
fondo — y con ella el punto central, el de penalti y una mancha junto al
muro. Tienen tamaño y color de balón, así que el detector dispara. Eran
**11.982 detecciones, el 56 % del caché** (`docs/balon_fantasma.md`).

⚠️ Estos tests vigilan las dos direcciones, que es la lección de la
semana: que el filtro QUITE las marcas, y que NO se lleve por delante el
balón de verdad. Un filtro que limpia demasiado es tan malo como uno que
no limpia.
"""

import numpy as np
import pytest

from src.balon.marcas_estaticas import (
    encontrar_marcas_estaticas,
    filtrar_marcas_estaticas,
)
from src.balon.tracking_balon import ParametrosBalon, seleccionar_balon_activo

FPS, SAMPLE = 29.97, 2


def _det(px, py, lado=10.0, conf=0.6, mx=30.0, my=20.0):
    """(mx, my, x1, y1, x2, y2, conf) centrada en el píxel (px, py)."""
    return (mx, my, px - lado / 2, py - lado / 2, px + lado / 2, py + lado / 2, conf)


def _marca_fija(n=400, px=372.0, py=628.0, desde=0, paso=30):
    """Una marca: siempre en el mismo píxel, a lo largo de todo el partido."""
    dets, tiempos = {}, {}
    for i in range(n):
        f = desde + i * paso
        dets[f] = [_det(px + np.sin(i) * 0.4, py + np.cos(i) * 0.4)]
        tiempos[f] = f / FPS
    return dets, tiempos


def _balon_en_juego(n=400, desde=1, paso=30):
    """Un balón que recorre el campo: cada detección en otro sitio."""
    dets, tiempos = {}, {}
    for i in range(n):
        f = desde + i * paso
        dets[f] = [_det(200 + (i * 37) % 1500, 400 + (i * 53) % 500)]
        tiempos[f] = f / FPS
    return dets, tiempos


# ─────────────────────────── quita lo que debe ────────────────────────────


def test_encuentra_una_marca_fija():
    """⚠️ Se comprueba que la ENCUENTRA, no cuántas celdas ocupa: un objeto
    sobre el borde de la rejilla cae en dos celdas, y en los datos reales
    pasa igual (las celdas 360 y 372 son la misma mancha). El recuento de
    celdas es una cota superior del número de objetos, no el número."""
    dets, tiempos = _marca_fija()
    marcas = encontrar_marcas_estaticas(dets, tiempos)
    assert marcas, "no ha visto la marca fija"


def test_el_filtro_deja_el_cache_vacio_si_solo_habia_una_marca():
    dets, tiempos = _marca_fija()
    limpio, marcas = filtrar_marcas_estaticas(dets, tiempos)
    assert limpio == {}, "ha dejado detecciones de una marca fija"
    assert marcas


# ──────────────── y NO se lleva por delante el balón bueno ────────────────


def test_no_toca_un_balon_que_recorre_el_campo():
    dets, tiempos = _balon_en_juego()
    limpio, marcas = filtrar_marcas_estaticas(dets, tiempos)
    assert marcas == set(), "ha marcado como fijo un balón en movimiento"
    assert len(limpio) == len(dets)


def test_separa_la_marca_del_balon_cuando_conviven():
    """El caso real: la marca y el balón en el mismo caché."""
    marca, t1 = _marca_fija()
    balon, t2 = _balon_en_juego()
    dets = {**marca, **balon}
    tiempos = {**t1, **t2}

    limpio, marcas = filtrar_marcas_estaticas(dets, tiempos)

    assert marcas, "no ha visto la marca"
    assert len(limpio) == len(balon), "se ha llevado detecciones del balón"
    assert set(limpio) == set(balon)


def test_un_balon_parado_UN_RATO_no_es_una_marca():
    """Una falta, un saque: el balón está quieto segundos, no minutos.

    Es el falso positivo que hay que evitar, y el motivo de exigir
    duración además de repetición."""
    dets, tiempos = {}, {}
    for i in range(60):  # 60 muestras seguidas = 4 s en el mismo sitio
        f = i * SAMPLE
        dets[f] = [_det(800.0, 500.0)]
        tiempos[f] = f / FPS
    marcas = encontrar_marcas_estaticas(dets, tiempos)
    assert marcas == set(), "ha confundido un balón parado en una falta con una marca"


def test_pocas_detecciones_repetidas_no_bastan():
    """El umbral de recuento existe porque el balón pasa por todas partes."""
    dets, tiempos = _marca_fija(n=40)  # pocas, aunque duren mucho
    assert encontrar_marcas_estaticas(dets, tiempos) == set()


# ───────────── la guarda de distancia: ahora PUEDE dispararse ─────────────


def test_la_guarda_de_distancia_puede_dispararse():
    """La que estaba en 25 m NO podía: el máximo observado en la parte
    entera fue 25,7 m y el p99, 17,2. Existía sin poder actuar nunca.

    Este test es el que faltaba: no comprueba el valor, comprueba que con
    datos plausibles la guarda LLEGA a descartar algo."""
    params = ParametrosBalon()
    assert params.dist_max_jugadores <= 17.0, (
        f"dist_max_jugadores = {params.dist_max_jugadores} m está por encima "
        f"del p99 medido (17,2 m): la guarda no podrá dispararse"
    )

    # un balón quieto en una esquina, con los jugadores en la otra punta
    dets, jugadores = {}, {}
    for i in range(30):
        f = i * SAMPLE
        dets[f] = [_det(100.0, 100.0, mx=2.0, my=2.0)]
        jugadores[f] = [(40.0, 20.0), (42.0, 22.0), (38.0, 18.0)]

    activo = seleccionar_balon_activo(dets, jugadores, params)
    assert activo == {}, "la guarda no ha descartado un balón quieto y lejísimos"


def test_la_guarda_no_descarta_un_balon_quieto_JUNTO_a_un_jugador():
    """La segunda condición existe para esto: un saque de banda."""
    dets, jugadores = {}, {}
    for i in range(30):
        f = i * SAMPLE
        dets[f] = [_det(100.0, 100.0, mx=30.0, my=20.0)]
        jugadores[f] = [(30.5, 20.5), (35.0, 25.0)]

    activo = seleccionar_balon_activo(dets, jugadores, ParametrosBalon())
    assert len(activo) == len(dets), "ha matado un balón parado en un saque"


@pytest.mark.parametrize("ancho,esperado", [(40.0, 10.0), (64.0, 16.0)])
def test_la_fraccion_del_campo_da_el_umbral_de_cada_campo(ancho, esperado):
    """Lo que hace que el número viaje a otro partido."""
    p = ParametrosBalon()
    assert p.fraccion_ancho_campo * ancho == pytest.approx(esperado)
