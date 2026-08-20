"""Fusión de cachés parciales: un partido entero en varias sesiones.

Problema real: procesar 20 minutos —y más aún un partido completo— no
cabe en una sesión de Colab sin que se muera a mitad. La solución no es
optimizar la detección, es partir el trabajo: cada sesión procesa UN
tramo, guarda su caché parcial en Drive, y al final se fusionan todos en
uno solo que el modo `desde_cache` consume como si fuera de una pieza.

Qué garantiza esta fusión, y por qué importa cada cosa:

- **Orden por frame global.** El tracking asume que el caché va en orden
  temporal; dos tramos concatenados al revés romperían la asociación sin
  dar ningún error visible.
- **Sin frames duplicados.** Los tramos suelen pedirse con solape (es
  buena práctica: da margen si uno falla). Un frame repetido metería dos
  veces a cada jugador y falsearía la concurrencia.
- **Metadatos coherentes.** Fusionar cachés con distinto `fps` o `sample`
  produciría un dt inconsistente, y todos los umbrales físicos del
  sistema (velocidad, huecos, suavizado) se calculan a partir de él. Se
  comprueba y se falla ruidosamente en vez de seguir con datos mezclados.

Los cachés de COLORES se fusionan igual, con la ventaja de que sus claves
(frame_idx, det_idx) ya son globales y únicas.
"""

import logging
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)


def fusionar_caches_detecciones(caches: list[dict]) -> dict:
    """Une varios cachés parciales en uno, ordenado y sin duplicados.

    Args:
        caches: contenido de cada caché parcial, en cualquier orden:
            {"cache": [...], "fps": float, "sample": int, "wh": (w, h)}.

    Returns:
        Un caché con la misma estructura, con las entradas de todos los
        tramos ordenadas por frame_idx.

    Raises:
        ValueError: si la lista está vacía o los metadatos no coinciden.
    """
    if not caches:
        raise ValueError("No hay ningún caché que fusionar.")

    base = caches[0]
    for i, otro in enumerate(caches[1:], start=1):
        for clave in ("fps", "sample", "wh"):
            if otro.get(clave) != base.get(clave):
                raise ValueError(
                    f"El caché {i} tiene {clave}={otro.get(clave)!r} y el "
                    f"primero {base.get(clave)!r}. Fusionarlos daría un dt "
                    "inconsistente y todos los umbrales físicos del sistema "
                    "(velocidad, huecos, suavizado) se calculan con él."
                )

    por_frame: dict[int, dict] = {}
    duplicados = 0
    for parcial in caches:
        for entrada in parcial["cache"]:
            if entrada["frame_idx"] in por_frame:
                duplicados += 1
                continue  # se queda el primero: los tramos con solape repiten
            por_frame[entrada["frame_idx"]] = entrada

    fusionado = dict(base)
    fusionado["cache"] = [por_frame[f] for f in sorted(por_frame)]
    logger.info(
        "Cachés fusionados: %d tramos → %d frames (%d duplicados por solape "
        "descartados), frames %d-%d",
        len(caches),
        len(fusionado["cache"]),
        duplicados,
        fusionado["cache"][0]["frame_idx"] if fusionado["cache"] else -1,
        fusionado["cache"][-1]["frame_idx"] if fusionado["cache"] else -1,
    )
    return fusionado


def fusionar_caches_colores(caches: list[dict]) -> dict:
    """Une los cachés de color. Las claves ya son globales y únicas."""
    fusionado: dict = {}
    colisiones = 0
    for parcial in caches:
        for clave, valor in parcial.items():
            if clave in fusionado:
                colisiones += 1
                continue
            fusionado[clave] = valor
    logger.info(
        "Colores fusionados: %d recortes (%d repetidos por solape)",
        len(fusionado),
        colisiones,
    )
    return fusionado


def huecos_de_cobertura(cache: list[dict], sample: int) -> list[tuple[int, int]]:
    """Tramos de frames que faltan, para saber si quedó alguno sin procesar.

    Devuelve [(desde, hasta)] de los saltos mayores que el muestreo. Es la
    comprobación que evita el peor final posible: creer que el partido
    está entero cuando se perdió una sesión de Colab por el camino.
    """
    huecos = []
    for anterior, siguiente in zip(cache, cache[1:]):
        salto = siguiente["frame_idx"] - anterior["frame_idx"]
        if salto > sample:
            huecos.append((anterior["frame_idx"], siguiente["frame_idx"]))
    return huecos


def fusionar_desde_rutas(
    rutas_detecciones: list[str | Path],
    rutas_colores: list[str | Path] | None = None,
) -> tuple[dict, dict | None]:
    """Carga y fusiona los cachés de disco. Devuelve (detecciones, colores)."""
    from src.tracking.cache_io import cargar_cache

    caches = []
    for ruta in rutas_detecciones:
        caches.append(cargar_cache(str(ruta)))
        logger.info("  %s: %d frames", ruta, len(caches[-1]["cache"]))
    detecciones = fusionar_caches_detecciones(caches)

    colores = None
    if rutas_colores:
        parciales = []
        for ruta in rutas_colores:
            with open(ruta, "rb") as f:
                parciales.append(pickle.load(f))
        colores = fusionar_caches_colores(parciales)

    huecos = huecos_de_cobertura(detecciones["cache"], detecciones["sample"])
    if huecos:
        logger.warning(
            "Hay %d hueco(s) en la cobertura temporal: %s. Falta algún tramo "
            "por procesar (o una sesión murió a mitad).",
            len(huecos),
            ", ".join(f"{a}→{b}" for a, b in huecos[:5]),
        )
    return detecciones, colores
