#!/usr/bin/env python
"""Herramienta MÍNIMA de clics para la máscara de zona de juego del balón (`balon.mascara_zona`).

docs/diagnostico_23oct_f.md, bloque 2. Se marca un polígono en PÍXELES sobre un frame: lo que
queda DENTRO es donde puede estar el balón del partido. La idea es seguir el borde superior de la
grada (por encima está el campo de al lado) y cerrar por el resto del perímetro de la imagen que
ve el juego. 6-8 clics bastan.

⚠️ El polígono NO se ajusta a las candidatas etiquetadas: se marca mirando la IMAGEN. Las etiquetas
del 23-oct (e) solo sirven para MEDIRLO después.

Teclas:
    clic izquierdo   añade un vértice
    z                deshace el último
    Enter            guarda y sale
    Esc              sale sin guardar

Uso:
    # 1) sacar un frame del vídeo con el decodificador de producción (una vez)
    python scripts/marcar_mascara_zona.py frame
    # 2) marcar
    python scripts/marcar_mascara_zona.py marcar
    # 2b) y escribirlo directamente en configs/campo_benja.yaml
    python scripts/marcar_mascara_zona.py marcar --escribir-yaml
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
VIDEO = R / "data/raw/benja_gredos_p1_20min.mp4"
FRAME = R / "data/calibracion_benja/frame_mascara.png"
SALIDA = R / "data/calibracion_benja/mascara_zona_benja.json"
CAMPO = R / "configs/campo_benja.yaml"
# Un frame con el balón del campo de al lado a la vista y la grada despejada (5:10,5 archivo /
# 6:43,5 reproductor). Solo es el fondo sobre el que se marca: cualquier frame vale.
FRAME_EJEMPLO = 9306


def sacar_frame() -> None:
    import cv2

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    _f, img = next(leer_frames_ffmpeg(VIDEO, [FRAME_EJEMPLO]))
    FRAME.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(FRAME), img)
    print(f"✓ {FRAME} (frame {FRAME_EJEMPLO})")


def escribir_en_yaml(poligono: list) -> None:
    """Sustituye la línea `mascara_zona: ...` del bloque balon: (conserva los comentarios)."""
    texto = CAMPO.read_text()
    linea = f"  mascara_zona: {json.dumps(poligono)}"
    nuevo, n = re.subn(r"^  mascara_zona:.*$", linea, texto, count=1, flags=re.M)
    if n != 1:
        raise RuntimeError(f"No encuentro `mascara_zona:` en {CAMPO}")
    CAMPO.write_text(nuevo)
    print(f"✓ escrito en {CAMPO}")


def marcar(escribir_yaml: bool) -> None:
    import cv2

    if not FRAME.exists():
        sacar_frame()
    base = cv2.imread(str(FRAME))
    puntos: list[list[int]] = []
    ventana = (
        "mascara de zona: clic = vertice, z = deshacer, Enter = guardar, Esc = salir"
    )

    def raton(evento, x, y, _flags, _param):
        if evento == cv2.EVENT_LBUTTONDOWN:
            puntos.append([int(x), int(y)])

    cv2.namedWindow(ventana, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(ventana, raton)
    while True:
        img = base.copy()
        for i, p in enumerate(puntos):
            cv2.circle(img, tuple(p), 6, (0, 255, 255), -1)
            cv2.putText(img, str(i + 1), (p[0] + 8, p[1] - 8), 0, 0.8, (0, 255, 255), 2)
        if len(puntos) >= 2:
            cv2.polylines(img, [np.array(puntos)], len(puntos) >= 3, (0, 255, 255), 2)
        cv2.imshow(ventana, img)
        tecla = cv2.waitKey(30) & 0xFF
        if tecla == ord("z") and puntos:
            puntos.pop()
        elif tecla == 27:
            print("Salgo sin guardar.")
            break
        elif tecla in (13, 10):
            if len(puntos) < 3:
                print("Hacen falta al menos 3 vértices.")
                continue
            SALIDA.write_text(
                json.dumps({"frame": FRAME_EJEMPLO, "poligono": puntos}, indent=1)
            )
            print(f"✓ {len(puntos)} vértices en {SALIDA}")
            print(f"  mascara_zona: {json.dumps(puntos)}")
            if escribir_yaml:
                escribir_en_yaml(puntos)
            break
    cv2.destroyAllWindows()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["frame", "marcar"])
    ap.add_argument("--escribir-yaml", action="store_true")
    args = ap.parse_args()
    if args.accion == "frame":
        sacar_frame()
    else:
        marcar(args.escribir_yaml)


if __name__ == "__main__":
    main()
