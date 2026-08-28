#!/usr/bin/env python
"""Genera el caché de BALÓN de un tramo (necesita GPU: Colab).

Independiente del de jugadores a propósito: el balón se muestrea MUCHO
más denso. Un jugador entre dos muestras se interpola sin drama —se mueve
despacio y en línea recta—, pero el balón puede recibir un toque y
cambiar de dirección entre una muestra y la siguiente, y ese contacto se
pierde para siempre. Por eso `sample_every` es propio de este modelo.

Además mide SAHI frente al frame entero: con imgsz=1280 y un balón de
5-12 px puede que el frame completo baste, y evitarlo ahorra ~10x de
inferencia.

Uso (Colab):
    python scripts/detectar_balon.py --config configs/processor_benja_balon.yaml
    python scripts/detectar_balon.py --config ... --comparar-sahi --frames 60
"""

import argparse
import logging
import os
import pickle
import tempfile
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking_data.processor import (  # noqa: E402
    _build_camera_matrix,
    _rango_de_frames,
    posicionar_en_frame,
    project_point,
)

logger = logging.getLogger("balon")


def iter_frames(cap, frame_ini, frame_fin, sample, total=0):
    """Genera (frame_idx, frame) del tramo, con posicionamiento VERIFICADO.

    El salto se comprueba LEYENDO, no preguntando. `cap.set` puede
    informar de que aterrizó donde se le pidió y dejar el lector
    inservible: entonces el primer `read()` devuelve False, el bucle sale
    a la primera y el script acaba procesando 0 frames sin decir por qué.
    Es lo que pasó en Colab con este mismo vídeo, que en local se lee sin
    problema — o sea, el fallo depende del build de OpenCV.

    Por eso, si el primer fotograma no llega, se rebobina y se avanza
    decodificando (`grab()` es barato). Cuesta unos segundos y elimina
    toda una familia de fallos que dependen del entorno.
    """
    posicionar_en_frame(cap, frame_ini)
    ok, frame = cap.read()
    if not ok:
        logger.warning(
            "El salto al frame %d dejó el vídeo ilegible (read() falló pese a "
            "que el seek se dio por bueno): se rebobina y se decodifica.",
            frame_ini,
        )
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        pos = 0
        while pos < frame_ini and cap.grab():
            pos += 1
        ok, frame = cap.read()
        if not ok:
            raise SystemExit(
                f"\nERROR: no se puede leer el frame {frame_ini} ni saltando "
                f"ni decodificando desde el principio.\n"
                f"  El vídeo declara {total} frames. Si el tramo cae dentro, "
                f"el archivo puede estar truncado o mal copiado a Drive."
            )

    frame_idx = frame_ini
    while True:
        if frame_fin is not None and frame_idx >= frame_fin:
            return
        if frame_idx % sample == 0:
            yield frame_idx, frame
        frame_idx += 1
        ok, frame = cap.read()
        if not ok:
            return


def _detectar_frame_entero(modelo, frame, conf, imgsz):
    r = modelo.predict(frame, conf=conf, imgsz=imgsz, verbose=False)[0]
    return [(*map(float, b.xyxy[0].tolist()), float(b.conf[0])) for b in r.boxes]


def _detectar_sahi(modelo_sahi, frame, cfg_sahi, w, h):
    from sahi.predict import get_sliced_prediction

    r = get_sliced_prediction(
        frame,
        modelo_sahi,
        slice_height=h // cfg_sahi["filas"],
        slice_width=w // cfg_sahi["columnas"],
        overlap_height_ratio=cfg_sahi["solape"],
        overlap_width_ratio=cfg_sahi["solape"],
        verbose=0,
    )
    return [
        (p.bbox.minx, p.bbox.miny, p.bbox.maxx, p.bbox.maxy, p.score.value)
        for p in r.object_prediction_list
    ]


