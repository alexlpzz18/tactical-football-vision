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
