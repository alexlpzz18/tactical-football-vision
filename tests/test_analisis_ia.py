"""Tests del análisis táctico con IA — SIN llamadas reales a la API.

Se verifica lo crítico del diseño: (1) el prompt contiene las métricas y
las reglas anti-invención, (2) la llamada usa el modelo configurado (vía
un cliente mock) y (3) el informe degrada limpio a placeholder sin flag,
sin clave o si la llamada falla.
"""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from src.report import analisis_ia
from src.report.informe_v2 import generar_informe_v2

# ── datos de ejemplo compartidos ──────────────────────────────────────

METRICAS = {
    "equipos": {
        "A": {
            "amplitud_m": 28.4,
            "altura_linea_defensiva_m": 21.0,
            "altura_bloque_m": None,
            "tercios_pct": {"defensa_pct": 50.0},
        }
    }
}
DEFINICIONES = {"altura_linea_defensiva": "Distancia media a su portería."}
CONTEXTO = {
    "partido": "Partido de prueba",
    "categoria": "fútbol base",
    "duracion_tramo_s": 59.9,
    "pct_posiciones_sin_equipo": 20.0,
}


def _csv(tmp_path):
    """CSV mínimo válido para el informe (A y B con posiciones)."""
    filas = []
    for k in range(40):
        t = round(300.0 + 0.12 * k, 2)
        frame = 7500 + 3 * k
        filas.append(
            dict(
                frame=frame,
                tiempo_s=t,
                id_jugador=1,
                equipo=0,
                etiqueta="A",
                x_m=25.0,
                y_m=30.0,
            )
        )
        filas.append(
            dict(
                frame=frame,
                tiempo_s=t,
                id_jugador=2,
                equipo=1,
                etiqueta="B",
                x_m=80.0,
                y_m=40.0,
            )
        )
    ruta = tmp_path / "pos.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    return ruta


class ClienteFalso:
    """Mock del cliente de Anthropic: captura la petición, no llama a nada."""

    def __init__(self, texto="Análisis de prueba."):
        self.capturado = None
        respuesta = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=texto)],
            stop_reason="end_turn",
        )

        def create(**kwargs):
            self.capturado = kwargs
            return respuesta

        self.messages = SimpleNamespace(create=create)


# ── el prompt: métricas + reglas anti-invención ───────────────────────


def test_prompt_contiene_las_metricas():
    _, usuario = analisis_ia.construir_prompt(METRICAS, DEFINICIONES, CONTEXTO)
    assert "28.4" in usuario and "21.0" in usuario  # los números, literales
    assert "Distancia media a su portería." in usuario  # definiciones del yaml
    assert "fútbol base" in usuario and "59.9" in usuario  # contexto
    # El JSON de métricas va como única fuente de verdad
    assert "única fuente de verdad" in usuario


def test_prompt_contiene_las_reglas_anti_invencion():
    sistema, _ = analisis_ia.construir_prompt(METRICAS, DEFINICIONES, CONTEXTO)
    assert "PROHIBIDO" in sistema
    assert "goles" in sistema and "tiros" in sistema and "jugadas" in sistema
    assert "citar su número" in sistema
    assert "150 y 250 palabras" in sistema
    assert "español" in sistema
    # Estructura (a) lectura general, (b) por equipo, (c) accionables
    assert "Lectura general" in sistema
    assert "párrafo por equipo" in sistema
    assert "accionables" in sistema


# ── la llamada: modelo configurado, una petición, sin red ─────────────


def test_generar_analisis_usa_el_cliente_y_el_modelo():
    cliente = ClienteFalso("Buen tramo del equipo A.")
    texto = analisis_ia.generar_analisis(
        METRICAS,
        DEFINICIONES,
        CONTEXTO,
        modelo="claude-sonnet-4-6",
        max_tokens=512,
        cliente=cliente,
    )
    assert texto == "Buen tramo del equipo A."
    assert cliente.capturado["model"] == "claude-sonnet-4-6"
    assert cliente.capturado["max_tokens"] == 512
    assert "PROHIBIDO" in cliente.capturado["system"]
    # El mensaje de usuario lleva el JSON de métricas
    assert "28.4" in cliente.capturado["messages"][0]["content"]


def test_respuesta_sin_texto_falla_claro():
    cliente = ClienteFalso(texto="")
    with pytest.raises(RuntimeError, match="no devolvió texto"):
        analisis_ia.generar_analisis(METRICAS, DEFINICIONES, CONTEXTO, cliente=cliente)


def test_sin_api_key_falla_claro(monkeypatch):
    monkeypatch.setattr(analisis_ia, "cargar_api_key", lambda: None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        analisis_ia.generar_analisis(METRICAS, DEFINICIONES, CONTEXTO)


# ── el JSON de métricas se ensambla desde los cálculos reales ─────────


def test_construir_json_metricas_desde_calculos():
    colectivas = {
        "por_equipo": {
            "A": {
                "posiciones": 40,
                "centroide": {"x_m": 25.0, "y_m": 30.0},
                "amplitud_m": 5.0,
                "profundidad_m": 3.0,
            }
        }
    }
    met = SimpleNamespace(
        altura_linea_defensiva=21.0,
        altura_bloque=33.5,
        distancia_lineas=25.0,
        tercios={"defensa_pct": 50.0},
        pasillos={"central_pct": 100.0},
        basculacion_y=[30.0, 32.0, 31.0],
    )
    ctx = SimpleNamespace(x_porteria=0.0)
    salida = analisis_ia.construir_json_metricas(colectivas, {"A": met}, {"A": ctx})
    eq = salida["equipos"]["A"]
    assert eq["altura_linea_defensiva_m"] == 21.0
    assert eq["orientacion_conocida"] is True
    assert eq["basculacion_eje_ancho"] == {
        "y_medio_m": 31.0,
        "y_min_m": 30.0,
        "y_max_m": 32.0,
    }
    json.dumps(salida)  # serializable tal cual para el prompt


# ── degradación limpia en el informe ──────────────────────────────────


def test_informe_sin_flag_lleva_placeholder(tmp_path):
    salida = generar_informe_v2(_csv(tmp_path), tmp_path / "i.html")
    html = salida.read_text()
    assert "Análisis táctico con IA" in html
    assert "--con-ia" in html  # placeholder con instrucciones


def test_informe_con_flag_sin_key_degrada_a_placeholder(tmp_path, monkeypatch):
    monkeypatch.setattr(analisis_ia, "cargar_api_key", lambda: None)
    salida = generar_informe_v2(_csv(tmp_path), tmp_path / "i.html", con_ia=True)
    html = salida.read_text()
    assert "--con-ia" in html  # sale igual, con el hueco marcado
    assert "ANTHROPIC_API_KEY" in html


def test_informe_con_analisis_rellena_la_seccion(tmp_path, monkeypatch):
    monkeypatch.setattr(
        analisis_ia,
        "generar_analisis",
        lambda *a, **k: "Lectura general del tramo.\n\n- Ajustar la línea.",
    )
    salida = generar_informe_v2(_csv(tmp_path), tmp_path / "i.html", con_ia=True)
    html = salida.read_text()
    assert "Lectura general del tramo." in html
    assert "- Ajustar la línea." in html
    assert "Redactado automáticamente por IA" in html  # nota de transparencia
    assert "--con-ia" not in html  # el placeholder ya no está
