"""Carga y validación del caché de detecciones generado en Colab.

El caché es un pickle con este formato:
    {
        "cache": [
            {"frame_idx": int,          # índice de frame global del vídeo
             "t": float,                # tiempo en segundos
             "dets": [(mx, my, x1, y1, x2, y2, conf), ...]},
            ...
        ],
        "fps": float,    # fps del vídeo original
        "sample": int,   # se guardó 1 de cada `sample` frames
        "wh": (w, h),    # resolución del vídeo (píxeles)
    }

donde (mx, my) es la posición del jugador en METROS (pies proyectados con la
homografía) y (x1, y1, x2, y2) la caja en píxeles.
"""

import logging
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)

# Claves que debe tener el diccionario raíz del caché
_CLAVES_RAIZ = {"cache", "fps", "sample", "wh"}
# Claves que debe tener cada entrada de frame
_CLAVES_FRAME = {"frame_idx", "t", "dets"}
# Longitud de cada tupla de detección: (mx, my, x1, y1, x2, y2, conf)
_LARGO_DETECCION = 7


def cargar_cache(ruta: str | Path) -> dict:
    """Carga el caché de detecciones desde disco y valida su estructura.

    Args:
        ruta: ruta al archivo .pkl del caché.

    Returns:
        El diccionario del caché tal cual se guardó en Colab.

    Raises:
        FileNotFoundError: si el archivo no existe.
        ValueError: si la estructura del pickle no es la esperada.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe el caché de detecciones: {ruta}. "
            "Cópialo desde Google Drive a data/tracking/."
        )

    with open(ruta, "rb") as f:
        datos = pickle.load(f)

    _validar_cache(datos, ruta)

    logger.info(
        "Caché cargado: %d frames, fps=%.1f, sample=%d, wh=%s",
        len(datos["cache"]),
        datos["fps"],
        datos["sample"],
        datos["wh"],
    )
    return datos


def _validar_cache(datos: dict, ruta: Path) -> None:
    """Comprueba que el pickle tiene la estructura documentada arriba."""
    if not isinstance(datos, dict) or not _CLAVES_RAIZ.issubset(datos):
        raise ValueError(
            f"El caché {ruta} no tiene las claves esperadas {_CLAVES_RAIZ}; "
            f"encontrado: {list(datos) if isinstance(datos, dict) else type(datos)}"
        )
    if not datos["cache"]:
        raise ValueError(f"El caché {ruta} está vacío (lista 'cache' sin frames).")

    # Validamos la primera entrada como muestra representativa (validar las
    # 500 entradas det a det sería lento y no aporta seguridad extra real)
    primera = datos["cache"][0]
    if not _CLAVES_FRAME.issubset(primera):
        raise ValueError(
            f"Las entradas del caché deben tener claves {_CLAVES_FRAME}; "
            f"la primera tiene: {list(primera)}"
        )
    if primera["dets"] and len(primera["dets"][0]) != _LARGO_DETECCION:
        raise ValueError(
            "Cada detección debe ser (mx, my, x1, y1, x2, y2, conf); "
            f"la primera tiene longitud {len(primera['dets'][0])}"
        )
    _validar_contenido(datos, ruta)


def _validar_contenido(datos: dict, ruta: Path) -> None:
    """Comprueba PROPIEDADES del caché, no su ortografía.

    Hasta el 28-ago-2026 esta validación miraba solo que estuvieran las
    claves y que la primera detección tuviera 7 campos. Una auditoría
    adversarial le metió siete corrupciones y **las siete pasaron**, entre
    ellas multiplicar las posiciones por 20 —el caché deja de estar en
    metros y todo el pipeline lo trata como si lo estuviera— y vaciar
    todos los frames menos el primero.

    Es la función que encarna el control de "¿lo que he recuperado es de
    verdad lo que creo?", así que era el peor sitio posible para
    comprobar solo la forma.

    Los umbrales salen de MEDIR los once cachés del repo, no de números
    que suenen bien; cada uno lleva su rango observado al lado.
    """
    import numpy as np

    cache = datos["cache"]
    sample = int(datos.get("sample") or 1)

    # ── 1. El caché es una SERIE TEMPORAL ────────────────────────────
    fi = [e["frame_idx"] for e in cache]
    if any(b <= a for a, b in zip(fi, fi[1:])):
        raise ValueError(
            f"El caché {ruta} no está ordenado por frame_idx. Es una serie "
            "temporal y el tracking asume que avanza."
        )
    saltos = {b - a for a, b in zip(fi, fi[1:])}
    if sample > 1 and any(s % sample for s in saltos):
        raise ValueError(
            f"El caché {ruta} dice sample={sample} pero hay saltos de "
            f"frame_idx que no son múltiplos: {sorted(saltos)[:5]}. O el "
            "sample es otro, o se han mezclado dos cachés."
        )

    # ── 2. No puede estar casi vacío ─────────────────────────────────
    # Observado: 0 % de frames vacíos en los cachés de jugadores y 47 % en
    # el de balón (el balón no siempre se ve). El 95 % deja sitio de sobra
    # y caza el "✓ engañoso" de un caché que no detectó nada.
    vacios = sum(1 for e in cache if not e["dets"])
    if vacios > 0.95 * len(cache):
        raise ValueError(
            f"El caché {ruta} tiene {vacios} de {len(cache)} frames SIN "
            "detecciones. Eso no es un caché, es una pasada fallida."
        )

    dets = [d for e in cache[:: max(len(cache) // 500, 1)] for d in e["dets"]]
    if not dets:
        return
    arr = np.asarray([d[:7] for d in dets], dtype=float)

    # ── 3. Las posiciones siguen en METROS ───────────────────────────
    # La MEDIANA, no el máximo: la proyección se dispara legítimamente en
    # el fondo (se han medido |mx| de hasta 6808 m en un caché sano), así
    # que un tope sobre el máximo no separaría nada. La mediana observada
    # va de 35 a 62 m en los once cachés; multiplicar por 20 la lleva a
    # 695. El corte en 300 está holgado por los dos lados.
    for eje, nombre in ((0, "mx"), (1, "my")):
        mediana = float(np.median(np.abs(arr[:, eje])))
        if mediana > 300.0:
            raise ValueError(
                f"El caché {ruta} tiene una mediana de |{nombre}| de "
                f"{mediana:.0f} m. Las posiciones deben estar en METROS "
                "(mediana observada: 35-62 m). ¿Se ha guardado en píxeles "
                "o con otra homografía?"
            )

    # ── 4. Confianzas y cajas ────────────────────────────────────────
    conf = arr[:, 6]
    if conf.min() < 0.0 or conf.max() > 1.0:
        raise ValueError(
            f"El caché {ruta} tiene confianzas fuera de [0, 1]: "
            f"[{conf.min():.2f}, {conf.max():.2f}]."
        )
    if (arr[:, 4] <= arr[:, 2]).any() or (arr[:, 5] <= arr[:, 3]).any():
        raise ValueError(
            f"El caché {ruta} tiene cajas con x2<=x1 o y2<=y1: las "
            "coordenadas están invertidas o corruptas."
        )

    # ── 5. Huecos temporales: AVISO, no error ────────────────────────
    # Un caché al que le falta un trozo por el medio sigue teniendo saltos
    # múltiplos de `sample`, así que parece uno legítimo más corto. Pero
    # un caché FUSIONADO puede tener huecos de verdad (los gestiona
    # src/tracking/fusion_caches.py), así que esto avisa y no rompe.
    paso = min(saltos) if saltos else sample
    grandes = [s for s in saltos if s > 5 * paso]
    if grandes:
        logger.warning(
            "El caché %s tiene %d salto(s) grandes de frame_idx (hasta %d "
            "frames, %.0f× el paso normal de %d). Si no es un caché "
            "fusionado, le falta un trozo por el medio.",
            ruta,
            len(grandes),
            max(grandes),
            max(grandes) / paso,
            paso,
        )