def _volcar(ruta, objeto) -> None:
    """Escribe el caché de forma ATÓMICA (temporal único + rename).

    Con un `.tmp` de nombre fijo dos procesos abrirían el mismo fichero e
    intercalarían bytes (medido en el procesador de jugadores: 1 de cada
    12 intentos con 4 procesos). Y si el volcado falla, el caché bueno
    anterior sigue en su sitio.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp = tempfile.mkstemp(dir=str(ruta.parent), suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as f:
            pickle.dump(objeto, f)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _reanudar_balon(ruta, firma):
    """Recupera un checkpoint compatible, o None."""
    ruta = Path(ruta)
    if not ruta.exists():
        return None
    try:
        with open(ruta, "rb") as f:
            previo = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError) as err:
        logger.warning("No se pudo leer el caché de balón previo (%s); se rehace.", err)
        return None
    if previo.get("firma") != firma:
        logger.warning(
            "Hay un caché de balón hecho con OTRA configuración: se SOBRESCRIBE."
        )
        return None
    if previo.get("completo") or not previo.get("cache"):
        return None
    return previo["cache"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--comparar-sahi",
        action="store_true",
        help="Mide SAHI vs frame entero en unos frames y sale (no cachea)",
    )
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    cb = cfg["balon"]
    H = np.load(cfg["rutas"]["homografia"])

    # Validación de rutas ANTES de cargar nada: un fallo de config debe
    # verse como tal y no después de gastar medio minuto de GPU.
    ruta_video = Path(cfg["rutas"]["video"])
    if not ruta_video.exists():
        candidatos = sorted(x.name for x in ruta_video.parent.glob("*.mp4")) or [
            "(ninguno)"
        ]
        raise SystemExit(
            f"\nERROR: no existe el vídeo {ruta_video}\n"
            f"  Lo pide {args.config} (rutas.video).\n"
            f"  En {ruta_video.parent} hay: {', '.join(candidatos)}\n"
            f"  Haz que el enlace y el config usen el MISMO nombre."
        )
    if not Path(cb["modelo"]).exists():
        raise SystemExit(f"\nERROR: no existe el modelo {cb['modelo']}")

    from ultralytics import YOLO

    modelo = YOLO(cb["modelo"])
    modelo_sahi = None
    if cb.get("sahi", {}).get("activo", False) or args.comparar_sahi:
        from sahi import AutoDetectionModel

        modelo_sahi = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=cb["modelo"],
            confidence_threshold=cb["confianza"],
            device=cfg["deteccion"]["device"],
        )

    # Comprobaciones ANTES de tocar la GPU. Sin ellas, una ruta que no
    # existe hacía que VideoCapture fallara callando, read() devolviera
    # False a la primera y el script acabara dividiendo por cero tras
    # "Comparación sobre 0 frames" — un mensaje que no dice nada de la
    # causa real. Un fallo de configuración debe verse como tal.
    ruta_video = Path(cfg["rutas"]["video"])
    if not ruta_video.exists():
        candidatos = sorted(x.name for x in ruta_video.parent.glob("*.mp4")) or [
            "(ninguno)"
        ]
        raise SystemExit(
            f"\nERROR: no existe el vídeo {ruta_video}\n"
            f"  El config {args.config} apunta ahí (rutas.video).\n"
            f"  En {ruta_video.parent} hay: {', '.join(candidatos)}\n"
            f"  Arregla el enlace o la ruta del config para que coincidan."
        )
    cap = cv2.VideoCapture(str(ruta_video))
    if not cap.isOpened():
        raise SystemExit(
            f"\nERROR: {ruta_video} existe pero OpenCV no puede abrirlo.\n"
            f"  ¿Está completo? ¿Es un enlace roto (ls -l) o un códec no "
            f"soportado por este build de OpenCV?"
        )

    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample = cb["sample_every"]
    frame_ini, frame_fin = _rango_de_frames(cfg["muestreo"], fps)

    # ── CHECKPOINT Y REANUDACIÓN ─────────────────────────────────────
    #
    # Este script ya nos dio dos sustos: procesar 0 frames en silencio y
    # un "✓ Caché de balón" sobre un archivo vacío. La guarda de abajo
    # arregló el segundo, pero quedaba el peor: el `pickle.dump` está al
    # final, así que una caída de sesión en el minuto 35 de 40 lo pierde
    # todo. Sobre la parte entera son ~18.000 frames de GPU.
    #
    # Mismo diseño que `procesar_full`: volcado atómico cada N frames,
    # las detecciones (que anclan la reanudación) SIEMPRE al final, y una
    # firma que impide reanudar sobre otra configuración de detección.
    cfg_ck = cfg.get("checkpoint") or {}
    cada = int(cfg_ck.get("cada_frames", 500) or 0)
    firma_balon = {
        "video": str(cfg["rutas"]["video"]),
        "modelo": cb["modelo"],
        "confianza": cb["confianza"],
        "imgsz": cb["imgsz"],
        "sample_every": sample,
        "sahi": dict(cb.get("sahi") or {}),
        "k1": cfg["distorsion"]["k1"],
        "k2": cfg["distorsion"]["k2"],
        "tramo": dict(cfg["muestreo"].get("tramo") or {}),
    }
    ruta_ck = Path(cfg["rutas"]["cache_balon"])

    def _guardar(cache_actual, completo):
        _volcar(
            ruta_ck,
            {
                "cache": cache_actual,
                "fps": fps,
                "sample": sample,
                "wh": (w, h),
                "modelo": cb["modelo"],
                "confianza": cb["confianza"],
                "completo": completo,
                "firma": firma_balon,
            },
        )

    logger.info(
        "Vídeo %s: %dx%d, %.2f fps, %d frames (%.1f min). Tramo [%d, %s), "
        "1 de cada %d",
        ruta_video.name,
        w,
        h,
        fps,
        total,
        total / fps / 60 if fps else 0,
        frame_ini,
        frame_fin if frame_fin is not None else "fin",
        sample,
    )
    if total > 0 and frame_ini >= total:
        raise SystemExit(
            f"\nERROR: el tramo empieza en el frame {frame_ini} "
            f"({frame_ini / fps / 60:.1f} min) y el vídeo solo tiene {total} "
            f"({total / fps / 60:.1f} min).\n"
            f"  Revisa muestreo.tramo en {args.config}."
        )
    posicionar_en_frame(cap, frame_ini)

    K = _build_camera_matrix(w, h)
    dist = np.array(
        [cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], dtype=np.float64
    )
    sin_dist = cfg["distorsion"]["k1"] == 0 and cfg["distorsion"]["k2"] == 0

    cache, n_con = [], 0
    if cada and not args.comparar_sahi and cfg_ck.get("reanudar", True):
        previo = _reanudar_balon(ruta_ck, firma_balon)
        if previo:
            cache = previo
            n_con = sum(1 for e in cache if e["dets"])
            frame_ini = cache[-1]["frame_idx"] + 1
            logger.info(
                "REANUDANDO el balón: %d frames ya cacheados, se sigue desde "
                "el %d (t=%.1f s)",
                len(cache),
                frame_ini,
                frame_ini / fps,
            )
    t_entero = t_sahi = 0.0
    n_entero = n_sahi = 0
    hechos = 0
    for frame_idx, frame in iter_frames(cap, frame_ini, frame_fin, sample, total):
        if args.comparar_sahi and len(cache) >= args.frames:
            break
        if not sin_dist:
            frame = cv2.undistort(frame, K, dist)

        if args.comparar_sahi:
            t0 = time.time()
            d1 = _detectar_frame_entero(modelo, frame, cb["confianza"], cb["imgsz"])
            t_entero += time.time() - t0
            n_entero += len(d1)
            t0 = time.time()
            d2 = _detectar_sahi(modelo_sahi, frame, cb["sahi"], w, h)
            t_sahi += time.time() - t0
            n_sahi += len(d2)
            cache.append(1)
            continue

        if modelo_sahi is not None:
            crudas = _detectar_sahi(modelo_sahi, frame, cb["sahi"], w, h)
        else:
            crudas = _detectar_frame_entero(modelo, frame, cb["confianza"], cb["imgsz"])

        dets = []
        for x1, y1, x2, y2, conf in crudas:
            if conf < cb["confianza"]:
                continue
            mx, my = project_point((x1 + x2) / 2.0, y2, H)
            dets.append((mx, my, x1, y1, x2, y2, conf))
        cache.append({"frame_idx": frame_idx, "t": frame_idx / fps, "dets": dets})
        if dets:
            n_con += 1
        hechos += 1
        if cada and hechos % cada == 0:
            _guardar(cache, False)
            logger.info(
                "  %d frames (%d con balón) · checkpoint guardado", len(cache), n_con
            )
        elif len(cache) % 200 == 0:
            logger.info("  %d frames (%d con balón)", len(cache), n_con)
    cap.release()

    # Validar ANTES de escribir. Antes se guardaba el caché, se imprimía
    # un "✓ Caché de balón" y solo después reventaba el resumen: un ✓
    # sobre un archivo vacío es peor que un error, porque se cree.
    if not cache:
        raise SystemExit(
            f"\nERROR: no se procesó NINGÚN frame.\n"
            f"  vídeo   : {ruta_video} ({total} frames)\n"
            f"  tramo   : del {frame_ini} al "
            f"{frame_fin if frame_fin is not None else 'fin'}\n"
            f"  muestreo: 1 de cada {sample}\n"
            f"  No se ha escrito ningún caché."
        )

    if args.comparar_sahi:
        n = len(cache)
        print(f"\nComparación sobre {n} frames:")
        print(
            f"  frame entero (imgsz {cb['imgsz']}): {n_entero} detecciones, "
            f"{1000 * t_entero / n:.0f} ms/frame"
        )
        print(
            f"  SAHI {cb['sahi']['filas']}x{cb['sahi']['columnas']}: "
            f"{n_sahi} detecciones, {1000 * t_sahi / n:.0f} ms/frame"
        )
        print(
            f"  SAHI cuesta {t_sahi / max(t_entero, 1e-9):.1f}x y encuentra "
            f"{n_sahi - n_entero:+d} detecciones"
        )
        print(
            "\n  Si SAHI no encuentra bastantes más, no compensa: pon "
            "balon.sahi.activo: false"
        )
        return

    salida = Path(cfg["rutas"]["cache_balon"])
    _guardar(cache, True)

    # ⚠️ SE RELEE EL FICHERO ANTES DE DAR EL ✓. Contar lo que se envió al
    # disco no prueba que esté en el disco: ya nos pasó con el vídeo, donde
    # OpenCV reventaba al final y el proceso salía con estado 0.
    with open(salida, "rb") as f:
        releido = pickle.load(f)
    if len(releido.get("cache", [])) != len(cache):
        raise SystemExit(
            f"\nERROR: el caché salió INCOMPLETO. Se procesaron {len(cache)} "
            f"frames y en {salida} hay {len(releido.get('cache', []))}."
        )
    print(f"\n✓ Caché de balón en {salida} ({len(releido['cache'])} releídos)")
    print(
        f"  {len(cache)} frames, {n_con} con balón ({100 * n_con / len(cache):.0f} %)"
    )


if __name__ == "__main__":
    main()
