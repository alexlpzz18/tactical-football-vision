"""Tests del diagnóstico de calibración (`src/homography/diagnostico.py`).

El caso que motiva el módulo: dos clics del benjamín cayeron en el filo de
la imagen y nadie se enteró. Aquí se comprueba que ahora se cazan, y que la
estabilidad ordena las zonas del campo como la geometría manda.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from src.homography.diagnostico import clics_en_el_borde, estabilidad

PUNTOS_BENJA = Path("data/calibracion_benja/puntos_marcados_benja.json")


def _rejilla(paso_x: int = 8) -> list[dict]:
    """Calibración sintética limpia: una rejilla con identidad píxel↔metro."""
    return [
        {"nombre": f"p{x}_{y}", "pixel": [x * 10.0, y * 10.0], "metros": [x, y]}
        for x in range(0, 40, paso_x)
        for y in range(0, 40, paso_x)
    ]


class TestClicsEnElBorde:
    def test_una_rejilla_interior_no_tiene_ninguno(self):
        puntos = [
            {"nombre": "centro", "pixel": [960, 540], "metros": [31, 20]},
            {"nombre": "otro", "pixel": [500, 300], "metros": [10, 10]},
        ]
        assert clics_en_el_borde(puntos, 1920, 1080) == []

    @pytest.mark.parametrize(
        "pixel", [[0, 500], [1919, 500], [960, 0], [960, 1079], [1, 1]]
    )
    def test_caza_los_cuatro_filos(self, pixel):
        puntos = [{"nombre": "sospechoso", "pixel": pixel, "metros": [12, 33]}]
        assert len(clics_en_el_borde(puntos, 1920, 1080)) == 1

    def test_un_punto_a_diez_pixeles_del_filo_no_es_sospechoso(self):
        puntos = [{"nombre": "cerca", "pixel": [10, 500], "metros": [12, 33]}]
        assert clics_en_el_borde(puntos, 1920, 1080) == []

    def test_el_margen_es_un_parametro_y_manda(self):
        puntos = [{"nombre": "cerca", "pixel": [10, 500], "metros": [12, 33]}]
        assert clics_en_el_borde(puntos, 1920, 1080, margen_px=20.0) != []

    @pytest.mark.skipif(not PUNTOS_BENJA.exists(), reason="sin datos del benjamín")
    def test_caza_los_dos_clics_reales_del_benjamin(self):
        """El caso real: box_left_top (x=0) y box_left_bottom (x=1919)."""
        puntos = json.loads(PUNTOS_BENJA.read_text())
        nombres = {p["nombre"] for p in clics_en_el_borde(puntos, 1920, 1080)}
        assert nombres == {"box_left_top", "box_left_bottom"}


class TestEstabilidad:
    def test_sin_ruido_no_se_mueve_nada(self):
        valores = estabilidad(
            _rejilla(), [(10.0, 10.0), (30.0, 30.0)], ruido_px=0.0, repeticiones=5
        )
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in valores)

    def test_devuelve_un_valor_por_consulta(self):
        consultas = [(5.0, 5.0), (15.0, 15.0), (25.0, 25.0)]
        assert len(estabilidad(_rejilla(), consultas, repeticiones=20)) == 3

    def test_mas_ruido_de_clic_da_mas_desplazamiento(self):
        """Control de que la medida RESPONDE: si no, no está midiendo nada."""
        consulta = [(20.0, 20.0)]
        poco = estabilidad(_rejilla(), consulta, ruido_px=1.0, repeticiones=120)[0]
        mucho = estabilidad(_rejilla(), consulta, ruido_px=6.0, repeticiones=120)[0]
        assert mucho > poco * 2.0

    def test_extrapolar_lejos_es_menos_estable_que_el_centro(self):
        """Fuera de la nube de puntos el ruido se amplifica; dentro, no."""
        rejilla = _rejilla()
        dentro, fuera = estabilidad(
            rejilla, [(16.0, 16.0), (400.0, 400.0)], repeticiones=150
        )
        assert fuera > dentro

    def test_lo_que_devuelve_es_una_mediana_no_el_mejor_caso(self):
        """Fija el estadístico: con el mínimo, la medida vendería precisión.

        Sobre la misma rejilla y 3 px de ruido, la mediana da 0,097 y el
        mínimo de 300 repeticiones 0,003 — treinta veces menos. Un
        diagnóstico que informa del mejor caso es el "✓" engañoso de
        siempre, esta vez sobre la herramienta que decide si fiarse del
        informe.
        """
        valor = estabilidad(_rejilla(), [(20.0, 20.0)], ruido_px=3.0, repeticiones=300)[
            0
        ]
        assert valor > 0.03

    def test_es_determinista_con_la_misma_semilla(self):
        c = [(12.0, 12.0)]
        a = estabilidad(_rejilla(), c, repeticiones=30, semilla=7)
        b = estabilidad(_rejilla(), c, repeticiones=30, semilla=7)
        assert a == b

    def test_semillas_distintas_dan_puntos_distintos(self):
        c = [(12.0, 12.0)]
        a = estabilidad(_rejilla(), c, repeticiones=30, semilla=1)
        b = estabilidad(_rejilla(), c, repeticiones=30, semilla=2)
        assert a != b

    def test_sin_consultas_devuelve_lista_vacia(self):
        assert estabilidad(_rejilla(), [], repeticiones=5) == []

    def test_con_menos_de_cuatro_puntos_falla(self):
        with pytest.raises(ValueError, match="al menos 4"):
            estabilidad(_rejilla()[:3], [(1.0, 1.0)])

    @pytest.mark.skipif(not PUNTOS_BENJA.exists(), reason="sin datos del benjamín")
    def test_en_el_benjamin_el_fondo_es_menos_estable_que_la_zona_cercana(self):
        """El resultado que refutó la hipótesis de la extrapolación.

        Va contra la intuición —el fondo tiene cinco puntos marcados y la
        franja cercana ninguno— pero es lo que manda la óptica: un píxel
        vale 3 cm cerca y 50 cm en el fondo.
        """
        puntos = json.loads(PUNTOS_BENJA.read_text())
        cerca, fondo = estabilidad(puntos, [(12.0, 20.0), (62.0, 20.0)])
        assert cerca < fondo
        assert cerca < 0.25  # medido: 0,09 m
        assert np.isfinite(fondo)
