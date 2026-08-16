#!/usr/bin/env python
"""Ensambla el dataset v4 (478 + 360) con auditoría de calidad integrada.

El lote nuevo lo etiqueta otra persona, así que la pregunta no es solo
"¿están las cajas?" sino "¿están etiquetadas con el mismo criterio?".
Una diferencia sistemática —cajas más apretadas, piernas fuera, porteros
sin etiquetar— envenena el entrenamiento sin que nada falle, y se
descubre tarde, cuando el modelo ya está entrenado.

Por eso la auditoría NO es un paso aparte que uno se salta: corre siempre
y bloquea el ensamblaje si algo se sale de rango.

Qué comprueba, y por qué cada cosa:

- **Cajas por frame**: si un lote tiene sistemáticamente menos, es que su
  etiquetador se dejó jugadores (típico: los del fondo, diminutos).
- **Tamaños**: la distribución de altura de caja delata criterios
  distintos al encuadrar (piernas dentro o fuera).
- **Clases**: que no haya ids de clase inesperados ni lotes que usen otra
  numeración.
- **Cajas degeneradas**: ancho o alto ~0, coordenadas fuera de [0,1].
- **Imágenes sin etiqueta y etiquetas sin imagen**: los dos sentidos.

Uso:
    python scripts/ensamblar_dataset_v4.py \\
        --lote data/datasets/lote_alex_478 \\
        --lote data/datasets/lote_ayudante_360 \\
        --salida data/datasets/v4_840
"""

import argparse
import logging
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("dataset_v4")

EXTENSIONES = (".jpg", ".jpeg", ".png")
# Desviación tolerada entre lotes antes de parar el ensamblaje. Un 25 %
# de diferencia en cajas por frame ya no es azar: es otro criterio.
TOLERANCIA_CAJAS = 0.25
TOLERANCIA_TAMANO = 0.30


def leer_lote(carpeta: Path) -> dict:
    """{nombre: [(clase, cx, cy, w, h)]} de un lote en formato YOLO."""
    imagenes, etiquetas = {}, {}
    for sub in ("images", "labels", "."):
        base = carpeta / sub if sub != "." else carpeta
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if f.suffix.lower() in EXTENSIONES:
                imagenes[f.stem] = f
            elif f.suffix.lower() == ".txt" and f.stem != "classes":
                filas = []
                for linea in f.read_text().strip().splitlines():
                    partes = linea.split()
                    if len(partes) >= 5:
                        filas.append((int(partes[0]), *[float(x) for x in partes[1:5]]))
                etiquetas[f.stem] = filas
    return {"imagenes": imagenes, "etiquetas": etiquetas, "carpeta": carpeta}


def auditar(lote: dict, nombre: str) -> dict:
    """Estadísticos del lote + problemas encontrados."""
    imgs, etqs = lote["imagenes"], lote["etiquetas"]
    problemas = []

    sin_etiqueta = sorted(set(imgs) - set(etqs))
    sin_imagen = sorted(set(etqs) - set(imgs))
    if sin_imagen:
        problemas.append(f"{len(sin_imagen)} etiquetas sin su imagen")

    cajas_por_frame, alturas, clases, degeneradas, fuera = [], [], Counter(), 0, 0
    for nom, filas in etqs.items():
        cajas_por_frame.append(len(filas))
        for clase, cx, cy, w, h in filas:
            clases[clase] += 1
            alturas.append(h)
            if w <= 1e-4 or h <= 1e-4:
                degeneradas += 1
            if not (0 <= cx <= 1 and 0 <= cy <= 1 and w <= 1 and h <= 1):
                fuera += 1

    if degeneradas:
        problemas.append(f"{degeneradas} cajas de tamaño ~0")
    if fuera:
        problemas.append(f"{fuera} cajas fuera de [0,1]")

    return {
        "nombre": nombre,
        "n_imagenes": len(imgs),
        "n_etiquetadas": len(etqs),
        "sin_etiqueta": len(sin_etiqueta),
        "vacias": sum(1 for f in etqs.values() if not f),
        "cajas": sum(cajas_por_frame),
        "cajas_por_frame": float(np.mean(cajas_por_frame)) if cajas_por_frame else 0.0,
        "altura_mediana": float(np.median(alturas)) if alturas else 0.0,
        "clases": dict(clases),
        "problemas": problemas,
    }


def comparar_lotes(auditorias: list[dict]) -> list[str]:
    """Diferencias SISTEMÁTICAS entre lotes: el riesgo real del multi-etiquetador."""
    alertas = []
    if len(auditorias) < 2:
        return alertas

    ref = auditorias[0]
    for otro in auditorias[1:]:
        for campo, tol, que in (
            ("cajas_por_frame", TOLERANCIA_CAJAS, "cajas por frame"),
            ("altura_mediana", TOLERANCIA_TAMANO, "altura mediana de caja"),
        ):
            a, b = ref[campo], otro[campo]
            if a <= 0:
                continue
            desvio = abs(b - a) / a
            if desvio > tol:
                alertas.append(
                    f"{que}: '{ref['nombre']}' {a:.2f} vs '{otro['nombre']}' "
                    f"{b:.2f} ({100 * desvio:.0f} % de diferencia, tolerancia "
                    f"{100 * tol:.0f} %) — probable criterio de etiquetado distinto"
                )
        if set(ref["clases"]) != set(otro["clases"]):
            alertas.append(
                f"clases distintas: '{ref['nombre']}' {sorted(ref['clases'])} vs "
                f"'{otro['nombre']}' {sorted(otro['clases'])}"
            )
    return alertas


