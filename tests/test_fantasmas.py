"""Filas fantasma: solo salen INTERPOLADAS pegadas a una real del mismo equipo o de un portero."""

import pandas as pd

from src.tracking.fantasmas import marcar_fantasmas, quitar_fantasmas


def _df(filas):
    return pd.DataFrame(
        filas, columns=["frame", "id_jugador", "etiqueta", "x_m", "y_m", "es_real"]
    )


def test_el_fantasma_del_portero_sale():
    # el caso del 3:00.0: portero real y, a 0,57 m, una interpolada etiquetada como jugador
    df = _df([(1, 16, "portero_B", 19.8, 34.5, 1), (1, 713, "B", 19.5, 35.0, 0)])
    assert marcar_fantasmas(df).tolist() == [False, True]


def test_una_real_nunca_sale_aunque_este_pegada():
    df = _df([(1, 1, "A", 10.0, 10.0, 1), (1, 2, "A", 10.5, 10.0, 1)])
    assert not marcar_fantasmas(df).any()


def test_interpolada_junto_a_un_RIVAL_no_sale():
    # un jugador tapado en un cruce con un rival (la variante V2 lo borraba)
    df = _df([(1, 1, "A", 10.0, 10.0, 1), (1, 2, "B", 10.5, 10.0, 0)])
    assert not marcar_fantasmas(df).any()


def test_interpolada_lejos_no_sale_y_otro_frame_no_cuenta():
    df = _df(
        [
            (1, 1, "A", 10.0, 10.0, 1),
            (1, 2, "A", 13.0, 10.0, 0),
            (2, 3, "A", 10.2, 10.0, 0),
        ]
    )
    assert not marcar_fantasmas(df).any()


def test_quitar_devuelve_el_recuento():
    df = _df([(1, 16, "portero_B", 19.8, 34.5, 1), (1, 713, "B", 19.5, 35.0, 0)])
    limpio, n = quitar_fantasmas(df)
    assert n == 1 and limpio.id_jugador.tolist() == [16]
