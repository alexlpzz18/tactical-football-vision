#!/usr/bin/env python
"""¿VE el modelo el balón pegado al pie, aunque sea con confianza baja? (Colab, GPU)

docs/balon_en_vuelo.md: en 9 frames con el balón VISIBLE (GT de Alex) el caché
de producción no tiene ninguna caja del balón cerca. No es la fusión del
postproceso (el modelo del balón es aparte y no queda caja encima). Queda
saber si el modelo da una señal DÉBIL, por debajo de la confianza de
producción (0,35), o no da nada.

Corre el MISMO esquema que producción (`balon.esquema: mixto`, la misma franja
derivada de la homografía, el mismo postproceso de SAHI) sobre esos 9 frames,
dos veces:

1. **CONTROL**, a la confianza del config (0,35): tiene que reproducir el caché
   local (mismas cajas). Si no, la sesión de Colab no es producción y lo que
   salga a 0,05 no vale. ⚠️ Una herramienta que resume puede mentir sobre el
   sistema que diagnostica (CLAUDE.md).
2. **UMBRAL BAJO** (0,05): todas las cajas, con su confianza y su distancia a
   la posición del balón que marcó Alex (celda de 80 px: ±40 px de margen).

⚠️ Esto mide SOLO el beneficio en 9 frames. Si sale positivo, bajar el umbral
mete ruido en TODO el partido; el coste se mide aparte (celda 2 de
docs/colab_balon_umbral_bajo.md) antes de proponer nada.

Uso (Colab, desde la raíz del repo):
    python scripts/colab_balon_umbral_bajo.py \\
        --config configs/processor_benja_balon_parte_entera.yaml \\
        --salida /content/drive/MyDrive/tactical-football-vision-data/salidas/umbral_bajo
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Los 9 casos del GT de Alex (outputs/gt_balon_en_vuelo, 2-oct-2026): frame
# del vídeo, celdas de la rejilla de 80 px que marcó y, como CONTROL, las cajas
# que tiene el caché local de producción en ese frame (centro px, lado px).
CELDA_PX = 80
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWX"
CASOS = {
    "V03": (3780, ["O8", "P8"]),
    "V05": (4434, ["O8"]),
    "V06": (5276, ["H5"]),
    "V08": (11114, ["O8"]),
    "V12": (18850, ["N8"]),
    "V15": (21850, ["N8"]),
    "V16": (22818, ["U9", "V9"]),
    "V18": (27032, ["F8"]),  # visible pero BORROSO
    "V24": (32918, ["O8"]),
}
CACHE_LOCAL_N = {
    "V03": 2,
    "V05": 1,
    "V06": 0,
    "V08": 2,
    "V12": 0,
    "V15": 2,
    "V16": 2,
    "V18": 1,
    "V24": 0,
}
RADIO_BALON_PX = 60.0  # medio lado de celda (40) + holgura por el tamaño de la caja


def punto_de_celdas(celdas: list[str]) -> tuple[float, float]:
    """Centro (px) de una celda 'K7', o el punto medio si Alex dio dos ('O8/P8')."""
    pts = []
    for c in celdas:
        col, fila = LETRAS.index(c[0].upper()), int(c[1:])
        pts.append(((col + 0.5) * CELDA_PX, (fila - 0.5) * CELDA_PX))
    return tuple(np.mean(pts, axis=0))


def en_el_balon(cajas, punto, radio=RADIO_BALON_PX):
    """Cajas (x1, y1, x2, y2, conf) cuyo centro cae a ≤ radio del balón, con su distancia."""
    salida = []
    for x1, y1, x2, y2, conf in cajas:
        d = float(np.hypot((x1 + x2) / 2 - punto[0], (y1 + y2) / 2 - punto[1]))
        if d <= radio:
            salida.append(
                (round(d, 1), round(float(conf), 3), round(max(x2 - x1, y2 - y1), 1))
            )
    return sorted(salida)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config", default="configs/processor_benja_balon_parte_entera.yaml"
    )
    p.add_argument("--umbral", type=float, default=0.05)
    p.add_argument("--salida", required=True)
    args = p.parse_args()

    from sahi import AutoDetectionModel
    from ultralytics import YOLO

    from detectar_balon import _detectar_con_esquema, _esquema_de_config
    from src.balon.franja_lejana import banda_a_trocear

    cfg = yaml.safe_load(open(args.config))
    cb = cfg["balon"]
    nombre, esquema = _esquema_de_config(cb)
    if nombre != "mixto":
        raise SystemExit(f"El config usa el esquema {nombre!r}; producción es 'mixto'.")
    H = np.load(cfg["rutas"]["homografia"])
    cap = cv2.VideoCapture(cfg["rutas"]["video"])
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )
    banda = banda_a_trocear(
        H,
        float(cfg["campo_m"]["largo"]),
        float(cfg["campo_m"]["ancho"]),
        float(cb.get("zona_min_m", 45.0)),
        h,
        w,
        float(cb.get("margen_campo_m", 20.0)),
        float(cb.get("altura_aerea_m", 3.0)),
    )
    print(f"esquema {nombre} · franja troceada y {banda} (local: 534-805)")
    modelo = YOLO(cb["modelo"])

    def sahi(conf):
        return AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=cb["modelo"],
            confidence_threshold=conf,
            device=cfg["deteccion"]["device"],
        )

    sahi_prod, sahi_bajo = sahi(cb["confianza"]), sahi(args.umbral)
    cb_bajo = dict(cb, confianza=args.umbral)

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    resultado, pos, control_ok = {}, 0, True
    for caso, (frame_idx, celdas) in sorted(CASOS.items(), key=lambda x: x[1][0]):
        # Lectura SECUENCIAL hacia delante: el frame exacto (nunca cap.set).
        while pos < frame_idx:
            cap.grab()
            pos += 1
        ok, img = cap.read()
        pos += 1
        if not ok:
            raise RuntimeError(f"No se pudo leer el frame {frame_idx}")
        punto = punto_de_celdas(celdas)
        prod = _detectar_con_esquema(esquema, modelo, sahi_prod, img, cb, w, h, banda)
        bajo = _detectar_con_esquema(
            esquema, modelo, sahi_bajo, img, cb_bajo, w, h, banda
        )
        coincide = len(prod) == CACHE_LOCAL_N[caso]
        control_ok &= coincide
        cerca = en_el_balon(bajo, punto)
        resultado[caso] = {
            "frame": frame_idx,
            "balon_px": [round(v) for v in punto],
            "control_cajas_produccion": len(prod),
            "control_cajas_cache_local": CACHE_LOCAL_N[caso],
            "cajas_umbral_bajo": len(bajo),
            "en_el_balon": [
                {"dist_px": d, "conf": c, "lado_px": s} for d, c, s in cerca
            ],
        }
        print(
            f"{caso} f={frame_idx}: control {len(prod)} cajas (caché local "
            f"{CACHE_LOCAL_N[caso]}) {'OK' if coincide else '⚠️ NO COINCIDE'} · a "
            f"{args.umbral}: {len(bajo)} cajas · EN EL BALÓN: "
            + (
                ", ".join(f"conf {c} a {d} px ({s} px)" for d, c, s in cerca)
                or "NINGUNA"
            )
        )
        vis = img.copy()
        cv2.circle(
            vis, (int(punto[0]), int(punto[1])), int(RADIO_BALON_PX), (0, 255, 255), 2
        )
        for x1, y1, x2, y2, conf in bajo:
            col = (0, 0, 255) if conf >= cb["confianza"] else (255, 0, 255)
            cv2.rectangle(
                vis, (int(x1) - 3, int(y1) - 3), (int(x2) + 3, int(y2) + 3), col, 2
            )
            cv2.putText(
                vis,
                f"{conf:.2f}",
                (int(x2) + 4, int(y1)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                col,
                2,
            )
        x0 = int(np.clip(punto[0] - 240, 0, w - 480))
        y0 = int(np.clip(punto[1] - 135, 0, h - 270))
        y1, x1 = y0 + 270, x0 + 480
        recorte = cv2.resize(vis[y0:y1, x0:x1], (960, 540))
        cv2.imwrite(str(salida / f"{caso}.jpg"), recorte)

    (salida / "resultado.json").write_text(json.dumps(resultado, indent=1))
    con_balon = [c for c, r in resultado.items() if r["en_el_balon"]]
    print(
        f"\nCONTROL contra el caché local: {'OK' if control_ok else '⚠️ FALLA, no fiarse'}"
    )
    print(
        f"casos con alguna caja a umbral {args.umbral} sobre el balón: {len(con_balon)} de "
        f"{len(CASOS)} {con_balon}"
    )
    print(f"✓ recortes y resultado.json en {salida}")


if __name__ == "__main__":
    main()
