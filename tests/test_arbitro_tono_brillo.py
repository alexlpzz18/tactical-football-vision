"""El criterio del árbitro por tono y brillo (scripts/arbitro_tono_brillo.py), sin datos."""

import importlib.util
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "atb", Path(__file__).resolve().parent.parent / "scripts/arbitro_tono_brillo.py"
)
atb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(atb)


def _clase(h, s, v, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    return np.column_stack(
        [
            rng.normal(h, 2, n),
            rng.normal(s, 10, n),
            np.clip(rng.normal(v, 10, n), 0, 255),
        ]
    )


def test_umbrales_de_percentiles_y_separan_chaleco_de_cesped_y_portero():
    ch, ce, pb = (
        _clase(46, 175, 247),
        _clase(55, 80, 120, seed=1),
        _clase(50, 112, 160, seed=2),
    )
    u = atb.derivar_umbrales(ch, ce, pb, None, None)
    assert u["h"][0] < 46 < u["h"][1]
    assert u["v_min"] > 160  # por encima del p95 del portero de B
    assert not u["aviso_v"]
    assert atb.es_pixel_chaleco(ch, u).mean() > 0.8
    assert atb.es_pixel_chaleco(ce, u).mean() < 0.01
    assert atb.es_pixel_chaleco(pb, u).mean() < 0.05


def test_aviso_si_el_brillo_minimo_se_come_el_chaleco():
    ch, ce, pb = (
        _clase(46, 175, 200),
        _clase(55, 80, 200, seed=1),
        _clase(50, 112, 160, seed=2),
    )
    assert atb.derivar_umbrales(ch, ce, pb, None, None)["aviso_v"]


def test_veredicto():
    assert atb.veredicto(10, 10, 0, False).startswith("NO CONCLUYENTE")
    assert atb.veredicto(40, 39, 0, True).startswith("NO SE ADOPTA (un jugador")
    assert atb.veredicto(40, 39, 2, False).startswith("NO SE ADOPTA (demasiados")
    assert atb.veredicto(40, 30, 1, False).startswith("NO SE ADOPTA (recupera")
    assert atb.veredicto(40, 33, 1, False).startswith("PASA")
