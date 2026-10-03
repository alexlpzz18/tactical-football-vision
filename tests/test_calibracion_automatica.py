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


# ───────────────────────── el método (src/homography/auto_calibracion.py) ─────────────────────────
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from src.homography import auto_calibracion as ac  # noqa: E402

CAMARA = (-9.4, 18.7, 6.0, 137.0, 25.7, 0.0, 1690.0)  # ≈ la del benjamín


def _lineas_sinteticas(H, w=1920, h=1080, grosor=5):
    m = np.zeros((h, w), np.uint8)
    for seg in ac._polilineas_modelo(62.0, 40.0):
        px, delante = ac.proyectar(H, seg)
        if delante.all() and np.isfinite(px).all():
            cv2.polylines(m, [px.astype(np.int32)], False, 255, grosor)
    return m


def test_camara_a_homografia_proyecta_el_centro_en_el_eje_optico():
    H = ac.camara_a_homografia((-10, 20, 5, 31, 20, 0, 1500), 1920, 1080)
    px, delante = ac.proyectar(H, np.array([[31.0, 20.0]]))
    assert delante[0] and np.allclose(px[0], (960, 540), atol=1e-6)


def test_adelgazar_deja_una_linea_de_un_pixel():
    m = np.zeros((40, 200), np.uint8)
    m[15:22, 10:190] = 255
    esq = ac.adelgazar(m)
    filas = np.nonzero(esq[:, 50:150])[0]
    assert len(set(filas)) == 1 and 15 <= filas[0] <= 21


def test_canonica_pone_la_porteria_cercana_en_x0():
    H = ac.camara_a_homografia(CAMARA, 1920, 1080)
    rot = np.array([[-1, 0, 62.0], [0, -1, 40.0], [0, 0, 1.0]])
    assert np.allclose(ac.canonica(H @ rot, 62, 40), H)
    assert np.allclose(ac.canonica(H, 62, 40), H)


def test_recupera_una_camara_sintetica():
    H = ac.camara_a_homografia(CAMARA, 1920, 1080)
    lineas = _lineas_sinteticas(H)
    campo = np.full_like(lineas, 255)
    r = ac.calibrar(ac.preparar_desde_lineas(lineas, campo), 62.0, 40.0)
    m = np.array([[31, 20], [50, 7], [50, 33], [62, 20], [12, 20]], float)
    err = np.hypot(*(ac.proyectar(r.H_m2px, m)[0] - ac.proyectar(H, m)[0]).T)
    assert r.S > 0.9 and np.median(err) < 3.0, (r.S, err)
