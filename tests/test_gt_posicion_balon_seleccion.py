import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gt_posicion_balon import _elegir_espaciadas  # noqa: E402


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
