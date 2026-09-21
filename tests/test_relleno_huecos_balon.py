"""El relleno de huecos de balón mantiene la posición SOLO donde acierta.

Sale de una etiqueta de Alex en el GT de huecos (caso 4: *"el balón está
quieto exactamente en el mismo sitio... pero lo tapan los jugadores"*) y
de la medición de `docs/relleno_de_huecos_balon.md`.

⚠️ Estos tests comprueban COMPORTAMIENTO, no ortografía. El fallo canónico
del proyecto es una guarda que se esquiva renombrando algo, así que aquí
se exige que apagar el interruptor CAMBIE el resultado, y que el relleno
se vea desde la función pública —no solo desde la privada—, porque un
tratamiento anunciado en un docstring y nunca ejecutado es justo el bug
que este cambio arregla.
"""

import numpy as np
import pytest

from src.balon.tracking_balon import (
    ParametrosBalon,
    _rellenar_huecos_parados,
    preparar_para_replay,
)

FPS = 29.97


def _tiempos(frames):
    return {f: f / FPS for f in frames}


def _serie(posiciones, primer_frame=0, paso=2):
    """[(frame, pos, es_aereo, es_real)] a partir de una lista de (x, y)."""
    return [
        (primer_frame + i * paso, np.array(p, dtype=float), False, True)
        for i, p in enumerate(posiciones)
    ]


# ─────────────────── la regla, sobre la función privada ───────────────────


def test_rellena_un_hueco_corto_con_el_balon_parado():
    """Balón quieto y hueco de 0,27 s: se mantiene la última posición."""
    salida = _serie([(30.0, 20.0)] * 4) + _serie([(30.0, 20.0)], primer_frame=14)
    todos = list(range(0, 16, 2))
    resultado = _rellenar_huecos_parados(salida, _tiempos(todos), ParametrosBalon())

    frames = [f for f, *_ in resultado]
    assert frames == todos, "faltan los frames del hueco"
    metidos = [t for t in resultado if t[0] in (8, 10, 12)]
    assert len(metidos) == 3
    for _f, pos, es_aereo, es_real in metidos:
        assert pos == pytest.approx([30.0, 20.0]), "no mantiene la última posición"
        assert es_real is False, "un relleno NO puede ir marcado como medido"
        assert es_aereo is False


def test_no_rellena_si_el_balon_venia_volando():
    """Rápido = la zona prohibida: 22 % de acierto y cola de 15,4 m."""
    # 1,2 m por paso de 0,067 s ≈ 18 m/s, muy por encima de los 4 m/s.
    veloz = [(10.0 + 1.2 * i, 20.0) for i in range(4)]
    salida = _serie(veloz) + _serie([(30.0, 20.0)], primer_frame=14)
    resultado = _rellenar_huecos_parados(
        salida, _tiempos(range(0, 16, 2)), ParametrosBalon()
    )

    assert [f for f, *_ in resultado] == [0, 2, 4, 6, 14], "ha rellenado volando"


def test_no_rellena_un_hueco_largo_aunque_este_parado():
    """0,4 s es el centro de la meseta; a partir de 0,6 s el acierto cae."""
    salida = _serie([(30.0, 20.0)] * 4) + _serie([(30.0, 20.0)], primer_frame=60)
    resultado = _rellenar_huecos_parados(
        salida, _tiempos(range(0, 62, 2)), ParametrosBalon()
    )

    assert [f for f, *_ in resultado] == [0, 2, 4, 6, 60], "ha rellenado 1,8 s"


def test_no_rellena_partiendo_de_una_posicion_aerea():
    """En vuelo la posición proyectada no es de fiar: no se mantiene."""
    salida = _serie([(30.0, 20.0)] * 3)
    salida.append((6, np.array([30.0, 20.0]), True, False))  # despegue
    salida += _serie([(30.0, 20.0)], primer_frame=14)
    resultado = _rellenar_huecos_parados(
        salida, _tiempos(range(0, 16, 2)), ParametrosBalon()
    )

    assert [f for f, *_ in resultado] == [0, 2, 4, 6, 14]


