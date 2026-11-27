#!/usr/bin/env python
"""Revisión visual del interruptor `staff_dentro_del_campo` en el alevín B (27-nov-2026).

El interruptor (adoptado en el benjamín el 30-oct, `docs/staff_dentro_del_campo.md`) etiqueta como
jugador las observaciones de una identidad de staff con el pie DENTRO del campo y en trozos que
corren. En el alevín B recupera las 3 marcas del mini-GT que iban a staff (86,1 → 89,9 %), pero
pasa a A/B 1.387 filas en 53 identidades, muchas en la banda lejana junto al banquillo. Pregunta del
criterio 2 del benjamín: ¿cuántas de esas rachas NO son jugadores?

Hace una hoja de miniaturas, una por racha (identidad, filas cambiadas seguidas con huecos < 1 s):
el fotograma del centro de la racha, con la caja de la PROPIA detección de esa identidad en ese
fotograma (regla de las hojas, CLAUDE.md), ampliada. Fotogramas con el ffmpeg CLI.

Uso:
    python scripts/staff_dentro_alevinb.py --salida outputs/alevinb_staff_dentro/hoja
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

from src.utils.video_ffmpeg import leer_frames_ffmpeg  # noqa: E402

VIDEO = R / "data/raw/alevinb_p1.mp4"
BASE = R / "outputs/alevinb_siglip/alevinb/posiciones_siglip.csv"
FLAG = {
    "agregacion": {
        "por_observacion": {
            "staff_dentro_del_campo": {
                "activo": True,
                "margen_m": 1.0,
                "solo_trozos_rapidos": True,
                "hueco_trozo_s": 1.0,
            }
        }
    }
}


def rachas(base: pd.DataFrame, nueva: pd.DataFrame) -> list[pd.DataFrame]:
    cambia = base.etiqueta.to_numpy() != nueva.etiqueta.to_numpy()
    c = nueva[cambia].sort_values(["id_jugador", "tiempo_s"])
    salida = []
    for _id, g in c.groupby("id_jugador"):
        corte = (g.tiempo_s.diff() > 1.0).cumsum()
        salida += [r for _k, r in g.groupby(corte)]
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--por-hoja", type=int, default=20)
    a = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    import banco_mision as bm

    bm.SALIDA = a.salida.parent / "captura"
    csv, identidades, cache = bm.correr_capturando("alevinb", "staff_dentro", {}, FLAG)
    base, nueva = pd.read_csv(BASE), pd.read_csv(csv)
    assert len(base) == len(nueva), "las dos pasadas tienen que tener las mismas filas"
    det_de = {}
    for n, ident in enumerate(identidades, start=1):
        for f, j in ident:
            det_de[(n, f)] = j
    lista = []
    for r in rachas(base, nueva):
        reales = r[r.es_real == 1]
        if reales.empty:
            continue
        m = reales.iloc[len(reales) // 2]
        f, n = int(m.frame), int(m.id_jugador)
        j = det_de.get((n, f))
        if j is None:
            continue
        lista.append(
            {
                "id": n,
                "frame": f,
                "caja": [float(v) for v in cache[f][j][2:6]],
                "inicio_s": float(r.tiempo_s.min()),
                "dura_s": round(float(r.tiempo_s.max() - r.tiempo_s.min()), 1),
                "filas": len(r),
                "etiqueta": "/".join(sorted(set(r.etiqueta))),
                "x_m": round(float(m.x_m), 1),
                "y_m": round(float(m.y_m), 1),
            }
        )
    imgs = dict(leer_frames_ffmpeg(VIDEO, sorted({d["frame"] for d in lista})))
    a.salida.mkdir(parents=True, exist_ok=True)
    teselas = []
    for k, d in enumerate(lista):
        img = imgs[d["frame"]]
        x1, y1, x2, y2 = d["caja"]
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        h, w = img.shape[:2]
        x0 = int(np.clip(cx - 120, 0, w - 240))
        y0 = int(np.clip(cy - 80, 0, h - 160))
        rec = img[y0 : y0 + 160, x0 : x0 + 240].copy()  # noqa: E203
        cv2.rectangle(
            rec,
            (int(x1 - x0), int(y1 - y0)),
            (int(x2 - x0), int(y2 - y0)),
            (0, 255, 255),
            1,
        )
        rec = cv2.resize(rec, (480, 320), interpolation=cv2.INTER_NEAREST)
        mm, ss = divmod(d["inicio_s"], 60)
        texto = [
            f"#{k} id {d['id']} -> {d['etiqueta']}",
            f"{int(mm)}:{ss:04.1f} archivo, {d['dura_s']} s, {d['filas']} filas",
            f"({d['x_m']}, {d['y_m']}) m",
        ]
        for i, t in enumerate(texto):
            cv2.putText(
                rec, t, (6, 18 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3
            )
            cv2.putText(
                rec,
                t,
                (6, 18 + 18 * i),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )
        teselas.append(rec)
    for h0 in range(0, len(teselas), a.por_hoja):
        grupo = teselas[h0 : h0 + a.por_hoja]  # noqa: E203
        grupo += [np.zeros_like(teselas[0])] * (-len(grupo) % 4)
        filas = [
            np.hstack(grupo[i : i + 4]) for i in range(0, len(grupo), 4)  # noqa: E203
        ]
        cv2.imwrite(str(a.salida / f"hoja_{h0 // a.por_hoja}.jpg"), np.vstack(filas))
    pd.DataFrame(lista).to_csv(a.salida / "rachas.csv", index=False)
    print(json.dumps({"rachas": len(lista), "hojas": -(-len(teselas) // a.por_hoja)}))


if __name__ == "__main__":
    main()
