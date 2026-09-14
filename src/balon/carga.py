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

    dets = filtrar_balon_plausible(dets, modelo_campo)
    tras_plausible = len(dets)

    marcas = set()
    if quitar_marcas:
        dets, marcas = filtrar_marcas_estaticas(dets, tiempos, **umbrales_marcas)

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
