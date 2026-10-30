"""La lente nueva tiene que recuperar una cámara conocida y coincidir con OpenCV.

docs/lente_f11.md. Si el ajuste no recupera una lente sintética, sus números sobre clics reales no
significan nada. Y el modelo propio tiene que proyectar igual que `cv2.fisheye` y
`cv2.projectPoints`, porque el ajuste no los llama.
"""

import importlib.util
from pathlib import Path

import cv2
import numpy as np
import pytest

R = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "lente_camara", R / "scripts/lente_camara.py"
)
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)


def _verdad(tipo="ojo_pez") -> lc.Camara:
    """Cámara en la tribuna, a media altura de campo, mirando hacia abajo."""
    coefs = np.array([0.05, -0.02, 0.01, -0.002]) if tipo == "ojo_pez" else None
    if tipo == "racional":
        coefs = np.array([-0.2, 0.05, 0.0, 0.1, 0.01, 0.0])
    Rm = cv2.Rodrigues(np.array([np.radians(102.0), 0.0, 0.0]))[0]  # 12° hacia abajo
    C = np.array([50.0, -12.0, 9.0])  # posición de la cámara en el mundo
    return lc.Camara(
        tipo, 900.0, 1290.0, 525.0, coefs, cv2.Rodrigues(Rm)[0].ravel(), -Rm @ C
    )


def _clics(cam: lc.Camara, ruido=0.0, semilla=0) -> lc.Clics:
    g = np.random.default_rng(semilla)
    m = np.array(
        [[0, 0], [100, 0], [0, 64], [100, 64], [50, 0], [50, 64], [16.5, 11.84], [16.5, 52.16],
         [83.5, 11.84], [83.5, 52.16], [0, 11.84], [0, 52.16], [100, 11.84], [100, 52.16],
         [50, 32], [11, 32], [89, 32]], float,
    )  # fmt: skip
    lineas = [
        ((0, 0), (100, 0)),
        ((0, 64), (100, 64)),
        ((50, 0), (50, 64)),
        ((0, 0), (0, 64)),
        ((100, 0), (100, 64)),
        ((16.5, 11.84), (16.5, 52.16)),
        ((83.5, 11.84), (83.5, 52.16)),
    ]
    px, a, b, nom = [], [], [], []
    for n, (p, q) in enumerate(lineas):
        for s in (0.15, 0.35, 0.55, 0.75, 0.9):
            xy = np.array(p) + s * (np.array(q) - np.array(p))
            px.append(cam.proyectar(xy)[0])
            a.append(p)
            b.append(q)
            nom.append(f"l{n}")
    cruces = cam.proyectar(m)
    lpx = np.array(px)
    if ruido:
        cruces = cruces + g.normal(0, ruido, cruces.shape)
        lpx = lpx + g.normal(0, ruido, lpx.shape)
    return lc.Clics(
        cruces,
        m,
        [f"c{i}" for i in range(len(m))],
        lpx,
        np.array(a, float),
        np.array(b, float),
        nom,
    )


@pytest.mark.parametrize("tipo", ["ojo_pez", "racional"])
def test_proyectar_coincide_con_opencv(tipo):
    cam = _verdad(tipo)
    xy = np.array([[10.0, 5.0], [50.0, 32.0], [90.0, 60.0], [30.0, 10.0]])
    P = np.column_stack([xy, np.zeros(4)]).astype(np.float64)
    K = np.array([[cam.f, 0, cam.cx], [0, cam.f, cam.cy], [0, 0, 1.0]])
    if tipo == "ojo_pez":
        ref = cv2.fisheye.projectPoints(P[None], cam.rvec, cam.tvec, K, cam.coefs)[0][0]
    else:
        k = cam.coefs
        d = np.array([k[0], k[1], 0, 0, k[2], k[3], k[4], k[5]])
        ref = cv2.projectPoints(P, cam.rvec, cam.tvec, K, d)[0].reshape(-1, 2)
    assert np.abs(cam.proyectar(xy) - ref).max() < 1e-6


@pytest.mark.parametrize("tipo", ["ojo_pez", "racional"])
def test_ida_y_vuelta_pixel_metros(tipo):
    cam = _verdad(tipo)
    xy = np.array([[2.0, 3.0], [50.0, 32.0], [97.0, 60.0], [20.0, 1.0], [80.0, 1.0]])
    assert np.abs(cam.pixel_a_metros(cam.proyectar(xy)) - xy).max() < 0.02


