#!/usr/bin/env python
"""GT de POSICIÓN de balón: recortes grandes con rejilla, un código por frame.

No existía en el proyecto ningún GT con la posición real del balón (ni en
píxeles ni en metros, en ningún frame) — confirmado al intentar medir
recall@K contra "el candidato correcto" sin saber cuál era
(`docs/sahi_balon.md`, verificación del 1-oct-2026). Esta herramienta
anota una muestra pequeña, con el mismo estilo que `gt_huecos_balon.py` y
`hoja_revision_recuento.py`: recorte grande, rejilla para responder con un
código corto en vez de coordenadas a mano, y las cajas/candidatos salen
del CACHÉ real, no de una re-detección.

⚠️ Dos grupos, a propósito (pedido de Alex, 1-oct-2026):

- **A (candidato_bajo)**: frames donde SÍ hay un candidato, pero de
  confianza baja. Decide si "el balón no se detecta" es realmente "no
  genera ninguna señal" o "genera señal débil que el filtro final tira" —
  la pregunta del punto 2 del plan.
- **B (hueco)**: frames SIN ningún candidato (plausible) en absoluto. La
  mayoría, A PROPÓSITO, caen cerca en el tiempo de una de las 10 marcas
  fijas conocidas — es el caso que más preocupa: ¿se come la marca al
  balón real que está ahí al lado? El resto son huecos "de control",
  lejos de cualquier marca, para tener contraste.

Cada recorte usa `posicionar_en_frame()` (nunca `cap.set`, ver
`src/tracking_data/processor.py`) y una rejilla de celdas de 20×20 px
REALES del vídeo (el recorte se pinta ampliado ×2 para que se vea con
claridad, pero las celdas siguen midiendo 20 px en el original). Columna
(letra) + fila (número), como una hoja de cálculo: "K7".

Uso:
    python scripts/gt_posicion_balon.py --salida-dir outputs/gt_posicion_balon
"""

import argparse
import bisect
import logging
import pickle
import random
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.marcas_estaticas import encontrar_marcas_estaticas  # noqa: E402
from src.balon.tracking_balon import filtrar_balon_plausible  # noqa: E402
from src.campo_modelo import cargar_modelo  # noqa: E402
from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("gt_posicion_balon")

CELDA_PX = 20  # tamaño de celda en píxeles DEL VÍDEO ORIGINAL
ZOOM = 2  # factor de ampliación solo para mostrar
COLUMNAS, FILAS = 25, 18  # recorte de 500x360 px reales -> 1000x720 mostrados
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXY"  # 25 letras, sin Ñ ni acentos
SEMILLA = 20261001  # fecha de la medición, para que la selección sea reproducible


def _centro_px(det):
    return (det[2] + det[4]) / 2.0, (det[3] + det[5]) / 2.0


def _elegir_espaciadas(items_ordenados, n, min_separacion_s, clave_t):
    """Toma como mucho n elementos de una lista ORDENADA por tiempo, sin dos
    a menos de `min_separacion_s` entre sí — para no repetir casi el mismo
    instante dos veces en la muestra."""
    elegidos = []
    for item in items_ordenados:
        t = clave_t(item)
        if all(abs(t - clave_t(e)) >= min_separacion_s for e in elegidos):
            elegidos.append(item)
        if len(elegidos) >= n:
            break
    return elegidos


