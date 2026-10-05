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
    if args.json:
        import json

        etq = destino / "labels" / "todo"
        filas = [
            {
                "nombre": n,
                "frame": f,
                "con_balon": (etq / f"{Path(n).stem}.txt").exists()
                and bool((etq / f"{Path(n).stem}.txt").read_text().strip()),
            }
            for n, f in zip(nombres, frames)
        ]
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump(filas, fh)
        print(f"✓ {len(filas)} frames del original en {args.json} (bájalo al Mac)")
    if args.manifiesto:
        import pandas as pd

        m = pd.read_csv(args.manifiesto)
        test = set(m[m.split == "test"].frame)
        iguales = sorted(test & {f for f in frames if f is not None})
        print(
            f"frames del TEST del pool que están EXACTOS en el dataset original: {iguales}"
        )


# ───────────────────────── augmentation: medida fina (5-oct-2026) ─────────────────────────
# Qué significa "CONSERVA": que ultralytics NO descarte la caja tras la transformación. Su
# filtro (RandomPerspective.box_candidates) la tira si, a la resolución de la red, mide
# ≤ 2 px de ancho o de alto, si tras recortarla por el borde le queda < 10 % de su área, o
# si su proporción pasa de 100. Sin mosaico, solo mueven cajas `scale` y `translate` (giro,
# cizalla y perspectiva están a 0; volteos y color no pierden cajas).
#
# Una caja perdida NO es siempre un daño: si la traslación saca el balón de la imagen, esa
# imagen es un NEGATIVO CORRECTO. El daño es descartar la caja con el balón aún visible. Por
# eso cada caja se clasifica en uno de cuatro destinos:
DESTINOS = ("conservado", "fuera", "recortado", "pequeno")
LADO_MIN_V1_PX = 7.1  # el balón más pequeño que v1 ha detectado nunca, a imgsz 1280
UMBRAL_CONSERVA = 0.95


def clasificar_caja(w1, h1, w2, h2, conservada: bool, wh_thr=2.0, area_thr=0.10) -> str:
    """Destino de una caja: (w1, h1) escalada SIN recortar, (w2, h2) final recortada (px)."""
    if conservada:
        return "conservado"
    if w2 <= 0 or h2 <= 0:
        return "fuera"  # entera fuera de la imagen: negativo correcto
    if w2 * h2 / max(w1 * h1, 1e-9) <= area_thr:
        return "recortado"  # asoma por el borde menos de un 10 %
    return "pequeno"  # visible, pero ≤ 2 px: el balón sigue ahí y la etiqueta no


def lado_px(cajas_xywh_norm, alto: int, ancho: int) -> list[float]:
    """Lado de cada caja en píxeles de la red: la media de ancho y alto."""
    return [float((w * ancho + h * alto) / 2) for _cx, _cy, w, h in cajas_xywh_norm]


def elegir_mas_suave(
    barrido: list[dict], umbral: float = UMBRAL_CONSERVA
) -> dict | None:
    """De los ajustes que conservan ≥ umbral, el MÁS PARECIDO a v1: el de mayor escala y,
    a igualdad, mayor traslación. barrido: [{'scale', 'translate', 'conserva'}]."""
    validos = [b for b in barrido if b["conserva"] >= umbral]
    return max(validos, key=lambda b: (b["scale"], b["translate"])) if validos else None


def _carpeta_dataset(args) -> tuple[Path, Path]:
    """(imágenes, etiquetas) del dataset a medir: el original o el train del pool."""
    destino = Path(args.trabajo)
    if args.paquete_pool:
        pool = destino / "pool"
        if not pool.exists():
            with zipfile.ZipFile(args.paquete_pool) as z:
                z.extractall(pool)
        return pool / "images" / "train", pool / "labels" / "train"
    if not (destino / "images" / "todo").exists():
        normalizar_dataset(args.imagenes_zip, args.etiquetas_zip, destino)
    return destino / "images" / "todo", destino / "labels" / "todo"


