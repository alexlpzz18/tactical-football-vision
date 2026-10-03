"""Calibración automática del campo: el criterio (y, más abajo, el método)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import medir_calibracion_automatica as mc  # noqa: E402

BUENO = dict(
    a_auto_px=6.0,
    a_manual_px=5.0,
    s_frame=0.8,
    b_pies_m=0.4,
    c_dispersion_px=3.0,
    c_aceptados=18,
    d_scores=[0.1] * 11,
)


def test_veredicto_viable():
    assert mc.veredicto(BUENO)["viable"]


def test_veredicto_cada_punto_suspende():
    assert not mc.veredicto({**BUENO, "a_auto_px": 7.6})["a_reproyeccion"]
    assert not mc.veredicto({**BUENO, "s_frame": 0.4})["a_reproyeccion"]
    assert not mc.veredicto({**BUENO, "b_pies_m": 1.2})["b_pies"]
    assert not mc.veredicto({**BUENO, "c_dispersion_px": 6.5})["c_dispersion"]
    assert not mc.veredicto({**BUENO, "c_aceptados": 15})["c_aceptados"]
    assert not mc.veredicto({**BUENO, "d_scores": [0.1] * 10 + [0.55]})["d_control"]
    assert not mc.veredicto({**BUENO, "d_scores": []})["d_control"]
