"""Tests del informe v2 (por equipo, heatmaps suavizados, transparencia)."""

import pandas as pd
import pytest

from src.metrics.collective import compute_collective_metrics
from src.report.informe_v2 import generar_informe_v2


def _csv(tmp_path, n_otro=20):
    """CSV sintético: equipo A a la izquierda, B a la derecha + 'otro'."""
    filas = []
    for k in range(40):
        t = round(300.0 + 0.12 * k, 2)
        filas.append(
            {
                "frame": 7500 + 3 * k,
                "tiempo_s": t,
                "id_jugador": 1,
                "equipo": 0,
                "etiqueta": "A",
                "x_m": 25.0 + k * 0.1,
                "y_m": 30.0,
            }
        )
        filas.append(
            {
                "frame": 7500 + 3 * k,
                "tiempo_s": t,
                "id_jugador": 2,
                "equipo": 1,
                "etiqueta": "B",
                "x_m": 80.0 - k * 0.1,
                "y_m": 40.0,
            }
        )
    for k in range(n_otro):
        filas.append(
            {
                "frame": 7500 + 3 * k,
                "tiempo_s": round(300.0 + 0.12 * k, 2),
                "id_jugador": 9,
                "equipo": 2,
                "etiqueta": "otro",
                "x_m": 52.0,
                "y_m": 60.0,
            }
        )
    ruta = tmp_path / "pos.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    return ruta


def test_informe_dos_columnas_y_heatmaps(tmp_path):
    salida = generar_informe_v2(_csv(tmp_path), tmp_path / "informe.html")
    html = salida.read_text()
    assert "Equipo A" in html and "Equipo B" in html
    # un heatmap por equipo + la gráfica de basculación
    assert html.count("data:image/png;base64,") == 3
    for kpi in ("Amplitud", "Profundidad", "Centroide", "Pasillos", "Basculación"):
        assert kpi in html
    assert "suavizado gaussiano" in html  # leyenda del heatmap


def test_nota_de_transparencia_con_porcentaje(tmp_path):
    """El % de posiciones excluidas (20 de 100 = 20%) aparece en el banner."""
    salida = generar_informe_v2(_csv(tmp_path, n_otro=20), tmp_path / "i.html")
    html = salida.read_text()
    assert "Transparencia" in html
    assert "20" in html and "sin equipo asignable" in html
    # Sin staff en este CSV, el desglose lo dice explícitamente
    assert "0 de personal no jugador" in html


def test_banner_separa_staff_de_sin_equipo(tmp_path):
    """El staff (fuera del campo) se cuenta aparte de los inclasificables."""
    df = pd.read_csv(_csv(tmp_path, n_otro=10))
    staff = df[df["equipo"] == 2].head(4).copy()
    staff["etiqueta"] = "staff"
    staff["id_jugador"] = 99
    ruta = tmp_path / "con_staff.csv"
    pd.concat([df, staff]).to_csv(ruta, index=False)
    html = generar_informe_v2(ruta, tmp_path / "i2.html").read_text()
    assert "4 de personal no jugador" in html
    assert "10 sin equipo asignable" in html


def test_tramo_arbitrario_en_encabezado(tmp_path):
    """El encabezado usa el reloj absoluto del vídeo (t0=300 → 05:00).

    Se comprueba el RELOJ, no la redacción: la portada puede cambiar de
    palabras, pero un informe que dijera 00:00 estaría mintiendo sobre
    qué parte del partido se analizó.
    """
    html = generar_informe_v2(_csv(tmp_path), tmp_path / "i.html").read_text()
    assert "05:00" in html
    assert "00:00" not in html


def test_csv_sin_equipos_falla_claro(tmp_path):
    ruta = tmp_path / "solo_otro.csv"
    pd.DataFrame(
        [
            {
                "frame": 1,
                "tiempo_s": 1.0,
                "id_jugador": 1,
                "equipo": 2,
                "etiqueta": "otro",
                "x_m": 5.0,
                "y_m": 5.0,
            }
        ]
    ).to_csv(ruta, index=False)
    with pytest.raises(ValueError, match="equipo asignado"):
        generar_informe_v2(ruta, tmp_path / "i.html")


def test_collective_zonas_por_equipo(tmp_path):
    """collective.py reporta zonas POR EQUIPO (A a la izq, B a la der)."""
    m = compute_collective_metrics(str(_csv(tmp_path)))
    zonas_a = m["por_equipo"]["A"]["zonas"]
    zonas_b = m["por_equipo"]["B"]["zonas"]
    assert zonas_a["izquierda_pct"] == 100.0  # A vive en x≈25-29 (< 105/3)
    assert zonas_b["derecha_pct"] == 100.0  # B vive en x≈76-80 (> 2*105/3)
    assert sum(zonas_a.values()) == pytest.approx(100.0, abs=0.2)
