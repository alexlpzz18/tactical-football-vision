import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from leer_gt_posicion_balon import _parsear_respuesta  # noqa: E402


def test_celda_simple_dentro_del_crop():
    # Columna K (índice 10), fila 7 (índice 6), celda de 20 px.
    estado, x, y = _parsear_respuesta("K7", origen_x=100, origen_y=200, celda_px=20)
    assert estado == "visto"
    assert x == 100 + (10 + 0.5) * 20
    assert y == 200 + (6 + 0.5) * 20


def test_celda_minuscula_se_normaliza():
    estado, x, y = _parsear_respuesta("k7", origen_x=0, origen_y=0, celda_px=20)
    assert estado == "visto"
    assert x == (10 + 0.5) * 20


def test_primera_celda_A1():
    estado, x, y = _parsear_respuesta("A1", origen_x=0, origen_y=0, celda_px=20)
    assert estado == "visto"
    assert x == 10.0
    assert y == 10.0


def test_espacios_alrededor_se_ignoran():
    estado, x, y = _parsear_respuesta("  K7  ", origen_x=0, origen_y=0, celda_px=20)
    assert estado == "visto"


def test_fuera_no_da_posicion():
    estado, x, y = _parsear_respuesta("fuera", origen_x=50, origen_y=50, celda_px=20)
    assert estado == "fuera"
    assert x is None and y is None


def test_tapado_y_no_se_tambien_sin_posicion():
    for palabra in ("tapado", "no_se", "NO_SE", "Tapado"):
        estado, x, y = _parsear_respuesta(palabra, 0, 0, 20)
        assert estado == palabra.lower()
        assert x is None and y is None


def test_formato_no_reconocido_da_estado_none():
    estado, x, y = _parsear_respuesta("ZZ99", 0, 0, 20)
    assert estado is None
    estado, x, y = _parsear_respuesta("algo raro", 0, 0, 20)
    assert estado is None


def test_celda_fuera_del_rango_de_letras_da_none():
    # 'Z' no está en LETRAS (se para en 'Y' aposta, 25 letras para 25 columnas).
    estado, x, y = _parsear_respuesta("Z1", 0, 0, 20)
    assert estado is None


def test_entre_dos_celdas_da_el_punto_medio():
    # M9 (col 12, fila 8) y M10 (col 12, fila 9), celda de 20px desde origen 0,0.
    estado, x, y = _parsear_respuesta("M9/M10", origen_x=0, origen_y=0, celda_px=20)
    assert estado == "visto"
    x_m9 = (12 + 0.5) * 20
    y_m9 = (8 + 0.5) * 20
    y_m10 = (9 + 0.5) * 20
    assert x == x_m9
    assert y == (y_m9 + y_m10) / 2


def test_entre_dos_celdas_distintas_columna_y_fila():
    estado, x, y = _parsear_respuesta("P11/O11", origen_x=0, origen_y=0, celda_px=20)
    assert estado == "visto"
    x_p = (15 + 0.5) * 20
    x_o = (14 + 0.5) * 20
    assert x == (x_p + x_o) / 2
    assert y == (10 + 0.5) * 20


def test_entre_dos_celdas_con_espacios_alrededor_de_la_barra():
    estado, x, y = _parsear_respuesta("M9 / M10", origen_x=0, origen_y=0, celda_px=20)
    assert estado == "visto"


def test_tapado_con_celda_da_posicion_pero_estado_tapado():
    estado, x, y = _parsear_respuesta(
        "Tapado en M9", origen_x=0, origen_y=0, celda_px=20
    )
    assert estado == "tapado"
    assert x == (12 + 0.5) * 20
    assert y == (8 + 0.5) * 20


def test_tapado_sin_celda_sigue_sin_posicion():
    # "tapado" a secas (sin "en X") no debe confundirse con el patrón nuevo.
    estado, x, y = _parsear_respuesta("tapado", origen_x=0, origen_y=0, celda_px=20)
    assert estado == "tapado"
    assert x is None and y is None


def test_tapado_con_celda_invalida_da_none():
    estado, x, y = _parsear_respuesta(
        "Tapado en Z1", origen_x=0, origen_y=0, celda_px=20
    )
    assert estado is None
