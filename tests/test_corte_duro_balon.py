"""Corte duro del balón (flag `balon.descartar_fuera_m`, apagado por defecto).

docs/diagnostico_22oct_c.md, bloque 1: sin balón si el elegido cae lejos del campo, y sin
rellenar ni unir a través de esos frames.
"""

from pathlib import Path

import numpy as np
import pytest

from src.balon.carga import parametros_balon_de_campo
from src.balon.tracking_balon import (
    ParametrosBalon,
    descartar_balon_fuera,
    preparar_balon,
)

R = Path(__file__).resolve().parent.parent
CAMPO = (62.0, 40.0)


def _d(x, y):
    return (x, y, 0, 0, 10, 10, 0.5)


def test_apagado_por_defecto_y_en_el_config_de_produccion():
    assert ParametrosBalon().descartar_fuera_m is None
    assert (
        parametros_balon_de_campo(R / "configs/campo_benja.yaml").descartar_fuera_m
        is None
    )


def test_apagado_no_toca_nada():
    activo = {0: _d(80.0, 20.0), 2: _d(30.0, 20.0)}
    out, fuera = descartar_balon_fuera(activo, CAMPO, ParametrosBalon())
    assert out == activo and fuera == set()


def test_encendido_quita_lo_lejano_y_deja_los_saques_de_banda():
    """El interruptor CAMBIA el resultado (guarda de comportamiento)."""
    activo = {
        0: _d(80.0, 20.0),
        2: _d(30.0, 41.5),
        4: _d(30.0, 20.0),
        6: _d(30.0, 44.0),
    }
    out, fuera = descartar_balon_fuera(
        activo, CAMPO, ParametrosBalon(descartar_fuera_m=3.0)
    )
    assert fuera == {0, 6}  # 18 m y 4 m fuera
    assert set(out) == {2, 4}  # 1,5 m fuera (saque de banda) y dentro


def test_clave_mal_escrita_en_el_config_da_error(tmp_path):
    cfg = tmp_path / "campo.yaml"
    cfg.write_text("campo: {largo: 62, ancho: 40}\nbalon:\n  descartar_fuera: 3.0\n")
    with pytest.raises(ValueError, match="descartar_fuera"):
        parametros_balon_de_campo(cfg)


def _preparar(frames, vetados=frozenset()):
    """Balón quieto (rellenable por las dos reglas) con un hueco en los frames que faltan."""
    tiempos = {f: f / 15.0 for f in range(0, 40)}
    tray = [(f, np.array([30.0 + 0.01 * f, 20.0]), 15.0, 0.5) for f in frames]
    filas, cortes = preparar_balon(
        tray, [False] * len(tray), tiempos, ParametrosBalon(), vetados=vetados
    )
    return {f: (p, real) for f, p, _a, real in filas}, cortes


def test_sin_veto_el_hueco_se_rellena_y_con_veto_no():
    frames = [f for f in range(0, 20) if f not in (10, 11, 12)]
    sin, _ = _preparar(frames)
    assert {10, 11, 12} <= set(sin)  # control: hoy ese hueco se rellena
    con, cortes = _preparar(frames, vetados={11})
    assert not ({10, 11, 12} & set(con))  # ni recta ni mantener a través del veto
    assert 13 in cortes  # el balón de después abre otro tramo


def test_el_suavizado_no_cruza_un_veto():
    tiempos = {f: f / 15.0 for f in range(0, 40)}
    # un salto de 5 m justo en el veto: si el suavizado lo cruzara, movería las filas vecinas
    tray = [
        (f, np.array([30.0 if f < 11 else 35.0, 20.0]), 15.0, 0.5) for f in range(0, 22)
    ]
    tray = [t for t in tray if t[0] != 11]
    filas, _ = preparar_balon(
        tray, [False] * len(tray), tiempos, ParametrosBalon(), vetados={11}
    )
    pos = {f: p for f, p, _a, _r in filas}
    assert pos[10][0] == pytest.approx(30.0) and pos[12][0] == pytest.approx(35.0)


def test_recortar_al_campo_es_el_punto_mas_cercano_y_no_toca_lo_de_dentro():
    from src.balon.tracking_balon import recortar_al_campo

    x, y = recortar_al_campo(
        np.array([30.0, -2.0, 70.0, 30.0]), np.array([20.0, 10.0, 45.0, -1.5]), CAMPO
    )
    assert x.tolist() == [30.0, 0.0, 62.0, 30.0]
    assert y.tolist() == [20.0, 10.0, 40.0, 0.0]
    # activado en el benjamín (22-oct f, bloque D): solo cambia el dibujo de la pizarra
    assert (
        parametros_balon_de_campo(R / "configs/campo_benja.yaml").recortar_a_campo
        is True
    )


def test_la_pizarra_dibuja_el_balon_de_fuera_en_la_linea_y_no_toca_jugadores():
    import pandas as pd

    from src.report.replay_tactico import _filtrar_fuera_del_campo, _recortar_balon

    df = pd.DataFrame(
        {
            "etiqueta": ["balon", "balon", "A", "A"],
            "x_m": [30.0, 63.5, 30.0, 63.5],
            "y_m": [-2.0, 20.0, 10.0, 20.0],
        }
    )
    sin = _filtrar_fuera_del_campo(df, 62.0, 40.0)
    con = _filtrar_fuera_del_campo(_recortar_balon(df, 62.0, 40.0), 62.0, 40.0)
    assert len(sin) == 1  # hoy: el balón de fuera DESAPARECE
    assert con.etiqueta.tolist() == ["balon", "balon", "A"]  # con el flag, se dibuja
    assert con.iloc[0].y_m == 0.0 and con.iloc[1].x_m == 62.0
    assert sin[sin.etiqueta == "A"].equals(con[con.etiqueta == "A"])  # jugadores igual
