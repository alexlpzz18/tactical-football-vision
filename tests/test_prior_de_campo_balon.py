"""Prior de campo del selector de balón (flag, apagado por defecto). docs/diagnostico_22oct_b.md."""

from src.balon.tracking_balon import ParametrosBalon, _prior_de_campo

CAMPO = (62.0, 40.0)


def _d(x, y, conf=0.5):
    return (x, y, 0, 0, 10, 10, conf)


def test_apagado_por_defecto():
    assert ParametrosBalon().prior_campo_activo is False


def test_elige_el_candidato_de_dentro_si_lo_hay():
    p = ParametrosBalon(prior_campo_activo=True)
    fuera, dentro = _d(80.0, 20.0, 0.9), _d(30.0, 20.0, 0.4)
    out = _prior_de_campo({0: [fuera, dentro]}, {0: 0.0}, CAMPO, p)
    assert out[0] == [dentro]


def test_sin_candidato_valido_deja_el_frame_como_estaba():
    p = ParametrosBalon(prior_campo_activo=True)
    fuera = _d(80.0, 20.0)
    assert _prior_de_campo({0: [fuera]}, {0: 0.0}, CAMPO, p)[0] == [fuera]
    # a menos de 3 m fuera (un saque de banda) sigue siendo válido
    banda = _d(30.0, 41.5)
    assert _prior_de_campo({0: [banda]}, {0: 0.0}, CAMPO, p)[0] == [banda]


def test_la_velocidad_desde_el_ultimo_valido():
    p = ParametrosBalon(prior_campo_activo=True)
    ordenados = {0: [_d(10.0, 20.0)], 1: [_d(40.0, 20.0), _d(12.0, 20.0)]}
    out = _prior_de_campo(ordenados, {0: 0.0, 1: 0.1}, CAMPO, p)
    assert out[1] == [_d(12.0, 20.0)]  # el de 30 m en 0,1 s (300 m/s) se descarta
