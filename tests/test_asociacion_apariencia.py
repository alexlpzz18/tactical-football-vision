"""Tests de la asociación en metros con coste mixto."""

import numpy as np

from src.tracking.asociacion_apariencia import (
    ParametrosAsociacionApariencia,
    asociar_con_apariencia,
)

FPS, SAMPLE = 25.0, 3
DT = SAMPLE / FPS
P = ParametrosAsociacionApariencia(min_frames_consecutivos=1)


def _cache(trayectorias):
    """trayectorias: lista de listas de (mx, my) por frame."""
    cache = []
    for k in range(len(trayectorias[0])):
        dets = []
        for tr in trayectorias:
            if tr[k] is None:
                continue
            mx, my = tr[k]
            dets.append((mx, my, 0, 0, 10, 30, 0.9))
        cache.append({"frame_idx": k * SAMPLE, "t": k * DT, "dets": dets})
    return cache


def test_un_jugador_una_identidad():
    cache = _cache([[(x, 10.0) for x in np.arange(0, 5, 0.5)]])
    ids = asociar_con_apariencia(cache, FPS, SAMPLE, None, P)
    assert len(ids) == 1
    assert len(ids[0][0].pos) == 10


def test_dos_jugadores_separados_no_se_mezclan():
    a = [(x, 10.0) for x in np.arange(0, 5, 0.5)]
    b = [(x, 40.0) for x in np.arange(0, 5, 0.5)]
    ids = asociar_con_apariencia(_cache([a, b]), FPS, SAMPLE, None, P)
    assert len(ids) == 2


def test_un_salto_imposible_abre_identidad_nueva():
    """El veto por radio: nadie recorre 80 m en 0,12 s."""
    tray = [(0.0, 10.0), (0.5, 10.0), (80.0, 10.0), (80.5, 10.0)]
    ids = asociar_con_apariencia(_cache([tray]), FPS, SAMPLE, None, P)
    assert len(ids) >= 2


def test_la_apariencia_decide_en_la_re_entrada():
    """Dos jugadores se cruzan y uno desaparece; al volver, el embedding
    dice a cuál de los dos pertenece — que es el caso #43."""
    rojo, azul = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    # a: sigue recto; b: desaparece y reaparece cerca de a
    a = [(x, 10.0) for x in (0.0, 0.6, 1.2, 1.8, 2.4)]
    b = [(0.2, 10.0), (0.7, 10.0), None, None, (2.5, 10.0)]
    cache = _cache([a, b])
    emb = {}
    for e in cache:
        for i, d in enumerate(e["dets"]):
            # el de arriba (mx menor en el primer par) es "a"
            emb[(e["frame_idx"], i)] = rojo if i == 0 else azul
    ids = asociar_con_apariencia(cache, FPS, SAMPLE, emb, P)
    assert len(ids) >= 2, "no debería fundir a los dos en una identidad"


def test_sin_embeddings_funciona_solo_con_geometria():
    cache = _cache([[(x, 10.0) for x in np.arange(0, 3, 0.5)]])
    ids = asociar_con_apariencia(cache, FPS, SAMPLE, None, P)
    assert len(ids) == 1
