#!/usr/bin/env python
"""El mismo partido a dos escalas: ¿qué aguanta y qué se degrada?

Compara el CSV de un tramo corto con el de la parte entera SOBRE LOS
MISMOS FRAMES, que es la única comparación honesta: los dos CSV cubren la
ventana del GT (frames 9750-10635 del benjamín), así que la diferencia
que salga es de la ESCALA del fit y de las reglas, no del trozo de
partido que a cada uno le tocó.

⚠️ Dos cuidados que no son opcionales:

1. **Las etiquetas A/B son arbitrarias** y se intercambian entre
   corridas. Aquí se elige el emparejamiento que MAXIMIZA el acuerdo y se
   dice cuál se eligió. Comparar A con A a ciegas mediría el orden del
   KMeans, no la calidad.
2. **El casado es por POSICIÓN**, nunca por id del sistema: un id caduca
   al cambiar de tramo o de detector (CLAUDE.md).

Uso:
    python scripts/comparar_escalas.py \
        --csv "5 min=/ruta/piloto.csv" --csv "20 min=data/tracking_benja/posiciones_benja_p1.csv"
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402

logger = logging.getLogger("escalas")

# Radio máximo para dar por casada una observación con una persona del
# GT. 2 m es generoso para un F7 pero necesario en la mitad lejana, donde
# un píxel vale casi medio metro.
RADIO_CASADO_M = 2.0


def equipo_gt(obs):
    """Equipo del GT, con los porteros contando para su equipo."""
    t = str(obs.team)
    return t.replace("portero_", "") if t.startswith("portero_") else t


def casar(df, gt_m):
    """Empareja cada persona del GT con la fila más cercana del CSV."""
    pares = []
    por_frame = {f: g for f, g in df.groupby("frame")}
    for frame, obs_gt in sorted(gt_m.items()):
        if frame not in por_frame:
            continue
        sub = por_frame[frame]
        xy = sub[["x_m", "y_m"]].to_numpy()
        etiquetas = sub.etiqueta.to_numpy()
        for o in obs_gt:
            eq = equipo_gt(o)
            if eq not in ("A", "B"):
                continue  # el árbitro no entra en la exactitud de equipos
            d = np.hypot(xy[:, 0] - o.pos[0], xy[:, 1] - o.pos[1])
            k = int(np.argmin(d))
            if d[k] > RADIO_CASADO_M:
                pares.append((eq, None))
                continue
            sis = str(etiquetas[k]).replace("portero_", "")
            pares.append((eq, sis))
    return pares


def informar(nombre, pares):
    casados = [(g, s) for g, s in pares if s is not None]
    conf = Counter(casados)
    # Las etiquetas A/B son arbitrarias: se prueba el emparejamiento
    # directo y el cruzado y se queda el que más acierta.
    directo = conf[("A", "A")] + conf[("B", "B")]
    cruzado = conf[("A", "B")] + conf[("B", "A")]
    invertido = cruzado > directo
    aciertos = max(directo, cruzado)
    en_equipo = sum(v for (g, s), v in conf.items() if s in ("A", "B"))
    fuera = len(casados) - en_equipo  # staff / otro sobre una persona real
    print(f"\n── {nombre} ──")
    print(f"  personas del GT             : {len(pares)}")
    print(
        f"  casadas (≤ {RADIO_CASADO_M:.0f} m)          : {len(casados)}"
        f" ({100*len(casados)/max(len(pares),1):.1f} %)"
    )
    print(f"  con etiqueta de equipo      : {en_equipo}")
    print(
        f"  mandadas a staff/otro       : {fuera}"
        f" ({100*fuera/max(len(casados),1):.1f} % de las casadas)"
    )
    if en_equipo:
        print(
            f"  EQUIPO EQUIVOCADO           : {en_equipo - aciertos}"
            f" ({100*(en_equipo-aciertos)/en_equipo:.1f} %)"
            f"{'  [emparejamiento invertido]' if invertido else ''}"
        )
    return {
        "gt": len(pares),
        "casadas": len(casados),
        "en_equipo": en_equipo,
        "fuera": fuera,
        "mal": en_equipo - aciertos,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--csv", action="append", required=True, help="nombre=ruta (se puede repetir)"
    )
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    H = np.load(args.homografia)
    gt_m = gt_a_por_frame(parsear_cvat(args.gt), H, args.offset, args.paso)
    print(
        f"\nGT: {len(gt_m)} frames anotados ({min(gt_m)}-{max(gt_m)}), "
        f"{sum(len(v) for v in gt_m.values())} observaciones"
    )

    res = {}
    for entrada in args.csv:
        nombre, ruta = entrada.split("=", 1)
        df = pd.read_csv(ruta)
        df = df[df.es_real == 1]
        comunes = sorted(set(df.frame) & set(gt_m))
        print(f"\n{nombre}: {ruta}")
        print(f"  frames en común con el GT: {len(comunes)} de {len(gt_m)}")
        res[nombre] = informar(nombre, casar(df, {f: gt_m[f] for f in comunes}))

    if len(res) == 2:
        (n1, a), (n2, b) = res.items()
        print(f"\n{'='*60}\n  {n1} → {n2}\n{'='*60}")
        for clave, etq in (
            ("casadas", "personas casadas"),
            ("fuera", "a staff/otro"),
            ("mal", "equipo equivocado"),
        ):
            base = a["en_equipo"] if clave == "mal" else a["casadas"]
            base2 = b["en_equipo"] if clave == "mal" else b["casadas"]
            print(
                f"  {etq:<22} {100*a[clave]/max(base,1):>6.1f} %"
                f" → {100*b[clave]/max(base2,1):>6.1f} %"
            )


if __name__ == "__main__":
    main()
