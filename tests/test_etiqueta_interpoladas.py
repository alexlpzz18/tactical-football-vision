"""Una fila INTERPOLADA del CSV no puede llevar una etiqueta ajena a sus dos vecinas reales.

Hasta el 30-oct-2026 el escritor del CSV (`processor.py::exportar_posiciones`) daba a las filas
interpoladas el VOTO de su identidad. Las filas reales llevan la etiqueta por observación, así que
una identidad cuyas observaciones decían B y cuyo voto era A destellaba A en cada hueco: 29 «islas»
y 58 de los 132 cambios de color de la pizarra de 14:00-15:30 (docs/pizarra_sin_identidades.md,
docs/fix_interpoladas.md). Era la moda de la identidad colándose en el dibujo, solo en los huecos.

La guarda mira el CSV ESCRITO, no la función: comprueba el resultado, no cómo se calcula. Y se
comprueba que muerde: con el método antiguo (`etiqueta_interpoladas: identidad`) tiene que fallar.
"""

import numpy as np
import pandas as pd
import pytest

from src.tracking_data.processor import etiquetas_de_la_identidad, exportar_posiciones


def interpoladas_con_etiqueta_ajena(df: pd.DataFrame) -> list[tuple[int, int]]:
    """(id_jugador, frame) de las interpoladas con etiqueta distinta de SUS DOS vecinas reales."""
    malas = []
    for i, g in df.sort_values("frame").groupby("id_jugador"):
        e = g.etiqueta.astype(str).to_numpy()
        r = g.es_real.to_numpy() == 1
        f = g.frame.to_numpy()
        reales = np.where(r)[0]
        for k in np.where(~r)[0]:
            antes, despues = reales[reales < k], reales[reales > k]
            vecinas = {e[antes[-1]]} if len(antes) else set()
            vecinas |= {e[despues[0]]} if len(despues) else set()
            if vecinas and e[k] not in vecinas:
                malas.append((int(i), int(f[k])))
    return malas


def _escribir(tmp_path, modo):
    """Dos identidades sintéticas con voto A y observaciones que dicen otra cosa."""
    p = np.array([10.0, 10.0])
    trayectorias = [
        # id 1: todas sus observaciones dicen B; el voto dice A. Un hueco de 2 filas.
        [(0, p, True), (3, p, True), (6, p, False), (9, p, False), (12, p, True)],
        # id 2: A antes del hueco y B después; 3 filas en el hueco (la del centro, empate).
        [(0, p, True), (3, p, False), (6, p, False), (9, p, False), (12, p, True)],
    ]
    etiquetas_por_obs = {
        (1, 0): "B",
        (1, 3): "B",
        (1, 12): "B",
        (2, 0): "A",
        (2, 12): "B",
    }
    cfg = {
        "campo_m": {"largo": 62.0, "ancho": 40.0, "margen": 5.0},
        "tracking": {"perfil": "bytetrack"},
        "rutas": {
            "homografia": "data/calibracion_benja/homografia_benja.npy",
            "salida_csv": str(tmp_path / f"pos_{modo}.csv"),
            "salida_meta": str(tmp_path / f"meta_{modo}.json"),
        },
        "exportacion": {"etiqueta_interpoladas": modo},
    }
    datos = {"fps": 30.0, "sample": 3, "wh": (100, 100), "cache": []}
    return exportar_posiciones(
        trayectorias,
        {1: "A", 2: "A"},
        datos,
        cfg,
        trayectorias=trayectorias,
        etiquetas_por_obs=etiquetas_por_obs,
    )


def test_ninguna_interpolada_lleva_una_etiqueta_ajena_a_sus_vecinas(tmp_path):
    df = _escribir(tmp_path, "vecina_real")
    assert interpoladas_con_etiqueta_ajena(df) == []


def test_la_guarda_MUERDE_con_el_metodo_antiguo(tmp_path):
    """Prueba de mutación permanente: con el voto de la identidad, la guarda tiene que saltar."""
    df = _escribir(tmp_path, "identidad")
    assert interpoladas_con_etiqueta_ajena(df) == [(1, 6), (1, 9)]


def test_la_clave_del_yaml_CAMBIA_el_csv(tmp_path):
    """Un interruptor que nadie lee es peor que no tenerlo: cambiarlo tiene que mover el CSV."""
    nuevo = _escribir(tmp_path, "vecina_real")
    antiguo = _escribir(tmp_path, "identidad")
    assert not nuevo.etiqueta.equals(antiguo.etiqueta)
    # y solo cambian las filas interpoladas
    reales = nuevo.es_real == 1
    assert nuevo[reales].equals(antiguo[reales])
    for c in ("frame", "tiempo_s", "id_jugador", "x_m", "y_m", "es_real"):
        assert nuevo[c].equals(antiguo[c])


def test_vecina_mas_cercana_y_empate_a_la_anterior():
    p = np.array([0.0, 0.0])
    obs = [(0, p, True), (3, p, False), (6, p, False), (9, p, False), (12, p, True)]
    et = etiquetas_de_la_identidad(obs, 2, "A", {(2, 0): "A", (2, 12): "B"})
    # 3 está a 3 de la anterior; 6, empate (6 y 6): la anterior; 9, a 3 de la siguiente
    assert et == ["A", "A", "A", "B", "B"]


def test_fila_real_sin_etiqueta_por_observacion_usa_el_voto():
    """Porteros y staff no tienen etiqueta por observación: la vecina real lleva el voto."""
    p = np.array([0.0, 0.0])
    obs = [(0, p, True), (3, p, False), (6, p, True)]
    et = etiquetas_de_la_identidad(obs, 7, "portero_A", {})
    assert et == ["portero_A", "portero_A", "portero_A"]


def test_modo_desconocido_falla_en_alto():
    with pytest.raises(ValueError):
        etiquetas_de_la_identidad([], 1, "A", {}, modo="vecina")
