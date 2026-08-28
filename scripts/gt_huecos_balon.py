#!/usr/bin/env python
"""Tiras de frames alrededor de una pérdida de balón, para anotarlas a mano.

Idea de Alex (28-ago-2026), mejorada: *"enséñame un frame donde se ve el
balón y el siguiente donde no se ve, así te digo exactamente dónde
tendría que estar de verdad"*.

⚠️ POR QUÉ ESTO Y NO LO ANTERIOR. El primer intento pintaba una cruz en
la posición INTERPOLADA en el medio del hueco. Es inservible por dos
motivos que Alex vio antes que yo: en 4-5 s el balón hace lo que quiere,
así que una recta entre "última vez visto" y "vuelve a verse" no dice
nada; y la homografía inversa supone el balón EN EL SUELO, así que si iba
por el aire el píxel está desplazado decenas de metros. Sus palabras:
*"viendo a dónde están mirando todos los jugadores no tiene ninguna pinta
de que el balón esté donde tú has interpolado"*.

Lo que hace esta versión:

- **Ancla en el último frame CON balón**, no en el medio del hueco. En
  los frames inmediatamente siguientes el balón todavía tiene que estar
  cerca, así que la ventana de recorte se mantiene FIJA y el ojo compara.
- **No inventa ninguna posición.** En los frames sin balón no hay cruz:
  solo una marca tenue de dónde se vio por última vez, etiquetada como
  tal.
- **Rejilla con celdas nombradas**, para que la anotación sea precisa:
  "en el frame +2 el balón está en la C3".

Uso:
    python scripts/gt_huecos_balon.py --casos 4 --despues 3
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("gt_huecos")

# Ventana de recorte alrededor de la última posición vista. Generosa: en
# 0,1-0,3 s el balón no se va de aquí ni con un disparo.
ANCHO, ALTO = 900, 620
CELDA = 4  # rejilla CELDA x CELDA


def rejilla(img):
    """Dibuja una rejilla con celdas nombradas A1..D4."""
    h, w = img.shape[:2]
    for i in range(1, CELDA):
        cv2.line(img, (w * i // CELDA, 0), (w * i // CELDA, h), (90, 90, 90), 1)
        cv2.line(img, (0, h * i // CELDA), (w, h * i // CELDA), (90, 90, 90), 1)
    for f in range(CELDA):
        for c in range(CELDA):
            cv2.putText(
                img,
                f"{chr(65+f)}{c+1}",
                (w * c // CELDA + 6, h * f // CELDA + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (120, 120, 120),
                1,
            )
    return img


def main():
    import pickle

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--balon", default="data/tracking_benja/cache_balon_p1.pkl")
    p.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument("--casos", type=int, default=4)
    p.add_argument("--despues", type=int, default=3, help="frames tras la pérdida")
    p.add_argument("--salida", default="outputs/gt_huecos")
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    from src.balon.tracking_balon import filtrar_balon_plausible
    from src.campo_modelo import cargar_modelo

    modelo = cargar_modelo(config=args.campo)
    with open(args.balon, "rb") as f:
        datos = pickle.load(f)
    dets = filtrar_balon_plausible(
        {e["frame_idx"]: e["dets"] for e in datos["cache"] if e["dets"]}, modelo
    )
    tiempos = {e["frame_idx"]: e["t"] for e in datos["cache"]}
    sample = datos["sample"]
    vistos = sorted(dets)

    # Huecos que empiezan en la portería cercana (x < 20 m).
    casos = []
    for a, b in zip(vistos, vistos[1:]):
        dt = tiempos[b] - tiempos[a]
        if 1.0 < dt < 8.0 and float(dets[a][0][0]) < 20.0:
            casos.append((a, b, dt))
    casos.sort(key=lambda c: -c[2])
    paso = max(len(casos) // args.casos, 1)
    elegidos = casos[::paso][: args.casos]
    print(
        f"huecos en la portería cercana: {len(casos)}; se muestran " f"{len(elegidos)}"
    )

    # Frames a leer: el último CON balón y los N siguientes SIN.
    pedidos = {}
    for a, b, dt in elegidos:
        secuencia = [a] + [a + sample * (i + 1) for i in range(args.despues)]
        for f in secuencia:
            pedidos.setdefault(f, []).append(a)

    cap = cv2.VideoCapture(args.video)
    objetivo = set(pedidos)
    cargados, n = {}, 0
    while cargados.keys() != objetivo:
        ok, img = cap.read()
        if not ok:
            break
        if n in objetivo:
            cargados[n] = img.copy()
        n += 1
        if n > max(objetivo) + 2:
            break
    cap.release()
    print(f"frames leídos: {len(cargados)} de {len(objetivo)}")

    Path(args.salida).mkdir(parents=True, exist_ok=True)
    for a, b, dt in elegidos:
        det = dets[a][0]
        cx = int((det[2] + det[4]) / 2)
        cy = int((det[3] + det[5]) / 2)
        img0 = cargados.get(a)
        if img0 is None:
            continue
        H, W = img0.shape[:2]
        x1 = max(min(cx - ANCHO // 2, W - ANCHO), 0)
        y1 = max(min(cy - ALTO // 2, H - ALTO), 0)
        tiras = []
        for i, f in enumerate(
            [a] + [a + sample * (k + 1) for k in range(args.despues)]
        ):
            img = cargados.get(f)
            if img is None:
                continue
            y2, x2 = y1 + ALTO, x1 + ANCHO
            rec = img[y1:y2, x1:x2].copy()
            rejilla(rec)
            if i == 0:
                # el ÚNICO sitio donde se marca algo: aquí SÍ se detectó
                cv2.rectangle(
                    rec,
                    (int(det[2]) - x1 - 14, int(det[3]) - y1 - 14),
                    (int(det[4]) - x1 + 14, int(det[5]) - y1 + 14),
                    (0, 255, 0),
                    2,
                )
                etq = "SE VE (detectado aqui)"
                color = (0, 255, 0)
            else:
                # marca TENUE de dónde estaba, etiquetada como tal.
                # No es una prediccion: es el ultimo sitio conocido.
                cv2.circle(rec, (cx - x1, cy - y1), 26, (0, 140, 190), 1)
                etq = f"NO se detecta (+{i} muestra, {i*sample/datos['fps']:.2f}s)"
                color = (0, 170, 220)
            barra = np.zeros((40, ANCHO, 3), np.uint8) + 26
            cv2.putText(barra, etq, (8, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2)
            tiras.append(np.vstack([rec, barra]))
        if not tiras:
            continue
        fila = np.hstack(tiras)
        cab = np.zeros((44, fila.shape[1], 3), np.uint8) + 26
        cv2.putText(
            cab,
            f"t={tiempos[a]:.0f}s  hueco de {dt:.1f}s  "
            f"(el circulo naranja = ULTIMO sitio visto, NO una prediccion)",
            (8, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (235, 235, 235),
            2,
        )
        ruta = f"{args.salida}/hueco_t{int(tiempos[a]):04d}s.png"
        cv2.imwrite(ruta, np.vstack([cab, fila]))
        print(f"  {ruta}")


if __name__ == "__main__":
    main()
