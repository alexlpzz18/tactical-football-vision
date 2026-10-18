"""Herramienta de calibración semiautomática (scripts/herramienta_calibracion.py)."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

import herramienta_calibracion as hc  # noqa: E402
from src.campo_modelo import cargar_modelo  # noqa: E402


@pytest.mark.skipif(shutil.which("node") is None, reason="sin node")
def test_homografia_js_igual_que_opencv():
    clics = json.load(open(R / "data/calibracion_benja/puntos_marcados_benja.json"))[:7]
    m = [c["metros"] for c in clics]
    p = [c["pixel"] for c in clics]
    js = hc.JS_HOMOGRAFIA + f"\nconsole.log(JSON.stringify(homografia({p}, {m})));"
    H_js = np.array(
        json.loads(
            subprocess.run(
                ["node", "-e", js], capture_output=True, text=True, check=True
            ).stdout
        )
    )
    H_cv, _ = cv2.findHomography(np.float32(p), np.float32(m), 0)
    H_cv /= H_cv[2, 2]
    q = np.c_[np.float64(p), np.ones(len(p))]
    a, b = q @ H_js.T, q @ H_cv.T
    assert np.allclose(a[:, :2] / a[:, 2:], b[:, :2] / b[:, 2:], atol=1e-3)


def test_orden_esquinas_primero_y_circulo_al_final():
    nombres = [p["nombre"] for p in hc.puntos_ordenados(cargar_modelo("f7"))]
    assert nombres[0].startswith("corner_")
    assert nombres[-1].startswith("circulo_") and nombres.index(
        "center"
    ) > nombres.index("penalty_left")


def test_textos_legibles():
    assert hc.texto_de("box_right_top_line") == (
        "la esquina del ÁREA derecha arriba (sobre la línea de fondo)"
    )


def test_genera_html_sin_marcadores(tmp_path):
    frame = tmp_path / "f.png"
    cv2.imwrite(str(frame), np.zeros((60, 80, 3), np.uint8))
    html = hc.generar(
        str(R / "configs/campo_benja.yaml"), str(frame), str(tmp_path / "h.html")
    )
    texto = html.read_text()
    assert not re.search(r"__[A-Z_]+__", texto)
    assert '"largo": 62.0' in texto and "data:image/jpeg;base64," in texto
