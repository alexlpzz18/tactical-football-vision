"""Relleno de huecos MIRANDO AL FUTURO: recta entre el punto de antes y el de después.

21-sep-2026 (docs/balon_con_futuro.md, BACKLOG 30). Se procesa en diferido, así
que en un hueco ya se sabe dónde REAPARECE el balón. Reponderado a los huecos
reales, la recta acierta el 83 % a menos de 2 m contra el 51 % de mantener la
última posición (97 % en huecos de 0,7-1,2 s).

Guardas: hueco <= 1,2 s, velocidad entre extremos <= 12 m/s, fuera de la zona
cercana a la cámara (x >= 20 m), extremos de suelo REAL, y sin un corte de la
puerta de píxeles de por medio. Los rellenos van con es_real=False y NO entran
en contactos ni posesión (esos se calculan sobre detecciones).
"""

import numpy as np
import pytest

from src.balon.tracking_balon import ParametrosBalon, _rellenar_huecos_parados

FPS = 29.97


def _tiempos(frames):
    return {f: f / FPS for f in frames}


def _fila(frame, x, y=20.0, aereo=False, real=True):
    return (frame, np.array([x, y], dtype=float), aereo, real)


def _con_hueco(x_ini, x_fin, frames_antes=(0, 2, 4), frames_despues=(20, 22, 24)):
    """Balón en x_ini hasta el frame 4, hueco (6..18) y vuelve en x_fin."""
    salida = [_fila(f, x_ini) for f in frames_antes] + [
        _fila(f, x_fin) for f in frames_despues
    ]
    return salida, _tiempos(range(0, 26, 2))


def _rellenos(resultado, originales):
    ya = {f[0] for f in originales}
    return [f for f in resultado if f[0] not in ya]


def test_interpola_por_tiempo_entre_el_punto_de_antes_y_el_de_despues():
    """Balón que va de x=30 a x=36 durante el hueco: la recta pasa por los rellenos."""
    salida, tiempos = _con_hueco(30.0, 36.0)
    res = _rellenar_huecos_parados(salida, tiempos, ParametrosBalon())
    rell = _rellenos(res, salida)
    assert [f[0] for f in rell] == [6, 8, 10, 12, 14, 16, 18]
    t0, t1 = tiempos[4], tiempos[20]
    for frame, pos, _aereo, _real in rell:
        esperado = 30.0 + 6.0 * (tiempos[frame] - t0) / (t1 - t0)
        assert pos[0] == pytest.approx(esperado, abs=1e-6)


def test_los_rellenos_no_son_medidas_ni_aereos():
    salida, tiempos = _con_hueco(30.0, 36.0)
    for _f, _p, aereo, real in _rellenos(
        _rellenar_huecos_parados(salida, tiempos, ParametrosBalon()), salida
    ):
        assert real is False and aereo is False


def test_interpola_donde_mantener_habria_fallado():
    """Balón rápido (>4 m/s): la regla de mantener no rellena, la recta sí."""
    salida, tiempos = _con_hueco(30.0, 36.0)  # 6 m en 0,53 s = 11 m/s
    sin_futuro = _rellenar_huecos_parados(
        salida, tiempos, ParametrosBalon(interp_futuro_max_hueco_s=0.0)
    )
    assert not _rellenos(sin_futuro, salida), "el control: mantener no rellena"
    assert _rellenos(
        _rellenar_huecos_parados(salida, tiempos, ParametrosBalon()), salida
    )


def test_no_interpola_un_hueco_de_mas_de_1_2_s():
    frames_despues = (60, 62, 64)  # hueco de ~1,9 s
    salida = [_fila(f, 30.0) for f in (0, 2, 4)] + [
        _fila(f, 33.0) for f in frames_despues
    ]
    tiempos = _tiempos(range(0, 66, 2))
    assert not _rellenos(
        _rellenar_huecos_parados(salida, tiempos, ParametrosBalon()), salida
    )


def test_no_interpola_si_los_extremos_implican_mas_de_12_m_s():
    """Dos detecciones que no son el mismo balón: 20 m en 0,53 s = 38 m/s."""
    salida, tiempos = _con_hueco(30.0, 50.0)
    assert not _rellenos(
        _rellenar_huecos_parados(salida, tiempos, ParametrosBalon()), salida
    )


def test_no_interpola_en_la_zona_cercana_a_la_camara():
    """x < 20: allí los huecos son a menudo balón FUERA de encuadre."""
    salida, tiempos = _con_hueco(8.0, 14.0)
    assert not _rellenos(
        _rellenar_huecos_parados(salida, tiempos, ParametrosBalon()), salida
    )


def test_no_interpola_si_un_extremo_es_aereo():
    salida, tiempos = _con_hueco(30.0, 36.0)
    salida[2] = _fila(4, 30.0, aereo=True, real=False)
    assert not _rellenos(
        _rellenar_huecos_parados(salida, tiempos, ParametrosBalon()), salida
    )


def test_no_interpola_si_un_extremo_no_es_una_medida():
    """Un relleno no puede ser ancla de otro relleno."""
    salida, tiempos = _con_hueco(30.0, 36.0)
    salida[3] = _fila(20, 36.0, real=False)
    assert not _rellenos(
        _rellenar_huecos_parados(salida, tiempos, ParametrosBalon()), salida
    )


def test_no_interpola_a_traves_de_un_corte_de_la_puerta_de_pixeles():
    salida, tiempos = _con_hueco(30.0, 36.0)
    res = _rellenar_huecos_parados(salida, tiempos, ParametrosBalon(), cortes={20})
    assert not _rellenos(res, salida)


def test_la_recta_es_el_caso_general_de_mantener_un_balon_parado():
    """Extremos iguales: la recta es constante, igual que mantener."""
    salida, tiempos = _con_hueco(30.0, 30.0)
    for _f, pos, *_ in _rellenos(
        _rellenar_huecos_parados(salida, tiempos, ParametrosBalon()), salida
    ):
        assert pos == pytest.approx([30.0, 20.0])


def test_los_umbrales_son_parametros_y_mandan():
    salida, tiempos = _con_hueco(30.0, 36.0)
    apagado = ParametrosBalon(interp_futuro_max_hueco_s=0.0)
    assert not _rellenos(_rellenar_huecos_parados(salida, tiempos, apagado), salida)
    sin_zona = ParametrosBalon(interp_futuro_x_min_m=100.0)
    assert not _rellenos(_rellenar_huecos_parados(salida, tiempos, sin_zona), salida)
    lento = ParametrosBalon(interp_futuro_vel_max_m_s=2.0)
    assert not _rellenos(_rellenar_huecos_parados(salida, tiempos, lento), salida)


def test_la_recta_se_reparte_por_TIEMPO_aunque_los_frames_no_esten_equiespaciados():
    """Con un vídeo de fps variable, índice y tiempo dejan de coincidir."""
    salida = [_fila(f, 30.0) for f in (0, 2, 4)] + [
        _fila(f, 34.0) for f in (14, 16, 18)
    ]
    tiempos = {
        0: 0.0,
        2: 0.07,
        4: 0.13,
        6: 0.15,
        8: 0.20,
        10: 0.45,
        14: 0.55,
        16: 0.62,
        18: 0.68,
    }
    res = _rellenar_huecos_parados(salida, tiempos, ParametrosBalon())
    por_frame = {f: p for f, p, *_ in res}
    for f in (6, 8, 10):
        esperado = 30.0 + 4.0 * (tiempos[f] - tiempos[4]) / (tiempos[14] - tiempos[4])
        assert por_frame[f][0] == pytest.approx(esperado, abs=1e-6)
