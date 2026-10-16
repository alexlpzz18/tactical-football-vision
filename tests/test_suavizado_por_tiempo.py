"""Las variantes V1/V2/V3 del suavizado (scripts/suavizado_por_tiempo.py)."""

import importlib.util
from pathlib import Path

import numpy as np

from src.tracking.suavizado import ParametrosSuavizado, suavizar_trayectorias

_spec = importlib.util.spec_from_file_location(
    "suavizado_por_tiempo",
    Path(__file__).resolve().parent.parent / "scripts/suavizado_por_tiempo.py",
)
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

FPS, PASO = 30.0, 3
DT = PASO / FPS
PARAMS = ParametrosSuavizado(
    activo=True, ventana_s=0.5, metodo="media", escalar_con_resolucion=0
)


class _Resolucion:
    """m/píxel constante (para no depender de una homografía en el test)."""

    def __init__(self, mpp):
        self.mpp = mpp

    def metros_por_pixel(self, _pos):
        return self.mpp

    def factor(self, _pos):
        return 1.0


def _tray(frames, rng, salto_en=None, salto=0.0):
    pts = []
    for k, f in enumerate(frames):
        x = (
            30.0
            + 0.3 * k
            + rng.normal(0, 0.2)
            + (salto if salto_en is not None and k >= salto_en else 0)
        )
        pts.append((int(f), np.array([x, 20.0 + rng.normal(0, 0.2)]), True))
    return pts


def test_V1_sin_huecos_es_B0_byte_a_byte():
    rng = np.random.default_rng(1)
    trays = [_tray(range(0, 300, PASO), rng), _tray(range(900, 1020, PASO), rng)]
    b0 = suavizar_trayectorias(trays, PARAMS, resolucion=None, dt=DT)
    v1 = sp.suavizar_variante(trays, PARAMS, None, DT, "V1", FPS, [])
    for a, b in zip(b0, v1):
        assert all(np.array_equal(p[1], q[1]) for p, q in zip(a, b))


def test_V1_no_promedia_a_traves_de_un_hueco():
    rng = np.random.default_rng(2)
    frames = list(range(0, 60, PASO)) + list(range(600, 660, PASO))  # hueco de 18 s
    pts = np.array([p[1] for p in _tray(frames, rng)])
    pts[len(pts) // 2 :, 0] += 20.0  # tras el hueco está en otro sitio  # noqa: E203
    fr = np.array(frames)
    hoy = sp.media_movil(pts, 5)
    v1 = sp.media_por_tiempo(pts, fr, 5, PASO)
    k = len(pts) // 2  # primera muestra tras el hueco
    assert abs(hoy[k, 0] - pts[k, 0]) > 5  # hoy arrastra lo de antes del hueco
    assert abs(v1[k, 0] - pts[k, 0]) < 1  # V1 no
    assert np.array_equal(v1[2], hoy[2])  # lejos del hueco, idéntico


def test_umbral_local_corta_el_salto_y_no_el_paso_normal():
    res = _Resolucion(0.4)  # fondo: 0,4 m/px → umbral 8,5 + 3·3,5·0,4/0,1 = 50,5 m/s
    assert abs(sp.umbral_local((50, 20), DT, res) - 50.5) < 1e-9
    pts = np.array([[50.0, 20.0], [50.5, 20.0], [57.0, 20.0], [57.4, 20.0]])
    cortes, pasos = sp.cortes_v2(pts, np.array([0, 3, 6, 9]), FPS, res)
    assert cortes == [1]  # 6,5 m en 0,1 s = 65 m/s > 50,5; los otros, 5 y 4 m/s
    assert [p[2] for p in pasos] == [False, True, False]


def test_el_mismo_salto_cerca_de_la_camara_tambien_se_corta_y_el_temblor_del_fondo_no():
    cerca, fondo = _Resolucion(0.025), _Resolucion(0.42)
    pts = np.array([[5.0, 20.0], [6.6, 20.0]])  # 16 m/s
    assert sp.cortes_v2(pts, np.array([0, 3]), FPS, cerca)[0] == [0]  # umbral 11,1
    assert (
        sp.cortes_v2(pts, np.array([0, 3]), FPS, fondo)[0] == []
    )  # umbral 52,6: temblor


def test_V2_sin_cortes_es_B0_y_con_un_salto_no_lo_cruza():
    rng = np.random.default_rng(3)
    res = _Resolucion(0.1)  # umbral 19 m/s: el ruido sintético (0,2 m) no lo alcanza
    sin = [_tray(range(0, 300, PASO), rng)]
    b0 = suavizar_trayectorias(sin, PARAMS, resolucion=None, dt=DT)
    v2 = sp.suavizar_variante(sin, PARAMS, res, DT, "V2", FPS, [])
    assert all(np.array_equal(p[1], q[1]) for p, q in zip(b0[0], v2[0]))
    con = [_tray(range(0, 300, PASO), rng, salto_en=50, salto=15.0)]
    b0 = suavizar_trayectorias(con, PARAMS, resolucion=None, dt=DT)
    registro = []
    v2 = sp.suavizar_variante(con, PARAMS, res, DT, "V2", FPS, registro)
    assert sum(p[2] for p in registro) == 1
    # la primera muestra tras el salto: hoy queda arrastrada hacia atrás; V2 no
    assert abs(b0[0][50][1][0] - con[0][50][1][0]) > 3
    assert abs(v2[0][50][1][0] - con[0][50][1][0]) < 1


def test_la_huella_cambia_si_cambia_la_entrada():
    rng = np.random.default_rng(4)
    t = [_tray(range(0, 30, PASO), rng)]
    t2 = [list(t[0])]
    t2[0][3] = (t2[0][3][0], t2[0][3][1] + 0.001, True)
    assert sp.huella(t) == sp.huella([list(t[0])])
    assert sp.huella(t) != sp.huella(t2)


def _res(v1_lejos_ic, v1_temblor_ic, ruido_v2=False, control=True):
    vari = {
        "1_lejos_todas": {"dif_IC": v1_lejos_ic},
        "4_temblor_franja2": {"dif_IC": v1_temblor_ic},
    }
    base = {"1_lejos_todas": {"dif_IC": (0.0, -0.01, 0.01)}}
    return {
        "benja": {
            "controles": {
                "entrada_al_suavizado_identica": control,
                "filas_por_id_igual_que_B0": {"V1": True, "V2": True, "V3": True},
            },
            "variantes": {
                "V1": vari,
                "V2": {**base, "corta_ruido": ruido_v2},
                "V3": base,
            },
        }
    }


def test_veredicto_del_criterio():
    v = sp.veredicto_de(_res((-0.02, -0.03, -0.01), (0.0, -0.01, 0.01)))
    assert v["V1"]["veredicto"].startswith("PASA")
    assert v["V3"]["veredicto"].startswith("NO SE ADOPTA (no mejora")
    v = sp.veredicto_de(_res((-0.02, -0.03, -0.01), (0.01, 0.005, 0.02)))
    assert v["V1"]["veredicto"].startswith(
        "NO SE ADOPTA (empeora"
    )  # el temblor sube con IC
    v = sp.veredicto_de(_res((-0.02, -0.03, -0.01), (0.0, -0.01, 0.01), ruido_v2=True))
    assert v["V2"]["veredicto"].startswith("NO SE LEE COMO MEJORA")
    v = sp.veredicto_de(_res((-0.02, -0.03, -0.01), (0.0, -0.01, 0.01), control=False))
    assert all(x["veredicto"].startswith("NO CONCLUYENTE") for x in v.values())
