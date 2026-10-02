#!/usr/bin/env python
"""Mide cada umbral del detector de balón con el banco completo, y aplica el criterio.

Entrada: los cachés de la celda 2 (`colab_cache_balon_umbrales.py`), uno por
umbral, reconstruidos con la cadena de producción. El CRITERIO se fijó ANTES
de ver ningún número (docs/colab_balon_umbral_bajo.md) y está aquí escrito
como código, para que no se pueda mover después:

0. CONTROL: el caché reconstruido a 0,35 tiene que ser el de producción
   (≥ 99 % de frames idénticos). Si no, todo se compara contra el
   reconstruido a 0,35 (misma sesión de Colab), no contra el viejo, y se dice.
1. GT de desempates sin bajar de lo que da producción CON ESTE SCRIPT (35 de 38:
   aquí se acepta la caja a ≤ 15 px del balón; con la caja exacta eran 34).
2. Cambios de objeto ≤ 3 por minuto.
3. Fracción en las 5 marcas de verdad = 0.
4. Duración máxima anclada ≤ 19,4 s; si la supera, se mira a ojo y solo vale
   si es una parada real (este script la imprime para mirarla, no la juzga).
5. Tramos etiquetados a ojo: lo que no es balón no sube.
6. BENEFICIO: de los 14 casos visibles con posición del GT de 25, al menos 3
   recuperados más que a 0,35 (los que se vieron a 0,05: V03, V08, V12).
7. COSTE: de 30 frames ganados al azar, mirados a ojo, ≥ 2/3 balón real y
   ≤ 1/6 basura clara (el listón de la readmisión de vuelos). Este script saca
   la hoja; el juicio es a ojo.

Si varios umbrales pasan, el del centro del tramo que pasa. Si el ruido sube
sin que suba lo recuperado, se cierra.

Uso:
    python scripts/medir_umbral_balon.py --caches data/tracking_benja/umbral_bajo
"""

import argparse
import contextlib
import io
import json
import pickle
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.carga import cargar_detecciones_limpias  # noqa: E402
from src.balon.carga import contexto_del_selector  # noqa: E402
from src.balon.metricas_adopcion import duracion_maxima_anclada  # noqa: E402
from src.balon.metricas_adopcion import fraccion_en_marcas  # noqa: E402
from src.balon.tracking_balon import ParametrosBalon  # noqa: E402
from src.balon.tracking_balon import seleccionar_balon_activo  # noqa: E402
from src.campo_modelo import cargar_modelo  # noqa: E402

MARCAS_VERDAD = {(26, 53), (27, 53), (30, 52), (31, 52), (20, 54)}
UMBRALES = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35)
PRODUCCION = 0.35
ANCLADA_MAX_S = 19.4
RADIO_GT_PX = 60.0  # celda de 80 px (±40) + holgura por el tamaño de la caja
# Los 14 casos con balón VISIBLE y posición del GT de vuelo (respuestas de Alex,
# leídas a mano, docs/balon_en_vuelo.md). Ancla: el círculo que nombró o su celda.
GT_VISIBLES = {
    "V03": (["O8", "P8"], None),
    "V05": (["O8"], "verde"),
    "V06": (["H5"], "verde"),
    "V07": (["B9"], "verde"),
    "V08": (["O8"], "rojo"),
    "V09": (["H8", "H9"], "rojo"),
    "V12": (["N8"], "rojo"),
    "V14": (["C9"], "verde"),
    "V15": (["N8"], None),
    "V16": (["U9", "V9"], "rojo_arriba"),
    "V17": (["I9"], None),
    "V18": (["F8"], "verde"),
    "V19": (["J9"], None),
    "V24": (["O8"], "verde"),
}
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWX"


def centro(d):
    return np.array(((d[2] + d[4]) / 2.0, (d[3] + d[5]) / 2.0))


def punto_gt(celdas, ancla, meta):
    if ancla == "verde":
        return np.array(meta["antes"]["px"])
    if ancla == "rojo":
        return np.array(meta["despues"]["px"])
    if ancla == "rojo_arriba":
        return np.array(meta["despues"]["px"]) - (0, 22)
    pts = [((LETRAS.index(c[0]) + 0.5) * 80, (int(c[1:]) - 0.5) * 80) for c in celdas]
    return np.mean(pts, axis=0)


def cambios_por_minuto(sel, tiempos):
    fr = sorted(sel)
    n = 0
    for a, b in zip(fr, fr[1:]):
        dt = tiempos[b] - tiempos[a]
        if (
            0 < dt <= 0.5
            and np.linalg.norm(centro(sel[b]) - centro(sel[a])) / dt > 1000
        ):
            n += 1
    return n / ((max(tiempos.values()) - min(tiempos.values())) / 60)


