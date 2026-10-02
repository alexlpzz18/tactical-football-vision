#!/usr/bin/env python
"""Comprobaciones ANTES de reentrenar el detector de balón (Colab). No entrena nada.

docs/plan_reentreno_balon.md, paso 5. Dos órdenes:

`minutos`: ¿de qué frames y minutos del partido sale el dataset ORIGINAL de v1
(799 frames del benjamín)? Si incluye los minutos del TEST del pool (0, 9, 10,
17) o frames exactos del test, hay que saberlo antes: los dos modelos los
habrían visto igual, y un frame idéntico al test se saca del test. Si el nombre
de los ficheros no permite saber el frame, lo DICE y para: no se adivina.

`augmentacion`: ¿la augmentation de la receta (configs/entrenamiento_balon.yaml)
conserva el balón? Regla de docs/plan_deteccion_balon.md: ≥ 95 % de las
imágenes con balón tienen que seguir teniéndolo tras aumentarlas. Se mide SIN
mosaico (que mezcla cuatro imágenes y taparía la pérdida de una) y, aparte, con
el mosaico de entrenamiento, solo como dato. Deja 12 ejemplos dibujados.

Uso (Colab, raíz del repo; los zips del dataset original en Drive):
    python scripts/colab_comprobaciones_reentreno.py minutos \\
        --imagenes-zip "$D/balon_benja_frames.zip" --etiquetas-zip "$D/balon_benja_labels..zip"
    python scripts/colab_comprobaciones_reentreno.py augmentacion \\
        --imagenes-zip ... --etiquetas-zip ... --salida "$D/salidas/reentreno_prev"
"""

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FPS = 30000 / 1001
FRAMES_VIDEO = 35966  # benja_gredos_p1_20min.mp4, decodificados
EXT_IMAGEN = (".png", ".jpg", ".jpeg")
RE_NUMERO = re.compile(r"(\d+)")


def frame_del_nombre(nombre: str) -> int | None:
    """El ÚLTIMO grupo de dígitos del nombre, si puede ser un frame del vídeo; si no, None."""
    numeros = RE_NUMERO.findall(Path(nombre).stem)
    if not numeros:
        return None
    n = int(numeros[-1])
    return n if 0 <= n < FRAMES_VIDEO else None


def normalizar_dataset(imagenes_zip, etiquetas_zip, destino: Path) -> tuple[int, int]:
    """Deja el dataset como lo quiere ultralytics: destino/images/todo y labels/todo.

    Empareja imagen y etiqueta por NOMBRE (sin extensión), sea cual sea la
    estructura de carpetas de los zips. Una imagen sin .txt es un negativo.
    Devuelve (imágenes, etiquetas emparejadas).
    """
    crudo = destino / "_crudo"
    for z in (imagenes_zip, etiquetas_zip):
        with zipfile.ZipFile(z) as zz:
            zz.extractall(crudo)
    (destino / "images" / "todo").mkdir(parents=True, exist_ok=True)
    (destino / "labels" / "todo").mkdir(parents=True, exist_ok=True)
    etiquetas = {p.stem: p for p in crudo.rglob("*.txt")}  # classes.txt no casa
    n_img = n_lab = 0
    for img in crudo.rglob("*"):
        if img.suffix.lower() not in EXT_IMAGEN:
            continue
        shutil.copy(img, destino / "images" / "todo" / img.name)
        n_img += 1
        if img.stem in etiquetas:
            shutil.copy(
                etiquetas[img.stem], destino / "labels" / "todo" / f"{img.stem}.txt"
            )
            n_lab += 1
    shutil.rmtree(crudo)
    return n_img, n_lab