def _medir(
    imagenes: Path, etiquetas: Path, imgsz: int, aug: dict, semillas, guardar=None
):
    """Pasa TODAS las imágenes con balón por la augmentation, con varias semillas.

    Devuelve {destino: n, 'lados': [...], 'n': total, 'conserva': fracción}.
    """
    import random

    import numpy as np
    import torch
    from ultralytics.cfg import get_cfg
    from ultralytics.data import build_yolo_dataset
    from ultralytics.data.augment import RandomPerspective

    datos = {"path": str(imagenes.parent.parent), "train": str(imagenes),
             "val": str(imagenes), "names": {0: "balon"}, "nc": 1, "channels": 3}  # fmt: skip
    con_balon = {t.stem for t in etiquetas.glob("*.txt") if t.read_text().strip()}
    ov = dict(aug, mosaic=0.0, mixup=0.0, imgsz=imgsz)
    ds = build_yolo_dataset(
        get_cfg(overrides=ov), str(imagenes), 8, datos, mode="train"
    )
    indices = [i for i, f in enumerate(ds.im_files) if Path(f).stem in con_balon]

    import inspect

    registro = []  # lo que ve el filtro de ultralytics en cada llamada
    crudo = inspect.getattr_static(RandomPerspective, "box_candidates")
    estatico = isinstance(crudo, staticmethod)
    original = crudo.__func__ if estatico else crudo

    def anotar(box1, box2, res, wh_thr, area_thr):
        w1, h1 = box1[2] - box1[0], box1[3] - box1[1]
        w2, h2 = box2[2] - box2[0], box2[3] - box2[1]
        registro.extend(
            zip(w1, h1, w2, h2, res, [wh_thr] * len(res), [area_thr] * len(res))
        )
        return res

    # Es método ESTÁTICO en las versiones recientes y de instancia en las viejas: se espía
    # con la misma forma que tenga, o el parche rompería la llamada.
    if estatico:

        def espia(box1, box2, wh_thr=2, ar_thr=100, area_thr=0.1, eps=1e-16):
            res = original(
                box1, box2, wh_thr=wh_thr, ar_thr=ar_thr, area_thr=area_thr, eps=eps
            )
            return anotar(box1, box2, res, wh_thr, area_thr)

        RandomPerspective.box_candidates = staticmethod(espia)
    else:

        def espia(self, box1, box2, wh_thr=2, ar_thr=100, area_thr=0.1, eps=1e-16):
            res = original(
                self,
                box1,
                box2,
                wh_thr=wh_thr,
                ar_thr=ar_thr,
                area_thr=area_thr,
                eps=eps,
            )
            return anotar(box1, box2, res, wh_thr, area_thr)

        RandomPerspective.box_candidates = espia
    cuenta = {d: 0 for d in DESTINOS}
    lados, imgs_ok, total = [], 0, 0
    try:
        for semilla in semillas:
            random.seed(semilla)
            np.random.seed(semilla)
            torch.manual_seed(semilla)
            for k, i in enumerate(indices):
                registro.clear()
                s = ds[i]
                total += 1
                imgs_ok += int(len(s["cls"]) > 0)
                for w1, h1, w2, h2, ok, wt, at in registro:
                    cuenta[clasificar_caja(w1, h1, w2, h2, bool(ok), wt, at)] += 1
                alto, ancho = s["img"].shape[1:]
                lados += lado_px(s["bboxes"].numpy(), alto, ancho)
                if guardar is not None and semilla == semillas[0] and k < 12:
                    _dibujar(s, guardar / f"aumentada_{k:02d}.jpg")
    finally:
        RandomPerspective.box_candidates = crudo
    if total and not sum(cuenta.values()):
        print(
            "⚠️ el espía no registró ninguna caja: esta versión de ultralytics no pasa por "
            "box_candidates. 'conserva' sigue valiendo; el desglose por destino, NO."
        )
    return {**cuenta, "lados": lados, "n": total, "conserva": imgs_ok / max(total, 1)}


def _dibujar(s, ruta: Path) -> None:
    import cv2

    img = s["img"].numpy().transpose(1, 2, 0)[:, :, ::-1].copy()
    h, w = img.shape[:2]
    for cx, cy, bw, bh in s["bboxes"].numpy():
        x1, y1 = int((cx - bw / 2) * w), int((cy - bh / 2) * h)
        x2, y2 = int((cx + bw / 2) * w), int((cy + bh / 2) * h)
        cv2.rectangle(img, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (0, 0, 255), 2)
    cv2.imwrite(str(ruta), img)


