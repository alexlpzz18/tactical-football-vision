"""Guarda de caja fundida (SOLO MEDICIÓN): scripts/guarda_caja_fundida.py y el criterio.

Casos sintéticos con la geometría de la 525 (docs/cambio_de_identidad_por_caja_fundida.md):
cajas de ~40 px, una caja fundida de 52 px y un salto de 6 m en un paso.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import guarda_caja_fundida as gcf  # noqa: E402
from src.tracking.field_tracker import Tracklet  # noqa: E402

DT = 0.1


def identidad(posiciones, cajas_px, frame0=1000):
    """Una identidad de un tracklet; devuelve (identidad, {clave: caja})."""
    tr = None
    cajas = {}
    for k, (pos, caja) in enumerate(zip(posiciones, cajas_px)):
        f = frame0 + 3 * k
        if tr is None:
            tr = Tracklet(1, k * DT, np.array(pos), 0, f)
        else:
            tr.anadir(k * DT, np.array(pos), 0, f)
        cajas[(f, 0)] = caja
    return [tr], cajas


def cambio_de_persona():
    """Portero quieto en (61,20); en k=20 una caja fundida y la identidad pasa al jugador."""
    pos = [(61.0, 20.0)] * 20 + [(55.0, 20.0)] * 20
    cajas = (
        [(500, 300, 516, 340)] * 20  # el portero, 40 px
        + [(492, 300, 523, 352)]  # FUNDIDA: cabeza del portero, pies del jugador
        + [(507, 312, 523, 352)] * 19  # el jugador: se mueve la caja ENTERA
    )
    return identidad(pos, cajas)


def piernas_que_reaparecen():
    """La MISMA persona: el pie baja 12 px (4 m en el fondo) y la cabeza no se mueve."""
    pos = [(61.0, 20.0)] * 20 + [(57.0, 20.0)] * 20
    cajas = [(500, 300, 516, 340)] * 20 + [(500, 300, 516, 352)] * 20
    return identidad(pos, cajas)


def params(**kw):
    return gcf.ParametrosGuarda(**kw)


def cortes(caso, **kw):
    ident, cajas = caso
    return gcf.detectar_cortes(gcf.observaciones(ident), cajas, params(**kw))


def test_cambio_de_persona_se_corta_en_el_salto():
    c = cortes(cambio_de_persona())
    assert len(c) == 1 and c[0]["i"] == 20 and c[0]["fundida"]


def test_piernas_que_reaparecen_las_salva_solo_la_caja_entera():
    # el hueco del plan: pasa el salto Y la caja fundida (crece hacia abajo)...
    assert len(cortes(piernas_que_reaparecen(), usar_entera=False)) == 1
    # ...y solo la guarda de "se mueve la caja entera" evita partirla
    assert cortes(piernas_que_reaparecen()) == []


def test_salto_sin_fundir_solo_lo_corta_la_rama_salto():
    ident, cajas = cambio_de_persona()
    cajas = {
        k: (507, 312, 523, 352) if v[3] - v[1] == 52 and v[0] == 492 else v
        for k, v in cajas.items()
    }
    assert cortes((ident, cajas)) == []
    assert len(cortes((ident, cajas), usar_fundida=False)) == 1


def test_un_error_suelto_no_persiste():
    pos = [(61.0, 20.0)] * 20 + [(55.0, 20.0)] + [(61.0, 20.0)] * 19
    cajas = (
        [(500, 300, 516, 340)] * 20
        + [(492, 300, 523, 352)]
        + [(500, 300, 516, 340)] * 19
    )
    assert cortes(identidad(pos, cajas), usar_fundida=False, usar_entera=False) == []


def test_fuera_del_campo_no_se_corta():
    ident, cajas = cambio_de_persona()
    for tr in ident:
        tr.pos = [p + np.array([30.0, 0.0]) for p in tr.pos]  # x ≈ 85-91 m, F7 mide 62
    assert cortes((ident, cajas)) == []


def test_partir_conserva_todas_las_observaciones():
    ident, _ = cambio_de_persona()
    trozos = gcf.partir(ident, [20])
    assert [sum(len(t) for t in tz) for tz in trozos] == [20, 20]
    assert trozos[1][0].det_idxs[0] == ident[0].det_idxs[20]


def test_posiciones_validas_exige_lados_medibles():
    ident, _ = cambio_de_persona()
    v = gcf.posiciones_validas(gcf.observaciones(ident), params())
    assert min(v) >= 3 and max(v) <= 37


# ─────────────── el criterio (scripts/medir_guarda_caja_fundida.py) ───────────────
def _m(quim=3, frag=1.5, mal=1.2, cen=1.5, anc=2.0, cortes_v=6, etq=0.6):
    return dict(
        quimeras=quim,
        fragmentacion=frag,
        equipo_mal_pct=mal,
        centroide_m=cen,
        anchura_m=anc,
        cortes_ventana=cortes_v,
        cambio_etiqueta=etq,
    )


def test_veredicto():
    import medir_guarda_caja_fundida as mg

    base = {"a": _m(), "b": _m()}
    azar = {
        "a": [_m(quim=3, frag=1.9, etq=0.2)] * 10,
        "b": [_m(quim=3, frag=1.9, etq=0.2)] * 10,
    }
    buena = {"a": _m(quim=2), "b": _m(quim=3)}
    assert mg.veredicto(base, buena, azar)["pasa"] is True
    # empeorar el centroide 2 cm suspende aunque todo lo demás mejore
    assert mg.veredicto(base, {**buena, "b": _m(cen=1.52)}, azar)["pasa"] is False
    # pocos cortes en una ventana: los puntos de MEJORA quedan sin decidir...
    poca = {"a": _m(quim=2), "b": _m(cortes_v=2)}
    v = mg.veredicto(base, poca, azar)
    assert v["b"]["5_gana_al_azar"] is None and v["suma_quimeras_baja"] is None
    assert v["pasa"] is None
    # ...pero un empeoramiento con pocos cortes sigue suspendiendo
    assert (
        mg.veredicto(base, {**poca, "b": _m(cortes_v=2, mal=1.5)}, azar)["pasa"]
        is False
    )
    # empatar con el azar no es ganarle
    assert (
        mg.veredicto(base, buena, {"a": [_m(quim=2)] * 10, "b": azar["b"]})["pasa"]
        is False
    )
