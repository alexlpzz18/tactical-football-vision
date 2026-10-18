#!/usr/bin/env python
"""Altura mediana de los jugadores en un vídeo nuevo, con el detector (Colab, GPU).

docs/plan_generalizacion_f11.md, paso 1: lo barato antes de procesar un tramo. Para cada
vídeo, `--n` frames repartidos (sin el 3 % inicial ni el final), leídos con
`posicionar_en_frame()`; el detector de jugadores con el SAHI de producción; y la altura de las
cajas CON EL PIE SOBRE EL CÉSPED (si no, entra el público de la grada cercana). Se mide en bruto y
con la corrección de distorsión de Villaviciosa (hipótesis: parece la misma cámara).

Deja en `--salida` un JSON con todo y los frames corregidos (JPEG), para elegir después el de
calibrar.

Uso (Colab, raíz del repo):
    python scripts/colab_altura_jugadores.py --videos "$D/videos/raw/advdo_bazan_p1.mp4" ... \\
        --salida "$D/salidas/generalizacion_f11"
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

PREDICCION = ((40.0, "sirve de pata"), (30.0, "intermedio (~86 % de color)"),
              (0.0, "no aporta (como Villaviciosa, 26 px)"))  # fmt: skip


def pie_en_cesped(cajas, region) -> list:
    """Las cajas cuyo pie (centro del borde inferior) cae dentro de la región del césped."""
    h, w = region.shape[:2]
    salida = []
    for x1, y1, x2, y2 in cajas:
        px, py = int((x1 + x2) / 2), int(y2) - 2
        if 0 <= px < w and 0 <= py < h and region[py, px] > 0:
            salida.append((x1, y1, x2, y2))
    return salida


def resumen(alturas: list[float]) -> dict:
    if not alturas:
        return {"n": 0}
    a = np.asarray(alturas, float)
    return {
        "n": int(len(a)),
        "mediana": float(np.median(a)),
        "p10": float(np.percentile(a, 10)),
        "p90": float(np.percentile(a, 90)),
        "frac_menor_25": float((a < 25).mean()),
    }


def lectura(mediana: float | None) -> str:
    if mediana is None:
        return "sin cajas"
    return next(txt for umbral, txt in PREDICCION if mediana >= umbral)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--videos", nargs="+", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--modelo", default="models/weights/best_v4pre.pt")
    ap.add_argument(
        "--config-lente", default="configs/processor.yaml", help="k1/k2 de Villa"
    )
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()

    import cv2
    import yaml
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction

    from src.tracking_data.processor import (
        _build_camera_matrix,
        _corregir_distorsion,
        posicionar_en_frame,
    )
    from src.validacion_video import mascara_cesped

    lente = yaml.safe_load(open(args.config_lente))["distorsion"]
    dist = np.array([lente["k1"], lente["k2"], 0, 0, 0], float)
    modelo = AutoDetectionModel.from_pretrained(
        model_type="ultralytics", model_path=args.modelo, confidence_threshold=0.3,
        device="cuda",
    )  # fmt: skip
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    informe = {}
    for ruta in args.videos:
        cap = cv2.VideoCapture(ruta)
        if not cap.isOpened():
            raise SystemExit(f"no se pudo abrir {ruta}. PARA")
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(
            cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        )
        K = _build_camera_matrix(w, h)
        ini, fin = int(total * 0.03), int(total * 0.97)
        objetivos = [int(ini + (k + 0.5) * (fin - ini) / args.n) for k in range(args.n)]
        nombre = Path(ruta).stem
        alt = {"bruto": [], "corregido": []}
        por_frame = []
        for f in objetivos:
            posicionar_en_frame(cap, f)
            ok, img = cap.read()
            if not ok:
                continue
            fila = {"frame": f, "t_archivo_s": round(f / fps, 1)}
            for clave, im in (
                ("bruto", img),
                ("corregido", _corregir_distorsion(img, K, dist)),
            ):
                pred = get_sliced_prediction(
                    im, modelo, slice_height=im.shape[0] // 2, slice_width=im.shape[1] // 4,
                    overlap_height_ratio=0.2, overlap_width_ratio=0.2, verbose=0,
                )  # fmt: skip
                cajas = [
                    p.bbox.to_xyxy() for p in pred.object_prediction_list
                    if (p.bbox.maxx - p.bbox.minx) * (p.bbox.maxy - p.bbox.miny)
                    <= 0.05 * im.shape[0] * im.shape[1]
                ]  # fmt: skip
                _verde, region = mascara_cesped(im)
                buenas = pie_en_cesped(cajas, region)
                alt[clave] += [y2 - y1 for _x1, y1, _x2, y2 in buenas]
                fila[clave] = {"cajas": len(cajas), "en_cesped": len(buenas)}
                if clave == "corregido":
                    cv2.imwrite(str(salida / f"{nombre}_f{f:06d}.jpg"), im,
                                [cv2.IMWRITE_JPEG_QUALITY, 88])  # fmt: skip
            por_frame.append(fila)
        cap.release()
        r = {"resolucion": [w, h], "fps": fps, "frames": total,
             "duracion_min": round(total / fps / 60, 1),
             "bruto": resumen(alt["bruto"]), "corregido": resumen(alt["corregido"]),
             "por_frame": por_frame}  # fmt: skip
        r["lectura"] = lectura(r["corregido"].get("mediana"))
        informe[nombre] = r
        c, b = r["corregido"], r["bruto"]
        print(
            f"{nombre}: {w}×{h} a {fps:.2f} fps, {r['duracion_min']} min · "
            f"CORREGIDO mediana {c.get('mediana', 0):.1f} px (p10 {c.get('p10', 0):.1f}, "
            f"p90 {c.get('p90', 0):.1f}, < 25 px: {100 * c.get('frac_menor_25', 0):.0f} %, "
            f"n={c['n']}) · bruto {b.get('mediana', 0):.1f} px → {r['lectura']}",
            flush=True,
        )
    (salida / "altura_jugadores.json").write_text(json.dumps(informe, indent=1))
    print(f"✓ {salida}/altura_jugadores.json y los frames corregidos")


if __name__ == "__main__":
    main()