def _linea(nombre: str, r: dict) -> str:
    cajas = sum(r[d] for d in DESTINOS) or 1
    chicos = sum(1 for x in r["lados"] if x < LADO_MIN_V1_PX)
    pct_chicos = 100 * chicos / max(len(r["lados"]), 1)
    return (
        f"{nombre:<34} conserva {100 * r['conserva']:5.1f} % de {r['n']} · cajas: "
        + " · ".join(f"{d} {100 * r[d] / cajas:.1f} %" for d in DESTINOS)
        + f" · conservadas < {LADO_MIN_V1_PX} px: {chicos} ({pct_chicos:.1f} %)"
    )


def augmentacion(args, cfg):
    """a) todas las imágenes con balón y 3 semillas, sin mosaico; b) atribución por
    transformación; c) balones < 7,1 px; d) barrido si no llega al 95 %."""
    import json

    import numpy as np

    imagenes, etiquetas = _carpeta_dataset(args)
    imgsz = int(cfg["entrenamiento"]["imgsz"])
    base = dict(cfg["reentreno"]["augmentation"])
    semillas = list(range(1, args.semillas + 1))
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    print(f"dataset: {imagenes} · imgsz {imgsz} · semillas {semillas} · SIN mosaico")
    ramas = {
        "config (scale+translate)": base,
        "solo escala (translate 0)": dict(base, translate=0.0),
        "solo traslación (scale 0)": dict(base, scale=0.0),
        "ninguna (control)": dict(base, scale=0.0, translate=0.0),
    }
    res = {}
    for nombre, aug in ramas.items():
        res[nombre] = _medir(imagenes, etiquetas, imgsz, aug, semillas,
                             salida if nombre.startswith("config") else None)  # fmt: skip
        print(_linea(nombre, res[nombre]), flush=True)
    barrido = []
    if res["config (scale+translate)"]["conserva"] < UMBRAL_CONSERVA and args.barrido:
        print(f"\nBARRIDO (no llega al {100 * UMBRAL_CONSERVA:.0f} %):")
        for sc in (0.5, 0.4, 0.3, 0.25, 0.2, 0.1):
            for tr in (base["translate"], base["translate"] / 2):
                r = _medir(
                    imagenes,
                    etiquetas,
                    imgsz,
                    dict(base, scale=sc, translate=tr),
                    semillas,
                )
                barrido.append(
                    {"scale": sc, "translate": tr, "conserva": r["conserva"]}
                )
                print(_linea(f"scale {sc} · translate {tr}", r), flush=True)
        elegido = elegir_mas_suave(barrido)
        print(f"\n→ el más suave que llega al {100 * UMBRAL_CONSERVA:.0f} %: {elegido}")
    resumen = {}
    for k, v in res.items():
        lados = v["lados"] or [0.0]
        resumen[k] = {kk: vv for kk, vv in v.items() if kk != "lados"}
        resumen[k]["lado_p5_p50_px"] = [float(np.percentile(lados, q)) for q in (5, 50)]
        resumen[k]["conservadas_menores_7_1"] = sum(
            1 for x in lados if x < LADO_MIN_V1_PX
        )
    nombre = f"augmentacion_{'pool' if args.paquete_pool else 'original'}.json"
    with open(salida / nombre, "w") as fh:
        json.dump({"ramas": resumen, "barrido": barrido}, fh, indent=1)
    print(f"✓ resultados y 12 ejemplos en {salida}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="orden", required=True)
    for nombre in ("minutos", "augmentacion"):
        s = sub.add_parser(nombre)
        s.add_argument("--imagenes-zip", default=None)
        s.add_argument("--etiquetas-zip", default=None)
        s.add_argument("--trabajo", default="/content/ds_v1")
        s.add_argument("--config", default="configs/entrenamiento_balon.yaml")
        if nombre == "minutos":
            s.add_argument("--manifiesto", default=None, help="manifiesto.csv del pool")
            s.add_argument(
                "--json", default=None, help="guarda aquí los frames del original"
            )
        else:
            s.add_argument("--salida", required=True)
            s.add_argument("--semillas", type=int, default=3)
            s.add_argument(
                "--barrido", action="store_true", help="barre scale/translate"
            )
            s.add_argument(
                "--paquete-pool", default=None, help="zip del pool (mide su train)"
            )
    args = p.parse_args()
    cfg = yaml.safe_load(open(args.config))
    minutos(args, cfg) if args.orden == "minutos" else augmentacion(args, cfg)


if __name__ == "__main__":
    main()
