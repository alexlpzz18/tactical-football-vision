#!/usr/bin/env python
"""¿De qué partidos y cámaras está hecho el dataset? ¿Falta alguno?

La pregunta que motiva esto: si un partido está infrarrepresentado, el
detector estará especializado en los otros y rendirá peor ahí — y eso se
confunde fácilmente con "el modelo es peor". Saber la composición separa
las dos explicaciones antes de gastar horas etiquetando.

Clasifica por el NOMBRE del archivo, que es lo único que sobrevive al
ensamblado. Los patrones se declaran abajo y se pueden ampliar; lo que no
encaje en ninguno sale en "sin_clasificar", que es información y no un
error a esconder.

Uso (donde esté el dataset, típicamente Colab con Drive montado):
    python scripts/auditar_composicion_dataset.py --raiz data/datasets/v4_840
    python scripts/auditar_composicion_dataset.py --raiz /content/drive/.../v4_840
"""

import argparse
import logging
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

EXTENSIONES = (".jpg", ".jpeg", ".png")

# Orden importante: el primero que casa, gana.
PATRONES = [
    ("benja (F7, cámara del benjamín)", r"benja|gredos"),
    ("Villaviciosa (F11)", r"villa|vcs"),
    ("Arganzuela (F11 gran angular)", r"argan"),
    ("Bazán (F11 gran angular)", r"bazan|bazán"),
    ("dataset público", r"public|soccernet|open|kaggle"),
]


def clasificar(nombre: str) -> str:
    n = nombre.lower()
    for etiqueta, patron in PATRONES:
        if re.search(patron, n):
            return etiqueta
    return "sin_clasificar"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raiz", required=True, help="Carpeta del dataset")
    p.add_argument(
        "--ejemplos",
        type=int,
        default=5,
        help="Nombres de ejemplo a mostrar de cada grupo (para verificar el patrón)",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    raiz = Path(args.raiz)
    if not raiz.exists():
        raise SystemExit(f"No existe: {raiz}")

    imagenes = [
        f
        for f in raiz.rglob("*")
        if f.suffix.lower() in EXTENSIONES and "label" not in f.parts
    ]
    if not imagenes:
        raise SystemExit(f"Ninguna imagen bajo {raiz}")

    cuenta: Counter = Counter()
    ejemplos: dict[str, list[str]] = {}
    por_split: dict[str, Counter] = {}
    for f in imagenes:
        grupo = clasificar(f.name)
        cuenta[grupo] += 1
        ejemplos.setdefault(grupo, []).append(f.name)
        # train/val/test si el dataset está partido
        split = next((p for p in f.parts if p in ("train", "val", "test")), "—")
        por_split.setdefault(grupo, Counter())[split] += 1

    total = sum(cuenta.values())
    print(f"\n── COMPOSICIÓN DE {raiz} ({total} imágenes) ──\n")
    cab = f"{'origen':<36}{'imágenes':>10}{'%':>8}   splits"
    print(cab)
    print("-" * (len(cab) + 10))
    for grupo, n in cuenta.most_common():
        splits = ", ".join(f"{k}:{v}" for k, v in sorted(por_split[grupo].items()))
        print(f"{grupo:<36}{n:>10}{n / total:>8.1%}   {splits}")

    print("\nEjemplos de nombre (para verificar que el patrón acierta):")
    for grupo, nombres in ejemplos.items():
        print(f"  {grupo}: {', '.join(nombres[: args.ejemplos])}")

    sin = cuenta.get("sin_clasificar", 0)
    if sin:
        print(
            f"\n⚠ {sin} imágenes ({sin / total:.1%}) no encajan en ningún patrón: "
            "amplía PATRONES antes de fiarte de los porcentajes."
        )


if __name__ == "__main__":
    main()