def gt_desempates(sel, gt):
    """Aciertos: lo elegido a ≤ 15 px del candidato que Alex marcó como balón.

    15 px y no igualdad exacta: a otro umbral la fusión puede mover un poco la
    caja del mismo balón.
    """
    ok = 0
    for _caso, d in gt.groupby("caso"):
        f = int(d.frame_idx.iloc[0])
        if d.estado_caso.iloc[0] != "balon" or f not in sel or d.es_balon.sum() == 0:
            continue
        b = d[d.es_balon == 1].iloc[0]
        ok += bool(np.hypot(*(centro(sel[f]) - (b.cx, b.cy))) <= 15)
    return ok


def tramos_etiquetados(sel, ruta_tramos):
    """Balón / no balón / sin etiqueta elegidos en los dos tramos etiquetados a ojo."""
    et = json.loads((ruta_tramos / "etiquetas.json").read_text())
    res = {}
    for t in ("t365", "t990"):
        pist = pickle.load(open(ruta_tramos / f"{t}_pistillas.pkl", "rb"))
        por_frame = {}
        for k, p in enumerate(pist):
            for f, d in p["obs"]:
                por_frame.setdefault(f, []).append((centro(d), et[t][str(k)]))
        c = {"balon": 0, "malo": 0, "sin_etiqueta": 0}
        for f, cands in por_frame.items():
            if f not in sel:
                continue
            dist, lab = min(
                ((np.linalg.norm(cc - centro(sel[f])), lb) for cc, lb in cands)
            )
            if dist > 3:
                c["sin_etiqueta"] += 1
            elif lab == "balon":
                c["balon"] += 1
            elif lab in ("bota", "zapato", "otro", "dorsal"):
                c["malo"] += 1
        res[t] = c
    return res


