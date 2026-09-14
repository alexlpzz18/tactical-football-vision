"""El comparador de esquemas de detección no puede mentir sobre sí mismo.

Es una herramienta de DIAGNÓSTICO, y en este proyecto ya nos han mentido
cinco: el "✓" de un caché vacío, el tick del balón, el `tail` que se comió
un crash de OpenCV, la pizarra pintando la moda, y un proxy que recuperó
los recortes equivocados.

El fallo concreto que vigilan estos tests: el esquema MIXTO trocea una
franja recortada de la imagen, así que sus cajas salen en coordenadas de
la franja. Si no se les suma el `y0`, caen decenas de metros fuera del
campo, el filtro de plausibilidad las tira, y el informe diría
tranquilamente que el esquema mixto cierra 0 huecos. Un negativo falso
sobre una idea buena es peor que no medirla.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_ruta = Path(__file__).resolve().parent.parent / "scripts" / "detectar_balon.py"
_spec = importlib.util.spec_from_file_location("detectar_balon", _ruta)
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)

ANCHO, ALTO = 1920, 1080
CB = {"confianza": 0.35, "imgsz": 1280}
# La franja ya no es una constante del módulo: la deriva
# `banda_a_trocear` de la homografía. Aquí se fija una para poder
# probar el desplazamiento de coordenadas sin depender de datos.
BANDA = (540, 720)


class _DetectorFalso:
    """Sustituye a YOLO: devuelve las cajas que se le digan."""

    def __init__(self, cajas_entero=(), cajas_franja=()):
        self.cajas_entero = list(cajas_entero)
        self.cajas_franja = list(cajas_franja)
        self.altos_vistos = []


@pytest.fixture
def parcheado(monkeypatch):
    falso = _DetectorFalso()

    def entero(_modelo, frame, _conf, _imgsz):
        falso.altos_vistos.append(frame.shape[0])
        return list(falso.cajas_entero)

    def sahi(_modelo_sahi, frame, _cfg, _w, _h):
        falso.altos_vistos.append(frame.shape[0])
        return list(falso.cajas_franja)

    monkeypatch.setattr(db, "_detectar_frame_entero", entero)
    monkeypatch.setattr(db, "_detectar_sahi", sahi)
    return falso


def _frame():
    return np.zeros((ALTO, ANCHO, 3), dtype=np.uint8)


# ───────────────────────── el desplazamiento de la franja ─────────────────


def test_el_mixto_devuelve_la_franja_en_coordenadas_de_la_IMAGEN(parcheado):
    """Una caja a y=80 DENTRO de la franja está a y=620 en la imagen."""
    y0, _y1 = BANDA
    parcheado.cajas_franja = [(1000.0, 80.0, 1010.0, 90.0, 0.7)]

    cajas = db._detectar_con_esquema(
        {"modo": "mixto", "columnas": 5, "solape": 0.15},
        None,
        None,
        _frame(),
        CB,
        ANCHO,
        ALTO,
        BANDA,
    )

    assert len(cajas) == 1
    assert cajas[0][1] == pytest.approx(80.0 + y0), (
        "la caja de la franja NO se ha subido a coordenadas de la imagen: "
        "el filtro de plausibilidad la tirará y el informe dirá que el "
        "esquema mixto no cierra huecos"
    )
    assert cajas[0][3] == pytest.approx(90.0 + y0)


def test_el_mixto_trocea_solo_la_franja_no_el_frame_entero(parcheado):
    """Si troceara la imagen completa no ahorraría nada de coste."""
    y0, y1 = BANDA
    db._detectar_con_esquema(
        {"modo": "mixto", "columnas": 5, "solape": 0.15},
        None,
        None,
        _frame(),
        CB,
        ANCHO,
        ALTO,
        BANDA,
    )

    assert y1 - y0 in parcheado.altos_vistos, "no ha troceado la franja"
    assert parcheado.altos_vistos.count(ALTO) == 1, "debe ver la imagen entera UNA vez"


def test_el_mixto_no_cuenta_el_mismo_balon_dos_veces(parcheado):
    """El recuento de candidatos por frame es justo lo que Alex vigila."""
    y0, _ = BANDA
    parcheado.cajas_entero = [(1000.0, y0 + 80.0, 1010.0, y0 + 90.0, 0.6)]
    parcheado.cajas_franja = [(1001.0, 81.0, 1011.0, 91.0, 0.7)]  # el mismo

    cajas = db._detectar_con_esquema(
        {"modo": "mixto", "columnas": 5, "solape": 0.15},
        None,
        None,
        _frame(),
        CB,
        ANCHO,
        ALTO,
        BANDA,
    )

    assert len(cajas) == 1, "el mismo balón contado dos veces infla los candidatos"


def test_el_mixto_si_suma_un_balon_que_el_frame_entero_no_ve(parcheado):
    """Que deduplique no puede significar que se coma los hallazgos."""
    parcheado.cajas_entero = [(200.0, 900.0, 230.0, 930.0, 0.6)]  # otro sitio
    parcheado.cajas_franja = [(1000.0, 80.0, 1010.0, 90.0, 0.7)]

    cajas = db._detectar_con_esquema(
        {"modo": "mixto", "columnas": 5, "solape": 0.15},
        None,
        None,
        _frame(),
        CB,
        ANCHO,
        ALTO,
        BANDA,
    )

    assert len(cajas) == 2


# ───────────────────────────── la banda ───────────────────────────────────


def test_la_banda_ya_no_es_una_constante_del_script():
    """La franja fija (540-720) era el número que no viajaba entre
    cámaras. Si alguien la vuelve a escribir a mano, esto falla."""
    assert not hasattr(db, "BANDA_LEJOS"), (
        "ha vuelto una franja fija al script; tiene que derivarse con "
        "src.balon.franja_lejana.banda_a_trocear"
    )
    assert (
        "banda" in db._detectar_con_esquema.__code__.co_varnames
    ), "el esquema mixto ya no recibe la franja por parámetro"


def test_los_esquemas_son_distintos_entre_si():
    """Un barrido cuyos puntos son iguales no mide nada."""
    firmas = {tuple(sorted(e.items())) for _n, e in db.ESQUEMAS}
    assert len(firmas) == len(db.ESQUEMAS), "hay dos esquemas idénticos"


# ───────────────────────────── el solape ──────────────────────────────────


def test_solapan_distingue_la_misma_caja_de_dos_distintas():
    a = (100.0, 100.0, 110.0, 110.0)
    assert db._solapan(a, (101.0, 101.0, 111.0, 111.0))
    assert not db._solapan(a, (400.0, 400.0, 410.0, 410.0))
    assert not db._solapan(a, (108.0, 108.0, 118.0, 118.0)), "roce no es la misma caja"
