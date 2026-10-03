#!/usr/bin/env python
"""Hoja para revisar A OJO una muestra de los cortes de la guarda de caja fundida.

El GT del benjamín cubre 30 s de 20 minutos, así que casi todos los cortes de la regla
caen donde no hay GT. Esto saca una muestra al azar (semilla fija) y, para cada corte,
cuatro recortes: ~1 s antes, la última observación antes del corte, la primera después
y ~1 s después. En verde, la caja de la identidad ANTES del corte; en rojo, DESPUÉS.

Lo que hay que mirar: ¿el verde y el rojo son la MISMA persona (corte malo) u OTRA
(corte bueno)? Los tiempos van con los dos relojes: el del archivo y el del reproductor
de Alex, que va 1:33 por delante.

Uso:
    python scripts/hoja_guarda_caja_fundida.py [--rama candidata] [--n 16]
"""

import argparse
import logging
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

import guarda_caja_fundida as gcf  # noqa: E402
import src.tracking.perfiles as perfiles  # noqa: E402
from medir_guarda_caja_fundida import RAMAS, _cajas, _parametros  # noqa: E402
from mirar_recortes_sueltos import texto  # noqa: E402
from src.tracking_data.processor import (  # noqa: E402
    posicionar_en_frame,
    procesar_desde_cache,
)  # noqa

ADELANTO_REPRODUCTOR_S = 93  # el reproductor de Alex va 1:33 por delante del archivo
LADO = 150  # px de cada recorte (antes de escalar)
VERDE, ROJO = (0, 200, 0), (0, 0, 255)


def reloj(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def eventos_de_la_rama(cfg: dict, rama: str, salida: Path):
    """Corre producción, captura identidades pre-cosido + caché y detecta los cortes."""
    capt = {}
    asociar0, coser0 = perfiles.asociar_con_bytetrack, perfiles.coser_por_pureza

    def asociar(cache, *a, **k):
        capt["cache"] = cache
        return asociar0(cache, *a, **k)

    def coser(identidades, *a, **k):
        capt["identidades"] = identidades
        return coser0(identidades, *a, **k)

    cfg = yaml.safe_load(yaml.safe_dump(cfg))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(salida / "_hoja.csv")
    cfg["rutas"]["salida_meta"] = str(salida / "_hoja.json")
    perfiles.asociar_con_bytetrack, perfiles.coser_por_pureza = asociar, coser
    try:
        procesar_desde_cache(cfg)
    finally:
        perfiles.asociar_con_bytetrack, perfiles.coser_por_pureza = asociar0, coser0
    cajas = _cajas(capt["cache"])
    p = _parametros(rama, cfg)
    eventos = []
    for ident in capt["identidades"]:
        obs = gcf.observaciones(ident)
        for c in gcf.detectar_cortes(obs, cajas, p):
            i = c["i"]
            eventos.append(
                {
                    **c,
                    # (frame, caja, color) de los cuatro recortes
                    "vistas": [
                        (obs[j][2][0], cajas[obs[j][2]], VERDE if j < i else ROJO)
                        for j in (max(0, i - 10), i - 1, i, min(len(obs) - 1, i + 10))
                    ],
                }
            )
    return eventos


def leer_frames(video: str, frames: list[int]) -> dict:
    """Decodifica en orden; posicionar_en_frame verifica el salto (nunca cap.set a pelo)."""
    cap = cv2.VideoCapture(video)
    salida, pos = {}, 0
    for f in sorted(set(frames)):
        if f - pos > 300:
            pos = posicionar_en_frame(cap, f)
        while pos < f:
            cap.grab()
            pos += 1
        ok, img = cap.read()
        pos += 1
        if ok:
            salida[f] = img
    cap.release()
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/processor_benja_parte_entera.yaml")
    ap.add_argument("--rama", default="candidata", choices=list(RAMAS))
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--semilla", type=int, default=20261003)
    ap.add_argument("--salida", default="outputs/guarda_caja_fundida")
    args = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    sal = R / args.salida
    sal.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(R / args.config))
    eventos = eventos_de_la_rama(cfg, args.rama, sal)
    muestra = random.Random(args.semilla).sample(eventos, min(args.n, len(eventos)))
    muestra.sort(key=lambda e: e["t"])
    imgs = leer_frames(
        str(R / cfg["rutas"]["video"]), [f for e in muestra for f, *_ in e["vistas"]]
    )

    filas = []
    for n, e in enumerate(muestra, start=1):
        recortes = []
        for f, c, color in e["vistas"]:
            # cada recorte, centrado en SU caja: la de 1 s después puede estar lejos
            cx, cy = int((c[0] + c[2]) / 2), int((c[1] + c[3]) / 2)
            img = imgs.get(f, np.zeros((1080, 1920, 3), np.uint8)).copy()
            cv2.rectangle(img, (int(c[0]), int(c[1])), (int(c[2]), int(c[3])), color, 1)
            y0, x0 = max(0, cy - LADO // 2), max(0, cx - LADO // 2)
            trozo = img[y0 : y0 + LADO, x0 : x0 + LADO]  # noqa: E203
            r = cv2.resize(trozo, (LADO * 2, LADO * 2))
            recortes.append(r)
        fila = np.hstack(recortes)
        t = e["t"]
        texto(
            fila,
            f"#{n}  archivo {reloj(t)} | reproductor {reloj(t + ADELANTO_REPRODUCTOR_S)}  "
            f"salto {e['salto_m']:.1f} m  x={e['x']:.0f} y={e['y']:.0f}",
            (6, 16),
        )
        texto(fila, "verde = antes del corte, rojo = despues", (6, LADO * 2 - 8))
        filas.append(fila)
    hoja = np.vstack(filas)
    ruta = sal / f"hoja_cortes_{args.rama}.jpg"
    cv2.imwrite(str(ruta), hoja, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(
        f"{len(eventos)} cortes en la rama {args.rama}; muestra de {len(muestra)} en {ruta}"
    )
    for n, e in enumerate(muestra, start=1):
        print(
            f"  #{n:<2} archivo {reloj(e['t'])}  "
            f"reproductor {reloj(e['t'] + ADELANTO_REPRODUCTOR_S)}  "
            f"frame {e['frame']}  salto {e['salto_m']:.1f} m  (x={e['x']:.0f}, y={e['y']:.0f})"
        )


if __name__ == "__main__":
    main()
