"""Corte de identidades en TELETRANSPORTES (velocidad imposible sostenida).

Motivación (objetivo "replay creíble", 08-ago-2026): en el replay hay
fichas que cruzan el campo a velocidad imposible. Medido: 94 rachas de
>8,5 m/s sostenidas y una velocidad máxima de 309 m/s. No las causa la
interpolación (aparecen igual sin ella): son cadenas quimera — el cosido
unió dos fragmentos de jugadores DISTINTOS y la identidad "salta".

Por qué el criterio es SOSTENIDO y no un paso suelto: con dt=0,12 s,
8,5 m/s son solo 1,02 m entre observaciones, y el ruido de localización
del fondo ya vale 1,16 m de mediana (p90 2,45). Cortar en cada paso
rápido trocearía las identidades del fondo en confeti. Una racha de medio
segundo, en cambio, implica un desplazamiento real de >4 m que ningún
jugador hace: eso sí es un salto de identidad.

Nota sobre concurrencia: cortar NO añade fichas simultáneas — parte la
identidad en el TIEMPO, así que en cada frame sigue viva una sola pieza.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Trayectoria = lista de (frame_idx, pos, es_real)
Trayectoria = list[tuple[int, np.ndarray, bool]]


def cortar_por_velocidad(
    trayectorias: list[Trayectoria],
    equipos: dict[int, str],
    tiempos: dict[int, float],
    v_max: float = 8.5,
    duracion_min: float = 0.5,
    min_observaciones: int = 3,
    v_teleport: float | None = 60.0,
) -> tuple[list[Trayectoria], dict[int, str]]:
    """Parte las identidades allí donde teletransportan.

    Dos criterios complementarios, porque hay dos fenómenos distintos:

    - **Racha sostenida** (`v_max` durante `duracion_min`): la identidad
      va impossiblemente rápida un rato — cadena quimera en transición.
    - **Salto instantáneo** (`v_teleport` en UN paso): la ficha aparece
      de golpe a 7 m o más en 0,12 s. No es una racha (dura un frame) pero
      es lo más visible del replay. Nacen en las fusiones de identidades
      entrelazadas: al deduplicar por frame, frames consecutivos pueden
      venir de fragmentos distintos y la ficha "parpadea" entre dos sitios.

    El umbral de salto es alto a propósito: el ruido de localización del
    fondo (p90 2,45 m) equivale a ~20 m/s a dt=0,12 s, así que cortar por
    debajo de eso trocearía las identidades lejanas. 60 m/s son 7,2 m en
    un frame: 3× el ruido, inequívocamente otro jugador.

    Args:
        trayectorias: una por identidad (ids 1..N por posición).
        equipos: {id_identidad: etiqueta}; cada trozo hereda la etiqueta.
        tiempos: {frame_idx: t en segundos}.
        v_max: velocidad humanamente plausible (m/s).
        duracion_min: duración mínima de la racha imposible para cortar (s).
        min_observaciones: los trozos más cortos que esto se descartan
            (un fragmento de 1-2 puntos no es una ficha, es un parpadeo).
        v_teleport: velocidad de un solo paso que ya se considera
            teletransporte (None = desactivar este criterio).

    Returns:
        (trayectorias nuevas, equipos nuevos) renumeradas 1..M.
    """
    nuevas: list[Trayectoria] = []
    nuevos_equipos: dict[int, str] = {}
    n_cortes = 0

    for indice, trayectoria in enumerate(trayectorias, start=1):
        puntos = sorted(trayectoria, key=lambda x: x[0])
        etiqueta = equipos.get(indice)

        # Rachas imposibles como intervalos [inicio, fin] de ÍNDICES: los
        # pasos inicio→inicio+1 … fin-1→fin son todos > v_max.
        rachas: list[tuple[int, int]] = []
        inicio_racha: int | None = None
        for k in range(len(puntos) - 1):
            f0, p0, _r0 = puntos[k]
            f1, p1, _r1 = puntos[k + 1]
            dt = tiempos[f1] - tiempos[f0]
            if dt <= 0:
                continue
            velocidad = float(np.linalg.norm(p1 - p0) / dt)
            if v_teleport is not None and velocidad > v_teleport:
                # Salto instantáneo: se corta aquí mismo (racha de un paso)
                if inicio_racha is not None:
                    rachas.append((inicio_racha, k))
                    inicio_racha = None
                rachas.append((k, k + 1))
                continue
            if velocidad > v_max:
                if inicio_racha is None:
                    inicio_racha = k
            elif inicio_racha is not None:
                if tiempos[puntos[k][0]] - tiempos[puntos[inicio_racha][0]] >= (
                    duracion_min
                ):
                    rachas.append((inicio_racha, k))
                inicio_racha = None
        if inicio_racha is not None:
            ultimo = len(puntos) - 1
            if tiempos[puntos[ultimo][0]] - tiempos[puntos[inicio_racha][0]] >= (
                duracion_min
            ):
                rachas.append((inicio_racha, ultimo))

        if not rachas:
            nuevas.append(puntos)
            if etiqueta is not None:
                nuevos_equipos[len(nuevas)] = etiqueta
            continue

        # Se ESCINDE la racha entera: el trozo previo acaba en su inicio y
        # el siguiente empieza en su fin, así que ningún paso imposible
        # sobrevive dentro de una identidad (cortar por el medio dejaba
        # media racha en cada trozo — medido: 94 → 27 rachas en vez de 0).
        n_cortes += len(rachas)
        trozos = []
        anterior_fin = 0
        for inicio, fin in rachas:
            hasta = inicio + 1
            trozos.append(puntos[anterior_fin:hasta])
            anterior_fin = fin
        trozos.append(puntos[anterior_fin:])
        for trozo in trozos:
            if len(trozo) < min_observaciones:
                continue
            nuevas.append(trozo)
            if etiqueta is not None:
                nuevos_equipos[len(nuevas)] = etiqueta

    logger.info(
        "Corte por velocidad (>%.1f m/s durante ≥%.1f s): %d cortes → "
        "%d → %d identidades",
        v_max,
        duracion_min,
        n_cortes,
        len(trayectorias),
        len(nuevas),
    )
    return nuevas, nuevos_equipos
