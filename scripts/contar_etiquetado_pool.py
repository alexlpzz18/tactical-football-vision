#!/usr/bin/env python
"""Cuenta el etiquetado del pool del balón pegado al pie, ANTES de entrenar.

Lee los dos exports de CVAT en YOLO 1.1 (tarea train y tarea test) y el
manifiesto del pool, y responde a lo que hay que saber antes de lanzar nada
(docs/plan_reentreno_balon.md):

- positivos (con balón) y negativos (sin caja) por split: train, val, test;
- ⚠️ si los negativos pasan de la MITAD del pool, avisa: el reentreno
  aprendería sobre todo "aquí no hay balón";
- ⚠️ si el test tiene menos de 12 positivos, avisa: un cambio de 2-3 balones
  sería ruido, no mejora;
- el criterio 1 del plan reescrito en BALONES ABSOLUTOS sobre los positivos
  reales del test;
- cuántas cajas quedaron EXACTAMENTE como la preanotación (¿revisadas o no?).

Uso:
    python scripts/contar_etiquetado_pool.py \\
        --train outputs/pool_balon_pegado/etiquetado/train_yolo.zip \\
        --test outputs/pool_balon_pegado/etiquetado/test_yolo.zip
"""

import argparse
import math
import zipfile
from pathlib import Path

import pandas as pd

MIN_POSITIVOS_TEST = 12
MEJORA_RELATIVA = 0.25  # la del plan: +0,25 de recall, pasado a balones


def leer_export_yolo(ruta_zip) -> dict[str, list[str]]:
    """{nombre_imagen_sin_extensión: [líneas de caja]} de un export YOLO 1.1 de CVAT."""
    salida = {}
    with zipfile.ZipFile(ruta_zip) as z:
        for nombre in z.namelist():
            if nombre.endswith(".txt") and "obj_train_data/" in nombre:
                lineas = [
                    ln for ln in z.read(nombre).decode().splitlines() if ln.strip()
                ]
                salida[Path(nombre).stem] = lineas
    return salida


def balones_para_mejorar(positivos: int) -> int:
    """El +0,25 de recall del plan, en balones: redondeo hacia ARRIBA (más exigente)."""
    return math.ceil(MEJORA_RELATIVA * positivos)


def contar(
    manifiesto: pd.DataFrame, etiquetas: dict, preanotadas: dict
) -> pd.DataFrame:
    filas = []
    for r in manifiesto.itertuples():
        nombre = f"f{int(r.frame):06d}"
        if r.split not in ("train", "val", "test"):
            continue
        cajas = etiquetas.get(nombre)
        filas.append(
            {
                "split": r.split,
                "frame": r.frame,
                "en_export": cajas is not None,
                "positivo": bool(cajas),
                "cajas": len(cajas or []),
                "sin_tocar": bool(cajas) and cajas == preanotadas.get(nombre),
            }
        )
    return pd.DataFrame(filas)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--train", required=True, help="export YOLO 1.1 de la tarea train")
    p.add_argument("--test", required=True, help="export YOLO 1.1 de la tarea test")
    p.add_argument("--pool", default="outputs/pool_balon_pegado")
    args = p.parse_args()

    pool = Path(args.pool)
    manifiesto = pd.read_csv(pool / "manifiesto.csv")
    etiquetas = {**leer_export_yolo(args.train), **leer_export_yolo(args.test)}
    preanotadas = {}
    for tarea in ("train", "test"):
        for txt in (pool / tarea / "labels").glob("*.txt"):
            preanotadas[txt.stem] = [
                ln for ln in txt.read_text().splitlines() if ln.strip()
            ]
    t = contar(manifiesto, etiquetas, preanotadas)

    faltan = t[~t.en_export]
    if len(faltan):
        print(
            f"⚠️ {len(faltan)} imágenes del manifiesto NO están en los exports: "
            f"{sorted(faltan.frame)[:10]}… (¿export sin todas las imágenes?)"
        )
    resumen = t.groupby("split").agg(
        imagenes=("frame", "size"),
        positivos=("positivo", "sum"),
        cajas=("cajas", "sum"),
    )
    resumen["negativos"] = resumen.imagenes - resumen.positivos
    print(resumen.to_string())
    print(
        f"cajas con más de una por imagen: {int((t.cajas > 1).sum())} imágenes "
        "(¿un segundo balón real?)"
    )
    print(
        f"cajas idénticas a la preanotación: {int(t.sin_tocar.sum())} de "
        f"{int(t.positivo.sum())} positivos (¿revisadas?)"
    )

    negativos = int(len(t) - t.positivo.sum())
    print(
        f"\nNEGATIVOS en el pool: {negativos} de {len(t)} "
        f"({100 * negativos / max(len(t), 1):.0f} %)"
        + (
            " ⚠️ MÁS DE LA MITAD: avisar a Alex antes de entrenar"
            if negativos > len(t) / 2
            else ""
        )
    )
    pos_test = int(t[t.split == "test"].positivo.sum())
    k = balones_para_mejorar(pos_test)
    print(
        f"TEST: {pos_test} positivos, {int((t.split == 'test').sum()) - pos_test} negativos"
    )
    print(
        f"CRITERIO 1 en balones: el modelo nuevo detecta al menos {k} balones MÁS que v1 "
        f"de los {pos_test} del test (+0,25 × {pos_test}, redondeado hacia arriba)"
    )
    if pos_test < MIN_POSITIVOS_TEST:
        print(
            f"⚠️ MENOS DE {MIN_POSITIVOS_TEST} POSITIVOS EN EL TEST: un cambio de pocos balones "
            "sería ruido. Propuesta: ampliar el test con más frames de los MISMOS minutos de "
            "test (hay huecos sin usar) hasta llegar a 12, sin tocar train ni val."
        )


if __name__ == "__main__":
    main()
