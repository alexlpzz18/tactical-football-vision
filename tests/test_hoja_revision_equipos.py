"""La elección de ventanas de scripts/hoja_revision_equipos.py."""

import importlib.util
from itertools import combinations
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "hoja", Path(__file__).resolve().parent.parent / "scripts/hoja_revision_equipos.py"
)
hr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hr)


def test_tres_ventanas_sin_solaparse_y_el_minuto_malo_es_el_peor_fuera_del_gt():
    cuenta = {m: 12.0 for m in range(300, 1140, 60)}
    cuenta[300] = 5.0  # el peor, pero se solapa con la del GT (310): no vale
    cuenta[780] = 8.0
    for semilla in range(20):
        v = hr.elegir_ventanas(cuenta, np.random.default_rng(semilla))
        assert v["gt"] == 310 and v["minuto_malo"] == 780
        inicios = list(v.values())
        assert all(not hr.solapa(a, b) for a, b in combinations(inicios, 2))
        assert 300 <= v["azar"] <= 1140 - 60


def test_reloj():
    assert hr.reloj(325.0) == "5:25.0"
    assert hr.reloj(325.0 + 93) == "6:58.0"
