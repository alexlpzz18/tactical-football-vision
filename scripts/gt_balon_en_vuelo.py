#!/usr/bin/env python
"""GT corto del balón EN VUELO: ¿hay balón visible donde el detector no da nada?

Pregunta de Alex (2-oct-2026, docs/balon_en_vuelo.md): de los frames de vuelo
que siguen sin balón, la mayoría (372) no tiene NINGUNA detección del balón.
Antes de gastar en más resolución hay que saber si el balón se ve en la
imagen (lo pierde el detector) o no está (fuera de plano, tapado): eso último
sería el techo físico del vídeo, no del sistema.

Qué frames: los que caen DENTRO de un vuelo o pase largo (entre dos
posiciones elegidas a > 8 m en ≤ 2 s, con el selector SIN readmitir vuelos,
que es la definición de los 687 originales), que siguen sin balón con el
selector de producción, y cuyas detecciones crudas son todas marcas del
campo (o ninguna). Se eligen al azar, separados en el tiempo.

Cada imagen: el FRAME ENTERO con una rejilla de celdas de 80 px (letra =
columna, número = fila, como una hoja de cálculo) y, debajo, un ZOOM ×2 de la
zona entre la última posición conocida del balón (círculo VERDE) y la
siguiente (círculo ROJO), ampliada hacia arriba, que es por donde iría un
vuelo. La rejilla es la misma en las dos, así que el código vale para las dos.

⚠️ Lección del GT de posición: allí "fuera" significaba "fuera del RECORTE",
no de la imagen, y la mitad de las respuestas no daba posición. Aquí se ve
siempre el frame entero: "no_visible" quiere decir que no está en la IMAGEN.

Respuestas (columna `respuesta` de respuestas.csv, o el .numbers):
    K7          balón visible en esa celda
    no_visible  no está en la imagen (también valen "fuera" y "tapado")
    no_se       no se puede decir

Uso:
    python scripts/gt_balon_en_vuelo.py generar
    python scripts/gt_balon_en_vuelo.py leer outputs/gt_balon_en_vuelo/respuestas.csv
"""

import argparse
import csv
import io
import contextlib
import json
import random
import re
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.carga import cargar_detecciones_limpias  # noqa: E402
from src.balon.carga import contexto_del_selector  # noqa: E402
from src.balon.tracking_balon import ParametrosBalon  # noqa: E402
from src.balon.tracking_balon import seleccionar_balon_activo  # noqa: E402
from src.campo_modelo import cargar_modelo  # noqa: E402

CELDA_PX = 80  # celdas de la rejilla, en píxeles del vídeo original
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWX"  # 24 columnas x 80 px = 1920
SEMILLA = 20261002
OFFSET_REPRODUCTOR_S = 93.0  # el vídeo que mira Alex va 1:33 por delante del archivo
SALTO_VUELO_M, DT_VUELO_S = 8.0, 2.0
RE_CELDA = re.compile(r"^([A-Xa-x])\s*(\d{1,2})$")


def celda_de_px(x: float, y: float) -> str:
    return f"{LETRAS[int(x // CELDA_PX)]}{int(y // CELDA_PX) + 1}"


def celda_a_px(celda: str) -> tuple[float, float] | None:
    """Centro en píxeles de una celda 'K7', o None si no es una celda válida."""
    m = RE_CELDA.match(celda.strip())
    if not m:
        return None
    col, fila = LETRAS.index(m.group(1).upper()), int(m.group(2))
    if not 1 <= fila <= 14:
        return None
    return (col + 0.5) * CELDA_PX, (fila - 0.5) * CELDA_PX


def parsear_respuesta(texto) -> tuple[str | None, tuple[float, float] | None]:
    """'K7' -> ('visible', (x, y)) · 'no_visible'/'fuera'/'tapado' -> ('no_visible', None)."""
    t = str(texto).strip().lower().replace(" ", "_").replace("é", "e")
    if t in ("no_visible", "fuera", "tapado", "fuera_de_plano"):
        return "no_visible", None
    if t in ("no_se", "nose"):
        return "no_se", None
    pos = celda_a_px(str(texto))
    return ("visible", pos) if pos else (None, None)


def frames_de_vuelo_sin_deteccion(
    sel_sin_vuelos, sel_produccion, crudo, en_marca, tiempos
):
    """Frames dentro de un vuelo, todavía sin balón y sin ninguna detección que no sea marca.

    Args:
        sel_sin_vuelos: selección con `readmitir_vuelos=False` (define los vuelos).
        sel_produccion: selección de producción (lo que sigue sin balón).
        crudo: {frame: [det]} el caché SIN filtrar.
        en_marca: función det -> bool, ¿cae en una celda de marca?
        tiempos: {frame: s}.
    """
    fs = sorted(sel_sin_vuelos)
    todos = sorted(tiempos)
    vuelo = set()
    for a, b in zip(fs, fs[1:]):
        dt = tiempos[b] - tiempos[a]
        pa, pb = np.array(sel_sin_vuelos[a][:2]), np.array(sel_sin_vuelos[b][:2])
        if 0.2 < dt <= DT_VUELO_S and np.linalg.norm(pb - pa) > SALTO_VUELO_M:
            vuelo |= {f for f in todos if a < f < b}
    return sorted(
        f
        for f in vuelo
        if f not in sel_produccion and all(en_marca(d) for d in crudo.get(f, []))
    )


