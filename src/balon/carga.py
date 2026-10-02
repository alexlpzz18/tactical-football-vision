"""Punto ÚNICO de entrada al caché de balón, con su limpieza puesta.

⚠️ POR QUÉ EXISTE ESTE MÓDULO. Hasta ahora cada consumidor del caché
llamaba a `filtrar_balon_plausible` por su cuenta: `procesar_balon`,
`posesion_parte_entera`, `oraculo_balon`, `gt_huecos_balon` y el propio
comparador. Al añadir un segundo filtro —el de marcas pintadas del
campo— eso significaba cinco sitios donde olvidarlo, y **un consumidor
que se olvide no falla: da un número distinto**, que es el peor modo de
fallo posible. Aquí se limpia una vez y se limpia igual para todos.

Los dos filtros, en orden:

1. **Plausibilidad física** (`filtrar_balon_plausible`): quita lo que
   proyecta fuera del campo. Sin él la velocidad máxima del balón salía a
   4151 m/s.
2. **Marcas estáticas** (`filtrar_marcas_estaticas`): quita lo que no se
   mueve nunca. El punto central, el de penalti y una mancha del fondo
   eran **el 56 % del caché** tras el esquema mixto
   (`docs/balon_fantasma.md`).

El orden importa: la plausibilidad primero, porque descarta cosas
absurdas que ensuciarían la estadística por celda del segundo.
"""

import logging
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)


