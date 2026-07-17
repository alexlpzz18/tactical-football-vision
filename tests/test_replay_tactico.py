"""Tests del replay táctico 2D (estructura del HTML generado)."""

import json
import re

import pandas as pd
import pytest

from src.report.replay_tactico import generar_replay


def _csv(tmp_path, t0=300.0):
    """CSV sintético de 2 identidades empezando en t0 (tramo arbitrario)."""
    filas = []
    for k in range(10):
        t = round(t0 + 0.12 * k, 2)
        filas.append(
            {
                "frame": 7500 + 3 * k,
                "tiempo_s": t,
                "id_jugador": 1,
                "equipo": 0,
                "etiqueta": "A",
                "x_m": 10.0 + k,
                "y_m": 30.0,
            }
        )
        filas.append(
            {
                "frame": 7500 + 3 * k,
                "tiempo_s": t,
                "id_jugador": 2,
                "equipo": 2,
                "etiqueta": "otro",
                "x_m": 50.0,
                "y_m": 40.0,
            }
        )
    ruta = tmp_path / "pos.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    return ruta


def test_genera_html_autocontenido(tmp_path):
    salida = generar_replay(_csv(tmp_path), tmp_path / "replay.html", titulo="Test")
    html = salida.read_text()
    # Sin tokens sin sustituir y sin recursos externos
    assert "__" not in re.sub(r"__proto__", "", html)
    assert "http://" not in html and "https://" not in html
    # Controles presentes
    for control in ('id="play"', 'id="vel"', 'id="barra"', 'id="reloj"'):
        assert control in html


def test_datos_embebidos_parsean_y_conservan_tramo(tmp_path):
    """El JSON embebido es válido y el reloj usa el tiempo ABSOLUTO (t0=300)."""
    salida = generar_replay(_csv(tmp_path, t0=300.0), tmp_path / "r.html")
    html = salida.read_text()
    datos = json.loads(re.search(r"const DATOS = (\[.*?\]);\n", html).group(1))
    assert len(datos) == 2
    ident = next(d for d in datos if d["id"] == 1)
    assert ident["et"] == "A"
    assert ident["t"][0] == 300.0  # cualquier tramo: no se renormaliza a 0
    assert "const TMIN = 300.0" in html


def test_colores_por_etiqueta_presentes(tmp_path):
    salida = generar_replay(_csv(tmp_path), tmp_path / "r.html")
    html = salida.read_text()
    for color in ("#2563eb", "#dc2626", "#1e3a8a", "#7f1d1d"):
        assert color in html


def test_dimensiones_de_campo_configurables(tmp_path):
    salida = generar_replay(
        _csv(tmp_path), tmp_path / "r.html", largo=100.0, ancho=64.0
    )
    html = salida.read_text()
    assert "const LARGO = 100.0, ANCHO = 64.0" in html


def test_csv_sin_columnas_falla_claro(tmp_path):
    ruta = tmp_path / "malo.csv"
    pd.DataFrame({"frame": [1], "x_m": [1.0]}).to_csv(ruta, index=False)
    with pytest.raises(ValueError, match="columnas requeridas"):
        generar_replay(ruta, tmp_path / "r.html")


def test_csv_vacio_falla_claro(tmp_path):
    ruta = tmp_path / "vacio.csv"
    pd.DataFrame(
        columns=["frame", "tiempo_s", "id_jugador", "etiqueta", "x_m", "y_m"]
    ).to_csv(ruta, index=False)
    with pytest.raises(ValueError, match="vacío"):
        generar_replay(ruta, tmp_path / "r.html")
