"""Cálculo de las métricas tácticas del informe v2 (separado del render).

Todas se calculan SOLO desde el CSV de posiciones del pipeline (sin pasos
manuales), por equipo y excluyendo la etiqueta 'otro'. La orientación de
cada equipo (dónde está SU portería) se deriva automáticamente de la
posición mediana de su portero (etiqueta portero_A/portero_B); sin portero
detectado, las métricas que dependen de la orientación se reportan como
no disponibles (honesto antes que inventar el lado).

El catálogo (qué métricas existen, activas o prometidas, definiciones)
vive en configs/informe.yaml; aquí solo viven las calculadoras.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ContextoEquipo:
    """Datos preparados de un equipo para calcular sus métricas."""

    nombre: str  # 'A' o 'B'
    jugadores: pd.DataFrame  # posiciones del equipo SIN portero
    portero: pd.DataFrame  # posiciones del portero (puede estar vacío)
    x_porteria: float | None  # coordenada x de SU portería (None = sin portero)


@dataclass
class MetricasEquipo:
    """Resultados de las métricas activas de un equipo."""

    altura_linea_defensiva: float | None = None
    altura_bloque: float | None = None
    distancia_lineas: float | None = None
    # Serie temporal de basculación: (tiempos, y medio del bloque)
    basculacion_t: list = field(default_factory=list)
    basculacion_y: list = field(default_factory=list)
    # Tercios relativos a la propia portería y pasillos (ancho)
    tercios: dict = field(default_factory=dict)
    pasillos: dict = field(default_factory=dict)


def preparar_contextos(df: pd.DataFrame, largo: float) -> dict[str, ContextoEquipo]:
    """Separa el CSV por equipo y deriva la orientación desde el portero."""
    contextos = {}
    for nombre, equipo_int, etiqueta_portero in (
        ("A", 0, "portero_A"),
        ("B", 1, "portero_B"),
    ):
        del_equipo = df[df["equipo"] == equipo_int]
        portero = del_equipo[del_equipo["etiqueta"] == etiqueta_portero]
        jugadores = del_equipo[del_equipo["etiqueta"] != etiqueta_portero]
        if len(portero) > 0:
            # La portería propia es el extremo del campo más cercano al portero
            x_porteria = 0.0 if float(portero["x_m"].median()) < largo / 2 else largo
        else:
            x_porteria = None
            logger.warning(
                "Equipo %s sin portero detectado: métricas de orientación N/D",
                nombre,
            )
        contextos[nombre] = ContextoEquipo(nombre, jugadores, portero, x_porteria)
    return contextos


def _lineas_por_frame(
    ctx: ContextoEquipo, n_defensas: int, n_atacantes: int
) -> pd.DataFrame:
    """Por frame: distancia a la propia portería de la línea defensiva, la
    de ataque y el bloque completo (sin portero). Solo frames con jugadores
    suficientes para definir ambas líneas."""
    filas = []
    for frame, grupo in ctx.jugadores.groupby("frame"):
        # Distancia de cada jugador a su portería (metros "campo arriba")
        alturas = (grupo["x_m"] - ctx.x_porteria).abs().sort_values()
        if len(alturas) < n_defensas + n_atacantes:
            continue  # frame con poca cobertura: no se inventan líneas
        filas.append(
            {
                "frame": frame,
                "linea_def": float(alturas.iloc[:n_defensas].mean()),
                "linea_atq": float(alturas.iloc[-n_atacantes:].mean()),
                "bloque": float(alturas.mean()),
            }
        )
    return pd.DataFrame(filas)


def calcular_metricas_equipo(
    ctx: ContextoEquipo,
    largo: float,
    ancho: float,
    n_defensas: int = 4,
    n_atacantes: int = 3,
    ventana_basculacion_s: float = 2.0,
) -> MetricasEquipo:
    """Calcula todas las métricas activas de un equipo."""
    resultado = MetricasEquipo()
    if len(ctx.jugadores) == 0:
        return resultado

    # ── Alturas y distancia entre líneas (requieren orientación) ──
    if ctx.x_porteria is not None:
        lineas = _lineas_por_frame(ctx, n_defensas, n_atacantes)
        if len(lineas) > 0:
            resultado.altura_linea_defensiva = round(
                float(lineas["linea_def"].mean()), 1
            )
            resultado.altura_bloque = round(float(lineas["bloque"].mean()), 1)
            resultado.distancia_lineas = round(
                float((lineas["linea_atq"] - lineas["linea_def"]).mean()), 1
            )

    # ── Basculación lateral: y medio del bloque por instante, suavizado ──
    serie = ctx.jugadores.groupby("tiempo_s")["y_m"].mean().sort_index()
    if len(serie) > 1:
        dt = float(np.median(np.diff(serie.index)))
        ventana = max(int(round(ventana_basculacion_s / max(dt, 1e-6))), 1)
        suave = serie.rolling(ventana, center=True, min_periods=1).mean()
        resultado.basculacion_t = [round(float(t), 2) for t in suave.index]
        resultado.basculacion_y = [round(float(y), 2) for y in suave.values]

    # ── Territorio: tercios (relativos a la portería propia) y pasillos ──
    n = len(ctx.jugadores)
    if ctx.x_porteria is not None:
        altura = (ctx.jugadores["x_m"] - ctx.x_porteria).abs()
        resultado.tercios = {
            "defensa_pct": round(100 * int((altura < largo / 3).sum()) / n, 1),
            "medio_pct": round(
                100 * int(((altura >= largo / 3) & (altura < 2 * largo / 3)).sum()) / n,
                1,
            ),
            "ataque_pct": round(100 * int((altura >= 2 * largo / 3).sum()) / n, 1),
        }
    y = ctx.jugadores["y_m"]
    resultado.pasillos = {
        "cercano_pct": round(100 * int((y < ancho / 3).sum()) / n, 1),
        "central_pct": round(
            100 * int(((y >= ancho / 3) & (y < 2 * ancho / 3)).sum()) / n, 1
        ),
        "lejano_pct": round(100 * int((y >= 2 * ancho / 3).sum()) / n, 1),
    }
    return resultado
