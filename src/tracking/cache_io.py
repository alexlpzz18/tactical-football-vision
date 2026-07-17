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