def cargar_detecciones_limpias(
    ruta_cache, modelo_campo, quitar_marcas: bool = True, **umbrales_marcas
) -> tuple[dict, dict, dict]:
    """Lee el caché de balón y le aplica los dos filtros.

    Args:
        ruta_cache: el .pkl de balón.
        modelo_campo: modelo de campo, para la plausibilidad.
        quitar_marcas: se puede apagar para MEDIR el efecto del filtro,
            no para producción.
        **umbrales_marcas: se pasan a `filtrar_marcas_estaticas`.

    Returns:
        (detecciones, tiempos, metadatos del caché).
    """
    from src.balon.marcas_estaticas import filtrar_marcas_estaticas
    from src.balon.tracking_balon import filtrar_balon_plausible

    with open(ruta_cache, "rb") as f:
        datos = pickle.load(f)

    meta = {k: v for k, v in datos.items() if k != "cache"}
    n_frames = len(datos["cache"])
    tiempos = {e["frame_idx"]: e["t"] for e in datos["cache"]}
    dets = {e["frame_idx"]: e["dets"] for e in datos["cache"] if e["dets"]}
    crudas = len(dets)

    crudas_por_frame = dets
    dets = filtrar_balon_plausible(dets, modelo_campo)
    tras_plausible = len(dets)

    # Lo que quita la plausibilidad se GUARDA aparte: ahí está el balón en
    # vuelo (docs/balon_en_vuelo.md), que el selector puede readmitir por
    # continuidad. Sin las celdas de marca.
    plausibles = dets
    marcas = set()
    if quitar_marcas:
        dets, marcas = filtrar_marcas_estaticas(dets, tiempos, **umbrales_marcas)
    celda = umbrales_marcas.get("celda_px", 12)
    fuera_de_campo = {}
    for frame, todas in crudas_por_frame.items():
        quedan = plausibles.get(frame, [])
        fuera = [
            d
            for d in todas
            if d not in quedan
            and (int((d[2] + d[4]) / 2 // celda), int((d[3] + d[5]) / 2 // celda))
            not in marcas
        ]
        if fuera:
            fuera_de_campo[frame] = fuera
    meta["fuera_de_campo"] = fuera_de_campo

    # ⚠️ Se dice SIEMPRE de qué caché salen los números y cuánto se ha
    # quitado. El susto del 29-ago fue exactamente esto: un script dando
    # un reparto correcto del fichero equivocado, sin decir cuál era.
    esquema = (meta.get("firma") or {}).get("esquema")
    # print y no logger: varios scripts fijan el nivel de log en ERROR, y
    # un logger.warning aquí sería una guarda silenciada. Ya nos pasó.
    print(
        f"\nBALÓN · {Path(ruta_cache).name} · esquema "
        f"{esquema or 'DESCONOCIDO (anterior al mixto)'}\n"
        f"  {n_frames} frames · {crudas} con detección "
        f"({100 * crudas / max(n_frames, 1):.1f} %) → {tras_plausible} tras "
        f"plausibilidad → {len(dets)} tras marcas "
        f"({100 * len(dets) / max(n_frames, 1):.1f} %)\n"
        f"  celdas de marcas fijas quitadas: {len(marcas)}"
        + ("" if quitar_marcas else "   ⚠️ FILTRO DE MARCAS APAGADO")
    )
    meta["n_frames"] = n_frames
    meta["celdas_marcas"] = marcas
    return dets, tiempos, meta


def cargar_homografia_de_campo(ruta_config_campo):
    """La homografía píxeles→metros del config de campo (`rutas.homografia`).

    La necesita el selector del balón para saber cuánto mide un balón en
    cada punto de la imagen (1c, docs/selector_balon.md). Se lee del MISMO
    config de campo que ya usa la limpieza, para que no haya dos fuentes.
    """
    import numpy as np
    import yaml

    with open(ruta_config_campo) as fh:
        cfg = yaml.safe_load(fh)
    raiz = Path(ruta_config_campo).resolve().parent.parent
    ruta = Path(cfg["rutas"]["homografia"])
    return np.load(ruta if ruta.is_absolute() or ruta.exists() else raiz / ruta)


def contexto_del_selector(
    ruta_csv_jugadores,
    tiempos: dict,
    frames,
    ruta_config_campo,
    modelo,
    fuera_de_campo=None,
):
    """Todo lo que necesita `seleccionar_balon_activo` además de las detecciones.

    Un solo sitio para los cinco consumidores (procesar_balon, el vídeo y
    los scripts de medida): si cada uno lo armara a su manera, dos
    renderizadores podrían elegir balones distintos.

    Returns:
        (jugadores {frame: [(x, y, id)]}, kwargs para seleccionar_balon_activo).
    """
    jug = jugadores_por_frame_de_balon(ruta_csv_jugadores, tiempos, frames)
    staff = jugadores_por_frame_de_balon(
        ruta_csv_jugadores, tiempos, frames, solo_etiquetas=("staff",)
    )
    kwargs = {
        "tiempos": tiempos,
        "homografia": cargar_homografia_de_campo(ruta_config_campo),
        "posiciones_staff": {f: [(s[0], s[1]) for s in v] for f, v in staff.items()},
        "dimensiones_campo": (float(modelo.largo), float(modelo.ancho)),
        # Lo que quitó la plausibilidad (`meta["fuera_de_campo"]` de
        # cargar_detecciones_limpias): el balón en vuelo vuelve desde aquí.
        "detecciones_fuera_de_campo": fuera_de_campo,
    }
    return jug, kwargs


def jugadores_por_frame_de_balon(
    ruta_csv_jugadores,
    tiempos: dict,
    frames,
    excluir_etiquetas=("staff",),
    solo_etiquetas=None,
) -> dict:
    """{frame_de_balón: [(x_m, y_m, id)]} con los jugadores REALES de ese instante.

    ⚠️ El STAFF no cuenta como jugador (1-oct-2026, docs/selector_balon.md).
    Antes contaba: el entrenador y el niño del banquillo ganaban el desempate
    de "cercanía a un jugador" para el objeto que tuvieran a los pies (el
    zapato del entrenador llegó a ser el 43 % del balón elegido en un tramo)
    y podían recibir un contacto. Sacarlos sube el GT de desempates de 14 a
    16 de 38 y cuesta 14 frames: 7 del zapato y 7 de un balón real FUERA de
    juego, detrás de la línea de fondo. `excluir_etiquetas=()` es el
    comportamiento anterior. Con `solo_etiquetas=("staff",)` devuelve solo
    el staff (lo usa la regla del balón del banquillo, Plan 2).

    El balón y los jugadores van a frecuencias distintas (1 de cada 2
    frames contra 1 de cada 3), así que se casan por TIEMPO: el instante
    de jugadores más cercano dentro de 0,08 s, o ninguno.

    Estaba escrito dentro de `procesar_balon.py`. Se saca aquí para que el
    vídeo de diagnóstico elija el balón activo con los MISMOS jugadores que
    la pizarra: dos renderizadores con dos balones distintos serían otra
    herramienta de diagnóstico mintiendo sobre el sistema.
    """
    import pandas as pd

    jug = pd.read_csv(ruta_csv_jugadores)
    if solo_etiquetas is not None:
        reales = jug[(jug.es_real == 1) & jug.etiqueta.isin(list(solo_etiquetas))]
    else:
        reales = jug[(jug.es_real == 1) & ~jug.etiqueta.isin(list(excluir_etiquetas))]
    por_tiempo = {
        round(float(t), 2): [
            (float(r.x_m), float(r.y_m), int(r.id_jugador)) for r in g.itertuples()
        ]
        for t, g in reales.groupby("tiempo_s")
    }
    claves = sorted(por_tiempo)

    def en(frame):
        t = round(tiempos.get(frame, 0.0), 2)
        if t in por_tiempo:
            return por_tiempo[t]
        if not claves:
            return []
        import bisect

        i = bisect.bisect_left(claves, t)
        vecinos = [claves[k] for k in (i - 1, i) if 0 <= k < len(claves)]
        cercano = min(vecinos, key=lambda x: abs(x - t))
        return por_tiempo[cercano] if abs(cercano - t) <= 0.08 else []

    return {f: en(f) for f in frames}