def hoja_ganados(ganados, sel, video, salida, n=30, semilla=20261002):
    """30 frames ganados al azar, con la caja elegida, para mirarlos a ojo."""
    elegidos = sorted(
        random.Random(semilla).sample(sorted(ganados), min(n, len(ganados)))
    )
    cap, pos, tiles = cv2.VideoCapture(video), 0, []
    for f in elegidos:
        while pos < f:
            cap.grab()
            pos += 1
        ok, img = cap.read()
        pos += 1
        d = sel[f]
        cv2.rectangle(
            img,
            (int(d[2]) - 4, int(d[3]) - 4),
            (int(d[4]) + 4, int(d[5]) + 4),
            (0, 0, 255),
            2,
        )
        c = centro(d).astype(int)
        x0 = int(np.clip(c[0] - 160, 0, img.shape[1] - 320))
        y0 = int(np.clip(c[1] - 120, 0, img.shape[0] - 240))
        x1, y1 = x0 + 320, y0 + 240
        t = cv2.resize(img[y0:y1, x0:x1], (320, 240))
        cv2.putText(
            t,
            f"{len(tiles)} f{f} conf {d[6]:.2f}",
            (4, 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            2,
        )
        tiles.append(t)
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 6)
    cv2.imwrite(
        str(salida),
        np.vstack(
            [
                np.hstack(tiles[i:j])
                for i, j in zip(range(0, len(tiles), 6), range(6, len(tiles) + 6, 6))
            ]
        ),
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--caches", required=True, help="carpeta con cache_balon_p1_confNNN.pkl"
    )
    p.add_argument("--produccion", default="data/tracking_benja/cache_balon_p1.pkl")
    p.add_argument(
        "--csv-jugadores", default="data/tracking_benja/posiciones_benja_p1_v3.csv"
    )
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    p.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    p.add_argument(
        "--gt-desempates", default="data/tracking_benja/gt_desempates_balon.csv"
    )
    p.add_argument("--gt-vuelo", default="outputs/gt_balon_en_vuelo/metadatos.json")
    p.add_argument("--tramos", default="data/tracking_benja/tramos_balon_etiquetados")
    p.add_argument("--salida", default="outputs/umbral_balon")
    args = p.parse_args()

    carpeta, salida = Path(args.caches), Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    modelo = cargar_modelo(config=args.campo)
    gt = pd.read_csv(args.gt_desempates)
    meta_vuelo = json.loads(Path(args.gt_vuelo).read_text())

    # 0. CONTROL: el reconstruido a 0,35 contra el caché de producción
    prod = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(open(args.produccion, "rb"))["cache"]
    }
    rec = pickle.load(open(carpeta / "cache_balon_p1_conf035.pkl", "rb"))

    def firma(dets):
        return sorted(tuple(round(float(v), 1) for v in d[2:]) for d in dets)

    iguales = sum(
        firma(e["dets"]) == firma(prod.get(e["frame_idx"], [])) for e in rec["cache"]
    )
    frac = iguales / len(rec["cache"])
    print(
        f"0. CONTROL 0,35 reconstruido vs producción: {iguales}/{len(rec['cache'])} "
        f"frames idénticos ({100 * frac:.1f} %) → "
        + ("OK" if frac >= 0.99 else "⚠️ NO: se compara contra el reconstruido a 0,35")
    )

    filas, seleccion = [], {}
    for u in UMBRALES:
        ruta = carpeta / f"cache_balon_p1_conf{int(round(u * 100)):03d}.pkl"
        with contextlib.redirect_stdout(io.StringIO()):
            dets, tiempos, meta = cargar_detecciones_limpias(str(ruta), modelo)
        jug, ctx = contexto_del_selector(
            args.csv_jugadores,
            tiempos,
            dets,
            args.campo,
            modelo,
            meta["fuera_de_campo"],
        )
        pos = {f: [(j[0], j[1]) for j in jug.get(f, [])] for f in dets}
        sel = seleccionar_balon_activo(dets, pos, ParametrosBalon(), **ctx)
        seleccion[u] = sel
        fr = sorted(sel)
        tray_m = [(f, (sel[f][0], sel[f][1])) for f in fr]
        tray_px = [(f, tuple(centro(sel[f]))) for f in fr]
        recuperados = []
        for caso, (celdas, ancla) in GT_VISIBLES.items():
            f = meta_vuelo[caso]["frame"]
            punto = punto_gt(celdas, ancla, meta_vuelo[caso])
            if f in sel and np.linalg.norm(centro(sel[f]) - punto) <= RADIO_GT_PX:
                recuperados.append(caso)
        tr = tramos_etiquetados(sel, Path(args.tramos))
        filas.append(
            {
                "umbral": u,
                "gt_desempates": gt_desempates(sel, gt),
                "cambios_min": round(cambios_por_minuto(sel, tiempos), 2),
                "en_marcas": fraccion_en_marcas(tray_px, MARCAS_VERDAD),
                "anclada_s": round(
                    duracion_maxima_anclada(tray_m, tiempos, 1.0, 1.0), 1
                ),
                "frames_balon": len(sel),
                "gt_vuelo_recuperados": len(recuperados),
                "recuperados": ",".join(recuperados),
                "t365_balon_malo_sinet": "/".join(str(v) for v in tr["t365"].values()),
                "t990_balon_malo_sinet": "/".join(str(v) for v in tr["t990"].values()),
            }
        )
    tabla = pd.DataFrame(filas)
    print(tabla.to_string(index=False))
    tabla.to_csv(salida / "tabla_umbrales.csv", index=False)

    base = tabla[tabla.umbral == PRODUCCION].iloc[0]
    print("\nCRITERIO (fijado antes de ver números):")
    for _i, r in tabla[(tabla.umbral >= 0.10) & (tabla.umbral <= 0.25)].iterrows():
        checks = {
            "1 GT ≥ producción": r.gt_desempates >= base.gt_desempates,
            "2 cambios ≤ 3/min": r.cambios_min <= 3,
            "3 marcas = 0": r.en_marcas == 0,
            "4 anclada ≤ 19,4 s (si no, mirar)": r.anclada_s <= ANCLADA_MAX_S,
            "5 malos no suben": all(
                int(r[c].split("/")[1]) <= int(base[c].split("/")[1])
                for c in ("t365_balon_malo_sinet", "t990_balon_malo_sinet")
            ),
            "6 recupera ≥ 3 más": r.gt_vuelo_recuperados - base.gt_vuelo_recuperados
            >= 3,
        }
        u = r.umbral
        ganados = set(seleccion[u]) - set(seleccion[PRODUCCION])
        hoja = salida / f"ganados_conf{int(round(u * 100)):03d}.jpg"
        if ganados:
            hoja_ganados(ganados, seleccion[u], args.video, hoja)
        fallos = [k for k, v in checks.items() if not v]
        print(
            f"  {u:.2f}: "
            + ("pasa 1-6" if not fallos else "FALLA " + "; ".join(fallos))
            + f" · {len(ganados)} frames ganados → criterio 7 a ojo en {hoja.name}"
        )


if __name__ == "__main__":
    main()
