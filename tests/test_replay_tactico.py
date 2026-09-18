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


# ── La etiqueta va por OBSERVACIÓN, no por identidad (27-ago-2026) ────
#
# El replay pintaba la MODA de toda la vida de la identidad, deshaciendo
# en el visor lo que el pipeline ya hace bien. Medido en el saque inicial
# del benjamín: el sistema acertaba el equipo de tres jugadores en el
# frame 0 y la pizarra los pintaba del contrario, porque esas identidades
# se contaminan más tarde (repartos 58/42, 53/47 y 75/25).


def _csv_identidad_que_cambia(tmp_path, etiquetas):
    import pandas as pd

    filas = [
        {
            "frame": i * 3,
            "tiempo_s": round(i * 0.1, 2),
            "id_jugador": 1,
            "etiqueta": e,
            "x_m": 30.0 + i * 0.01,
            "y_m": 20.0,
            "es_real": 1,
        }
        for i, e in enumerate(etiquetas)
    ]
    ruta = tmp_path / "pos.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    return ruta


def _datos_del_html(html):
    import json
    import re

    datos = json.loads(re.search(r"const DATOS = (\[.*?\]);", html, re.S).group(1))
    catalogo = json.loads(
        re.search(r"const CATALOGO = (\[.*?\]);", html, re.S).group(1)
    )
    return datos, catalogo


def test_la_pizarra_pinta_la_etiqueta_del_INSTANTE(tmp_path):
    """Identidad que empieza en A y acaba en B: al principio pinta A."""
    from src.report.replay_tactico import generar_replay

    # 40 muestras: 10 en A y 30 en B. La moda es B, pero al principio es A.
    csv = _csv_identidad_que_cambia(tmp_path, ["A"] * 10 + ["B"] * 30)
    salida = tmp_path / "r.html"
    generar_replay(csv, salida, largo=62.0, ancho=40.0, min_vida_s=0.0)
    datos, catalogo = _datos_del_html(salida.read_text())
    ident = datos[0]
    assert ident["et"] == "B", "la moda sigue siendo B"
    assert "ets" in ident, "una identidad mixta debe llevar etiqueta por muestra"
    assert catalogo[ident["ets"][0]] == "A"
    assert catalogo[ident["ets"][-1]] == "B"


def test_identidad_PURA_no_engorda_el_html(tmp_path):
    """Si nunca cambia de etiqueta, no se emite el array por muestra."""
    from src.report.replay_tactico import generar_replay

    csv = _csv_identidad_que_cambia(tmp_path, ["A"] * 40)
    salida = tmp_path / "r.html"
    generar_replay(csv, salida, largo=62.0, ancho=40.0, min_vida_s=0.0)
    datos, _ = _datos_del_html(salida.read_text())
    assert datos[0]["et"] == "A"
    assert "ets" not in datos[0]


def test_se_puede_volver_al_comportamiento_viejo(tmp_path):
    """La escotilla de salida: una etiqueta por identidad."""
    from src.report.replay_tactico import generar_replay

    csv = _csv_identidad_que_cambia(tmp_path, ["A"] * 10 + ["B"] * 30)
    salida = tmp_path / "r.html"
    generar_replay(
        csv,
        salida,
        largo=62.0,
        ancho=40.0,
        min_vida_s=0.0,
        etiqueta_por_identidad=True,
    )
    datos, _ = _datos_del_html(salida.read_text())
    assert datos[0]["et"] == "B"
    assert "ets" not in datos[0]


def _con_balon_aereo(tmp_path):
    """Un jugador de verdad + el balón tal como lo emite procesar_balon.py.

    El balón continuo (-1) tiene filas reales en tierra y la recta del vuelo
    con es_real=0; la ficha de "en el aire" (-2) va ENTERA con es_real=0.
    """
    filas = []
    for k in range(40):
        t = k * 0.1
        filas.append((k, t, 7, "A", 20.0 + k * 0.1, 15.0, 1))
        en_vuelo = 10 <= k < 30  # 2 s en el aire: más que max_edad_interp_s
        filas.append((k, t, -1, "balon", 30.0 + k * 0.3, 20.0, 0 if en_vuelo else 1))
        if en_vuelo:
            filas.append((k, t, -2, "balon_aereo", 30.0 + k * 0.3, 20.0, 0))
    df = pd.DataFrame(
        filas,
        columns=[
            "frame",
            "tiempo_s",
            "id_jugador",
            "etiqueta",
            "x_m",
            "y_m",
            "es_real",
        ],
    )
    ruta = tmp_path / "conjunto.csv"
    df.to_csv(ruta, index=False)
    return ruta


def _datos(html: str) -> list:
    return json.loads(re.search(r"const DATOS = (\[.*?\]);\n", html, re.S).group(1))


def test_la_ficha_de_BALON_AEREO_llega_a_la_pizarra(tmp_path):
    """Antes el filtro de credibilidad la borraba SIEMPRE: no tiene filas reales.

    En la parte entera era el 30 % del balón, y la leyenda lo anunciaba.
    """
    salida = generar_replay(_con_balon_aereo(tmp_path), tmp_path / "r.html")
    ids = {d["id"] for d in _datos(salida.read_text(encoding="utf-8"))}
    assert -2 in ids


def test_la_recta_del_vuelo_no_se_recorta_a_0_6_s(tmp_path):
    """El vuelo dura 2 s: con la regla de los jugadores se quedaba en 0,6 + 0,6."""
    salida = generar_replay(_con_balon_aereo(tmp_path), tmp_path / "r.html")
    balon = next(d for d in _datos(salida.read_text(encoding="utf-8")) if d["id"] == -1)
    assert len(balon["t"]) == 40


def test_a_los_JUGADORES_se_les_sigue_aplicando_el_filtro(tmp_path):
    """Control: la excepción es del balón, no un filtro apagado."""
    ruta = _con_balon_aereo(tmp_path)
    df = pd.read_csv(ruta)
    fantasma = df[df.id_jugador == 7].assign(id_jugador=99, es_real=0)
    pd.concat([df, fantasma]).to_csv(ruta, index=False)
    salida = generar_replay(ruta, tmp_path / "r.html")
    ids = {d["id"] for d in _datos(salida.read_text(encoding="utf-8"))}
    assert 99 not in ids and 7 in ids
