"""Tests de las métricas tácticas del informe con geometría conocida."""

import pandas as pd
import pytest

from src.report.informe_v2 import cargar_catalogo
from src.report.metricas_informe import calcular_metricas_equipo, preparar_contextos

LARGO, ANCHO = 105.0, 68.0


def _df_sintetico(n_frames=10, con_portero_a=True):
    """Equipo A defiende la portería de x=105 (su portero vive en x=95).

    Jugadores de campo de A por frame: x = 85, 83 (defensas), 60, 58
    (atacantes), con ys repartidos por pasillos conocidos.
    """
    filas = []
    for k in range(n_frames):
        t = round(300.0 + 0.12 * k, 2)
        frame = 7500 + 3 * k
        if con_portero_a:
            filas.append(
                {
                    "frame": frame,
                    "tiempo_s": t,
                    "id_jugador": 10,
                    "equipo": 0,
                    "etiqueta": "portero_A",
                    "x_m": 95.0,
                    "y_m": 34.0,
                }
            )
        for jid, x, y in (
            (1, 85.0, 10.0),
            (2, 83.0, 30.0),
            (3, 60.0, 50.0),
            (4, 58.0, 60.0),
        ):
            filas.append(
                {
                    "frame": frame,
                    "tiempo_s": t,
                    "id_jugador": jid,
                    "equipo": 0,
                    "etiqueta": "A",
                    "x_m": x,
                    "y_m": y,
                }
            )
        # Equipo B defiende x=0 (portero en x=10)
        filas.append(
            {
                "frame": frame,
                "tiempo_s": t,
                "id_jugador": 20,
                "equipo": 1,
                "etiqueta": "portero_B",
                "x_m": 10.0,
                "y_m": 34.0,
            }
        )
        for jid, x in ((21, 20.0), (22, 22.0), (23, 40.0), (24, 42.0)):
            filas.append(
                {
                    "frame": frame,
                    "tiempo_s": t,
                    "id_jugador": jid,
                    "equipo": 1,
                    "etiqueta": "B",
                    "x_m": x,
                    "y_m": 34.0,
                }
            )
    return pd.DataFrame(filas)


def test_orientacion_desde_el_portero():
    ctx = preparar_contextos(_df_sintetico(), LARGO)
    assert ctx["A"].x_porteria == 105.0  # portero_A vive en x=95 → defiende 105
    assert ctx["B"].x_porteria == 0.0
    # El portero queda FUERA de los jugadores de campo
    assert "portero_A" not in set(ctx["A"].jugadores["etiqueta"])


def test_alturas_y_lineas_valores_exactos():
    """Con geometría conocida, las alturas salen calculadas a mano."""
    ctx = preparar_contextos(_df_sintetico(), LARGO)
    met_a = calcular_metricas_equipo(
        ctx["A"], LARGO, ANCHO, n_defensas=2, n_atacantes=2
    )
    # A defiende x=105: defensas a 20 y 22 m de su portería → línea = 21
    assert met_a.altura_linea_defensiva == pytest.approx(21.0)
    assert met_a.altura_bloque == pytest.approx((20 + 22 + 45 + 47) / 4)
    assert met_a.distancia_lineas == pytest.approx(46.0 - 21.0)
    met_b = calcular_metricas_equipo(
        ctx["B"], LARGO, ANCHO, n_defensas=2, n_atacantes=2
    )
    # B defiende x=0: defensas en 20 y 22 → línea = 21 también
    assert met_b.altura_linea_defensiva == pytest.approx(21.0)
    assert met_b.distancia_lineas == pytest.approx(41.0 - 21.0)


def test_tercios_relativos_a_su_porteria():
    ctx = preparar_contextos(_df_sintetico(), LARGO)
    met = calcular_metricas_equipo(ctx["A"], LARGO, ANCHO, n_defensas=2, n_atacantes=2)
    # Alturas de A: 20,22 (defensa, <35) y 45,47 (medio, 35-70) → 50/50/0
    assert met.tercios["defensa_pct"] == pytest.approx(50.0)
    assert met.tercios["medio_pct"] == pytest.approx(50.0)
    assert met.tercios["ataque_pct"] == pytest.approx(0.0)


def test_pasillos_por_eje_ancho():
    ctx = preparar_contextos(_df_sintetico(), LARGO)
    met = calcular_metricas_equipo(ctx["A"], LARGO, ANCHO, n_defensas=2, n_atacantes=2)
    # ys de A: 10 (cercano), 30 (central), 50 y 60 (lejano) → 25/25/50
    assert met.pasillos["cercano_pct"] == pytest.approx(25.0)
    assert met.pasillos["central_pct"] == pytest.approx(25.0)
    assert met.pasillos["lejano_pct"] == pytest.approx(50.0)


def test_basculacion_es_serie_temporal():
    ctx = preparar_contextos(_df_sintetico(n_frames=20), LARGO)
    met = calcular_metricas_equipo(ctx["A"], LARGO, ANCHO)
    assert len(met.basculacion_t) == 20  # un punto por instante
    assert len(met.basculacion_y) == 20
    assert all(0 <= y <= ANCHO for y in met.basculacion_y)


def test_sin_portero_metricas_de_orientacion_nd():
    """Sin portero no se inventa el lado: alturas N/D, pasillos sí."""
    ctx = preparar_contextos(_df_sintetico(con_portero_a=False), LARGO)
    assert ctx["A"].x_porteria is None
    met = calcular_metricas_equipo(ctx["A"], LARGO, ANCHO, n_defensas=2, n_atacantes=2)
    assert met.altura_linea_defensiva is None
    assert met.tercios == {}  # requieren orientación
    assert met.pasillos  # los pasillos no la necesitan


def test_catalogo_valida_activas_sin_calculadora(tmp_path):
    """El yaml no puede prometer 'activa' lo que el código no sabe calcular."""
    ruta = tmp_path / "informe.yaml"
    ruta.write_text(
        "parametros: {}\nmetricas:\n"
        "  - {clave: magia, nombre: Magia, estado: activa, definicion: x}\n"
    )
    with pytest.raises(ValueError, match="sin calculadora.*magia"):
        cargar_catalogo(ruta)


def test_catalogo_real_es_valido():
    catalogo = cargar_catalogo()
    activas = [m for m in catalogo["metricas"] if m["estado"] == "activa"]
    proximas = [m for m in catalogo["metricas"] if m["estado"] == "proximamente"]
    assert len(activas) == 8
    assert len(proximas) == 9
    # Toda activa tiene definición; toda próxima dice qué requiere
    assert all(m.get("definicion") for m in activas)
    assert all(m.get("requiere") for m in proximas)
