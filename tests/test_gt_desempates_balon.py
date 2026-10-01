import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gt_desempates_balon import (  # noqa: E402
    dentro_de_alguna_caja,
    elegir_espaciados,
    parsear_respuesta,
)


def test_punto_dentro_y_fuera_de_una_caja():
    cajas = [(100, 100, 120, 160)]
    assert dentro_de_alguna_caja(110, 150, cajas)
    assert not dentro_de_alguna_caja(125, 150, cajas)
    assert not dentro_de_alguna_caja(110, 161, cajas)


def test_el_margen_amplia_la_caja():
    cajas = [(100, 100, 120, 160)]
    assert not dentro_de_alguna_caja(123, 150, cajas)
    assert dentro_de_alguna_caja(123, 150, cajas, margen=3)


def test_sin_cajas_nunca_esta_dentro():
    assert not dentro_de_alguna_caja(10, 10, [])


def test_respuesta_numero_valido():
    assert parsear_respuesta("2", 3) == ("balon", 2)
    assert parsear_respuesta(" 1 ", 2) == ("balon", 1)


def test_numbers_convierte_el_numero_en_float():
    assert parsear_respuesta("2.0", 3) == ("balon", 2)
    assert parsear_respuesta(2.0, 3) == ("balon", 2)


def test_numero_fuera_de_rango_o_decimal_no_vale():
    assert parsear_respuesta("4", 3) == (None, None)
    assert parsear_respuesta("0", 3) == (None, None)
    assert parsear_respuesta("1.5", 3) == (None, None)


def test_ninguno_y_no_se():
    assert parsear_respuesta("ninguno", 3) == ("ninguno", None)
    assert parsear_respuesta("Ninguno", 3) == ("ninguno", None)
    assert parsear_respuesta("no_se", 3) == ("no_se", None)


def test_texto_basura_no_vale():
    assert parsear_respuesta("el de la izquierda", 3) == (None, None)


def test_espaciados_respetan_la_separacion():
    items = [{"t": t} for t in (0.0, 1.0, 2.0, 10.0, 11.0, 30.0)]
    elegidos = elegir_espaciados(items, 10, 5.0, random.Random(0))
    ts = [e["t"] for e in elegidos]
    restantes = [ts[i + 1 :] for i in range(len(ts))]  # noqa: E203
    assert all(abs(a - b) >= 5.0 for a, resto in zip(ts, restantes) for b in resto)
    assert ts == sorted(ts)