def test_no_rellena_sin_pasos_previos_con_los_que_juzgar():
    """Sin un paso anterior no se puede comprobar que estaba parado.

    Aísla la regla de MANTENER: con el futuro conocido (docs/balon_con_futuro.md)
    la recta entre anclas sí puede rellenar aquí, así que se apaga.
    """
    salida = _serie([(30.0, 20.0)]) + _serie([(30.0, 20.0)], primer_frame=6)
    resultado = _rellenar_huecos_parados(
        salida,
        _tiempos(range(0, 8, 2)),
        ParametrosBalon(interp_futuro_max_hueco_s=0.0),
    )

    assert [f for f, *_ in resultado] == [0, 6]


def test_no_toca_ninguna_posicion_medida():
    """El relleno añade; jamás reescribe una medida real."""
    salida = _serie([(30.0, 20.0)] * 4) + _serie([(30.5, 20.0)], primer_frame=14)
    antes = {f: (tuple(p), r) for f, p, _a, r in salida}
    resultado = _rellenar_huecos_parados(
        salida, _tiempos(range(0, 16, 2)), ParametrosBalon()
    )

    for f, pos, _aereo, es_real in resultado:
        if f in antes:
            assert (tuple(pos), es_real) == antes[f], f"el frame {f} se ha modificado"


# ───────────────── el interruptor: apagarlo CAMBIA el resultado ─────────────


@pytest.mark.parametrize(
    "apagado",
    [
        ParametrosBalon(max_hueco_relleno_s=0.0, interp_futuro_max_hueco_s=0.0),
        ParametrosBalon(vel_max_relleno_m_s=0.0, interp_futuro_max_hueco_s=0.0),
    ],
)
def test_apagar_cualquiera_de_los_dos_umbrales_apaga_el_relleno(apagado):
    """Un interruptor que nadie lee da una falsa sensación de control.

    Con la interpolación al futuro también apagada: aquí se prueba la regla de
    MANTENER, y esta es la que se apaga con cualquiera de sus dos umbrales.
    """
    salida = _serie([(30.0, 20.0)] * 4) + _serie([(30.0, 20.0)], primer_frame=14)
    tiempos = _tiempos(range(0, 16, 2))

    encendido = _rellenar_huecos_parados(salida, tiempos, ParametrosBalon())
    apagado_r = _rellenar_huecos_parados(salida, tiempos, apagado)

    assert len(encendido) > len(
        apagado_r
    ), "apagarlo no cambia nada: no es un interruptor"
    assert [f for f, *_ in apagado_r] == [0, 2, 4, 6, 14]


# ──────── y que esté ENCHUFADO: el bug era justo que no se llamaba ────────


def test_preparar_para_replay_rellena_de_verdad():
    """Guarda contra el bug original: el tratamiento estaba en el docstring
    y no en el código. Si alguien desconecta la llamada, esto falla."""
    trayectoria = [(f, np.array([30.0, 20.0]), 0.0, 0.9) for f in (0, 2, 4, 6)]
    trayectoria.append((14, np.array([30.0, 20.0]), 0.0, 0.9))
    aereo = [False] * len(trayectoria)
    tiempos = _tiempos(range(0, 16, 2))

    preparadas = preparar_para_replay(trayectoria, aereo, tiempos, ParametrosBalon())

    frames = [f for f, *_ in preparadas]
    assert 8 in frames and 10 in frames and 12 in frames, (
        "preparar_para_replay NO está rellenando: el tratamiento 2 de su "
        "docstring vuelve a ser ficción"
    )
    inventados = [t for t in preparadas if t[0] in (8, 10, 12)]
    assert all(t[3] is False for t in inventados), "un relleno no es una medida"
