"""El STAFF no cuenta como "jugador" para el balón (docs/selector_balon.md, 1a).

El desempate del selector gana por cercanía a un jugador. Con el entrenador
contando como jugador, el objeto que tuviera a los pies (su zapato) ganaba al
balón del partido. Estos tests fijan que el staff queda fuera y que el
interruptor `excluir_etiquetas` de verdad cambia el resultado.
"""

import pandas as pd

from src.balon.carga import jugadores_por_frame_de_balon
from src.balon.tracking_balon import ParametrosBalon, seleccionar_balon_activo

# El staff afecta al desempate por cercanía, que sigue decidiendo el ORDEN de
# los candidatos; se prueba frame a frame para aislarlo. La selección por
# continuidad tiene sus tests en test_seleccion_por_continuidad.py.
FRAME_A_FRAME = ParametrosBalon(continuidad_activa=False)

DT = 1 / 15.0


def _det(mx, my, conf=0.8):
    return (mx, my, 100.0, 100.0, 108.0, 108.0, conf)


def _csv_con_entrenador(tmp_path, n):
    """Un jugador A en (30, 20) y el entrenador (staff) en (5, 0), cada frame."""
    filas = []
    for k in range(n):
        t = round(k * DT, 2)
        filas.append((k, t, 1, 0, "A", 30.0, 20.0, 1))
        filas.append((k, t, 9, 3, "staff", 5.0, 0.0, 1))
    ruta = tmp_path / "jug.csv"
    pd.DataFrame(
        filas,
        columns=[
            "frame",
            "tiempo_s",
            "id_jugador",
            "equipo",
            "etiqueta",
            "x_m",
            "y_m",
            "es_real",
        ],
    ).to_csv(ruta, index=False)
    return ruta


def test_el_staff_no_aparece_entre_los_jugadores_del_balon(tmp_path):
    n = 5
    tiempos = {k: k * DT for k in range(n)}
    jug = jugadores_por_frame_de_balon(
        _csv_con_entrenador(tmp_path, n), tiempos, range(n)
    )
    assert all([j[2] for j in jug[k]] == [1] for k in range(n))


def test_el_interruptor_vacio_recupera_el_comportamiento_anterior(tmp_path):
    """Un interruptor que nadie lee es peor que no tenerlo: apagarlo tiene
    que cambiar lo que sale."""
    n = 5
    tiempos = {k: k * DT for k in range(n)}
    jug = jugadores_por_frame_de_balon(
        _csv_con_entrenador(tmp_path, n), tiempos, range(n), excluir_etiquetas=()
    )
    assert all(sorted(j[2] for j in jug[k]) == [1, 9] for k in range(n))


def test_un_candidato_junto_al_staff_pierde_contra_uno_junto_a_un_jugador(tmp_path):
    """El caso del zapato: el candidato pegado al entrenador está a 0,3 m de él
    y el balón a 1,5 m del jugador. Con el staff contando, ganaba el zapato."""
    n = 20
    tiempos = {k: k * DT for k in range(n)}
    ruta = _csv_con_entrenador(tmp_path, n)
    # El balón se mueve (no lo quita la guarda de "quieto y lejos"); el zapato no.
    dets = {k: [_det(31.5 + 0.2 * k, 20.0), _det(5.3, 0.0, conf=0.9)] for k in range(n)}

    def elegido(excluir):
        jug = jugadores_por_frame_de_balon(
            ruta, tiempos, dets, excluir_etiquetas=excluir
        )
        pos = {f: [(j[0], j[1]) for j in jug[f]] for f in dets}
        return seleccionar_balon_activo(dets, pos, FRAME_A_FRAME)

    sin_staff, con_staff = elegido(("staff",)), elegido(())
    assert all(sin_staff[k][0] > 30 for k in range(n))
    assert all(con_staff[k][0] < 6 for k in range(n))