def muestra_para_revision(lotes, salida: Path, fraccion=0.02, semilla=7):
    """Copia un 2 % al azar para que Alex lo mire con sus etiquetas.

    La auditoría automática caza lo que es medible; el criterio de
    encuadre solo lo juzga un ojo. Un 2 % de 840 son ~17 imágenes: un
    rato, no una tarde.
    """
    rng = random.Random(semilla)
    destino = salida / "revision_2pct"
    destino.mkdir(parents=True, exist_ok=True)
    elegidas = []
    for lote in lotes:
        nombres = sorted(lote["etiquetas"])
        n = max(1, int(len(nombres) * fraccion))
        for nom in rng.sample(nombres, min(n, len(nombres))):
            if nom in lote["imagenes"]:
                elegidas.append((lote["carpeta"].name, nom, lote))
    for origen_nombre, nom, lote in elegidas:
        shutil.copy2(lote["imagenes"][nom], destino / f"{origen_nombre}__{nom}.jpg")
        etq = destino / f"{origen_nombre}__{nom}.txt"
        etq.write_text(
            "\n".join(" ".join(str(x) for x in fila) for fila in lote["etiquetas"][nom])
        )
    return destino, len(elegidas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lote", action="append", required=True)
    parser.add_argument("--salida", required=True)
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Ensambla aunque la auditoría encuentre diferencias entre lotes",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    lotes = []
    for ruta in args.lote:
        carpeta = Path(ruta)
        if not carpeta.exists():
            raise SystemExit(f"ERROR: no existe el lote {carpeta}")
        lotes.append(leer_lote(carpeta))

    print("\n── AUDITORÍA POR LOTE ──")
    cab = (
        f"{'lote':<24}{'imgs':>7}{'etiq':>7}{'vacías':>8}{'cajas':>8}"
        f"{'caj/frame':>11}{'alto med.':>11}"
    )
    print(cab)
    print("-" * len(cab))
    auditorias = []
    for lote in lotes:
        a = auditar(lote, lote["carpeta"].name)
        auditorias.append(a)
        print(
            f"{a['nombre']:<24}{a['n_imagenes']:>7}{a['n_etiquetadas']:>7}"
            f"{a['vacias']:>8}{a['cajas']:>8}{a['cajas_por_frame']:>11.2f}"
            f"{a['altura_mediana']:>11.4f}"
        )
        for p in a["problemas"]:
            print(f"    ⚠ {p}")

    alertas = comparar_lotes(auditorias)
    print("\n── COHERENCIA ENTRE LOTES ──")
    if alertas:
        for al in alertas:
            print(f"  ⚠ {al}")
    else:
        print("  Sin diferencias sistemáticas por encima de la tolerancia.")

    salida = Path(args.salida)
    if alertas and not args.forzar:
        raise SystemExit(
            "\nENSAMBLAJE DETENIDO. Las diferencias de arriba envenenarían el "
            "entrenamiento sin que nada falle.\n"
            "  Revísalas y, si son aceptables, repite con --forzar."
        )

    # ── ensamblaje ──
    rng = random.Random(11)
    todas = []
    for lote in lotes:
        for nom, filas in lote["etiquetas"].items():
            if nom in lote["imagenes"]:
                todas.append((lote["imagenes"][nom], filas, lote["carpeta"].name))
    rng.shuffle(todas)
    corte = int(len(todas) * (1 - args.val_frac))

    for particion, items in (("train", todas[:corte]), ("val", todas[corte:])):
        (salida / "images" / particion).mkdir(parents=True, exist_ok=True)
        (salida / "labels" / particion).mkdir(parents=True, exist_ok=True)
        for img, filas, lote_nombre in items:
            destino = f"{lote_nombre}__{img.stem}"
            shutil.copy2(img, salida / "images" / particion / f"{destino}{img.suffix}")
            (salida / "labels" / particion / f"{destino}.txt").write_text(
                "\n".join(" ".join(str(x) for x in f) for f in filas)
            )

    (salida / "data.yaml").write_text(
        f"path: {salida.resolve()}\ntrain: images/train\nval: images/val\n"
        f"nc: 1\nnames: [jugador]\n"
    )
    destino_rev, n_rev = muestra_para_revision(lotes, salida)

    print(f"\n✓ Dataset en {salida}")
    print(f"  train {corte} · val {len(todas) - corte} · total {len(todas)}")
    print(f"✓ Muestra del 2 % para tu revisión: {destino_rev} ({n_rev} imágenes)")
    print("  Ábrelas con sus .txt y comprueba que el criterio de encuadre")
    print("  es el mismo en los dos lotes (piernas dentro, porteros incluidos).")


if __name__ == "__main__":
    main()
