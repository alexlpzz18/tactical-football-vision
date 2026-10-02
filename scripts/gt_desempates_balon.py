#!/usr/bin/env python
"""GT dirigido de DESEMPATES del balón: ¿cuál de los candidatos numerados es el balón?

Por qué existe (Plan 1, 1-oct-2026). El selector elige, cuando sobreviven
varios candidatos, el más CERCANO A UN JUGADOR. El diagnóstico de los saltos
repetidos encontró que así gana a menudo un falso positivo SOBRE un jugador
(bota, calcetín, dorsal), que por construcción siempre está más cerca de él
que el balón que lleva en los pies. Para medir un criterio nuevo hace falta
saber, en frames de desempate, cuál es el balón — y el GT de 40 imágenes no
tiene NINGÚN desempate (7 de sus 8 balones caen en frames sin candidatos).

Selección, estratificada a propósito y sin usar el TAMAÑO (que es una de las
dos señales del criterio a medir, así que elegir por él sesgaría la medida):

- `pegado`: el candidato que gana hoy cae DENTRO de la caja de un jugador y
  hay al menos otro candidato que no — el caso que el diagnóstico señaló.
- `todos_pegados`: todos los candidatos caen dentro de una caja de jugador
  (decide entre quedarse con uno o dejar el hueco).
- `control`: el resto de desempates, para no medir solo donde se espera
  fallo.

Cada imagen: el frame entero reducido, con los candidatos numerados, y debajo
un zoom ×3 de cada uno. Se responde con el NÚMERO del balón, `ninguno` o
`no_se`. Los datos de cada candidato van en un JSON aparte: la hoja que edita
Alex solo tiene `caso, imagen, respuesta` — Numbers ya estropeó una vez una
columna de tiempo con decimales.

Uso:
    python scripts/gt_desempates_balon.py generar --salida-dir outputs/gt_desempates
    python scripts/gt_desempates_balon.py leer --respuestas outputs/gt_desempates/respuestas.csv
"""

import argparse
import csv
import json
import logging
import pickle
import random
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.carga import cargar_detecciones_limpias  # noqa: E402
from src.balon.carga import cargar_homografia_de_campo  # noqa: E402
from src.balon.carga import jugadores_por_frame_de_balon  # noqa: E402
from src.balon.tracking_balon import ParametrosBalon  # noqa: E402
from src.balon.tracking_balon import seleccionar_balon_activo  # noqa: E402
from src.campo_modelo import cargar_modelo  # noqa: E402

logger = logging.getLogger("gt_desempates")

SEMILLA = 20261001
CUOTAS = {"pegado": 22, "todos_pegados": 6, "control": 10}
SEPARACION_MIN_S = 5.0
ANCHO_FRAME = 1080  # el frame entero se pinta reducido a este ancho
LADO_ZOOM = 90  # px reales alrededor de cada candidato
FACTOR_ZOOM = 3


def centro_px(det) -> tuple[float, float]:
    return (det[2] + det[4]) / 2.0, (det[3] + det[5]) / 2.0


def dentro_de_alguna_caja(cx: float, cy: float, cajas, margen: float = 0.0) -> bool:
    """¿Cae el punto (cx, cy) dentro de alguna caja (x1, y1, x2, y2)?"""
    return any(
        x1 - margen <= cx <= x2 + margen and y1 - margen <= cy <= y2 + margen
        for x1, y1, x2, y2 in cajas
    )


def parsear_respuesta(texto: str, n_candidatos: int) -> tuple[str | None, int | None]:
    """'2' -> ('balon', 2) · 'ninguno' -> ('ninguno', None) · basura -> (None, None)."""
    t = str(texto).strip().lower().replace("í", "i")
    if t in ("ninguno", "no_se"):
        return t, None
    try:
        # Numbers puede convertir "2" en 2.0: se acepta si es entero.
        n = float(t)
    except ValueError:
        return None, None
    if n.is_integer() and 1 <= int(n) <= n_candidatos:
        return "balon", int(n)
    return None, None


def elegir_espaciados(items, n, sep_s, rng):
    """Hasta n items al azar, sin dos a menos de sep_s segundos entre sí."""
    items = list(items)
    rng.shuffle(items)
    elegidos = []
    for it in items:
        if all(abs(it["t"] - e["t"]) >= sep_s for e in elegidos):
            elegidos.append(it)
        if len(elegidos) >= n:
            break
    return sorted(elegidos, key=lambda e: e["t"])


