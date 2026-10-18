#!/usr/bin/env python
"""Prepara (NO lanza) el etiquetado dirigido del balón pegado al pie, para reentrenar.

Los 6 casos del GT de Alex donde el balón se VE y el modelo no da nada ni a
confianza 0,05 (docs/colab_balon_umbral_bajo.md): V05, V06, V15, V16, V18, V24.
Balón pegado al pie, tapado a medias, en conducción o desenfocado: lo que el
modelo no parece haber aprendido.

Por caso, el frame del GT y dos frames MUESTREADOS a cada lado (cada
`sample_every` del balón, ~0,07 s): el mismo momento de juego con el balón un
poco movido, 5 imágenes por caso, 30 en total. Cada una lleva una caja
PRE-PUESTA en la posición que marcó Alex, del tamaño que tendría un balón ahí
(1,9 × 0,20 m proyectados con la homografía: la proporción caja/balón medida en
el GT de desempates). En los frames vecinos la caja va en el mismo sitio y hay
que moverla: es solo un punto de partida.

Salida (en `outputs/`, no se versiona):
    images/*.png            frames enteros, sin dibujar nada
    labels/*.txt            preanotación en formato YOLO (clase 0 = balón)
    preanotaciones_coco.json  la misma preanotación en COCO, para importarla
    hoja.jpg                las 30 con la caja pre-puesta, para revisarlas
    LEEME.txt

⚠️ FUGA DE DATOS si se reentrena: estos frames son del mismo partido y minuto
que el banco de medida. El reentrenado no se puede evaluar en estos 6 casos
(ni en sus vecinos): hay que medir en frames que no entraron.

Uso:
    python scripts/preparar_etiquetado_balon_dirigido.py
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.tracking_balon import escala_px_por_m  # noqa: E402

CELDA_PX = 80
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWX"
# frame del GT, celdas de Alex y el ANCLA que nombró en su respuesta
# (outputs/gt_balon_en_vuelo, 2-oct-2026). "verde"/"rojo" son los círculos de su
# hoja: la posición del balón que el sistema SÍ midió justo antes/después, mucho
# más precisa que el centro de una celda de 80 px (±40 px para un balón de
# 10-15 px). Con la celda sola, la caja caía lejos del balón (V06: en el cielo).
CASOS = {
    "V05": (4434, ["O8"], "verde"),  # "O8, justo donde está el círculo verde"
    "V06": (5276, ["H5"], "verde"),  # "H5, justo donde el círculo verde"
    "V15": (21850, ["N8"], None),  # "N8 ... en el aire a la altura del brazo"
    "V16": (
        22818,
        ["U9", "V9"],
        "rojo_arriba",
    ),  # "en la parte de arriba del círculo rojo"
    "V18": (27032, ["F8"], "verde"),  # "justo dentro del círculo verde"
    "V24": (32918, ["O8"], "verde"),  # "O8, esto donde el círculo verde"
}
RADIO_CIRCULO_PX = 22  # el radio con que se pintaron los círculos en la hoja del GT
VECINOS = (-2, -1, 0, 1, 2)  # en pasos de `sample_every`
CAJA_SOBRE_BALON = 1.9  # lado de caja / diámetro proyectado (GT de desempates)
DIAMETRO_M = 0.20


def punto_del_caso(celdas, ancla, meta_caso):
    """Dónde poner la caja: el círculo que nombró Alex, o el centro de su celda."""
    if ancla == "verde":
        return tuple(meta_caso["antes"]["px"])
    if ancla == "rojo_arriba":
        x, y = meta_caso["despues"]["px"]
        return (x, y - RADIO_CIRCULO_PX)
    return punto_de_celdas(celdas)


def punto_de_celdas(celdas):
    pts = [
        ((LETRAS.index(c[0].upper()) + 0.5) * CELDA_PX, (int(c[1:]) - 0.5) * CELDA_PX)
        for c in celdas
    ]
    return tuple(np.mean(pts, axis=0))


def caja_preanotada(cx, cy, homografia, ancho, alto):
    """(x1, y1, x2, y2) de una caja de balón centrada en (cx, cy), mínimo 8 px."""
    lado = max(8.0, CAJA_SOBRE_BALON * DIAMETRO_M * escala_px_por_m(homografia, cx, cy))
    x1, y1 = max(0.0, cx - lado / 2), max(0.0, cy - lado / 2)
    return x1, y1, min(ancho - 1.0, cx + lado / 2), min(alto - 1.0, cy + lado / 2)


def a_yolo(caja, ancho, alto):
    x1, y1, x2, y2 = caja
    return (
        f"0 {(x1 + x2) / 2 / ancho:.6f} {(y1 + y2) / 2 / alto:.6f} "
        f"{(x2 - x1) / ancho:.6f} {(y2 - y1) / alto:.6f}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument("--sample-every", type=int, default=2)
    p.add_argument("--salida", default="outputs/etiquetado_balon_dirigido")
    p.add_argument("--metadatos-gt", default="outputs/gt_balon_en_vuelo/metadatos.json")
    args = p.parse_args()

    H = np.load(args.homografia)
    salida = Path(args.salida)
    (salida / "images").mkdir(parents=True, exist_ok=True)
    (salida / "labels").mkdir(parents=True, exist_ok=True)

    meta = json.loads(Path(args.metadatos_gt).read_text())
    pedidos = {}
    for caso, (frame, celdas, ancla) in CASOS.items():
        if meta[caso]["frame"] != frame:
            raise SystemExit(f"{caso}: el frame no coincide con {args.metadatos_gt}")
        punto = punto_del_caso(celdas, ancla, meta[caso])
        for k in VECINOS:
            pedidos[frame + k * args.sample_every] = (caso, k, punto)

    cap = cv2.VideoCapture(args.video)
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    pos, imagenes, anotaciones, miniaturas = 0, [], [], []
    for frame in sorted(pedidos):
        # Lectura SECUENCIAL hacia delante (nunca cap.set): el frame exacto.
        while pos < frame:
            cap.grab()
            pos += 1
        ok, img = cap.read()
        pos += 1
        if not ok:
            raise RuntimeError(f"No se pudo leer el frame {frame}")
        caso, k, (cx, cy) = pedidos[frame]
        nombre = f"{caso}_f{frame:06d}"
        cv2.imwrite(str(salida / "images" / f"{nombre}.png"), img)
        caja = caja_preanotada(cx, cy, H, ancho, alto)
        (salida / "labels" / f"{nombre}.txt").write_text(
            a_yolo(caja, ancho, alto) + "\n"
        )
        id_img = len(imagenes) + 1
        imagenes.append(
            {"id": id_img, "file_name": f"{nombre}.png", "width": ancho, "height": alto}
        )
        x1, y1, x2, y2 = caja
        anotaciones.append(
            {
                "id": id_img,
                "image_id": id_img,
                "category_id": 1,
                "bbox": [
                    round(x1, 1),
                    round(y1, 1),
                    round(x2 - x1, 1),
                    round(y2 - y1, 1),
                ],
                "area": round((x2 - x1) * (y2 - y1), 1),
                "iscrowd": 0,
            }
        )
        vis = img.copy()
        cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 1)
        x0 = int(np.clip(cx - 120, 0, ancho - 240))
        yy = int(np.clip(cy - 90, 0, alto - 180))
        x1r, y1r = x0 + 240, yy + 180
        mini = cv2.resize(
            vis[yy:y1r, x0:x1r], (360, 270), interpolation=cv2.INTER_NEAREST
        )
        cv2.putText(
            mini,
            f"{caso} {k:+d}",
            (4, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )
        miniaturas.append((caso, k, mini))

    coco = {
        "images": imagenes,
        "annotations": anotaciones,
        "categories": [{"id": 1, "name": "balon"}],
    }
    (salida / "preanotaciones_coco.json").write_text(json.dumps(coco, indent=1))
    filas = []
    for caso in CASOS:
        filas.append(np.hstack([m for c, _k, m in sorted(miniaturas) if c == caso]))
    cv2.imwrite(str(salida / "hoja.jpg"), np.vstack(filas))
    (salida / "LEEME.txt").write_text(
        "Etiquetado dirigido del balón (NO lanzado: se decide con la celda 2).\n"
        "30 imágenes: 6 casos x 5 frames. Cada una trae UNA caja pre-puesta donde\n"
        "marcaste el balón; en los vecinos (-2..+2) hay que moverla.\n"
        "- Importa images/ + preanotaciones_coco.json en el etiquetador, ajusta\n"
        "  cada caja al balón visible (aunque esté medio tapado: la caja cubre la\n"
        "  parte que se VE) y bórrala si en ese frame no se ve.\n"
        "- Clase única: balon. Exportar en YOLO (labels/*.txt) para ultralytics.\n"
        "⚠️ Si se reentrena con esto, NO medir en estos frames ni en sus vecinos.\n"
    )
    print(f"✓ {len(imagenes)} imágenes en {salida}/ (ver LEEME.txt y hoja.jpg)")


if __name__ == "__main__":
    main()
