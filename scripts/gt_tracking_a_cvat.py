#!/usr/bin/env python
"""Convierte el CSV de clics en un annotations.xml que el banco ya consume.

La herramienta de etiquetado guarda CLICS —un punto en los pies de cada
jugador— porque es lo que un humano puede marcar rápido y sin ambigüedad.
El banco espera CVAT for video 1.1 con cajas. Aquí se traduce.

Lo que importa de la traducción: la homografía proyecta los **pies**, o
sea el centro del borde inferior de la caja. Así que la caja se sintetiza
alrededor del clic de forma que su borde inferior central caiga
exactamente donde se pinchó. El alto y el ancho son nominales y no
afectan a la posición proyectada — solo existen para que el formato case.

`frame_local` es el índice DENTRO del GT (0, 1, 2...), no el frame del
vídeo: es como está el GT de Villaviciosa, y el banco lo alinea con
`frame_offset` y `paso_gt` del config de evaluación.

Uso:
    python scripts/gt_tracking_a_cvat.py \\
        --csv ~/Downloads/gt_tracking_5m25s_30s.csv \\
        --salida data/annotations/gt_benja/annotations.xml
"""

import argparse
import logging
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("gt_a_cvat")

ALTO = 40.0
ANCHO = 18.0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", required=True)
    p.add_argument(
        "--cache",
        default="data/tracking_benja/cache_detecciones_benja_v4.pkl",
        help="Caché de detecciones, para escalar la corrección de pies",
    )
    p.add_argument("--salida", required=True)
    p.add_argument(
        "--equipos",
        default="",
        help="Opcional: 'jugador:equipo,...' p. ej. '1:A,2:A,8:portero_B'",
    )
    p.add_argument("--alto", type=float, default=ALTO)
    p.add_argument(
        "--sin-corregir-pies",
        action="store_true",
        help=(
            "No baja los clics al suelo. Con la corrección el "
            "desplazamiento mediano pasa de 1,58 m a 0,42 m."
        ),
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    df = pd.read_csv(args.csv)
    if not args.sin_corregir_pies:
        from src.evaluation.correccion_pies import corregir_clics
        from src.tracking.cache_io import cargar_cache

        df = corregir_clics(df, cargar_cache(args.cache)["cache"])
    faltan = {"jugador", "frame", "x_px", "y_px"} - set(df.columns)
    if faltan:
        raise SystemExit(f"Al CSV le faltan columnas: {sorted(faltan)}")

    equipos = {}
    for par in filter(None, args.equipos.split(",")):
        j, eq = par.split(":")
        equipos[int(j)] = eq

    # frame_local: el índice del fotograma DENTRO del GT, no el del vídeo
    orden = {f: i for i, f in enumerate(sorted(df.frame.unique()))}

    raiz = ET.Element("annotations")
    ET.SubElement(raiz, "version").text = "1.1"
    meta = ET.SubElement(raiz, "meta")
    tarea = ET.SubElement(meta, "task")
    ET.SubElement(tarea, "name").text = Path(args.csv).stem
    ET.SubElement(tarea, "size").text = str(len(orden))
    ET.SubElement(tarea, "start_frame").text = "0"
    ET.SubElement(tarea, "stop_frame").text = str(len(orden) - 1)

    n_cajas = 0
    for tid, (jugador, g) in enumerate(df.groupby("jugador")):
        equipo = equipos.get(int(jugador))
        etiqueta = "referee" if equipo == "referee" else "player"
        nodo = ET.SubElement(
            raiz, "track", id=str(tid), label=etiqueta, source="manual"
        )
        for fila in g.sort_values("frame").itertuples():
            # El clic marca los PIES: borde inferior, centro.
            xtl = float(fila.x_px) - ANCHO / 2
            xbr = float(fila.x_px) + ANCHO / 2
            ybr = float(fila.y_px)
            ytl = ybr - args.alto
            caja = ET.SubElement(
                nodo,
                "box",
                frame=str(orden[fila.frame]),
                outside="0",
                occluded="0",
                keyframe="1",
                xtl=f"{xtl:.2f}",
                ytl=f"{ytl:.2f}",
                xbr=f"{xbr:.2f}",
                ybr=f"{ybr:.2f}",
            )
            if equipo and etiqueta == "player":
                attr = ET.SubElement(caja, "attribute", name="team")
                attr.text = equipo
            n_cajas += 1

    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    ET.indent(raiz, space="  ")
    ET.ElementTree(raiz).write(args.salida, encoding="utf-8", xml_declaration=True)

    print(f"\n✓ {args.salida}")
    print(f"  {df.jugador.nunique()} tracks, {n_cajas} cajas, {len(orden)} fotogramas")
    if not equipos:
        print(
            "\n  ⚠ Sin --equipos, ningún track lleva atributo 'team'. El banco\n"
            "    medirá cobertura, IDF1 y quimeras, pero NO la accuracy de\n"
            "    equipos ni las quimeras del MISMO equipo, que es justo lo que\n"
            "    motivó este GT. Pásale el mapa jugador→equipo."
        )
    # Comprobación de ida y vuelta: que el banco lo pueda leer
    from src.evaluation.gt_parser import parsear_cvat

    tracks = parsear_cvat(args.salida)
    print(f"  Releído por el banco: {len(tracks)} tracks ✓")


if __name__ == "__main__":
    main()