def construir_desempates(ruta_cache_balon, ruta_cache_jug, ruta_csv_jug, ruta_campo):
    modelo = cargar_modelo(config=ruta_campo)
    dets, tiempos, _meta = cargar_detecciones_limpias(ruta_cache_balon, modelo)
    jug = jugadores_por_frame_de_balon(ruta_csv_jug, tiempos, dets)
    pos_jug = {f: [(j[0], j[1]) for j in jug.get(f, [])] for f in dets}
    activo = seleccionar_balon_activo(
        dets,
        pos_jug,
        ParametrosBalon(),
        tiempos,
        cargar_homografia_de_campo(ruta_campo),
    )

    with open(ruta_cache_jug, "rb") as fh:
        cajas_jug = {
            e["frame_idx"]: [tuple(float(v) for v in d[2:6]) for d in e["dets"]]
            for e in pickle.load(fh)["cache"]
        }

    def cajas_cerca(f):
        # El caché de jugadores va 1 de cada 3 frames y el de balón 1 de cada 2:
        # siempre hay uno a ±1 frame.
        for g in (f, f - 1, f + 1):
            if g in cajas_jug:
                return cajas_jug[g]
        return []

    def dist_jug(f, d):
        js = pos_jug.get(f) or []
        return min(
            (float(np.hypot(j[0] - d[0], j[1] - d[1])) for j in js), default=None
        )

    salida = []
    for f, ds in dets.items():
        if len(ds) < 2 or f not in activo:
            continue
        cajas = cajas_cerca(f)
        cands = []
        for d in ds:
            cx, cy = centro_px(d)
            cands.append(
                {
                    "cx": cx,
                    "cy": cy,
                    "caja": [float(v) for v in d[2:6]],
                    "lado": float(max(d[4] - d[2], d[5] - d[3])),
                    "conf": float(d[6]),
                    "mx": float(d[0]),
                    "my": float(d[1]),
                    "dist_jugador_m": dist_jug(f, d),
                    "pegado": dentro_de_alguna_caja(cx, cy, cajas),
                    "elegido_hoy": tuple(d) == tuple(activo[f]),
                }
            )
        ganador = next((c for c in cands if c["elegido_hoy"]), None)
        if ganador is None:
            continue
        if all(c["pegado"] for c in cands):
            estrato = "todos_pegados"
        elif ganador["pegado"]:
            estrato = "pegado"
        else:
            estrato = "control"
        salida.append(
            {
                "frame_idx": int(f),
                "t": float(tiempos[f]),
                "estrato": estrato,
                "candidatos": cands,
            }
        )
    return salida


