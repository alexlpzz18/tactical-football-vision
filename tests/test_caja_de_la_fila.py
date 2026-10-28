"""La caja que dibuja una hoja de revisión tiene que ser la detección de la FILA.

docs/auditoria_hojas.md: la hoja `equipo_por_obs_20min` elegía «la detección más cercana a la
posición del CSV». Esa posición está suavizada, y en un cruce cae más cerca del OTRO jugador: 11 de
120 filas enseñaron la caja de otra persona, y 10 de los 12 «errores» eran de la herramienta.
"""

import importlib.util
from pathlib import Path

import pandas as pd

R = Path(__file__).resolve().parent.parent


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _cruce():
    """Un frame con un cruce: la fila es del jugador 1, pero su posición suavizada está pegada al 2.

    El caché CRUDO tiene además una detección de baja confianza al principio, que el filtrado quita:
    así los índices del crudo y del filtrado NO coinciden, como en producción.
    """
    f = 30
    basura = (50.0, 5.0, 100, 100, 110, 120, 0.1)
    jugador1 = (10.0, 10.0, 500, 300, 520, 350, 0.9)  # su pie proyecta a (10, 10)
    jugador2 = (11.0, 10.0, 530, 300, 550, 350, 0.9)  # el rival, a 1 m
    crudo = {f: [basura, jugador1, jugador2]}
    filtrado = {f: [jugador1, jugador2]}
    # tracker: identidad 1 = jugador1 (índice 0 del filtrado); identidad 2 = jugador2
    identidades = [[(f, 0)], [(f, 1)]]
    # la posición SUAVIZADA de la identidad 1 cae a 0,2 m del jugador 2
    filas = pd.DataFrame(
        [{"frame": f, "id_jugador": 1, "x_m": 10.8, "y_m": 10.0, "es_real": 1}]
    )
    return filas, identidades, filtrado, crudo


def test_la_caja_es_la_deteccion_de_la_fila():
    filas, identidades, filtrado, crudo = _cruce()
    hoja = _mod("hoja_otro_v3")
    assert hoja.deteccion_de_la_fila(filas, identidades, filtrado, crudo) == [1]
    r = hoja.con_caja_de_la_fila(filas, identidades, filtrado, crudo)
    assert list(r.k) == [1]


def test_el_metodo_antiguo_dibuja_al_otro():
    """El control: con «la más cercana» la hoja habría enseñado al jugador 2 (índice crudo 2)."""
    filas, _identidades, _filtrado, crudo = _cruce()
    antiguo = _mod("diag22b_bloque3_medir").caja_cruda_mas_cercana(filas, crudo)
    assert antiguo == [2]


def test_fila_sin_deteccion_no_se_dibuja():
    """Una fila interpolada (la identidad no tiene detección en ese frame) no tiene caja."""
    filas, identidades, filtrado, crudo = _cruce()
    filas["id_jugador"] = 3  # no está en `identidades`
    hoja = _mod("hoja_otro_v3")
    assert hoja.deteccion_de_la_fila(filas, identidades, filtrado, crudo) == [None]
    assert len(hoja.con_caja_de_la_fila(filas, identidades, filtrado, crudo)) == 0