def elegir_espaciados(frames, tiempos, n, sep_s, rng):
    frames = list(frames)
    rng.shuffle(frames)
    elegidos = []
    for f in frames:
        if all(abs(tiempos[f] - tiempos[e]) >= sep_s for e in elegidos):
            elegidos.append(f)
        if len(elegidos) >= n:
            break
    return sorted(elegidos)


def _mmss(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:04.1f}"


def _rejilla(img, x0=0, y0=0, escala=1.0):
    alto, ancho = img.shape[:2]
    for k in range(0, 1921, CELDA_PX):
        x = int((k - x0) * escala)
        if 0 <= x < ancho:
            cv2.line(img, (x, 0), (x, alto), (255, 255, 255), 1)
            if k < 1920:
                cv2.putText(
                    img,
                    LETRAS[k // CELDA_PX],
                    (x + 4, 18),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 0),
                    2,
                )
    for k in range(0, 1081, CELDA_PX):
        y = int((k - y0) * escala)
        if 0 <= y < alto:
            cv2.line(img, (0, y), (ancho, y), (255, 255, 255), 1)
            if k < 1080:
                # números a la DERECHA: a la izquierda la fila 1 se pisaba con la "A"
                cv2.putText(
                    img,
                    str(k // CELDA_PX + 1),
                    (ancho - 30, y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 0),
                    2,
                )
    return img


def pintar_caso(frame, pa, pb, titulo):
    """Frame entero con rejilla (960 px de ancho) + zoom ×2 de la zona del vuelo."""
    entero = frame.copy()
    for p, col in ((pa, (0, 255, 0)), (pb, (0, 0, 255))):
        cv2.circle(entero, (int(p[0]), int(p[1])), 22, col, 3)
    arriba = _rejilla(cv2.resize(entero, (960, 540)), escala=0.5)
    cv2.rectangle(arriba, (0, 510), (960, 540), (0, 0, 0), -1)
    cv2.putText(
        arriba, titulo, (8, 532), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
    )
    # zoom: 480x270 px reales alrededor del tramo, subido hacia arriba
    cx = (pa[0] + pb[0]) / 2
    cy = min(pa[1], pb[1]) - 60
    x0 = int(np.clip(cx - 240, 0, 1920 - 480))
    y0 = int(np.clip(cy - 135, 0, 1080 - 270))
    y1, x1 = y0 + 270, x0 + 480
    zoom = cv2.resize(entero[y0:y1, x0:x1], (960, 540), interpolation=cv2.INTER_LINEAR)
    zoom = _rejilla(zoom, x0, y0, escala=2.0)
    return np.vstack([arriba, zoom])


def generar(args):
    random.seed(SEMILLA)
    modelo = cargar_modelo(config=args.campo)
    with contextlib.redirect_stdout(io.StringIO()):
        dets, tiempos, meta = cargar_detecciones_limpias(args.cache_balon, modelo)
    import pickle

    with open(args.cache_balon, "rb") as fh:
        crudo = {
            e["frame_idx"]: e["dets"] for e in pickle.load(fh)["cache"] if e["dets"]
        }
    marcas = meta["celdas_marcas"]

    def en_marca(d):
        return (int((d[2] + d[4]) / 2 // 12), int((d[3] + d[5]) / 2 // 12)) in marcas

    jug, ctx = contexto_del_selector(
        args.csv_jugadores, tiempos, dets, args.campo, modelo, meta["fuera_de_campo"]
    )
    pos = {f: [(j[0], j[1]) for j in jug.get(f, [])] for f in dets}
    sin_vuelos = seleccionar_balon_activo(
        dets, pos, replace(ParametrosBalon(), readmitir_vuelos=False), **ctx
    )
    produccion = seleccionar_balon_activo(dets, pos, ParametrosBalon(), **ctx)
    candidatos = frames_de_vuelo_sin_deteccion(
        sin_vuelos, produccion, crudo, en_marca, tiempos
    )
    elegidos = elegir_espaciados(
        candidatos, tiempos, args.n, args.sep_s, random.Random(SEMILLA)
    )
    print(
        f"frames de vuelo sin balón y sin detección: {len(candidatos)} · elegidos {len(elegidos)}"
    )

    salida = Path(args.salida_dir)
    salida.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    pos_video, filas, metadatos = 0, [], {}
    fs = sorted(produccion)
    for k, f in enumerate(elegidos, start=1):
        # Lectura SECUENCIAL hacia delante (nunca cap.set): el frame exacto.
        while pos_video < f:
            cap.grab()
            pos_video += 1
        ok, img = cap.read()
        pos_video += 1
        if not ok:
            raise RuntimeError(f"No se pudo leer el frame {f}")
        a = max(g for g in fs if g < f)
        b = min(g for g in fs if g > f)
        pa = (
            (produccion[a][2] + produccion[a][4]) / 2,
            (produccion[a][3] + produccion[a][5]) / 2,
        )
        pb = (
            (produccion[b][2] + produccion[b][4]) / 2,
            (produccion[b][3] + produccion[b][5]) / 2,
        )
        caso = f"V{k:02d}"
        t = tiempos[f]
        # Solo ASCII: OpenCV pinta "??" en lugar de "·" o de una tilde.
        titulo = (
            f"{caso} | archivo {_mmss(t)} | tu reproductor {_mmss(t + OFFSET_REPRODUCTOR_S)}"
            " | verde = antes, rojo = despues"
        )
        cv2.imwrite(str(salida / f"{caso}.jpg"), pintar_caso(img, pa, pb, titulo))
        filas.append({"caso": caso, "imagen": f"{caso}.jpg", "respuesta": ""})
        metadatos[caso] = {
            "frame": int(f),
            "t_archivo": round(float(t), 3),
            "t_reproductor": round(float(t) + OFFSET_REPRODUCTOR_S, 3),
            "antes": {
                "frame": int(a),
                "px": [round(v, 1) for v in pa],
                "celda": celda_de_px(*pa),
            },
            "despues": {
                "frame": int(b),
                "px": [round(v, 1) for v in pb],
                "celda": celda_de_px(*pb),
            },
        }
    with open(salida / "respuestas.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["caso", "imagen", "respuesta"])
        w.writeheader()
        w.writerows(filas)
    (salida / "metadatos.json").write_text(json.dumps(metadatos, indent=1))
    (salida / "LEEME.txt").write_text(
        "Para cada imagen, escribe en la columna 'respuesta' de respuestas.csv:\n"
        "  K7          si VES el balón (letra de columna + número de fila; arriba el\n"
        "              frame entero, abajo el zoom con la MISMA rejilla)\n"
        "  no_visible  si no está en la imagen (fuera de plano o tapado; también\n"
        "              valen 'fuera' y 'tapado')\n"
        "  no_se       si no se puede decir\n"
        "Círculo verde: dónde estaba el balón justo antes; rojo: dónde aparece después.\n"
        f"Tiempos de los títulos: archivo y tu reproductor (+{OFFSET_REPRODUCTOR_S:.0f} s).\n"
    )
    print(f"✓ {len(filas)} casos en {salida}/ (rellena respuestas.csv; ver LEEME.txt)")


def leer(args):
    ruta = Path(args.respuestas)
    meta = json.loads((ruta.parent / "metadatos.json").read_text())
    if ruta.suffix == ".numbers":
        from numbers_parser import Document

        filas_raw = list(Document(str(ruta)).sheets[0].tables[0].rows(values_only=True))
        filas = [dict(zip(filas_raw[0], f)) for f in filas_raw[1:]]
    else:
        with open(ruta) as fh:
            filas = list(csv.DictReader(fh))
    cuenta, invalidas, visibles = {"visible": 0, "no_visible": 0, "no_se": 0}, [], []
    for f in filas:
        texto = "" if f.get("respuesta") is None else str(f["respuesta"])
        if not texto.strip():
            continue
        estado, pos = parsear_respuesta(texto)
        if estado is None:
            invalidas.append((f["caso"], texto))
            continue
        cuenta[estado] += 1
        if estado == "visible":
            visibles.append((f["caso"], texto.strip().upper(), pos[1]))
    total = sum(cuenta.values())
    print(f"respondidos {total} de {len(meta)}")
    for k, v in cuenta.items():
        print(f"  {k:10s} {v:3d} ({100 * v / max(total, 1):.0f} %)")
    franja_y0 = 534  # borde superior de la franja troceada (docs/balon_en_vuelo.md)
    if visibles:
        arriba = sum(y < franja_y0 for _c, _cel, y in visibles)
        print(
            f"  de los visibles, por ENCIMA de la franja troceada (y < {franja_y0}): {arriba}"
        )
    if invalidas:
        print("⚠️ respuestas que no entiendo (corrígelas):", invalidas)


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="orden", required=True)
    g = sub.add_parser("generar")
    g.add_argument("--cache-balon", default="data/tracking_benja/cache_balon_p1.pkl")
    g.add_argument(
        "--csv-jugadores", default="data/tracking_benja/posiciones_benja_p1_v3.csv"
    )
    g.add_argument("--campo", default="configs/campo_benja.yaml")
    g.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    g.add_argument("--salida-dir", default="outputs/gt_balon_en_vuelo")
    g.add_argument("--n", type=int, default=25)
    g.add_argument("--sep-s", type=float, default=10.0)
    r = sub.add_parser("leer")
    r.add_argument("respuestas")
    args = p.parse_args()
    generar(args) if args.orden == "generar" else leer(args)


if __name__ == "__main__":
    main()
