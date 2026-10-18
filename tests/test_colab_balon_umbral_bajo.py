"""Las dos piezas puras del experimento de umbral bajo (scripts/colab_balon_umbral_bajo.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import colab_balon_umbral_bajo as c  # noqa: E402


def test_punto_de_una_celda_y_de_dos():
    assert c.punto_de_celdas(["A1"]) == (40.0, 40.0)
    assert c.punto_de_celdas(["O8", "P8"]) == (1200.0, 600.0)  # punto medio


def test_en_el_balon_solo_lo_cercano_y_ordenado():
    punto = (1000.0, 600.0)
    cajas = [
        (995, 595, 1005, 605, 0.12),  # encima: 0 px
        (1040, 600, 1050, 610, 0.08),  # a ~45 px: dentro del radio
        (1300, 600, 1310, 610, 0.90),  # lejos: fuera
    ]
    r = c.en_el_balon(cajas, punto)
    assert [x[1] for x in r] == [0.12, 0.08]
    assert r[0][0] == 0.0
