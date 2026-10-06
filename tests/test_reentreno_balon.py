"""Veredicto del reentreno del balón (scripts/medir_reentreno_balon.py y la medida A)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import colab_test_pool_balon as ta  # noqa: E402
import medir_reentreno_balon as mr  # noqa: E402


def test_acierto_dentro_del_radio_y_el_resto_son_falsos_positivos():
    gt = [
        (0.5, 0.5, 10 / 1920, 10 / 1080)
    ]  # caja de 10×10 px en (960, 540): radio 14,1
    assert ta.evaluar_imagen([(950, 530, 970, 550, 0.9)], gt, 1920, 1080) == (1, 0)
    assert ta.evaluar_imagen([(970, 550, 990, 570, 0.9)], gt, 1920, 1080) == (
        0,
        1,
    )  # 28 px
    dos = [(955, 535, 965, 545, 0.9), (958, 538, 968, 548, 0.8)]
    assert ta.evaluar_imagen(dos, gt, 1920, 1080) == (1, 1)  # el segundo es FP
    assert ta.evaluar_imagen([(1, 1, 5, 5, 0.9)], [], 1920, 1080) == (0, 1)  # sin balón


def test_radio_minimo_de_8_px():
    gt = [(0.5, 0.5, 2 / 1920, 2 / 1080)]  # diagonal 2,8 px → manda el mínimo de 8
    cerca = [(963, 542, 969, 548, 0.9)]  # centro a 7,8 px: dentro del mínimo
    lejos = [(964, 543, 970, 549, 0.9)]  # centro a 9,2 px: fuera
    assert ta.evaluar_imagen(cerca, gt, 1920, 1080) == (1, 0)
    assert ta.evaluar_imagen(lejos, gt, 1920, 1080) == (0, 1)


def _a(frames):
    return {"por_frame": {str(f): v for f, v in frames.items()}}


def test_resumen_a_con_y_sin_cercanos():
    fila = {
        "positivo": True,
        "v1": {"aciertos": 0, "fp": 1},
        "v2": {"aciertos": 1, "fp": 0},
    }
    a = _a({1586: fila, 100: fila, 200: {**fila, "positivo": False}})
    r, s = mr.resumen_a(a), mr.resumen_a(a, mr.CERCANOS_AL_ORIGINAL)
    assert (r["imagenes"], r["positivos"], r["balones_mas"]) == (3, 2, 3)
    assert (s["imagenes"], s["positivos"], s["balones_mas"]) == (2, 1, 2)
    assert r["fp_img_v1"] == 1.0 and r["fp_img_v2"] == 0.0


B1 = {"gt_desempates": 35, "cambios_min": 2.85, "en_marcas": 0.0, "anclada_s": 19.4,
      "tramos": {"t365": {"malo": 3}, "t990": {"malo": 1}}, "vuelo_recuperados": []}  # fmt: skip
A_OK = {"balones_mas": 6, "fp_img_v1": 0.20, "fp_img_v2": 0.30}


def test_veredicto_pasa_y_cada_punto_suspende():
    b2 = {**B1, "vuelo_recuperados": ["V03", "V08"]}
    c = {"n": 30, "real": 20, "basura": 5}
    assert mr.veredicto(A_OK, B1, b2, c)["pasa"] is True
    assert mr.veredicto({**A_OK, "balones_mas": 5}, B1, b2, c)["pasa"] is False
    assert mr.veredicto({**A_OK, "fp_img_v2": 0.31}, B1, b2, c)["pasa"] is False
    assert mr.veredicto(A_OK, B1, {**b2, "gt_desempates": 34}, c)["pasa"] is False
    assert mr.veredicto(A_OK, B1, {**b2, "cambios_min": 3.01}, c)["pasa"] is False
    assert mr.veredicto(A_OK, B1, {**b2, "en_marcas": 0.001}, c)["pasa"] is False
    malo = {**b2, "tramos": {"t365": {"malo": 4}, "t990": {"malo": 1}}}
    assert mr.veredicto(A_OK, B1, malo, c)["pasa"] is False
    assert (
        mr.veredicto(A_OK, B1, {**b2, "vuelo_recuperados": ["V03"]}, c)["pasa"] is False
    )
    assert (
        mr.veredicto(A_OK, B1, b2, {"n": 30, "real": 19, "basura": 0})["pasa"] is False
    )
    assert (
        mr.veredicto(A_OK, B1, b2, {"n": 30, "real": 25, "basura": 6})["pasa"] is False
    )


def test_veredicto_pendiente_sin_juicio_o_con_anclada_larga():
    b2 = {**B1, "vuelo_recuperados": ["V03", "V08"]}
    assert mr.veredicto(A_OK, B1, b2, None)["pasa"] is None
    v = mr.veredicto(
        A_OK, B1, {**b2, "anclada_s": 25.0}, {"n": 30, "real": 20, "basura": 0}
    )
    assert v["6_anclada"] is None and v["pasa"] is None
