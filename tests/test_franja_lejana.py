"""La franja a trocear se DERIVA, no se escribe a mano.

El número fijo que había antes (540-720) estaba medido sobre la cámara del
benjamín, y es el tipo de número que no viaja entre partidos — como
`arbitro.margen_equipo` o las franjas de profundidad. Aquí el fallo además
sería silencioso: una banda heredada de otro encuadre trocearía césped
vacío, dejaría el fondo sin trocear, y el informe diría tranquilamente que
el esquema mixto no cierra huecos.

Por eso estos tests comprueban que la franja RESPONDE a la cámara y al
campo, no que valga un número concreto.
"""

import numpy as np
import pytest

from src.balon.franja_lejana import banda_a_trocear

ANCHO_IMG, ALTO_IMG = 1920, 1080
LARGO, ANCHO = 62.0, 40.0


def _homografia_benja():
    return np.load("data/calibracion_benja/homografia_benja.npy")


def _hay_homografia():
    from pathlib import Path

    return Path("data/calibracion_benja/homografia_benja.npy").exists()


saltar = pytest.mark.skipif(
    not _hay_homografia(), reason="necesita la homografía del benjamín"
)


# ────────────────── responde a la cámara, no es una constante ─────────────


@saltar
def test_la_franja_es_una_parte_pequena_de_la_imagen():
    """Si saliera casi la imagen entera, el esquema mixto no ahorraría."""
    y0, y1 = banda_a_trocear(
        _homografia_benja(), LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG
    )
    fraccion = (y1 - y0) / ALTO_IMG
    assert 0.05 < fraccion < 0.50, (
        f"la franja ocupa el {100 * fraccion:.0f} % del alto; con más de la "
        f"mitad el mixto deja de tener sentido frente a SAHI entero"
    )


@saltar
def test_mas_margen_de_campo_ensancha_la_franja():
    """El margen es un parámetro de verdad, no decorado."""
    corta = banda_a_trocear(
        _homografia_benja(), LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG, 0.0, 0.0
    )
    larga = banda_a_trocear(
        _homografia_benja(), LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG, 25.0, 0.0
    )
    assert larga[1] > corta[1], "el margen de campo no ensancha por abajo"
    assert larga[0] <= corta[0] + 1


@saltar
def test_el_margen_aereo_sube_el_borde_de_arriba():
    """Un balón por el aire aparece MÁS ARRIBA que su proyección de suelo."""
    sin_aire = banda_a_trocear(
        _homografia_benja(), LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG, 20.0, 0.0
    )
    con_aire = banda_a_trocear(
        _homografia_benja(), LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG, 20.0, 3.0
    )
    assert con_aire[0] < sin_aire[0], "el margen aéreo no hace nada"
    assert con_aire[1] == sin_aire[1], "el aire no debe tocar el borde de abajo"


@saltar
def test_una_camara_distinta_da_una_franja_distinta():
    """La guarda contra el número heredado: si la homografía cambia, la
    franja tiene que cambiar. Un valor fijo pasaría los demás tests."""
    H = _homografia_benja()
    otra = H.copy()
    otra[1, 2] += 150.0  # como si la cámara apuntase más abajo

    a = banda_a_trocear(H, LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG)
    b = banda_a_trocear(otra, LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG)
    assert a != b, "la franja NO depende de la homografía: es un número fijo"


@saltar
def test_un_campo_mas_largo_mueve_la_franja():
    """Las medidas del campo también mandan, no solo la cámara."""
    H = _homografia_benja()
    f7 = banda_a_trocear(H, 62.0, 40.0, 45.0, ALTO_IMG, ANCHO_IMG)
    f11 = banda_a_trocear(H, 100.0, 64.0, 45.0, ALTO_IMG, ANCHO_IMG)
    assert f7 != f11


# ─────────────────────────── se queja en vez de mentir ────────────────────


def test_una_homografia_degenerada_da_ERROR_no_una_franja_cualquiera():
    """Callarse aquí sería trocear la franja equivocada durante 29 min."""
    mala = np.array([[1e-9, 0, 0], [0, 1e-9, 0], [0, 0, 1.0]])
    with pytest.raises(ValueError):
        banda_a_trocear(mala, LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG)


@saltar
def test_la_franja_se_recorta_a_la_imagen():
    y0, y1 = banda_a_trocear(
        _homografia_benja(), LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG, 30.0, 5.0
    )
    assert 0 <= y0 < y1 <= ALTO_IMG


@saltar
def test_una_franja_que_se_come_la_imagen_da_ERROR():
    """Devolverla entera sería trocearlo todo creyendo que se ahorra, y
    nadie se enteraría hasta ver la factura de GPU."""
    with pytest.raises(ValueError, match="no ahorra nada"):
        banda_a_trocear(
            _homografia_benja(), LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG, 60.0, 30.0
        )


# ──────────────── y que cubra lo que tiene que cubrir en el benja ─────────


@saltar
@pytest.mark.skipif(
    not __import__("pathlib").Path("data/tracking_benja/cache_balon_p1.pkl").exists(),
    reason="necesita el caché de balón de la parte entera",
)
def test_la_franja_cubre_los_47_huecos_del_fondo():
    """El control con datos reales: los huecos que el mixto debe cerrar."""
    import pickle

    from src.balon.tracking_balon import filtrar_balon_plausible
    from src.campo_modelo import cargar_modelo

    modelo = cargar_modelo(config="configs/campo_benja.yaml")
    with open("data/tracking_benja/cache_balon_p1.pkl", "rb") as f:
        datos = pickle.load(f)
    dets = filtrar_balon_plausible(
        {e["frame_idx"]: e["dets"] for e in datos["cache"] if e["dets"]}, modelo
    )
    tiempos = {e["frame_idx"]: e["t"] for e in datos["cache"]}
    vistos = sorted(dets)
    huecos = [
        (a, b)
        for a, b in zip(vistos, vistos[1:])
        if 1.0 < tiempos[b] - tiempos[a] < 8.0 and dets[a][0][0] >= 45.0
    ]
    y0, y1 = banda_a_trocear(
        _homografia_benja(), LARGO, ANCHO, 45.0, ALTO_IMG, ANCHO_IMG
    )

    def centro_y(f):
        return (dets[f][0][3] + dets[f][0][5]) / 2

    dentro = sum(
        1 for a, b in huecos if y0 <= centro_y(a) <= y1 and y0 <= centro_y(b) <= y1
    )
    assert dentro == len(huecos), (
        f"la franja derivada solo cubre {dentro} de {len(huecos)} huecos del "
        f"fondo; con la fija de 540-720 el mixto se dejaba 5 sin cerrar"
    )
