"""Filtro de detecciones DÉBILES QUIETAS sobre el caché, con remapeo del caché de colores.

Opción 1 del embudo del tercio lejano (`docs/plan_opcion1_dos_etapas.md`, adoptada en la rama
`alevinb-preparacion` el 27-nov-2026): el caché lleva, además de las detecciones de producción
(conf ≥ 0,30), las débiles de 0,10-0,30, que el tracker solo usa para ALARGAR pistas. Entre las
débiles hay basura que no se mueve (marcas, conos, postes, un balón parado): la cámara tiembla
0,22 px (`docs/segunda_opinion_26nov.md`), así que algo que repite píxel durante segundos no es un
jugador.

Regla (fijada antes de medir): una detección con conf < `conf_max` se quita si, en al menos
`fraccion` de los fotogramas muestreados a ± `ventana_s`, hay otra caja con el centro a ≤
`radio_px`. Las detecciones de producción (conf ≥ `conf_max`) no se tocan nunca: con un caché de
producción el filtro no hace nada.

Igual que `filtro_confianza`: el caché de colores va indexado por (frame_idx, posición), así que
al quitar entradas hay que renumerar, o cada caja quedaría con el color de otra persona sin
avisar."""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def detecciones_quietas(
    cache: list[dict],
    conf_max: float = 0.30,
    ventana_s: float = 2.0,
    radio_px: float = 2.0,
    fraccion: float = 0.5,
) -> set[tuple[int, int]]:
    """{(frame_idx, j)} de las detecciones débiles quietas."""
    centros = [
        (
            np.array(
                [((d[2] + d[4]) / 2, (d[3] + d[5]) / 2) for d in e["dets"]], float
            ).reshape(-1, 2)
        )
        for e in cache
    ]
    tiempos = np.array([e["t"] for e in cache], float)
    salida = set()
    for k, e in enumerate(cache):
        debiles = [j for j, d in enumerate(e["dets"]) if d[6] < conf_max]
        if not debiles:
            continue
        a = int(np.searchsorted(tiempos, tiempos[k] - ventana_s, side="left"))
        b = int(np.searchsorted(tiempos, tiempos[k] + ventana_s, side="right"))
        vecinos = [i for i in range(a, b) if i != k]
        if not vecinos:
            continue
        for j in debiles:
            c = centros[k][j]
            hits = sum(
                1
                for i in vecinos
                if len(centros[i])
                and np.min(np.linalg.norm(centros[i] - c, axis=1)) <= radio_px
            )
            if hits >= fraccion * len(vecinos):
                salida.add((e["frame_idx"], j))
    return salida


def filtrar_quietas(
    cache: list[dict], colores: dict | None, **parametros
) -> tuple[list[dict], dict | None, int]:
    """(caché, colores renumerados, nº quitadas) sin las detecciones débiles quietas."""
    fuera = detecciones_quietas(cache, **parametros)
    if not fuera:
        return cache, colores, 0
    nuevo, nuevos_colores = [], ({} if colores is not None else None)
    for e in cache:
        f, dets = e["frame_idx"], []
        for j, d in enumerate(e["dets"]):
            if (f, j) in fuera:
                continue
            if colores is not None and (f, j) in colores:
                nuevos_colores[(f, len(dets))] = colores[(f, j)]
            dets.append(d)
        nuevo.append({**e, "dets": dets})
    logger.info("Filtro de quietas: %d detecciones débiles quietas fuera", len(fuera))
    return nuevo, nuevos_colores, len(fuera)
