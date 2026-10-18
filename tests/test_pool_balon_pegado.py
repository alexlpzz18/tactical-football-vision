"""Reglas del pool de etiquetado del balón pegado al pie (scripts/preparar_pool_balon_pegado.py).

Las que deciden si la medida del reentrenamiento valdrá algo: el test por MINUTOS
enteros, nada de entrenamiento junto al banco de medida, un frame por hueco.
"""

import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import preparar_pool_balon_pegado as pp  # noqa: E402


def test_un_minuto_de_test_por_cada_bloque_de_cinco():
    m = pp.minutos_de_test(20, random.Random(1))
    assert len(m) == 4
    assert sorted(x // 5 for x in m) == [0, 1, 2, 3]


def test_nada_de_entrenamiento_junto_al_banco_ni_en_los_tramos():
    banco = [100.0]
    assert pp.excluido_de_entrenamiento(102.5, banco)  # a 2,5 s de un frame del banco
    assert not pp.excluido_de_entrenamiento(104.0, banco)
    assert pp.excluido_de_entrenamiento(370.0, [])  # dentro del tramo 365-378


def test_un_frame_por_hueco_el_central():
    c = [(f, f * 0.0667, np.zeros(2), np.zeros(2)) for f in (10, 11, 12, 13, 14)]
    c += [(f, f * 0.0667, np.zeros(2), np.zeros(2)) for f in (100, 101, 102)]
    assert [x[0] for x in pp.huecos_de(c)] == [12, 101]


def test_elegir_respeta_separacion_objetivo_y_reparte_tercios():
    rng = random.Random(3)
    cands = [
        (i, i * 0.5, np.array([10.0 + 20 * (i % 3), 20.0]), None) for i in range(240)
    ]
    el = pp.elegir(cands, [], 30, rng)
    ts = sorted(c[1] for c in el)
    assert len(el) == 30
    assert all(b - a >= pp.SEPARACION_S for a, b in zip(ts, ts[1:]))
    tercios = [pp.zona(c[2][0]) for c in el]
    assert min(tercios.count(z) for z in (0, 1, 2)) >= 8  # los tres representados
