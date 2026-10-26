"""IDF1 y fragmentación por persona desde un CSV (docs/diagnostico_23oct_a.md, bloque 1)."""

import numpy as np
import pandas as pd

from src.evaluation.asociacion_desde_csv import asociacion_desde_csv
from src.evaluation.modelo import Observacion


def _gt(n=10):
    return {
        f: [
            Observacion(obj_id=1, pos=np.array([10.0, 10.0]), team="A", label="player"),
            Observacion(obj_id=2, pos=np.array([30.0, 10.0]), team="B", label="player"),
        ]
        for f in range(n)
    }


def _csv(ids_1, ids_2):
    filas = []
    for f, (a, b) in enumerate(zip(ids_1, ids_2)):
        filas += [(f, a, 10.0, 10.0, 1), (f, b, 30.0, 10.0, 1)]
    return pd.DataFrame(filas, columns=["frame", "id_jugador", "x_m", "y_m", "es_real"])


def test_perfecto():
    r = asociacion_desde_csv(_csv([7] * 10, [8] * 10), _gt())
    assert r["IDF1"] == 1.0 and r["identidades_por_persona_media"] == 1.0


def test_partir_baja_el_idf1_y_sube_la_fragmentacion():
    """La pureza no ve esto: cada trozo es puro. IDF1 y la fragmentación sí."""
    r = asociacion_desde_csv(_csv([7] * 5 + [9] * 5, [8] * 10), _gt())
    assert r["IDF1"] < 1.0
    assert r["identidades_por_persona_media"] == 1.5