def test_recupera_la_camara_sin_ruido_y_con_ruido_de_clic():
    verdad = _verdad()
    prueba = np.array(
        [[5.0, 2.0], [95.0, 2.0], [50.0, 20.0], [30.0, 60.0], [70.0, 45.0]]
    )

    cam, _ = lc.ajustar("ojo_pez", _clics(verdad))
    assert np.abs(cam.proyectar(prueba) - verdad.proyectar(prueba)).max() < 0.5

    # Con 2 px de ruido de clic, en puntos que no se clicaron: < 0,5 m salvo en la banda lejana,
    # donde 1 px son ~0,3 m de fondo y 2 px de ruido valen físicamente unos 0,6 m.
    cam, info = lc.ajustar("ojo_pez", _clics(verdad, ruido=2.0))
    assert info["residuo_px_mediana"] < 4
    e = np.linalg.norm(cam.pixel_a_metros(verdad.proyectar(prueba)) - prueba, axis=1)
    lejanos = prueba[:, 1] > 40
    assert e[~lejanos].max() < 0.5
    assert e[lejanos].max() < 1.0


def test_las_lineas_aportan_medir_la_lente_sin_saber_el_metro():
    """Con pocos cruces, los puntos de línea (sin metro conocido) tienen que ajustar la lente."""
    verdad = _verdad()
    todo = _clics(verdad, ruido=1.0)
    pocos = [0, 1, 2, 3, 6, 8]
    sin_lineas = lc.Clics(
        todo.cruces_px[pocos], todo.cruces_m[pocos], [todo.nombres[i] for i in pocos],
        np.zeros((0, 2)), np.zeros((0, 2)), np.zeros((0, 2)), [],
    )  # fmt: skip
    con_lineas = lc.Clics(
        todo.cruces_px[pocos], todo.cruces_m[pocos], sin_lineas.nombres,
        todo.lineas_px, todo.lineas_a, todo.lineas_b, todo.lineas_nombre,
    )  # fmt: skip
    prueba = np.array([[50.0, 32.0], [30.0, 40.0], [70.0, 20.0], [50.0, 2.0]])
    err = {}
    for nombre, c in (("sin", sin_lineas), ("con", con_lineas)):
        cam, _ = lc.ajustar("ojo_pez", c)
        err[nombre] = np.linalg.norm(
            cam.pixel_a_metros(verdad.proyectar(prueba)) - prueba, axis=1
        ).max()
    assert err["con"] < err["sin"]
    assert err["con"] < 0.6


def test_la_correccion_actual_se_dobla_a_unos_840_px():
    """El fallo que se quiere quitar, medido: más allá del pliegue no es representable."""
    centro = np.array([1280.0, 532.0])
    dentro = centro + [800.0, 0.0]
    fuera = centro + [900.0, 0.0]
    assert np.isfinite(lc.original_a_corregida(dentro[None])).all()
    assert np.isnan(lc.original_a_corregida(fuera[None])).all()


def test_ida_y_vuelta_corregida_original():
    """Debe ser el polinomio exacto de cv2.undistort: un píxel corregido vuelve a su sitio."""
    p = np.array([[1297.0, 558.0], [318.0, 603.0], [2317.0, 624.0], [1289.0, 823.0]])
    assert np.abs(lc.original_a_corregida(lc.corregida_a_original(p)) - p).max() < 0.05


def test_corregida_a_original_es_lo_que_hace_cv2_undistort():
    """Un punto blanco en el original tiene que aparecer en la corregida donde dice la fórmula."""
    img = np.zeros((1064, 2560), np.uint8)
    corr_p = np.array([[900.0, 600.0]])
    u, v = lc.corregida_a_original(corr_p)[0]
    cv2.circle(img, (int(round(u)), int(round(v))), 3, 255, -1)
    K = np.array([[2560.0, 0, 1280.0], [0, 2560.0, 532.0], [0, 0, 1]])
    salida = cv2.undistort(img, K, np.array([-1.5, 0.5, 0, 0, 0.0]))
    ys, xs = np.nonzero(salida > 100)
    assert abs(xs.mean() - 900) < 2 and abs(ys.mean() - 600) < 2


def test_rechaza_una_lente_que_se_dobla():
    cam = _verdad()
    cam.coefs = np.array([-0.6, 0.0, 0.0, 0.0])
    assert not cam.es_monotona()
    assert _verdad().es_monotona()


def test_medidas_libres_recupera_un_campo_que_no_mide_100x64():
    """Si el campo mide 96 × 60, el ajuste con medidas libres tiene que decirlo."""
    verdad = _verdad()
    limpio = _clics(verdad)
    real = lc.Clics(
        verdad.proyectar(lc.ajustar_medidas(limpio.cruces_m, 96.0, 60.0)),
        limpio.cruces_m, limpio.nombres, np.zeros((0, 2)), np.zeros((0, 2)), np.zeros((0, 2)), [],
    )  # fmt: skip
    _cam, info = lc.ajustar("ojo_pez", real, medidas_libres=True)
    assert abs(info["medidas_estimadas_m"][0] - 96) < 1.5
    assert abs(info["medidas_estimadas_m"][1] - 60) < 1.5
