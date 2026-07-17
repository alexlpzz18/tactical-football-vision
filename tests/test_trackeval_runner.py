"""Tests de la integración con TrackEval (truco de cajas sintéticas)."""

import numpy as np
import pytest

from src.evaluation.modelo import Observacion

trackeval = pytest.importorskip("trackeval", reason="trackeval no instalado")

from src.evaluation.trackeval_runner import (  # noqa: E402
    evaluar_con_trackeval,
    exportar_motchallenge,
)

FRAMES = [7500 + 15 * k for k in range(10)]


def _obs(obj_id, x, y):
    return Observacion(obj_id=obj_id, pos=np.array([x, y]))


def _gt_dos_jugadores():
    gt = {}
    for k, f in enumerate(FRAMES):
        # Jugador 1 avanza; jugador 2 quieto lejos
        gt[f] = [_obs(1, 10.0 + 0.3 * k, 10.0), _obs(2, 50.0, 40.0)]
    return gt


def test_exportar_motchallenge_formato(tmp_path):
    """El export remapea frames a 1..N y escribe cajas LxL centradas."""
    gt = _gt_dos_jugadores()
    rutas = exportar_motchallenge(gt, gt, FRAMES, tmp_path, lado_caja=2.0)
    gt_txt = (
        rutas["gt_folder"] / "TLENS-train" / "TLENS-01" / "gt" / "gt.txt"
    ).read_text()
    lineas = gt_txt.strip().split("\n")
    assert len(lineas) == 20  # 2 objetos x 10 frames
    campos = lineas[0].split(",")
    assert campos[0] == "1"  # frame 7500 → 1
    assert campos[1] == "2"  # id 1 → 2 (ids 1-based estrictos)
    assert float(campos[2]) == pytest.approx(9.0)  # left = 10 - lado/2
    assert float(campos[4]) == pytest.approx(2.0)  # width = lado


def test_tracker_perfecto_hota_1(tmp_path):
    """Predicciones = GT → HOTA e IDF1 deben ser 1.0."""
    gt = _gt_dos_jugadores()
    pred = {
        f: [_obs(71, o.pos[0], o.pos[1]) for o in observaciones]
        for f, observaciones in gt.items()
    }
    # Segundo objeto con otro id
    for f in FRAMES:
        pred[f][1].obj_id = 93
    res = evaluar_con_trackeval(gt, pred, FRAMES, tmp_path, lado_caja=2.0)
    assert res["HOTA"] == pytest.approx(1.0)
    assert res["IDF1"] == pytest.approx(1.0)
    assert res["IDSW"] == 0


def test_intercambio_de_ids_baja_idf1(tmp_path):
    """Un intercambio de IDs a mitad debe dar IDF1≈0.5 e IDSW=2 también aquí."""
    gt = _gt_dos_jugadores()
    pred = {}
    for k, f in enumerate(FRAMES):
        a, b = (71, 93) if k < 5 else (93, 71)
        pred[f] = [
            _obs(a, gt[f][0].pos[0], gt[f][0].pos[1]),
            _obs(b, gt[f][1].pos[0], gt[f][1].pos[1]),
        ]
    res = evaluar_con_trackeval(gt, pred, FRAMES, tmp_path, lado_caja=2.0)
    assert res["IDF1"] == pytest.approx(0.5)
    assert res["IDSW"] == 2
