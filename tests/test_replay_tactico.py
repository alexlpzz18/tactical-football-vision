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


def test_filtro_de_credibilidad_del_replay(tmp_path):
    """El replay no pinta interpolado viejo ni fichas efímeras."""
    filas = []
    # id 1: jugador sólido (reales durante 10 s)
    for k in range(80):
        filas.append(
            dict(
                frame=100 + 3 * k,
                tiempo_s=round(0.12 * k, 2),
                id_jugador=1,
                equipo=0,
                etiqueta="A",
                x_m=20.0,
                y_m=30.0,
                es_real=1,
            )
        )
    # id 2: efímero (reales solo 0.5 s) → fuera
    for k in range(5):
        filas.append(
            dict(
                frame=100 + 3 * k,
                tiempo_s=round(0.12 * k, 2),
                id_jugador=2,
                equipo=0,
                etiqueta="A",
                x_m=40.0,
                y_m=30.0,
                es_real=1,
            )
        )
    # id 3: sólido pero con una cola interpolada larga → la cola se corta
    for k in range(40):
        filas.append(
            dict(
                frame=100 + 3 * k,
                tiempo_s=round(0.12 * k, 2),
                id_jugador=3,
                equipo=1,
                etiqueta="B",
                x_m=60.0,
                y_m=30.0,
                es_real=1,
            )
        )
    for k in range(40, 80):
        filas.append(
            dict(
                frame=100 + 3 * k,
                tiempo_s=round(0.12 * k, 2),
                id_jugador=3,
                equipo=1,
                etiqueta="B",
                x_m=60.0,
                y_m=30.0,
                es_real=0,
            )
        )
    ruta = tmp_path / "pos.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)

    salida = generar_replay(
        ruta, tmp_path / "r.html", max_edad_interp_s=0.6, min_vida_s=2.0
    )
    html = salida.read_text()
    datos = json.loads(html.split("const DATOS = ")[1].split(";\n")[0])
    ids = {d["id"] for d in datos}
    assert ids == {1, 3}  # el efímero (2) no se pinta
    # De la cola interpolada de id 3 solo sobreviven ~0.6 s (5 puntos)
    ident3 = next(d for d in datos if d["id"] == 3)
    assert 40 < len(ident3["t"]) <= 46
    # Y las posiciones interpoladas van con menos opacidad que las reales
    assert min(ident3["a"]) < 1.0


def test_csv_antiguo_sin_es_real_sigue_funcionando(tmp_path):
    """Compatibilidad: sin la columna es_real se pinta todo el CSV."""
    filas = [
        dict(
            frame=100 + 3 * k,
            tiempo_s=round(0.12 * k, 2),
            id_jugador=1,
            equipo=0,
            etiqueta="A",
            x_m=20.0,
            y_m=30.0,
        )
        for k in range(30)
    ]
    ruta = tmp_path / "viejo.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    salida = generar_replay(ruta, tmp_path / "r.html")
    assert "const DATOS = " in salida.read_text()
