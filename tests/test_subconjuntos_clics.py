"""El criterio de la calibración semiautomática (scripts/medir_subconjuntos_clics.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import medir_subconjuntos_clics as ms  # noqa: E402


def test_veredicto_regla_exige_los_dos_campos():
    base = {"benja": {4: 14.0, 5: 13.0, 6: 12.0}, "villa": {4: 9.0, 5: 8.0, 6: 8.0}}
    r1 = {"benja": {4: 20.0, 5: 12.0, 6: 11.0}, "villa": {4: 8.0, 5: 9.0, 6: 7.0}}
    v = ms.veredicto_regla(r1, base)
    assert v[4] is False and v[5] is False and v[6] is True and v["k_minimo"] == 6


def test_veredicto_regla_sin_ninguno():
    base = {"a": {4: 1.0, 5: 1.0, 6: 1.0}}
    assert ms.veredicto_regla({"a": {4: 2.0, 5: 2.0, 6: 2.0}}, base)["k_minimo"] is None


def test_validador_util():
    assert ms.validador_util({"benja": 0.85, "villa": 0.81})
    assert not ms.validador_util({"benja": 0.95, "villa": 0.70})
    assert not ms.validador_util({"benja": 0.95, "villa": None})