def pintar_caso(frame, cands):
    esc = ANCHO_FRAME / frame.shape[1]
    reducido = cv2.resize(frame, (ANCHO_FRAME, int(frame.shape[0] * esc)))
    for i, c in enumerate(cands, start=1):
        u, v = int(c["cx"] * esc), int(c["cy"] * esc)
        cv2.circle(reducido, (u, v), 14, (0, 255, 255), 1)
        cv2.putText(
            reducido,
            str(i),
            (u + 12, v - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0),
            4,
        )
        cv2.putText(
            reducido,
            str(i),
            (u + 12, v - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )
    zooms = []
    lado_z = LADO_ZOOM * FACTOR_ZOOM
    for i, c in enumerate(cands, start=1):
        x0 = int(np.clip(c["cx"] - LADO_ZOOM / 2, 0, frame.shape[1] - LADO_ZOOM))
        y0 = int(np.clip(c["cy"] - LADO_ZOOM / 2, 0, frame.shape[0] - LADO_ZOOM))
        z = cv2.resize(
            frame[y0 : y0 + LADO_ZOOM, x0 : x0 + LADO_ZOOM],  # noqa: E203
            (lado_z, lado_z),
            interpolation=cv2.INTER_NEAREST,
        )
        x1, y1, x2, y2 = c["caja"]
        p1 = (int((x1 - x0) * FACTOR_ZOOM) - 4, int((y1 - y0) * FACTOR_ZOOM) - 4)
        p2 = (int((x2 - x0) * FACTOR_ZOOM) + 4, int((y2 - y0) * FACTOR_ZOOM) + 4)
        cv2.rectangle(z, p1, p2, (0, 255, 255), 1)
        cv2.putText(z, str(i), (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 5)
        cv2.putText(z, str(i), (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 2)
        zooms.append(z)
    por_fila = ANCHO_FRAME // lado_z
    filas = []
    for k in range(0, len(zooms), por_fila):
        fila = zooms[k : k + por_fila]  # noqa: E203
        relleno = ANCHO_FRAME - lado_z * len(fila)
        filas.append(np.hstack(fila + [np.zeros((lado_z, relleno, 3), np.uint8)]))
    return np.vstack([reducido] + filas)


def generar(args):
    desempates = construir_desempates(
        args.cache_balon, args.cache_jugadores, args.csv_jugadores, args.campo
    )
    rng = random.Random(SEMILLA)
    por_estrato = {e: [d for d in desempates if d["estrato"] == e] for e in CUOTAS}
    for e, ds in por_estrato.items():
        print(f"desempates '{e}': {len(ds)} en el partido")
    elegidos = []
    for e, n in CUOTAS.items():
        elegidos += elegir_espaciados(por_estrato[e], n, SEPARACION_MIN_S, rng)
    elegidos.sort(key=lambda d: d["frame_idx"])

    salida = Path(args.salida_dir)
    salida.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    pos, filas, meta = 0, [], {}
    # Lectura SECUENCIAL: un solo recorrido del vídeo, sin saltos que
    # obliguen a decodificar desde el principio (y sin `cap.set`).
    for k, d in enumerate(elegidos, start=1):
        while pos < d["frame_idx"]:
            cap.grab()
            pos += 1
        ok, frame = cap.read()
        pos += 1
        if not ok:
            logger.warning("No se pudo leer el frame %d", d["frame_idx"])
            continue
        caso = f"D{k:02d}"
        nombre = f"{caso}.jpg"
        cv2.imwrite(
            str(salida / nombre),
            pintar_caso(frame, d["candidatos"]),
            [cv2.IMWRITE_JPEG_QUALITY, 92],
        )
        filas.append({"caso": caso, "imagen": nombre, "respuesta": ""})
        meta[caso] = d
    with open(salida / "respuestas.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["caso", "imagen", "respuesta"])
        w.writeheader()
        w.writerows(filas)
    (salida / "metadatos.json").write_text(json.dumps(meta, indent=1))
    (salida / "LEEME.txt").write_text(
        f"""GT de desempates del balón — {len(filas)} imágenes.

Arriba: el frame entero con los candidatos numerados (círculo amarillo).
Debajo: un zoom x3 de cada candidato, con su número.

En respuestas.csv, columna "respuesta":
  - el NÚMERO del candidato que es el balón del partido (p. ej. 2)
  - "ninguno" si ninguno de los numerados es el balón
  - "no_se" si no sabrías decirlo

No hace falta hacerlas todas de una vez: el lector usa solo las contestadas.
""",
        encoding="utf-8",
    )
    print(
        f"\n✓ {len(filas)} imágenes en {salida}/ "
        + str({e: sum(m["estrato"] == e for m in meta.values()) for e in CUOTAS})
    )


def leer(args):
    carpeta = Path(args.respuestas).parent
    meta = json.loads((carpeta / "metadatos.json").read_text())
    ruta = Path(args.respuestas)
    if ruta.suffix == ".numbers":
        from numbers_parser import Document

        filas_raw = list(Document(str(ruta)).sheets[0].tables[0].rows(values_only=True))
        cab = filas_raw[0]
        filas = [dict(zip(cab, f)) for f in filas_raw[1:]]
    else:
        with open(ruta) as fh:
            filas = list(csv.DictReader(fh))
    salida, invalidas = [], []
    for f in filas:
        texto = "" if f.get("respuesta") is None else str(f["respuesta"])
        if not texto.strip():
            continue
        m = meta[f["caso"]]
        estado, n = parsear_respuesta(texto, len(m["candidatos"]))
        if estado is None:
            invalidas.append((f["caso"], texto))
            continue
        for i, c in enumerate(m["candidatos"], start=1):
            salida.append(
                {
                    "caso": f["caso"],
                    "frame_idx": m["frame_idx"],
                    "t": m["t"],
                    "estrato": m["estrato"],
                    "candidato": i,
                    "estado_caso": estado,
                    "es_balon": int(estado == "balon" and i == n),
                    **{
                        k: c[k]
                        for k in (
                            "cx",
                            "cy",
                            "lado",
                            "conf",
                            "mx",
                            "my",
                            "dist_jugador_m",
                            "pegado",
                            "elegido_hoy",
                        )
                    },
                }
            )
    if invalidas:
        print("⚠️ respuestas no reconocidas, se omiten:", invalidas)
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    with open(args.salida, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(salida[0].keys()))
        w.writeheader()
        w.writerows(salida)
    casos = {r["caso"] for r in salida}
    print(f"✓ {len(casos)} casos contestados → {args.salida}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="orden", required=True)
    g = sub.add_parser("generar")
    g.add_argument("--cache-balon", default="data/tracking_benja/cache_balon_p1.pkl")
    g.add_argument(
        "--cache-jugadores",
        default="data/tracking_benja/cache_detecciones_benja_p1.pkl",
    )
    g.add_argument(
        "--csv-jugadores", default="data/tracking_benja/posiciones_benja_p1_v3.csv"
    )
    g.add_argument("--campo", default="configs/campo_benja.yaml")
    g.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    g.add_argument("--salida-dir", default="outputs/gt_desempates")
    r = sub.add_parser("leer")
    r.add_argument("--respuestas", default="outputs/gt_desempates/respuestas.csv")
    r.add_argument("--salida", default="data/tracking_benja/gt_desempates_balon.csv")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    generar(args) if args.orden == "generar" else leer(args)


if __name__ == "__main__":
    main()
