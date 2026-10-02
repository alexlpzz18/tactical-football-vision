"""Piezas puras de la medida de umbrales del detector de balón.

- `combinar_mixto` (scripts/colab_cache_balon_umbrales.py): la deduplicación del
  esquema mixto. Este test fija POR QUÉ no vale reumbralar un caché hecho a 0,05:
  una caja débil del frame entero tapa a una buena de la franja.
- la preanotación del etiquetado dirigido (scripts/preparar_etiquetado_balon_dirigido.py).
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import colab_cache_balon_umbrales as cu  # noqa: E402
import preparar_etiquetado_balon_dirigido as pe  # noqa: E402
from detectar_balon import _solapan  # noqa: E402


def test_una_caja_debil_del_frame_entero_tapa_a_la_buena_de_la_franja():
    debil_entero = (100, 100, 112, 112, 0.08)
    buena_franja = (101, 101, 113, 113, 0.60)
    # a 0,05 la débil está y la buena de la franja se descarta por solaparse
    assert cu.combinar_mixto([debil_entero], [buena_franja], _solapan) == [debil_entero]
    # a 0,35 la débil no existe y la buena entra: reumbralar el caché de 0,05
    # habría perdido el balón. Por eso se reconstruye por umbral.
    assert cu.combinar_mixto([], [buena_franja], _solapan) == [buena_franja]


def test_sin_solape_entran_las_dos():
    a, b = (0, 0, 10, 10, 0.5), (500, 500, 510, 510, 0.5)
    assert cu.combinar_mixto([a], [b], _solapan) == [a, b]


def test_la_preanotacion_va_al_circulo_que_nombro_alex():
    meta = {"antes": {"px": [100.0, 200.0]}, "despues": {"px": [300.0, 400.0]}}
    assert pe.punto_del_caso(["O8"], "verde", meta) == (100.0, 200.0)
    assert pe.punto_del_caso(["O8"], "rojo_arriba", meta) == (
        300.0,
        400.0 - pe.RADIO_CIRCULO_PX,
    )
    assert pe.punto_del_caso(["A1"], None, meta) == (40.0, 40.0)


def test_caja_yolo_normalizada_y_de_tamano_de_balon():
    H = np.array([[0.01, 0, 0], [0, 0.01, 0], [0, 0, 1.0]])  # 100 px/m
    caja = pe.caja_preanotada(500, 500, H, 1920, 1080)
    assert abs((caja[2] - caja[0]) - 1.9 * 0.20 * 100) < 1e-6  # 38 px
    clase, xc, yc, w, h = pe.a_yolo(caja, 1920, 1080).split()
    assert clase == "0" and abs(float(xc) - 500 / 1920) < 1e-6 and 0 < float(w) < 1
