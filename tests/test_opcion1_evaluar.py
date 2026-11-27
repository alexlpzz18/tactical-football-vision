"""El evaluador de la opción 1 quita detecciones: las claves de color (frame, j) tienen que seguir
apuntando a SU caja (si no, el clasificador lee el color de otra persona sin avisar)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from opcion1_evaluar import quedarse, quietas  # noqa: E402


def _det(x, conf):
    return (0.0, 0.0, x, 10.0, x + 10, 30.0, conf)


def test_quitar_una_deteccion_renumera_los_colores():
    datos = {
        "cache": [
            {
                "frame_idx": 0,
                "t": 0.0,
                "dets": [_det(0, 0.9), _det(50, 0.2), _det(90, 0.8)],
            }
        ]
    }
    colores = {(0, 0): "c0", (0, 1): "c1", (0, 2): "c2"}
    d2, c2 = quedarse(datos, colores, lambda e, j, d: d[6] >= 0.3)
    assert [d[2] for d in d2["cache"][0]["dets"]] == [0, 90]
    assert c2 == {(0, 0): "c0", (0, 1): "c2"}  # el color de la caja x=90 sigue con ella


def test_una_debil_quieta_se_marca_y_una_que_se_mueve_no():
    cache = []
    for k in range(10):  # 10 fotogramas en 1,2 s
        dets = [
            _det(100, 0.2),
            _det(200 + 15 * k, 0.2),
        ]  # una fija, otra que avanza 15 px
        cache.append({"frame_idx": 3 * k, "t": 0.12 * k, "dets": dets})
    fijas = quietas({"cache": cache})
    assert all((3 * k, 0) in fijas for k in range(10))
    assert not any((3 * k, 1) in fijas for k in range(10))
