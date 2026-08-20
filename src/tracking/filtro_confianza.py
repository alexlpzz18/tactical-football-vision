"""Filtro de confianza sobre el caché, con remapeo del caché de colores.

Por qué es una etapa y no un `if` suelto: el barrido del 17-ago-2026
mostró que la confianza es una palanca de primer orden **para el v4**
—subirla de 0,3 a 0,45 baja las quimeras de 8 a 3 y sube la cobertura—
mientras que en el v4pre hunde la cobertura. O sea que el número correcto
va pegado al detector y tiene que vivir en el config, no en un script.

Y por qué no es un one-liner: el caché de colores está indexado por
`(frame_idx, det_idx)`, donde `det_idx` es la POSICIÓN en la lista de
detecciones de ese frame. Al tirar entradas, todos los índices
posteriores se desplazan y cada caja quedaría emparejada con el color de
otra persona — **sin fallar**, que es la peor forma de romperse. Aquí se
remapean las dos cosas a la vez.
"""

import logging

logger = logging.getLogger(__name__)

# Índice de la confianza en la tupla del caché:
# (mx, my, x1, y1, x2, y2, conf)
_IDX_CONF = 6


def filtrar_por_confianza(
    cache: list[dict],
    colores: dict | None,
    conf_min: float,
) -> tuple[list[dict], dict | None]:
    """Devuelve (caché, colores) sin las detecciones por debajo de `conf_min`.

    Args:
        cache: lista de frames del caché de detecciones (ver cache_io).
        colores: caché {(frame_idx, det_idx): feature}, o None.
        conf_min: confianza mínima. Un valor <= 0 devuelve todo tal cual.

    Returns:
        El caché filtrado y el caché de colores **reindexado** para que
        siga apuntando a la misma caja que antes.
    """
    if conf_min <= 0:
        return cache, colores

    nuevo_cache: list[dict] = []
    nuevos_colores: dict = {}
    n_antes = n_despues = 0

    for entrada in cache:
        frame = entrada["frame_idx"]
        dets = []
        for idx_viejo, det in enumerate(entrada["dets"]):
            n_antes += 1
            if det[_IDX_CONF] < conf_min:
                continue
            idx_nuevo = len(dets)
            dets.append(det)
            n_despues += 1
            if colores is not None and (frame, idx_viejo) in colores:
                nuevos_colores[(frame, idx_nuevo)] = colores[(frame, idx_viejo)]
        nuevo_cache.append({**entrada, "dets": dets})

    if n_antes:
        logger.info(
            "Filtro de confianza ≥ %.2f: %d → %d detecciones (%.1f %% descartadas)",
            conf_min,
            n_antes,
            n_despues,
            100 * (1 - n_despues / n_antes),
        )
    return nuevo_cache, (nuevos_colores if colores is not None else None)
