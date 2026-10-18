import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gt_posicion_balon import _construir_casos, _elegir_espaciadas  # noqa: E402


def test_respeta_la_separacion_minima():
    items = [(0, 0.0), (1, 2.0), (2, 4.0), (3, 20.0), (4, 22.0)]
    elegidos = _elegir_espaciadas(
        items, n=10, min_separacion_s=10.0, clave_t=lambda x: x[1]
    )
    tiempos = [clave for _, clave in elegidos]
    assert all(
        abs(a - b) >= 10.0
        for i, a in enumerate(tiempos)
        for b in tiempos[i + 1 :]  # noqa: E203
    )


def test_se_para_en_n():
    items = [(i, i * 100.0) for i in range(10)]
    elegidos = _elegir_espaciadas(
        items, n=3, min_separacion_s=1.0, clave_t=lambda x: x[1]
    )
    assert len(elegidos) == 3


def test_lista_vacia_da_lista_vacia():
    assert (
        _elegir_espaciadas([], n=5, min_separacion_s=1.0, clave_t=lambda x: x[1]) == []
    )


def test_todos_demasiado_juntos_da_solo_el_primero():
    items = [(i, i * 0.1) for i in range(20)]
    elegidos = _elegir_espaciadas(
        items, n=10, min_separacion_s=5.0, clave_t=lambda x: x[1]
    )
    assert len(elegidos) == 1


def test_el_ancla_del_grupo_candidato_bajo_es_en_PIXELES_no_en_metros():
    # Bug real (1-oct-2026): se usaba det[0], det[1] (METROS, formato del
    # caché) como si fueran píxeles, así que los 20 recortes del grupo A
    # salían pegados a la esquina (0,0) por el clip de _recortar().
    det = (45.0, 30.0, 900.0, 600.0, 920.0, 620.0, 0.4)  # mx, my, x1, y1, x2, y2, conf
    grupo_a = [(100, 3.33, det)]
    casos = _construir_casos(grupo_a, [], [], ancho_video=1920, alto_video=1080)
    _nombre, _grupo, _frame, _t, cx, cy = casos[0]
    # Centro real de la caja en píxeles: ((900+920)/2, (600+620)/2) = (910, 610)
    assert cx == 910.0
    assert cy == 610.0


def test_el_ancla_del_grupo_hueco_cerca_marca_usa_el_punto_del_vecino():
    vecino = (3.33, (10, 20), 500.0, 300.0)  # t, celda, px, py
    grupo_b_cerca = [(100, 3.33, vecino)]
    casos = _construir_casos([], grupo_b_cerca, [], ancho_video=1920, alto_video=1080)
    _nombre, _grupo, _frame, _t, cx, cy = casos[0]
    assert (cx, cy) == (500.0, 300.0)


def test_el_ancla_del_grupo_hueco_lejos_marca_es_el_centro_del_video():
    grupo_b_lejos = [(100, 3.33, None)]
    casos = _construir_casos([], [], grupo_b_lejos, ancho_video=1920, alto_video=1080)
    _nombre, _grupo, _frame, _t, cx, cy = casos[0]
    assert (cx, cy) == (960.0, 540.0)
