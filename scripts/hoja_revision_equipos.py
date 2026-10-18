#!/usr/bin/env python
"""Hoja de revisión del EQUIPO: 3 ventanas de 60 s, 1 imagen por segundo, para marcar a mano.

Plan: `docs/plan_causas_equipo_equivocado.md`, parte (b). Lee la pasada de
`scripts/causas_equipo_equivocado.py pasada` (el CSV de producción de hoy y la CAJA exacta de cada
fila), así que pinta lo mismo que sale de producción.

En cada imagen: todas las cajas que entran al tracking, con su NÚMERO de caja, la etiqueta DEL
INSTANTE (la de esa observación en el CSV, no la moda de la identidad) y la identidad. Las cajas sin
identidad o sin fila, en gris. Arriba, los dos relojes (archivo y reproductor de Alex, +1:33).

Salida (en `outputs/`, no se versiona):
- `<ventana>/NN_mm-ss.jpg`: las imágenes;
- `cajas.csv`: una fila por caja pintada (para saber qué es cada número);
- `revision.csv`: la plantilla que rellena Alex, solo con cabecera.

Uso:
    python scripts/hoja_revision_equipos.py --trabajo DIR_DE_LA_PASADA --salida outputs/hoja_equipos
"""

import argparse
import csv
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

CONFIG = R / "configs/processor_benja_parte_entera.yaml"
DESFASE_REPRODUCTOR_S = 93  # el reproductor de Alex va +1:33
VENTANA_S = 60
INICIO_GT_S = 310  # 5:10 de archivo: la ventana contiene los 30 s del GT (5:25-5:55)
RANGO_S = (300, 1140)  # de 5:00 a 19:00: los minutos 0-5 son otro régimen
SEMILLA = 0

# BGR. A y B con los colores reales del fit (#b7bbeb y #eb2d06).
COLORES = {
    "A": (235, 187, 183),
    "B": (6, 45, 235),
    "portero_A": (160, 60, 20),
    "portero_B": (0, 210, 255),
    "otro": (200, 0, 200),
    "staff": (120, 120, 120),
    "sin fila": (70, 70, 70),
}
CABECERA_REVISION = [
    "ventana",  # gt | minuto_malo | azar
    "imagen",  # el nombre del jpg
    "caja",  # el número pintado junto a la caja
    "equipo_correcto",  # A | B | portero_A | portero_B | arbitro | staff | no_es_persona | dudoso
    "causa",  # caja_dos_personas | arbitro | portero | staff | color_limpio | otra | no_se
    "nota",  # texto libre, opcional
]


def reloj(segundos: float) -> str:
    return f"{int(segundos // 60)}:{segundos % 60:04.1f}"


def solapa(a: int, b: int, ancho: int = VENTANA_S) -> bool:
    """¿Se solapan dos ventanas de `ancho` segundos que empiezan en a y b?"""
    return abs(a - b) < ancho


def elegir_ventanas(cuenta_por_minuto: dict[int, float], rng) -> dict[str, int]:
    """Inicio (s) de las tres ventanas: la del GT, el peor minuto y una al azar.

    `cuenta_por_minuto`: {inicio del minuto en s: filas A/B/portero en el campo por frame}.
    """
    ventanas = {"gt": INICIO_GT_S}
    candidatos = {
        m: c for m, c in cuenta_por_minuto.items() if not solapa(m, INICIO_GT_S)
    }
    ventanas["minuto_malo"] = min(candidatos, key=candidatos.get)
    while True:
        t = int(rng.integers(RANGO_S[0], RANGO_S[1] - VENTANA_S + 1))
        if not any(solapa(t, v) for v in ventanas.values()):
            ventanas["azar"] = t
            return ventanas


