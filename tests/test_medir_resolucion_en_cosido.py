"""Piezas puras de scripts/medir_resolucion_en_cosido.py (el veredicto y los envoltorios)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "medir_resolucion_en_cosido", _RAIZ / "scripts/medir_resolucion_en_cosido.py"
)
mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mr)


def _m(**cambios):
    base = dict(
        equipo_mal_pct=1.24,
        quimeras=4,
        fragmentacion=3.07,
        centroide_m=1.45,
        anchura_m=1.27,
        faltan=0.76,
        sobran=0.84,
        DetA=0.50,
        AssA=0.40,
        IDF1=0.45,
    )
    return {**base, **cambios}


def _uniones(cambiadas=10, k_nuevas=2, n_nuevas=20, tasa_base=0.2):
    return {
        "cambiadas_en_ventana": cambiadas,
        "tasa_etiqueta_base": tasa_base,
        "n_etiqueta_nuevas": n_nuevas,
        "ic_nuevas": mr.wilson(k_nuevas, n_nuevas),
    }


def test_pasa_si_mejora_sin_empeorar_y_villa_identica():
    v = mr.veredicto(_m(), _m(fragmentacion=2.9), _uniones(), True)
    assert v["pasa"] is True


def test_un_centimetro_de_mas_en_el_centroide_basta_para_suspender():
    v = mr.veredicto(_m(), _m(fragmentacion=2.9, centroide_m=1.4611), _uniones(), True)
    assert v["pasa"] is False and v["puntos"]["benja_centroide"] is False


def test_sin_uniones_cambiadas_en_la_ventana_la_mejora_no_es_concluyente():
    v = mr.veredicto(_m(), _m(), _uniones(cambiadas=2), True)
    assert v["puntos"]["benja_mejora"] is None and v["pasa"] is None


def test_un_empeoramiento_suspende_aunque_no_sea_concluyente():
    v = mr.veredicto(_m(), _m(quimeras=5), _uniones(cambiadas=2), True)
    assert v["pasa"] is False


def test_uniones_nuevas_que_cambian_de_etiqueta_mucho_mas_que_la_base_suspenden():
    # 15 de 20 cambian de etiqueta contra un 20 % de la base: IC inferior ≈ 0,53
    v = mr.veredicto(
        _m(), _m(fragmentacion=2.9), _uniones(k_nuevas=15, n_nuevas=20), True
    )
    assert v["puntos"]["benja_no_inventa"] is False and v["pasa"] is False


def test_villa_distinta_se_juzga_con_los_mismos_puntos():
    v = mr.veredicto(
        _m(), _m(fragmentacion=2.9), _uniones(), False, _m(), _m(IDF1=0.40)
    )
    assert v["puntos"]["villa_identico"] is False
    assert v["puntos"]["villa_IDF1"] is False and v["pasa"] is False


def test_wilson_contiene_la_proporcion_y_es_trivial_sin_datos():
    lo, hi = mr.wilson(3, 10)
    assert lo < 0.3 < hi
    assert mr.wilson(0, 0) == (0.0, 1.0)


class _ResFija:
    def metros_por_pixel(self, pos):
        return 0.4

    def velocidad_ruido(self, pos, jitter_px, dt):
        return jitter_px * 0.4 / dt


def test_resolucion_parcial_apaga_cada_margen_por_separado():
    solo_e = mr.ResolucionParcial(_ResFija(), espacial=True, velocidad=False)
    solo_v = mr.ResolucionParcial(_ResFija(), espacial=False, velocidad=True)
    assert solo_e.metros_por_pixel((0, 0)) == 0.4
    assert solo_e.velocidad_ruido((0, 0), 3.5, 0.1) == 0.0
    assert solo_v.metros_por_pixel((0, 0)) == 0.0
    assert solo_v.velocidad_ruido((0, 0), 3.5, 0.1) == pytest.approx(14.0)


def test_el_intento_2_pasa_el_hueco_como_dt():
    vistos = []

    def coste_falso(i, j, extremos, v, f, fi, p, res, jitter, dt):
        vistos.append(dt)
        return 0.0

    extremos = [
        (0.0, 1.0, np.zeros(2), np.zeros(2)),
        (3.5, 5.0, np.zeros(2), np.zeros(2)),
    ]
    mr._coste_con_hueco(coste_falso)(
        0, 1, extremos, None, None, None, None, None, 3.5, 0.1
    )
    assert vistos == [pytest.approx(2.5)]
