#!/usr/bin/env python
"""Herramienta de clics para medir la LENTE sobre el fotograma ORIGINAL. docs/lente_f11.md.

HTML autocontenido: los fotogramas sin corregir de los dos partidos (alevín y cadete, alineados a
menos de 0,5 px) y dos fases de clics:
1. **cruces** de medidas conocidas (esquinas, áreas, medio campo, postes, penaltis);
2. **líneas rectas**: 3-5 puntos por línea, sin saber a qué metro caen.

No ajusta nada en el navegador: exporta `clics_lente_villaviciosa.json`, que lee
`scripts/lente_camara.py ajustar`.

Uso:
    python scripts/herramienta_lente.py --salida outputs/lente_f11/clics.html
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import cv2

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.campo_modelo import cargar_modelo  # noqa: E402

LARGO, ANCHO = 100.0, 64.0  # las de producción de Villaviciosa, nunca medidas
FRAMES = (
    ("alevín (minuto 5)", R / "data/calibracion_villa_cadete/frame_alevin_crudo.png"),
    (
        "cadete (descanso, campo vacío)",
        R / "data/calibracion_villa_cadete/frame_crudo.png",
    ),
)
MIN_CRUCES, MIN_POR_LINEA, MAX_POR_LINEA = 6, 3, 5
TEXTOS = {
    "corner_bottom_left": "ESQUINA cercana izquierda",
    "corner_bottom_right": "ESQUINA cercana derecha",
    "corner_top_left": "ESQUINA lejana izquierda",
    "corner_top_right": "ESQUINA lejana derecha",
    "halfway_top": "MEDIO CAMPO con la banda LEJANA",
    "halfway_bottom": "MEDIO CAMPO con la banda CERCANA",
    "box_left_top": "ÁREA izquierda, esquina lejana (la que está en el campo)",
    "box_left_bottom": "ÁREA izquierda, esquina cercana (la que está en el campo)",
    "box_right_top": "ÁREA derecha, esquina lejana (la que está en el campo)",
    "box_right_bottom": "ÁREA derecha, esquina cercana (la que está en el campo)",
    "box_left_top_line": "ÁREA izquierda, corte lejano con la línea de fondo",
    "box_left_bottom_line": "ÁREA izquierda, corte cercano con la línea de fondo",
    "box_right_top_line": "ÁREA derecha, corte lejano con la línea de fondo",
    "box_right_bottom_line": "ÁREA derecha, corte cercano con la línea de fondo",
    "goal_left_top": "POSTE izquierdo lejano, en su base",
    "goal_left_bottom": "POSTE izquierdo cercano, en su base",
    "goal_right_top": "POSTE derecho lejano, en su base",
    "goal_right_bottom": "POSTE derecho cercano, en su base",
    "penalty_left": "PUNTO DE PENALTI izquierdo",
    "penalty_right": "PUNTO DE PENALTI derecho",
    "center": "CENTRO del campo",
    "circulo_top": "CÍRCULO con el medio campo, lado lejano",
    "circulo_bottom": "CÍRCULO con el medio campo, lado cercano",
}
ORDEN = tuple(TEXTOS)


def lineas_rectas(modelo) -> list[dict]:
    """Líneas rectas del campo, con sus extremos en metros."""
    L, W, m = modelo.largo, modelo.ancho, modelo.marcas
    cy, media = W / 2, m.area_ancho / 2
    y0, y1 = cy - media, cy + media
    x0, x1 = m.area_profundidad, L - m.area_profundidad
    filas = [
        ("banda_lejana", "BANDA LEJANA", (0, W), (L, W)),
        ("banda_cercana", "BANDA CERCANA (solo donde se vea)", (0, 0), (L, 0)),
        ("fondo_izquierda", "LÍNEA DE FONDO izquierda", (0, 0), (0, W)),
        ("fondo_derecha", "LÍNEA DE FONDO derecha", (L, 0), (L, W)),
        ("medio_campo", "LÍNEA DE MEDIO CAMPO", (L / 2, 0), (L / 2, W)),
        ("area_izq_frontal", "ÁREA izquierda, lado frontal", (x0, y0), (x0, y1)),
        ("area_izq_lejana", "ÁREA izquierda, lado lejano", (0, y1), (x0, y1)),
        ("area_izq_cercana", "ÁREA izquierda, lado cercano", (0, y0), (x0, y0)),
        ("area_der_frontal", "ÁREA derecha, lado frontal", (x1, y0), (x1, y1)),
        ("area_der_lejana", "ÁREA derecha, lado lejano", (x1, y1), (L, y1)),
        ("area_der_cercana", "ÁREA derecha, lado cercano", (x1, y0), (L, y0)),
    ]
    return [
        {
            "nombre": n,
            "texto": t,
            "a": [float(v) for v in a],
            "b": [float(v) for v in b],
        }
        for n, t, a, b in filas
    ]


def cruces_ordenados(modelo) -> list[dict]:
    pts = dict(modelo.puntos_clicables())
    return [
        {"nombre": n, "metros": list(pts[n]), "texto": TEXTOS[n]}
        for n in ORDEN
        if n in pts
    ]


def generar(salida: Path, calidad: int = 90) -> Path:
    modelo = cargar_modelo("f11").con_dimensiones(LARGO, ANCHO)
    frames = []
    for nombre, ruta in FRAMES:
        img = cv2.imread(str(ruta))
        if img is None:
            raise SystemExit(f"No se pudo leer {ruta}")
        _ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, calidad])
        frames.append(
            {
                "nombre": nombre,
                "dato": "data:image/jpeg;base64," + base64.b64encode(buf).decode(),
            }
        )
    plantilla = (R / "scripts/plantillas/lente.html").read_text(encoding="utf-8")
    html = (
        plantilla.replace("__FRAMES__", json.dumps(frames))
        .replace("__CRUCES__", json.dumps(cruces_ordenados(modelo), ensure_ascii=False))
        .replace("__LINEAS__", json.dumps(lineas_rectas(modelo), ensure_ascii=False))
        .replace("__LARGO__", str(modelo.largo))
        .replace("__ANCHO__", str(modelo.ancho))
        .replace(
            "__GEOMETRIA__", json.dumps({"lineas": modelo.geometria_dibujo()["lineas"]})
        )
        .replace("__MIN_CRUCES__", str(MIN_CRUCES))
        .replace("__MIN_POR_LINEA__", str(MIN_POR_LINEA))
        .replace("__MAX_POR_LINEA__", str(MAX_POR_LINEA))
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", type=Path, default=R / "outputs/lente_f11/clics.html")
    ap.add_argument("--calidad", type=int, default=90)
    a = ap.parse_args()
    r = generar(a.salida, a.calidad)
    print(f"✓ {r} ({r.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
