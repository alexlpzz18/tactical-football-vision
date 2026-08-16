#!/usr/bin/env python
"""Vídeo del tramo con las cajas dibujadas: la herramienta de diagnóstico.

Cuando el replay no cuadra con el partido, la pregunta siempre es la
misma: ¿falla la DETECCIÓN, el TRACKING o la CLASIFICACIÓN? Mirar el
replay al lado del vídeo no lo distingue. Este vídeo sí: pinta sobre las
imágenes originales exactamente lo que el sistema vio.

Reutiliza la MISMA cadena del modo full (undistort → SAHI → filtros →
proyección), así que lo que se ve aquí es literalmente lo que entra al
tracking, no una aproximación.

Dos modos, según lo que haya:
  - Con CACHÉ de detecciones (lo normal): dibuja las cajas guardadas. No
    necesita GPU ni el modelo, y es instantáneo.
  - Sin caché: corre SAHI sobre el vídeo (necesita GPU y el modelo).

Con `--csv` añade encima el resultado del tracking: id de identidad y
color del equipo, para ver si una caja correcta acabó en la identidad
equivocada.

Uso:
    # Tramo del benjamín, cajas del caché
    python scripts/generar_video_detecciones.py \\
        --config configs/processor_benja.yaml \\
        --salida outputs/detecciones_benja.mp4

    # Con el resultado del tracking encima
    python scripts/generar_video_detecciones.py \\
        --config configs/processor_benja.yaml \\
        --csv data/tracking_benja/posiciones_benja.csv \\
        --salida outputs/detecciones_benja.mp4
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking_data.processor import (  # noqa: E402
    _build_camera_matrix,
    _filtrar_detecciones_v2,
    _rango_de_frames,
    posicionar_en_frame,
    project_point,
)

logger = logging.getLogger("video_detecciones")

# Codecs por orden de preferencia: avc1 (H.264) lo reproduce cualquier
# navegador; mp4v es el respaldo universal de OpenCV pero Safari y Chrome
# a veces se niegan a reproducirlo.
# Medido en macOS + opencv 4.13: avc1 abre y mp4v NO, así que el orden
# importa y conviene un tercer recurso (MJPG/.avi) que abre siempre
# aunque el archivo pese más y no se vea en el navegador.
CODECS = [("avc1", ".mp4"), ("mp4v", ".mp4"), ("MJPG", ".avi")]

VERDE = (0, 220, 0)
GRIS = (150, 150, 150)


def _abrir_escritor(salida: Path, fps: float, w: int, h: int):
    """VideoWriter con el primer codec que funcione, avisando de cuál."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    for codec, extension in CODECS:
        ruta = salida.with_suffix(extension)
        escritor = cv2.VideoWriter(
            str(ruta), cv2.VideoWriter_fourcc(*codec), fps, (w, h)
        )
        if escritor.isOpened():
            if codec != "avc1":
                logger.warning(
                    "Codec avc1 (H.264) no disponible: se usa %s. Si el vídeo "
                    "no se ve en el navegador, conviértelo con "
                    "`ffmpeg -i %s -vcodec libx264 salida.mp4`.",
                    codec,
                    ruta.name,
                )
            return escritor, ruta, codec
        escritor.release()
    raise RuntimeError(
        "OpenCV no pudo abrir ningún codec de vídeo (probados: "
        f"{[c for c, _ in CODECS]})."
    )


def _hex_a_bgr(color_hex: str) -> tuple[int, int, int]:
    r, g, b = bytes.fromhex(color_hex.lstrip("#"))
    return (b, g, r)  # OpenCV trabaja en BGR


def cargar_tracking(ruta_csv: Path, homografia, tolerancia_m: float = 2.0):
    """Índice {frame: [(x_m, y_m, id, etiqueta)]} del CSV de posiciones.

    El CSV está en METROS y las cajas en píxeles, así que cada caja se
    empareja con la posición del tracking más cercana en metros (su pie
    proyectado). Es la misma proyección que usó el pipeline, de modo que
    la correspondencia es exacta salvo empates.
    """
    import pandas as pd

    df = pd.read_csv(ruta_csv)
    if "es_real" in df.columns:
        # Solo las posiciones REALES tienen una caja detrás
        df = df[df["es_real"] == 1]
    indice = {}
    for frame, grupo in df.groupby("frame"):
        indice[int(frame)] = [
            (float(f.x_m), float(f.y_m), int(f.id_jugador), str(f.etiqueta))
            for f in grupo.itertuples()
        ]
    logger.info("Tracking cargado: %d frames con posiciones reales", len(indice))
    return indice