def seleccionar_frames(
    ruta_cache, config_campo, n_bajo=20, n_hueco=20, frac_hueco_cerca_marca=0.7
):
    with open(ruta_cache, "rb") as f:
        crudo = pickle.load(f)
    tiempos = {e["frame_idx"]: e["t"] for e in crudo["cache"]}
    dets_crudas = {e["frame_idx"]: e["dets"] for e in crudo["cache"] if e["dets"]}
    todos_frames = sorted(tiempos)

    modelo = cargar_modelo(config=config_campo)
    dets_pl = filtrar_balon_plausible(dets_crudas, modelo)
    marcas = encontrar_marcas_estaticas(dets_pl, tiempos)

    rng = random.Random(SEMILLA)

    # ── Grupo A: candidato de confianza baja ──────────────────────────
    con_candidato = []
    for f, dets in dets_pl.items():
        mejor = max(dets, key=lambda d: d[6])
        con_candidato.append((f, tiempos[f], mejor))
    # El 30 % de score más bajo del propio conjunto: "bajo" es relativo a
    # esta cámara y este detector, no un número absoluto inventado.
    p30 = float(np.percentile([c[2][6] for c in con_candidato], 30))
    bajos = [c for c in con_candidato if c[2][6] <= p30]
    rng.shuffle(bajos)
    bajos.sort(key=lambda c: c[1])
    grupo_a = _elegir_espaciadas(
        bajos, n_bajo, min_separacion_s=10.0, clave_t=lambda c: c[1]
    )

    # ── Grupo B: hueco total, con/sin cercanía a una marca ─────────────
    frames_con_cand = set(dets_pl.keys())
    huecos = [f for f in todos_frames if f not in frames_con_cand]

    cand_marca = []  # (t, celda, px, py)
    for f, dets in dets_pl.items():
        t = tiempos[f]
        for det in dets:
            px, py = _centro_px(det)
            celda = (int(px // 12), int(py // 12))
            if celda in marcas:
                cand_marca.append((t, celda, px, py))
    cand_marca.sort()
    t_marca = [c[0] for c in cand_marca]

    cerca, lejos = [], []
    for f in huecos:
        t = tiempos[f]
        i = bisect.bisect_left(t_marca, t)
        vecino = None
        for j in (i - 1, i):
            if 0 <= j < len(cand_marca) and abs(cand_marca[j][0] - t) <= 1.0:
                vecino = cand_marca[j]
                break
        (cerca if vecino else lejos).append((f, t, vecino))

    n_cerca = round(n_hueco * frac_hueco_cerca_marca)
    n_lejos = n_hueco - n_cerca

    rng.shuffle(cerca)
    cerca.sort(key=lambda c: c[1])
    # Repartir entre marcas distintas, no siempre la misma: agrupar por celda
    # de marca y tomar en round-robin.
    por_celda = {}
    for c in cerca:
        por_celda.setdefault(c[2][1], []).append(c)
    ronda, restantes = [], list(por_celda.values())
    while restantes and len(ronda) < len(cerca):
        for lista in list(restantes):
            if lista:
                ronda.append(lista.pop(0))
            if not lista:
                restantes.remove(lista)
    grupo_b_cerca = _elegir_espaciadas(
        ronda, n_cerca, min_separacion_s=6.0, clave_t=lambda c: c[1]
    )

    rng.shuffle(lejos)
    lejos.sort(key=lambda c: c[1])
    grupo_b_lejos = _elegir_espaciadas(
        lejos, n_lejos, min_separacion_s=10.0, clave_t=lambda c: c[1]
    )

    return grupo_a, grupo_b_cerca, grupo_b_lejos, tiempos


def _dibujar_rejilla(img, ancho_orig, alto_orig):
    salida = cv2.resize(
        img, (ancho_orig * ZOOM, alto_orig * ZOOM), interpolation=cv2.INTER_NEAREST
    )
    paso = CELDA_PX * ZOOM
    for i, x in enumerate(range(0, ancho_orig * ZOOM, paso)):
        cv2.line(salida, (x, 0), (x, salida.shape[0]), (0, 255, 255), 1)
        if i < len(LETRAS):
            cv2.putText(
                salida,
                LETRAS[i],
                (x + 3, 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 255),
                1,
            )
    for j, y in enumerate(range(0, alto_orig * ZOOM, paso)):
        cv2.line(salida, (0, y), (salida.shape[1], y), (0, 255, 255), 1)
        cv2.putText(
            salida,
            str(j + 1),
            (3, y + 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
        )
    return salida


def _recortar(cap, frame_idx, ancho_video, alto_video, cx, cy):
    ancho_crop, alto_crop = COLUMNAS * CELDA_PX, FILAS * CELDA_PX
    x0 = int(np.clip(cx - ancho_crop / 2, 0, ancho_video - ancho_crop))
    y0 = int(np.clip(cy - alto_crop / 2, 0, alto_video - alto_crop))
    # posicionar_en_frame() deja el vídeo justo ANTES de frame_idx (o lanza
    # si no puede), así que el read() que sigue siempre cae en el objetivo.
    posicionar_en_frame(cap, frame_idx)
    ret, frame = cap.read()
    if not ret or frame is None:
        return None, (x0, y0)
    recorte = frame[y0 : y0 + alto_crop, x0 : x0 + ancho_crop]  # noqa: E203
    return recorte, (x0, y0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default="data/tracking_benja/cache_balon_p1.pkl")
    parser.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    parser.add_argument("--campo", default="configs/campo_benja.yaml")
    parser.add_argument("--salida-dir", default="outputs/gt_posicion_balon")
    parser.add_argument("--n-bajo", type=int, default=20)
    parser.add_argument("--n-hueco", type=int, default=20)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    salida = Path(args.salida_dir)
    salida.mkdir(parents=True, exist_ok=True)

    grupo_a, grupo_b_cerca, grupo_b_lejos, tiempos = seleccionar_frames(
        args.cache, args.campo, args.n_bajo, args.n_hueco
    )

    cap = cv2.VideoCapture(args.video)
    ancho_video = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto_video = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    filas_csv = []
    casos = (
        [
            (f"A{i+1:02d}", "candidato_bajo", f, t, det[0], det[1])
            for i, (f, t, det) in enumerate(grupo_a)
        ]
        + [
            (f"Bm{i+1:02d}", "hueco_cerca_marca", f, t, vecino[2], vecino[3])
            for i, (f, t, vecino) in enumerate(grupo_b_cerca)
        ]
        + [
            (f"Bl{i+1:02d}", "hueco_lejos_marca", f, t, ancho_video / 2, alto_video / 2)
            for i, (f, t, _) in enumerate(grupo_b_lejos)
        ]
    )

    for nombre, grupo, frame_idx, t, cx, cy in casos:
        recorte, (x0, y0) = _recortar(cap, frame_idx, ancho_video, alto_video, cx, cy)
        if recorte is None or recorte.size == 0:
            logger.warning("Frame %d (%s) no se pudo leer, se omite", frame_idx, nombre)
            continue
        con_rejilla = _dibujar_rejilla(recorte, recorte.shape[1], recorte.shape[0])
        ruta_img = salida / f"{nombre}_t{t:.2f}s_frame{frame_idx}.jpg"
        cv2.imwrite(str(ruta_img), con_rejilla, [cv2.IMWRITE_JPEG_QUALITY, 92])
        filas_csv.append(
            {
                "caso": nombre,
                "grupo": grupo,
                "frame_idx": frame_idx,
                "t": round(t, 3),
                "origen_x_px": x0,
                "origen_y_px": y0,
                "celda_px": CELDA_PX,
                "imagen": ruta_img.name,
                "respuesta": "",
            }
        )

    import csv

    ruta_plantilla = salida / "respuestas.csv"
    with open(ruta_plantilla, "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "caso",
                "grupo",
                "frame_idx",
                "t",
                "origen_x_px",
                "origen_y_px",
                "celda_px",
                "imagen",
                "respuesta",
            ],
        )
        w.writeheader()
        w.writerows(filas_csv)

    leeme = salida / "LEEME.txt"
    leeme.write_text(
        f"""GT de posición de balón — {len(filas_csv)} imágenes
({len(grupo_a)} de candidato_bajo, {len(grupo_b_cerca)} de hueco_cerca_marca,
{len(grupo_b_lejos)} de hueco_lejos_marca)

CÓMO RESPONDER (en respuestas.csv, columna "respuesta"):

  - Si ves el balón: el código de la celda donde está su CENTRO, p.ej "K7"
    (columna=letra arriba, fila=número a la izquierda). Si está justo entre
    dos celdas, la que más centro coja.
  - Si el balón NO aparece en el recorte (se fue de donde se buscó): "fuera"
  - Si el balón no se ve por estar tapado/oculto: "tapado"
  - Si de verdad no sabrías decirlo: "no_se"

Cada celda mide 20x20 píxeles REALES del vídeo (el recorte está ampliado
x2 solo para que se vea mejor, pero las celdas siguen siendo de 20 px).

Guarda respuestas.csv según vayas respondiendo — no hace falta terminar
las {len(filas_csv)} de una sentada. El script que lee las respuestas
(scripts/leer_gt_posicion_balon.py) solo usa las filas que ya tengan algo
en "respuesta", así que se puede ejecutar en cualquier momento, con lo que
haya.
""",
        encoding="utf-8",
    )

    print(f"\n✓ {len(filas_csv)} imágenes en {salida}/")
    print(
        f"  ({len(grupo_a)} candidato_bajo · {len(grupo_b_cerca)} hueco_cerca_marca · "
        f"{len(grupo_b_lejos)} hueco_lejos_marca)"
    )
    print(f"  Plantilla de respuestas: {ruta_plantilla}")


if __name__ == "__main__":
    main()
