#!/usr/bin/env python
"""CLI del replay táctico 2D: CSV de posiciones → HTML autocontenido.

Uso:
    python scripts/generar_replay.py [--csv data/tracking/posiciones_v2.csv]
                                     [--salida outputs/replay.html]
                                     [--largo 105] [--ancho 68]
                                     [--titulo "Partido X"]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.campo_modelo import cargar_modelo  # noqa: E402
from src.report.replay_tactico import generar_replay  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/tracking/posiciones_v2.csv")
    parser.add_argument("--salida", default="outputs/replay.html")
    parser.add_argument("--largo", type=float, default=None)
    parser.add_argument("--ancho", type=float, default=None)
    parser.add_argument("--max-hueco", type=float, default=3.0)
    parser.add_argument(
        "--campo",
        default=None,
        help="Modelo de campo a dibujar: f11 (defecto) o f7. Fija también "
        "las dimensiones salvo que se pasen --largo/--ancho.",
    )
    parser.add_argument(
        "--config-campo",
        default=None,
        help="YAML del campo (p. ej. configs/campo_benja.yaml). Tiene "
        "prioridad sobre --campo.",
    )
    parser.add_argument(
        "--radio",
        type=float,
        default=None,
        help="Radio de la ficha en metros (por defecto 0.8; el config del "
        "campo puede fijarlo con la clave `radio_ficha_m`)",
    )
    parser.add_argument("--titulo", default="Replay táctico")
    parser.add_argument(
        "--espejar",
        choices=["x", "y", "xy"],
        default=None,
        help="Voltea la VISTA para casarla con la orientación de la cámara "
        "(no toca los datos).",
    )
    parser.add_argument(
        "--meta",
        default=None,
        help="JSON de metadatos del processor, del que se leen los colores "
        "reales de cada equipo. Por defecto se busca junto al CSV.",
    )
    parser.add_argument(
        "--sin-colores-reales",
        action="store_true",
        help="Ignora los colores del meta y usa azul/rojo por convenio.",
    )
    parser.add_argument(
        "--max-edad-interp",
        type=float,
        default=0.6,
        help="Antigüedad máxima (s) de una posición interpolada respecto a "
        "una detección real para pintarla (credibilidad del replay)",
    )
    parser.add_argument(
        "--min-vida",
        type=float,
        default=2.0,
        help="Duración mínima (s) de detecciones reales para pintar una "
        "identidad (fuera el confeti de fragmentos)",
    )
    args = parser.parse_args()
    # La orientación puede venir del config del campo (es una propiedad
    # de la CÁMARA de ese partido, no del comando que se teclee).
    espejar = args.espejar
    if espejar is None and args.config_campo:
        import yaml

        with open(args.config_campo) as f:
            cfg_campo = yaml.safe_load(f) or {}
        espejar = cfg_campo.get("espejar")
        if args.radio is None:
            args.radio = cfg_campo.get("radio_ficha_m")

    modelo = None
    if args.config_campo or args.campo:
        modelo = cargar_modelo(
            nombre=None if args.config_campo else args.campo,
            config=args.config_campo,
        )
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    # Colores reales de equipo: del meta indicado o del que acompañe al CSV
    colores_equipo = None
    if not args.sin_colores_reales:
        ruta_meta = (
            Path(args.meta)
            if args.meta
            else Path(str(Path(args.csv).with_suffix("")) + "_meta.json")
        )
        if ruta_meta.exists():
            colores_equipo = json.loads(ruta_meta.read_text()).get("colores_equipo")
            if colores_equipo:
                print(f"Colores de equipo del clasificador: {colores_equipo}")
        elif args.meta:
            print(f"AVISO: no existe {ruta_meta}; se usan los colores por convenio.")

    ruta = generar_replay(
        args.csv,
        args.salida,
        modelo=modelo,
        espejar=espejar,
        radio_m=args.radio if args.radio else 0.8,
        colores_equipo=colores_equipo,
        max_edad_interp_s=args.max_edad_interp,
        min_vida_s=args.min_vida,
        largo=args.largo,
        ancho=args.ancho,
        max_hueco_s=args.max_hueco,
        titulo=args.titulo,
    )
    print(f"✓ Replay en {ruta}")


if __name__ == "__main__":
    main()
