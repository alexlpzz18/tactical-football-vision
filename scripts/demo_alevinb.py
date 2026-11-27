#!/usr/bin/env python
"""Demo del alevín B: clips con la superposición táctica y una pizarra 2D congelada y editable.

Para enseñar correcciones en una reunión (petición de Alex, 27-nov): para cada tramo,
1. el vídeo real con la superposición (`superposicion_tactica.py`: contorno del bloque, líneas de
   defensa / medio / ataque promediadas en 3 s y distancias en metros);
2. al pausar (o con «Congelar», tecla C), una pizarra 2D del instante: cada ficha en la MEDIANA de
   su posición en ± 0,4 s, con el contorno y las tres líneas de cada equipo;
3. las fichas se arrastran con el ratón o el dedo (doble clic o pulsación larga: se quita una ficha
   que sobra) y el contorno, las líneas y las distancias se recalculan al momento. Nada se guarda
   (todo en memoria): «Restaurar» vuelve a lo calculado.
4. la pizarra NO esconde los fallos del sistema, los marca: semitransparente, la ficha sin ninguna
   detección real en ± 0,4 s (solo filas interpoladas); con aro naranja, las parejas del MISMO
   equipo a < 1 m (posible duplicado: una persona en dos identidades). «Quitar duplicados» deja la
   de más detecciones reales de cada pareja, y se deshace con «Restaurar».

Las líneas de la pizarra se calculan igual que en la superposición (corte 1D óptimo en 3 grupos a lo
largo de la dirección de ataque, sin porteros); la dirección de ataque de cada equipo sale de dónde
está su portero en el tramo.

Uso:
    python scripts/demo_alevinb.py --csv outputs/f11_staff_dentro/alevinb/posiciones_staff_on.csv \\
        --tramos 180:210,600:630 --salida outputs/demo_alevinb
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
VIDEO = R / "data/raw/alevinb_p1.mp4"
CAMARA = R / "data/calibracion_alevinb/camara_alevinb.npz"
LARGO, ANCHO = 100.0, 64.0
COLORES = {
    "A": "#3b82f6",
    "B": "#ef4444",
}  # A = blancos, B = verdes (en el vídeo y en la pizarra)
NOMBRES = {"A": "Blancos", "B": "Verdes"}
EQUIPO = {"A": "A", "B": "B", "portero_A": "A", "portero_B": "B"}


def datos_del_tramo(df: pd.DataFrame, desde: float, hasta: float) -> dict:
    t = df[(df.tiempo_s >= desde - 0.5) & (df.tiempo_s <= hasta + 0.5)]
    t = t[t.etiqueta.isin(EQUIPO)]
    ataque = {}
    for e in ("A", "B"):
        p = t[t.etiqueta == f"portero_{e}"]
        x = p.x_m.median() if len(p) else t[t.etiqueta == e].x_m.median()
        ataque[e] = (
            1 if (not np.isnan(x) and x < LARGO / 2) else -1
        )  # defiende x=0 → ataca hacia +x
    filas = [
        [round(r.tiempo_s - desde, 2), int(r.id_jugador), EQUIPO[r.etiqueta],
         int(r.etiqueta.startswith("portero")), round(r.x_m, 2), round(r.y_m, 2), int(r.es_real)]
        for r in t.itertuples()
    ]  # fmt: skip
    return {"desde": desde, "hasta": hasta, "ataque": ataque, "filas": filas}


# La página (HTML + JS) vive aparte para que el formateador no la toque.
PLANTILLA = R / "scripts/plantillas/demo_alevinb.html"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument(
        "--tramos", required=True, help="desde:hasta en segundos del archivo, por comas"
    )
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--sin-video", action="store_true", help="no regenerar los clips")
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(a.csv)
    tramos = [tuple(float(x) for x in t.split(":")) for t in a.tramos.split(",")]
    datos = []
    for i, (desde, hasta) in enumerate(tramos):
        datos.append(datos_del_tramo(df, desde, hasta))
        if not a.sin_video:
            subprocess.run(
                [sys.executable, str(R / "scripts/superposicion_tactica.py"), "--csv", str(a.csv),
                 "--video", str(VIDEO), "--camara", str(CAMARA), "--largo", str(LARGO),
                 "--ancho", str(ANCHO), "--fps", "25", "--desde", str(desde), "--hasta", str(hasta),
                 "--colores", f"{COLORES['A']},{COLORES['B']}",
                 "--salida", str(a.salida / f"clip_{i}.mp4")],
                check=True,
            )  # fmt: skip
    html = (
        PLANTILLA.read_text()
        .replace("__DATOS__", json.dumps(datos, separators=(",", ":")))
        .replace("__COLORES__", json.dumps(COLORES))
        .replace("__NOMBRES__", json.dumps(NOMBRES, ensure_ascii=False))
        .replace("__LARGO__", str(LARGO))
        .replace("__ANCHO__", str(ANCHO))
    )
    (a.salida / "index.html").write_text(html)
    print(f"✓ {a.salida / 'index.html'} · {len(tramos)} clips")


if __name__ == "__main__":
    main()
