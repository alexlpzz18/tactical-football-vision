#!/usr/bin/env python
"""Comparación CONGELADA de un instante: vídeo real ↔ replay.

Herramienta de diagnóstico para responder a la pregunta que ninguna
métrica agregada contesta: cuando el replay "se ve mal", ¿es que la
identidad está mal, o es que la posición proyectada está mal?

Para un frame concreto pinta, lado a lado:

  - IZQUIERDA: el fotograma REAL del vídeo con las cajas CRUDAS del caché
    (píxeles exactos del detector, cero homografía) y el punto de apoyo
    marcado, que es lo único que se proyecta a metros.
  - DERECHA: el replay de ESE MISMO frame — las fichas del CSV sobre el
    modelo de campo, con su id.

Y una tabla por jugador visible con su posición proyectada en metros, los
metros-por-píxel de su zona y la incertidumbre que eso implica: un
jugador al fondo puede estar perfectamente detectado y aun así aparecer
en el replay a varios metros de donde está.

Uso:
    python scripts/comparar_instante.py --config configs/processor_benja.yaml \\
        --csv data/tracking_benja/posiciones_benja.csv \\
        --config-campo configs/campo_benja.yaml \\
        --segundos 11 15 58 --salida outputs/diagnostico
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.campo_modelo import cargar_modelo  # noqa: E402
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.resolucion import ResolucionCampo  # noqa: E402
from src.tracking_data.processor import (  # noqa: E402
    _rango_de_frames,
    posicionar_en_frame,
)

logger = logging.getLogger("comparar_instante")

COLORES_EQUIPO = {
    "A": "#3b82f6",
    "B": "#ef4444",
    "portero_A": "#1e3a8a",
    "portero_B": "#7f1d1d",
    "staff": "#9ca3af",
    "otro": "#9ca3af",
}


def _paleta_real(ruta_csv):
    """Colores REALES de equipo del meta que acompaña al CSV.

    Con el convenio azul/rojo no se puede juzgar si un portero está
    pintado del equipo correcto: hay que verlo con el color de la
    camiseta que el clasificador dedujo.
    """
    import json

    meta = Path(str(Path(ruta_csv).with_suffix("")) + "_meta.json")
    if not meta.exists():
        return dict(COLORES_EQUIPO)
    reales = json.loads(meta.read_text()).get("colores_equipo") or {}
    paleta = dict(COLORES_EQUIPO)
    for equipo in ("A", "B"):
        if equipo in reales:
            paleta[equipo] = reales[equipo]
            paleta[f"portero_{equipo}"] = reales[equipo]
    return paleta


def _leer_frame(ruta_video, frame_idx):
    """El fotograma exacto (con el posicionamiento verificado)."""
    cap = cv2.VideoCapture(str(ruta_video))
    if not cap.isOpened():
        raise FileNotFoundError(f"No se puede abrir {ruta_video}")
    posicionar_en_frame(cap, frame_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"No se pudo leer el frame {frame_idx}")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def _dibujar_campo(ax, modelo):
    g = modelo.geometria_dibujo()
    for (x1, y1), (x2, y2) in g["lineas"]:
        ax.plot([x1, x2], [y1, y2], color="#94a3b8", lw=1.0, zorder=1)
    for c in g["circulos"]:
        ax.add_patch(
            plt.Circle(
                (c["cx"], c["cy"]),
                c["r"],
                fill=False,
                color="#94a3b8",
                lw=1.0,
                zorder=1,
            )
        )
    for x, y in g["puntos"]:
        ax.plot(x, y, ".", color="#94a3b8", ms=3, zorder=1)


def comparar(
    frame_idx, cache_dets, df, modelo, resolucion, ruta_video, dt, salida, paleta=None
):
    """Genera el PNG del instante y devuelve la tabla por jugador."""
    frame = _leer_frame(ruta_video, frame_idx)
    dets = cache_dets.get(frame_idx, [])
    fichas = df[df.frame == frame_idx]

    fig, (izq, der) = plt.subplots(
        1, 2, figsize=(19, 5.6), gridspec_kw={"width_ratios": [1.55, 1]}
    )

    # ── izquierda: vídeo real + cajas crudas ──
    izq.imshow(frame)
    for mx, my, x1, y1, x2, y2, _conf in dets:
        # La ficha del CSV más cercana a esta detección (solo para el color)
        etiqueta = "otro"
        if len(fichas):
            d2 = (fichas.x_m - mx) ** 2 + (fichas.y_m - my) ** 2
            if d2.min() <= 4.0:
                etiqueta = fichas.loc[d2.idxmin(), "etiqueta"]
        color = (paleta or COLORES_EQUIPO).get(etiqueta, "#22c55e")
        izq.add_patch(
            plt.Rectangle(
                (x1, y1), x2 - x1, y2 - y1, fill=False, ec=color, lw=1.4, zorder=2
            )
        )
        # El punto de apoyo: lo ÚNICO que se proyecta a metros
        izq.plot((x1 + x2) / 2, y2, "x", color=color, ms=7, mew=1.8, zorder=3)
    izq.set_title(
        f"Vídeo real — frame {frame_idx} (t={frame_idx / 29.97:.1f} s) — "
        f"{len(dets)} cajas crudas del caché",
        fontsize=10,
    )
    izq.axis("off")

    # ── derecha: el replay de ESE frame ──
    _dibujar_campo(der, modelo)
    for f in fichas.itertuples():
        color = (paleta or COLORES_EQUIPO).get(f.etiqueta, "#22c55e")
        der.plot(
            f.x_m,
            f.y_m,
            "o",
            color=color,
            ms=9,
            mec="white",
            mew=1.0,
            zorder=3,
            alpha=1.0 if f.es_real else 0.45,
        )
        der.annotate(
            str(f.id_jugador),
            (f.x_m, f.y_m),
            fontsize=6.5,
            color="#111",
            ha="center",
            va="center",
            zorder=4,
        )
    der.set_xlim(-3, modelo.largo + 3)
    der.set_ylim(-3, modelo.ancho + 3)
    der.set_aspect("equal")
    der.set_title(
        f"Replay del MISMO frame — {len(fichas)} fichas "
        f"({int(fichas.es_real.sum())} reales)",
        fontsize=10,
    )
    der.set_xlabel("x (m) — se aleja de la cámara")
    der.set_ylabel("y (m)")

    fig.tight_layout()
    fig.savefig(salida, dpi=110)
    plt.close(fig)

    # ── tabla por jugador ──
    filas = []
    for mx, my, x1, y1, x2, y2, conf in dets:
        mpp = resolucion.metros_por_pixel((mx, my)) if resolucion else float("nan")
        id_j, etiqueta = None, None
        if len(fichas):
            d2 = (fichas.x_m - mx) ** 2 + (fichas.y_m - my) ** 2
            if d2.min() <= 4.0:
                fila = fichas.loc[d2.idxmin()]
                id_j, etiqueta = int(fila.id_jugador), fila.etiqueta
        filas.append(
            {
                "id": id_j,
                "equipo": etiqueta,
                "x_m": mx,
                "y_m": my,
                "alto_px": y2 - y1,
                "m_por_px": mpp,
                # Incertidumbre de la posición por el jitter medido de la caja
                "±m": 3.5 * mpp,
                "conf": conf,
            }
        )
    return pd.DataFrame(filas).sort_values("x_m")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--config-campo", default=None)
    parser.add_argument("--campo", default=None)
    parser.add_argument(
        "--segundos",
        type=float,
        nargs="+",
        required=True,
        help="Instantes del MP4 de diagnóstico (su reloj, no el del partido)",
    )
    parser.add_argument("--salida", default="outputs/diagnostico")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    datos = cargar_cache(cfg["rutas"]["cache"])
    cache_dets = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
    df = pd.read_csv(args.csv)
    modelo = cargar_modelo(
        nombre=None if args.config_campo else (args.campo or "f11"),
        config=args.config_campo,
    )
    resolucion = ResolucionCampo(
        np.load(cfg["rutas"]["homografia"]), modelo.largo, modelo.ancho
    )
    fps = datos["fps"]
    sample = datos["sample"]
    frame_ini, _ = _rango_de_frames(cfg["muestreo"], fps)
    dt = sample / fps

    Path(args.salida).mkdir(parents=True, exist_ok=True)
    for seg in args.segundos:
        # El MP4 va a fps/sample, así que su segundo `seg` es el frame
        # `seg · fps/sample` del caché.
        indice = int(round(seg * fps / sample))
        frame_idx = frame_ini + indice * sample
        if frame_idx not in cache_dets:
            frame_idx = min(cache_dets, key=lambda f: abs(f - frame_idx))
        png = Path(args.salida) / f"instante_{seg:g}s.png"
        tabla = comparar(
            frame_idx,
            cache_dets,
            df,
            modelo,
            resolucion,
            cfg["rutas"]["video"],
            dt,
            png,
            paleta=_paleta_real(args.csv),
        )
        print(f"\n{'=' * 78}\n  t={seg:g}s   frame {frame_idx}   →  {png}\n{'=' * 78}")
        print(
            tabla.to_string(
                index=False,
                float_format=lambda v: f"{v:.2f}",
                na_rep="—",
            )
        )
        lejos = tabla[tabla.x_m > 35]
        print(
            f"\n  cajas: {len(tabla)} · con identidad: {tabla.id.notna().sum()} · "
            f"en la mitad lejana (x>35): {len(lejos)}"
        )
        if len(lejos):
            print(
                f"  incertidumbre de posición en esa mitad lejana: "
                f"±{lejos['±m'].median():.2f} m (mediana), "
                f"±{lejos['±m'].max():.2f} m (peor)"
            )


if __name__ == "__main__":
    main()