def dibujar_frame(frame, dets, tracking_frame, colores_equipo, mostrar_conf):
    """Pinta las cajas y, si hay tracking, su identidad y equipo.

    REGLA INNEGOCIABLE de esta herramienta: la geometría que se dibuja
    son los píxeles CRUDOS del detector (x1, y1, x2, y2 del caché), sin
    homografía de por medio en ningún punto. Solo así el vídeo sirve para
    juzgar la predicción: si la caja se pinta re-proyectando metros a
    píxeles, lo que se ve es la calidad de la homografía, no la del
    detector.

    El CSV entra ÚNICAMENTE como etiqueta (identidad y equipo) sobre esa
    caja cruda, emparejando por cercanía en metros y solo con posiciones
    reales (`es_real == 1`, filtrado en cargar_tracking).
    """
    for det in dets:
        mx, my, x1, y1, x2, y2, conf = det[:7]
        etiqueta, id_jugador = None, None
        if tracking_frame:
            # La posición del tracking más cercana a este pie proyectado
            mejor = min(
                tracking_frame, key=lambda t: (t[0] - mx) ** 2 + (t[1] - my) ** 2
            )
            if (mejor[0] - mx) ** 2 + (mejor[1] - my) ** 2 <= 4.0:
                id_jugador, etiqueta = mejor[2], mejor[3]

        color = VERDE
        if etiqueta:
            color = _hex_a_bgr(colores_equipo.get(etiqueta, "#00dc00"))
            if etiqueta in ("otro", "staff"):
                color = GRIS
        p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
        cv2.rectangle(frame, p1, p2, color, 2)

        texto = []
        if id_jugador is not None:
            texto.append(f"#{id_jugador}")
        if etiqueta:
            texto.append(etiqueta)
        if mostrar_conf:
            texto.append(f"{conf:.2f}")
        if texto:
            etiqueta_txt = " ".join(texto)
            (tw, th), _ = cv2.getTextSize(
                etiqueta_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1
            )
            cv2.rectangle(
                frame, (p1[0], p1[1] - th - 6), (p1[0] + tw + 6, p1[1]), color, -1
            )
            cv2.putText(
                frame,
                etiqueta_txt,
                (p1[0] + 3, p1[1] - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )
        # Punto de apoyo: es LO QUE SE PROYECTA, y por tanto la posición
        # real que ve el resto del sistema
        cv2.circle(frame, (int((x1 + x2) / 2), int(y2)), 3, color, -1)
    return frame


def dets_del_cache(cfg):
    """{frame_idx: dets} del caché, si existe (sin GPU ni modelo)."""
    ruta = Path(cfg["rutas"]["cache"])
    if not ruta.exists():
        return None
    from src.tracking.cache_io import cargar_cache

    datos = cargar_cache(str(ruta))
    logger.info("Cajas del caché %s (%d frames)", ruta, len(datos["cache"]))
    return {e["frame_idx"]: e["dets"] for e in datos["cache"]}


def dets_con_sahi(cfg, frame, w, h, H):
    """Detecciones de UN frame con la cadena exacta del modo full."""
    from sahi.predict import get_sliced_prediction

    cfg_det = cfg["deteccion"]
    resultado = get_sliced_prediction(
        frame,
        cfg["_modelo_sahi"],
        slice_height=h // cfg_det["sahi"]["filas"],
        slice_width=w // cfg_det["sahi"]["columnas"],
        overlap_height_ratio=cfg_det["sahi"]["solape"],
        overlap_width_ratio=cfg_det["sahi"]["solape"],
        verbose=0,
    )
    dets = []
    for pred in resultado.object_prediction_list:
        b = pred.bbox
        mx, my = project_point((b.minx + b.maxx) / 2.0, b.maxy, H)
        dets.append((mx, my, b.minx, b.miny, b.maxx, b.maxy, pred.score.value))
    return _filtrar_detecciones_v2(
        dets, cfg_det["confianza"], cfg_det["max_area_caja"], w * h
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Config del processor")
    parser.add_argument("--salida", default="outputs/detecciones.mp4")
    parser.add_argument(
        "--csv",
        default=None,
        help="CSV de posiciones: añade id de identidad y color de equipo",
    )
    parser.add_argument(
        "--meta",
        default=None,
        help="Meta del processor (colores reales de equipo). Por defecto, "
        "el que acompaña al CSV.",
    )
    parser.add_argument(
        "--sin-cache",
        action="store_true",
        help="Ignora el caché y vuelve a detectar con SAHI (necesita GPU)",
    )
    parser.add_argument(
        "--cache-balon",
        default=None,
        help="Caché de balón: lo pinta encima, en su propio color y con "
        "su propia frecuencia de muestreo",
    )
    parser.add_argument("--conf", action="store_true", help="Escribir la confianza")
    parser.add_argument(
        "--fps-salida",
        type=float,
        default=None,
        help="FPS del vídeo generado (por defecto, los del tramo muestreado)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    ruta_video = Path(cfg["rutas"]["video"])
    if not ruta_video.exists():
        raise FileNotFoundError(
            f"No se encuentra el vídeo {ruta_video} (config {args.config})."
        )
    H = np.load(cfg["rutas"]["homografia"])

    # Colores reales de equipo (mismos que el replay)
    colores_equipo = {}
    from src.report.replay_tactico import buscar_meta

    ruta_meta = Path(args.meta) if args.meta else None
    if ruta_meta is None and args.csv:
        ruta_meta = buscar_meta(args.csv)
    if ruta_meta and ruta_meta.exists():
        colores_equipo = json.loads(ruta_meta.read_text()).get("colores_equipo", {})
        for equipo in ("A", "B"):
            if equipo in colores_equipo:
                colores_equipo[f"portero_{equipo}"] = colores_equipo[equipo]
        logger.info("Colores de equipo: %s", colores_equipo)

    tracking = cargar_tracking(Path(args.csv), H) if args.csv else {}

    # El balón va en su propio caché y a otra frecuencia, así que se
    # indexa por frame y se pinta el que toque (o ninguno).
    balon_por_frame = {}
    if args.cache_balon:
        import pickle as _pickle

        with open(args.cache_balon, "rb") as f:
            _d = _pickle.load(f)
        balon_por_frame = {e["frame_idx"]: e["dets"] for e in _d["cache"] if e["dets"]}
        logger.info("Balón: %d frames con detección", len(balon_por_frame))

    cache_dets = None if args.sin_cache else dets_del_cache(cfg)
    if cache_dets is None:
        logger.info("Sin caché: se detecta con SAHI (requiere GPU y el modelo)")
        from sahi import AutoDetectionModel

        cfg["_modelo_sahi"] = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=cfg["deteccion"]["modelo"],
            confidence_threshold=cfg["deteccion"]["confianza"],
            device=cfg["deteccion"]["device"],
        )

    cap = cv2.VideoCapture(str(ruta_video))
    if not cap.isOpened():
        raise FileNotFoundError(f"No se puede abrir {ruta_video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sample = cfg["muestreo"]["sample_every"]

    # MISMO undistort y MISMO tramo que el modo full
    K = _build_camera_matrix(w, h)
    dist_lente = np.array(
        [cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], dtype=np.float64
    )
    sin_distorsion = cfg["distorsion"]["k1"] == 0 and cfg["distorsion"]["k2"] == 0
    frame_ini, frame_fin = _rango_de_frames(cfg["muestreo"], fps)
    if frame_ini > 0:
        # Posicionamiento VERIFICADO: un cap.set a secas caía 301 frames
        # más adelante en este vídeo y pintaba las cajas sobre el
        # fotograma equivocado (ver posicionar_en_frame).
        posicionar_en_frame(cap, frame_ini)

    fps_salida = args.fps_salida or (fps / sample)
    escritor, ruta_salida, codec = _abrir_escritor(Path(args.salida), fps_salida, w, h)
    logger.info(
        "Vídeo %dx%d @ %.1f fps (codec %s), tramo desde el frame %d",
        w,
        h,
        fps_salida,
        codec,
        frame_ini,
    )

    frame_idx = frame_ini
    escritos = 0
    total_cajas = 0
    try:
        while True:
            if frame_fin is not None and frame_idx >= frame_fin:
                break
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % sample != 0:
                frame_idx += 1
                continue
            if not sin_distorsion:
                frame = cv2.undistort(frame, K, dist_lente)

            if cache_dets is not None:
                dets = cache_dets.get(frame_idx, [])
            else:
                dets = dets_con_sahi(cfg, frame, w, h, H)
            total_cajas += len(dets)

            frame = dibujar_frame(
                frame, dets, tracking.get(frame_idx), colores_equipo, args.conf
            )
            for b in balon_por_frame.get(frame_idx, []):
                x1, y1, x2, y2 = int(b[2]), int(b[3]), int(b[4]), int(b[5])
                cv2.circle(
                    frame,
                    ((x1 + x2) // 2, (y1 + y2) // 2),
                    max(6, (x2 - x1) // 2 + 4),
                    (255, 255, 255),
                    2,
                )
            # Reloj y contador, para poder citar un instante concreto
            cv2.putText(
                frame,
                f"t={frame_idx / fps:6.2f}s  frame={frame_idx}  cajas={len(dets)}",
                (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            escritor.write(frame)
            escritos += 1
            if escritos % 100 == 0:
                logger.info("  %d frames escritos...", escritos)
            frame_idx += 1
    finally:
        cap.release()
        escritor.release()

    if escritos == 0:
        raise RuntimeError(
            "No se escribió ningún frame: revisa el tramo (muestreo.tramo) "
            "y que el vídeo tenga contenido en ese rango."
        )
    print(f"\n✓ Vídeo en {ruta_salida}")
    print(
        f"  {escritos} frames, {total_cajas} cajas ({total_cajas / escritos:.1f} "
        f"por frame), codec {codec}"
    )
    if not tracking:
        print("  (sin --csv: solo detección. Con él se ve además la identidad)")


if __name__ == "__main__":
    main()
