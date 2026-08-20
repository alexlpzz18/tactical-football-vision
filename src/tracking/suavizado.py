"""Suavizado de las trayectorias exportadas.

Por qué existe (diagnóstico frame-a-frame del benjamín, 11-ago-2026): con
la detección PERFECTA, el replay del fondo del campo se ve mal. No es un
fallo de identidad ni de asociación — es que ahí un píxel vale 0,53 m, y
el temblor medido de la caja del detector (3,5 px) se traduce en ±1,85 m
de posición. A dt=0,1 s, eso son ±18 m/s de velocidad aparente: las colas
de 158 m/s del CSV.

La tentación era cortar la identidad donde la velocidad es imposible. Es
el arreglo equivocado: destruye identidades buenas para tapar un problema
de PRECISIÓN DE MEDIDA. Lo correcto es suavizar la posición, que no toca
la identidad y ataca el ruido donde está.

El suavizado se aplica solo a las posiciones REALES; las interpoladas ya
son suaves por construcción.
"""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ParametrosSuavizado:
    """Parámetros del suavizado.

    `ventana_s` está en SEGUNDOS, no en muestras: así el mismo valor
    significa lo mismo con cachés submuestreados de forma distinta.
    """

    activo: bool = True
    # Ventana temporal del filtro. Debe ser corta frente a un cambio real
    # de dirección (un jugador tarda ~0,5 s en frenar y girar).
    ventana_s: float = 0.5
    # 'media' (media móvil) o 'savgol' (Savitzky-Golay de orden 2, que
    # conserva mejor las aceleraciones reales).
    metodo: str = "savgol"
    # Si hay ResolucionCampo, la ventana se ALARGA donde peor se ve: en
    # el fondo del campo hace falta promediar más para el mismo error en
    # metros, y cerca de la cámara alargarla solo emborronaría el
    # movimiento real. 0 = ventana constante.
    escalar_con_resolucion: float = 1.0

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosSuavizado":
        if not d:
            return cls()
        conocidos = {c: d[c] for c in cls.__dataclass_fields__ if c in d}
        return cls(**conocidos)


def _savgol(valores: np.ndarray, ventana: int) -> np.ndarray:
    """Savitzky-Golay de orden 2 sin depender de scipy.

    Ajusta una parábola por mínimos cuadrados en cada ventana y evalúa en
    el centro. Frente a la media móvil, no aplasta los picos de un cambio
    de dirección real.
    """
    n = len(valores)
    if ventana < 5 or n < ventana:
        return valores
    medio = ventana // 2
    k = np.arange(-medio, medio + 1, dtype=float)
    # Pesos del ajuste cuadrático evaluado en el centro (fila central de
    # la pseudo-inversa de Vandermonde).
    A = np.vstack([np.ones_like(k), k, k**2]).T
    pesos = np.linalg.pinv(A)[0]
    suave = valores.copy()
    for i in range(medio, n - medio):
        ventana_i = valores[i - medio : i + medio + 1]  # noqa: E203
        suave[i] = float(pesos @ ventana_i)
    return suave


def suavizar_trayectorias(
    trayectorias: list[list[tuple]],
    params: ParametrosSuavizado | None = None,
    resolucion=None,
    dt: float = 0.12,
) -> list[list[tuple]]:
    """Suaviza las posiciones REALES de cada trayectoria.

    Args:
        trayectorias: [[(frame_idx, pos, es_real), ...], ...]
        params: ver ParametrosSuavizado.
        resolucion: ResolucionCampo opcional, para alargar la ventana en
            las zonas de mala resolución.
        dt: segundos entre frames del caché.

    Returns:
        Las mismas trayectorias con las posiciones reales suavizadas. Ni
        se añaden ni se quitan puntos: la cobertura no se toca.
    """
    params = params or ParametrosSuavizado()
    if not params.activo or dt <= 0:
        return trayectorias

    base = max(3, int(round(params.ventana_s / dt)))
    if base % 2 == 0:
        base += 1  # las ventanas centradas han de ser impares

    resultado, suavizadas = [], 0
    for trayectoria in trayectorias:
        indices = [i for i, (_f, _p, real) in enumerate(trayectoria) if real]
        if len(indices) < base:
            resultado.append(trayectoria)
            continue

        puntos = np.array([trayectoria[i][1] for i in indices], dtype=float)
        ventana = base
        if resolucion is not None and params.escalar_con_resolucion > 0:
            # Cuánto peor se ve esta identidad, en promedio
            factor = float(
                np.mean(
                    [resolucion.factor(p) for p in puntos[:: max(1, len(puntos) // 10)]]
                )
            )
            ventana = int(
                round(base * (1 + params.escalar_con_resolucion * np.log1p(factor)))
            )
            ventana = max(base, min(ventana, len(puntos) // 2 * 2 - 1, 61))
            if ventana % 2 == 0:
                ventana -= 1
        if ventana < 3 or len(puntos) < ventana:
            resultado.append(trayectoria)
            continue

        suave = puntos.copy()
        for eje in (0, 1):
            if params.metodo == "media":
                nucleo = np.ones(ventana) / ventana
                relleno = np.pad(puntos[:, eje], ventana // 2, mode="edge")
                suave[:, eje] = np.convolve(relleno, nucleo, mode="valid")
            else:
                suave[:, eje] = _savgol(puntos[:, eje], ventana)

        nueva = list(trayectoria)
        for k, i in enumerate(indices):
            frame, _pos, real = trayectoria[i]
            nueva[i] = (frame, suave[k], real)
        resultado.append(nueva)
        suavizadas += 1

    logger.info(
        "Suavizado (%s, ventana base %d muestras ≈ %.2f s): %d/%d trayectorias",
        params.metodo,
        base,
        base * dt,
        suavizadas,
        len(trayectorias),
    )
    return resultado
