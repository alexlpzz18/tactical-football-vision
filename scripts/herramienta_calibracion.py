#!/usr/bin/env python
"""Herramienta de CALIBRACIÓN SEMIAUTOMÁTICA: 6 clics guiados → homografía (HTML).

Sale de `docs/calibracion_semiautomatica.md`: con 6 puntos bien elegidos la homografía vale
lo que la de 19 clics, y con 4 no es fiable (un clic malo no tiene quien lo corrija).
El HTML es autocontenido (el frame va embebido en base64), como las herramientas de GT:

1. Pide los puntos del modelo parametrizado (`src/campo_modelo.py`, F7 u F11), uno a uno,
   con un dibujo del campo que señala cuál toca. Orden: esquinas, medio campo, áreas,
   penaltis, postes; el centro y el círculo al final (en las dos patas medidas, ESTROPEAN).
   Cualquiera se puede saltar si no se ve.
2. Con 4 puntos calcula una homografía provisional, dibuja el campo encima del frame y
   propone el siguiente: el visible que más agranda la envolvente de los clics (regla R1),
   lejos del borde. Avisa si un clic cae a < 30 px del borde.
3. No exporta con menos de 6 puntos. No da un "válido/no válido" automático: ninguno de
   los validadores medidos lo merece (AUC < 0,80 en algún campo). La validación es VISUAL
   (el campo dibujado encima) y, como ayuda, el error de cada clic predicho por los
   demás.
4. Descarga `puntos_marcados_<campo>.json` (el formato de `calcular_homografia.py`) y la
   homografía píxel → metros.

No se integra en el pipeline.

Uso:
    python scripts/herramienta_calibracion.py --config configs/campo_benja.yaml \\
        --frame data/calibracion_benja/frame.png --salida outputs/calibrar_benja.html
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.campo_modelo import cargar_modelo  # noqa: E402

MIN_PUNTOS = 6
BORDE_PX = 30
# Orden de petición, por TIPO de punto (prefijos de puntos_clicables). Medido en
# docs/calibracion_semiautomatica.md: los puntos del círculo y el centro estropean en los
# dos campos; las esquinas del campo y del área ayudan.
ORDEN = (
    "corner_", "halfway_", "box_left_top_line", "box_left_bottom_line",
    "box_right_top_line", "box_right_bottom_line", "box_", "penalty_", "goal_",
    "center", "circulo_",
)  # fmt: skip

# Homografía por DLT normalizada (Hartley) + refinado del error de reproyección, en un .js
# aparte para poder probarla con node contra OpenCV (tests/test_herramienta_calibracion.py).
PLANTILLAS = Path(__file__).resolve().parent / "plantillas"
JS_HOMOGRAFIA = (PLANTILLAS / "homografia.js").read_text(encoding="utf-8")

PLANTILLA = (PLANTILLAS / "calibracion.html").read_text(encoding="utf-8")

TEXTOS = {
    "center": "el CENTRO del campo",
    "halfway_top": "el corte de la línea de MEDIO CAMPO con la banda de arriba",
    "halfway_bottom": "el corte de la línea de MEDIO CAMPO con la banda de abajo",
    "penalty_left": "el punto de PENALTI izquierdo",
    "penalty_right": "el punto de PENALTI derecho",
}


def texto_de(nombre: str) -> str:
    """Descripción para el usuario: la de TEXTOS o una derivada del nombre."""
    if nombre in TEXTOS:
        return TEXTOS[nombre]
    partes = {
        "corner": "la ESQUINA del campo",
        "box": "la esquina del ÁREA",
        "goal": "la base del POSTE",
        "circulo": "el corte del CÍRCULO central",
    }
    tipo = nombre.split("_")[0]
    lado = " ".join(
        p for p in nombre.split("_")[1:] if p in ("left", "right", "top", "bottom")
    )
    lado = lado.replace("left", "izquierda").replace("right", "derecha")
    lado = lado.replace("top", "arriba").replace("bottom", "abajo")
    linea = " (sobre la línea de fondo)" if nombre.endswith("_line") else ""
    return f"{partes.get(tipo, nombre)} {lado}{linea}".strip()


def puntos_ordenados(modelo) -> list[dict]:
    """Puntos del modelo en el orden de petición (por tipo; dentro, el orden del modelo)."""
    pts = modelo.puntos_clicables()

    def rango(nombre):
        for i, pref in enumerate(ORDEN):
            if nombre.startswith(pref):
                return i
        return len(ORDEN)

    pts = sorted(pts, key=lambda p: rango(p[0]))
    return [{"nombre": n, "metros": list(m), "texto": texto_de(n)} for n, m in pts]


def generar(config: str, frame: str, salida: str) -> Path:
    modelo = cargar_modelo(config=config)
    img = cv2.imread(frame)
    if img is None:
        raise SystemExit(f"No se pudo leer el frame {frame}")
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    dato = "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")
    geo = modelo.geometria_dibujo()
    campo = {"largo": modelo.largo, "ancho": modelo.ancho, "lineas": geo["lineas"],
             "circulos": geo["circulos"]}  # fmt: skip
    html = (
        PLANTILLA.replace("__JS_HOMOGRAFIA__", JS_HOMOGRAFIA)
        .replace("__MODELO__", json.dumps(campo))
        .replace("__PUNTOS__", json.dumps(puntos_ordenados(modelo), ensure_ascii=False))
        .replace("__MIN__", str(MIN_PUNTOS))
        .replace("__BORDE__", str(BORDE_PX))
        .replace("__CAMPO__", modelo.nombre)
        .replace("__FRAME__", dato)
    )
    ruta = Path(salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(html, encoding="utf-8")
    return ruta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config",
        required=True,
        help="config de campo (p. ej. configs/campo_benja.yaml)",
    )
    ap.add_argument("--frame", required=True, help="un frame nítido del partido")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    r = generar(a.config, a.frame, a.salida)
    print(f"✓ {r} ({r.stat().st_size / 1e6:.1f} MB). Ábrelo en el navegador.")


if __name__ == "__main__":
    main()