def minutos(args, cfg):
    destino = Path(args.trabajo)
    n_img, n_lab = normalizar_dataset(args.imagenes_zip, args.etiquetas_zip, destino)
    nombres = sorted(p.name for p in (destino / "images" / "todo").iterdir())
    print(
        f"dataset original: {n_img} imágenes, {n_lab} con etiqueta (esperado 799 y ~502)"
    )
    print("10 nombres de ejemplo:", nombres[:5], "…", nombres[-5:])
    frames = [frame_del_nombre(n) for n in nombres]
    sin_frame = sum(f is None for f in frames)
    if sin_frame > len(nombres) * 0.05:
        print(
            f"⚠️ {sin_frame} nombres no dan un frame del vídeo: la convención de nombres no "
            "permite saber el minuto. PARA: no se adivina. Tráeme los nombres de ejemplo."
        )
        return
    r = cfg["reentreno"]
    por_minuto = {}
    for f in frames:
        if f is not None:
            por_minuto[int(f / FPS // 60)] = por_minuto.get(int(f / FPS // 60), 0) + 1
    print("imágenes por minuto del partido:", dict(sorted(por_minuto.items())))
    en_test = {m: por_minuto.get(m, 0) for m in r["test_pool_minutos"]}
    en_val = {m: por_minuto.get(m, 0) for m in r["validacion_pool_minutos"]}
    print(f"en los minutos de TEST del pool {en_test} · de VALIDACIÓN {en_val}")
    print(
        "⚠️ Ojo: suponer que el número es el frame es una HIPÓTESIS; compruébalo con los "
        "nombres de ejemplo antes de creerse esta tabla."
    )
    if args.manifiesto:
        import pandas as pd

        m = pd.read_csv(args.manifiesto)
        test = set(m[m.split == "test"].frame)
        iguales = sorted(test & {f for f in frames if f is not None})
        print(
            f"frames del TEST del pool que están EXACTOS en el dataset original: {iguales}"
        )


def augmentacion(args, cfg):
    import cv2
    import numpy as np
    from ultralytics.cfg import get_cfg
    from ultralytics.data import build_yolo_dataset

    destino = Path(args.trabajo)
    if not (destino / "images" / "todo").exists():
        normalizar_dataset(args.imagenes_zip, args.etiquetas_zip, destino)
    datos = {
        "path": str(destino),
        "train": str(destino / "images" / "todo"),
        "val": str(destino / "images" / "todo"),
        "names": {0: "balon"},
        "nc": 1,
        "channels": 3,
    }
    aug = dict(cfg["augmentation"])
    imgsz = int(cfg["entrenamiento"]["imgsz"])
    # nombres de las imágenes CON balón (etiqueta no vacía): solo esas cuentan
    con_balon_nombres = {
        t.stem
        for t in (destino / "labels" / "todo").glob("*.txt")
        if t.read_text().strip()
    }
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261003)
    for nombre, mosaico in (
        ("SIN mosaico (la regla)", 0.0),
        ("con mosaico", aug["mosaic"]),
    ):
        ov = dict(aug, mosaic=mosaico, imgsz=imgsz)
        ds = build_yolo_dataset(
            get_cfg(overrides=ov), datos["train"], 8, datos, mode="train"
        )
        # el orden de ds.im_files es el del dataset: se miran solo las imágenes CON balón
        con_balon = [
            i for i, f in enumerate(ds.im_files) if Path(f).stem in con_balon_nombres
        ]
        muestra = rng.choice(con_balon, size=min(args.n, len(con_balon)), replace=False)
        conservan = 0
        for k, i in enumerate(muestra):
            s = ds[int(i)]
            conservan += int(len(s["cls"]) > 0)
            if mosaico == 0.0 and k < 12:
                img = s["img"].numpy().transpose(1, 2, 0)[:, :, ::-1].copy()
                h, w = img.shape[:2]
                for cx, cy, bw, bh in s["bboxes"].numpy():
                    x1, y1 = int((cx - bw / 2) * w), int((cy - bh / 2) * h)
                    x2, y2 = int((cx + bw / 2) * w), int((cy + bh / 2) * h)
                    cv2.rectangle(
                        img, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (0, 0, 255), 2
                    )
                cv2.imwrite(str(salida / f"aumentada_{k:02d}.jpg"), img)
        frac = conservan / len(muestra)
        veredicto = (
            "OK"
            if frac >= 0.95
            else "⚠️ POR DEBAJO DEL 95 %: la augmentation va en contra"
        )
        print(
            f"{nombre}: {conservan}/{len(muestra)} conservan el balón ({100 * frac:.0f} %)"
            + (f" → {veredicto}" if mosaico == 0.0 else " (solo dato)")
        )
    print(f"✓ 12 ejemplos aumentados en {salida}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="orden", required=True)
    for nombre in ("minutos", "augmentacion"):
        s = sub.add_parser(nombre)
        s.add_argument("--imagenes-zip", required=True)
        s.add_argument("--etiquetas-zip", required=True)
        s.add_argument("--trabajo", default="/content/ds_v1")
        s.add_argument("--config", default="configs/entrenamiento_balon.yaml")
        if nombre == "minutos":
            s.add_argument("--manifiesto", default=None, help="manifiesto.csv del pool")
        else:
            s.add_argument("--salida", required=True)
            s.add_argument("--n", type=int, default=50)
    args = p.parse_args()
    cfg = yaml.safe_load(open(args.config))
    minutos(args, cfg) if args.orden == "minutos" else augmentacion(args, cfg)


if __name__ == "__main__":
    main()