def main() -> None:
    import cv2
    import pandas as pd
    import yaml

    from src.tracking_data.processor import posicionar_en_frame

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trabajo", required=True)
    ap.add_argument("--salida", default=str(R / "outputs/hoja_equipos"))
    args = ap.parse_args()
    trabajo, salida = Path(args.trabajo), Path(args.salida)
    cfg = yaml.safe_load(open(CONFIG))
    filas = pd.read_csv(trabajo / "posiciones.csv")
    capt = pickle.load(open(trabajo / "cajas.pkl", "rb"))
    fps = 29.97002997002997

    # el peor minuto: filas A/B/portero DENTRO del campo por frame, minuto a minuto (5 a 19)
    reales = filas[
        (filas.es_real == 1) & filas.etiqueta.isin(["A", "B", "portero_A", "portero_B"])
    ]
    dentro = reales[reales.x_m.between(0, 62) & reales.y_m.between(0, 40)]
    por_frame = dentro.groupby("frame").size()
    frames_cache = np.array(sorted(capt["cache_filtrado"]))
    cuenta = {}
    for m in range(RANGO_S[0], RANGO_S[1], 60):
        fr = frames_cache[(frames_cache >= m * fps) & (frames_cache < (m + 60) * fps)]
        cuenta[m] = float(por_frame.reindex(fr, fill_value=0).mean())
    ventanas = elegir_ventanas(cuenta, np.random.default_rng(SEMILLA))

    etiqueta = {
        (int(r.frame), int(r.id_jugador)): r.etiqueta
        for r in filas.itertuples()
        if r.es_real == 1
    }
    ident_de = {}
    for (n, f), d in capt["obs"].items():
        ident_de.setdefault(f, {})[d] = n

    salida.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(R / cfg["rutas"]["video"]))
    filas_cajas = []
    for nombre, t0 in ventanas.items():
        (salida / nombre).mkdir(exist_ok=True)
        objetivos = []
        for s in range(VENTANA_S):
            f = int(frames_cache[np.argmin(np.abs(frames_cache - (t0 + s) * fps))])
            objetivos.append((s, f))
        actual = posicionar_en_frame(cap, objetivos[0][1])
        for s, f in objetivos:
            while actual < f:
                cap.grab()
                actual += 1
            ok, img = cap.read()
            actual += 1
            if not ok:
                raise RuntimeError(f"no se pudo leer el frame {f}")
            t_arch = f / fps
            nombre_img = f"{s:02d}_{reloj(t_arch).replace(':', '-')}.jpg"
            for k, det in enumerate(capt["cache_filtrado"].get(f, [])):
                n = ident_de.get(f, {}).get(k)
                etq = etiqueta.get((f, n), "sin fila") if n is not None else "sin fila"
                x1, y1, x2, y2 = (int(round(v)) for v in det[2:6])
                color = COLORES.get(etq, COLORES["sin fila"])
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                texto = f"{k} {etq.replace('portero_', 'P')}" + (f" #{n}" if n else "")
                cv2.putText(
                    img,
                    texto,
                    (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 0, 0),
                    3,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    img,
                    texto,
                    (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    color,
                    1,
                    cv2.LINE_AA,
                )
                filas_cajas.append(
                    {
                        "ventana": nombre,
                        "imagen": nombre_img,
                        "frame": f,
                        "reloj_archivo": reloj(t_arch),
                        "reloj_reproductor": reloj(t_arch + DESFASE_REPRODUCTOR_S),
                        "caja": k,
                        "id_jugador": n if n is not None else "",
                        "etiqueta": etq,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "x_m": round(float(det[0]), 2),
                        "y_m": round(float(det[1]), 2),
                    }
                )
            cabecera = (
                f"{nombre}  {s + 1}/60  archivo {reloj(t_arch)}  "
                f"reproductor {reloj(t_arch + DESFASE_REPRODUCTOR_S)}  frame {f}"
            )
            cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
            cv2.putText(
                img,
                cabecera,
                (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imwrite(
                str(salida / nombre / nombre_img), img, [cv2.IMWRITE_JPEG_QUALITY, 88]
            )
    cap.release()
    pd.DataFrame(filas_cajas).to_csv(salida / "cajas.csv", index=False)
    with open(salida / "revision.csv", "w", newline="") as fh:
        csv.writer(fh).writerow(CABECERA_REVISION)
    resumen = {
        k: f"{reloj(v)}-{reloj(v + VENTANA_S)} archivo · "
        f"{reloj(v + DESFASE_REPRODUCTOR_S)}-{reloj(v + VENTANA_S + DESFASE_REPRODUCTOR_S)} reprod."
        for k, v in ventanas.items()
    }
    print("ventanas:", resumen)
    print(
        "cuenta del minuto malo:",
        round(cuenta[ventanas["minuto_malo"]], 2),
        "filas A/B/portero en campo por frame (mediana de minutos:",
        round(float(np.median(list(cuenta.values()))), 2),
        ")",
    )
    print(f"✓ {len(filas_cajas)} cajas en {3 * VENTANA_S} imágenes → {salida}")


if __name__ == "__main__":
    main()
