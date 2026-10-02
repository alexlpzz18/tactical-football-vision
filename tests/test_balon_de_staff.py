"""El balón de un STAFF fuera del campo no es el del partido (Plan 2).

Caso real (126-147 s del benjamín): un niño del banquillo juega con otro
balón fuera de la banda mientras el del partido no se detecta. Es grande y
real, así que ni la continuidad ni el tamaño lo quitan.
"""

from dataclasses import replace

from src.balon.tracking_balon import ParametrosBalon, quitar_balones_de_staff

P = ParametrosBalon()
CAMPO = (62.0, 40.0)


def _det(mx, my):
    return (mx, my, 100.0, 100.0, 120.0, 120.0, 0.8)


def test_quita_el_balon_del_nino_fuera_de_la_banda():
    dets = {0: [_det(37.5, -0.7), _det(20.0, 20.0)]}
    jug = {0: [(20.5, 20.0), (30.0, 10.0)]}  # el más cercano al balón del niño, a ~13 m
    staff = {0: [(37.6, -0.3)]}
    limpio = quitar_balones_de_staff(dets, jug, staff, CAMPO, P)
    assert limpio == {0: [_det(20.0, 20.0)]}


def test_no_quita_el_balon_en_juego_disputado_en_la_linea():
    """Mismo sitio, junto al entrenador, pero con un jugador encima: es el del partido."""
    dets = {0: [_det(35.2, -0.5)]}
    jug = {0: [(35.2, 1.5)]}  # a 2 m: puede estar tocándolo
    staff = {0: [(35.5, -1.0)]}
    assert quitar_balones_de_staff(dets, jug, staff, CAMPO, P) == dets


def test_no_quita_un_balon_DENTRO_del_campo_aunque_el_staff_este_mas_cerca():
    dets = {0: [_det(35.0, 0.5)]}
    jug = {0: [(35.0, 8.0)]}
    staff = {0: [(35.0, -0.5)]}
    assert quitar_balones_de_staff(dets, jug, staff, CAMPO, P) == dets


def test_el_interruptor_apagado_lo_deja_pasar():
    """Un interruptor que nadie lee es peor que no tenerlo."""
    from src.balon.tracking_balon import seleccionar_balon_activo

    dets = {f: [_det(37.5, -0.7)] for f in range(10)}
    # Jugador a ~6 m, como en 143-147 s: por debajo de los 10 m de la guarda
    # de "quieto y lejos", que por eso no lo quitaba.
    jug = {f: [(37.5, 5.5)] for f in dets}
    staff = {f: [(37.6, -0.3)] for f in dets}
    base = replace(P, continuidad_activa=False)
    kw = {"posiciones_staff": staff, "dimensiones_campo": CAMPO}
    assert seleccionar_balon_activo(dets, jug, base, **kw) == {}
    apagado = replace(base, quitar_balon_de_staff=False)
    assert len(seleccionar_balon_activo(dets, jug, apagado, **kw)) == 10
