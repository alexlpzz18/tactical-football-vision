"""Coste mixto GEOMETRÍA + APARIENCIA para asociar en METROS.

El "camino B" de `docs/apariencia_en_asociacion.md`, con la forma que
decidió Alex: el término geométrico no es un umbral abstracto sino una
**distancia física con radio de plausibilidad derivado de la física**.

## Por qué en metros y no IoU en píxeles

ByteTrack empareja por IoU de cajas, que es la magnitud que **deja de
distinguir justo cuando dos cuerpos se solapan** — el instante del cruce.
Y en píxeles un metro vale distinto según la zona: aquí un píxel va de
0,009 a 0,527 m según la profundidad. Asociar en metros es la ventaja
diferencial que CLAUDE.md protege.

En metros no hay IoU, así que el término geométrico es distancia física
normalizada por un radio de plausibilidad:

    radio(Δt, y) = v_max · Δt  +  k · σ(y)

- `v_max · Δt` crece **solo con el hueco**: cuanto más tiempo lleva
  perdido un jugador, más lejos puede estar legítimamente. Es física, no
  un umbral elegido.
- `σ(y)` es la incertidumbre de la propia proyección, que crece con la
  profundidad: medida en ±0,11 m cerca y ±1,85 m en el fondo del campo.
  Sin ella, el radio del fondo sería tan estrecho como el de cerca y
  vetaría emparejamientos correctos.

## Por qué el peso NO es constante

Lo importante del diseño: **α no puede ser un número fijo.** En el fondo
del campo la geometría es mala (σ grande) y además está medido que el
color es CERO separando equipos a menos de 20 px. Si α fuese constante,
el sistema seguiría fiándose de una geometría que allí no informa.

La solución no es inventar un α por zona sino derivarlo de la precisión,
que es lo estándar cuando se combinan dos evidencias: cada una pesa según
su inversa de la varianza.

    σ_geo(Δt, y)² = σ(y)²  +  (v_incert · Δt)²
    α = (1/σ_geo²) / (1/σ_geo² + 1/σ_app²)

Así α **baja solo** en los dos casos en que debe bajar —lejos y tras un
hueco largo— sin ninguna regla ad hoc, y sube cerca y en continuidad. La
única constante a calibrar es `σ_app`, la "incertidumbre equivalente" de
la apariencia: cuántos metros de error posicional valen lo mismo que la
distancia de coseno del embedding.

Corolario que encaja con lo medido: en el fondo la geometría es mala Y el
color es cero, así que la apariencia queda como única señal — y α tiende
a 0 justo ahí, sin que haya que decírselo.
"""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IncertidumbrePosicion:
    """σ(y) de la proyección: cuánto se fía uno de la posición en metros.

    Lineal en la profundidad, como el umbral de asociación del banco, y
    calibrada con la misma curva empírica: ±0,11 m cerca de la cámara,
    ±1,85 m en el fondo.
    """

    base: float = 0.11
    por_metro: float = 0.026
    minimo: float = 0.11
    maximo: float = 1.85

    def para(self, y: float) -> float:
        return float(np.clip(self.base + self.por_metro * y, self.minimo, self.maximo))


@dataclass
class ParametrosCosteMixto:
    """Los parámetros del coste, todos en unidades físicas."""

    # Velocidad máxima plausible de un jugador. Define cuánto crece el
    # radio por segundo perdido.
    v_max: float = 7.0
    # Cuántas sigmas de la proyección se admiten además del término de
    # velocidad. 2 ≈ 95 % si el error fuese normal.
    k_sigma: float = 2.0
    # Incertidumbre de la VELOCIDAD estimada (m/s). Sin ella, un hueco
    # largo no degradaría la confianza geométrica, solo el radio.
    v_incert: float = 1.5
    # Incertidumbre equivalente de la apariencia, en METROS: cuántos
    # metros de error posicional "valen" lo que la distancia de coseno.
    # Es la ÚNICA constante libre; se calibra contra el banco.
    sigma_apariencia: float = 1.0

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosCosteMixto":
        return cls(**(d or {}))


def radio_plausibilidad(dt, y, params, incert):
    """Metros a los que un jugador puede haberse ido en `dt` segundos.

    Crece con el hueco (física) y con la profundidad (incertidumbre de la
    proyección). No es un umbral elegido: es lo que permite la velocidad
    humana más lo que no sabemos de dónde estaba.
    """
    return params.v_max * float(dt) + params.k_sigma * incert.para(float(y))


def peso_geometrico(dt, y, params, incert):
    """α ∈ [0,1]: cuánto pesa la geometría frente a la apariencia.

    Por inversa de la varianza. Baja solo en el fondo y tras huecos
    largos, que es exactamente donde la posición deja de informar.
    """
    sigma_geo2 = incert.para(float(y)) ** 2 + (params.v_incert * float(dt)) ** 2
    prec_geo = 1.0 / max(sigma_geo2, 1e-9)
    prec_app = 1.0 / max(params.sigma_apariencia**2, 1e-9)
    return float(prec_geo / (prec_geo + prec_app))


def distancia_coseno(a, b):
    """1 − coseno entre dos embeddings. 0 = idénticos, 2 = opuestos."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(a)) + 1e-9
    nb = float(np.linalg.norm(b)) + 1e-9
    return float(1.0 - float(a @ b) / (na * nb))


def coste(
    pos_predicha,
    pos_detectada,
    dt,
    emb_track=None,
    emb_det=None,
    params=None,
    incert=None,
):
    """Coste de emparejar un track con una detección. `inf` = imposible.

    El veto por radio va ANTES de mirar la apariencia a propósito: por
    muy parecido que sea el aspecto, un jugador no puede estar donde no
    ha podido llegar. La apariencia desempata dentro de lo posible, no
    autoriza lo imposible.
    """
    params = params or ParametrosCosteMixto()
    incert = incert or IncertidumbrePosicion()
    p1 = np.asarray(pos_predicha, dtype=float)
    p2 = np.asarray(pos_detectada, dtype=float)
    d = float(np.linalg.norm(p1 - p2))
    y = float(p2[1])

    radio = radio_plausibilidad(dt, y, params, incert)
    if d > radio:
        return float("inf")

    coste_geo = d / max(radio, 1e-9)
    if emb_track is None or emb_det is None:
        return coste_geo

    # El coseno vive en [0,2]; se lleva a [0,1] para que las dos escalas
    # sean comparables antes de mezclarlas.
    coste_app = min(1.0, distancia_coseno(emb_track, emb_det) / 2.0 * 2.0)
    alfa = peso_geometrico(dt, y, params, incert)
    return alfa * coste_geo + (1.0 - alfa) * coste_app
