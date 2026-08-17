"""
Procesador de vídeo → tracking data.
Recorre un vídeo, corrige distorsión, detecta jugadores con SAHI (inferencia
por recortes), los trackea, clasifica equipos y proyecta posiciones a metros
con la homografía. Produce una tabla de posiciones (CSV) + metadatos (JSON).
"""

import json
import logging
import pickle
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import supervision as sv
import yaml

# SAHI se importa de forma perezosa dentro de las funciones que detectan:
# el modo desde-caché (local, sin GPU) no debe requerirlo.
from src.team_classification.classifier import TeamClassifier

logger = logging.getLogger(__name__)

# Convención de equipo del CSV (la misma de TEAM_COLORS en pipeline.py);
# los porteros cuentan con su equipo para el informe colectivo
# 'staff' (línier/cuerpo técnico, regla posicional) va al mismo cajón que
# 'otro': fuera de las métricas por equipo y del informe.
EQUIPO_A_ENTERO = {
    "A": 0,
    "portero_A": 0,
    "B": 1,
    "portero_B": 1,
    "otro": 2,
    "staff": 2,
}


def _build_camera_matrix(w, h, focal_factor=1.0):
    """Matriz de cámara para la corrección de distorsión."""
    fx = fy = w * focal_factor
    return np.array([[fx, 0, w / 2], [0, fy, h / 2], [0, 0, 1]], dtype=np.float64)


def project_point(x, y, H):
    """Proyecta un punto en píxeles a metros usando la homografía H."""
    punto = np.array([x, y, 1.0])
    proy = H @ punto
    proy = proy / proy[2]
    return float(proy[0]), float(proy[1])


def _sahi_to_detections(sahi_result):
    """Convierte el resultado de SAHI al formato sv.Detections de supervision."""
    boxes = []
    confidences = []
    for pred in sahi_result.object_prediction_list:
        b = pred.bbox
        boxes.append([b.minx, b.miny, b.maxx, b.maxy])
        confidences.append(pred.score.value)

    if len(boxes) == 0:
        return sv.Detections.empty()

    return sv.Detections(
        xyxy=np.array(boxes, dtype=np.float32),
        confidence=np.array(confidences, dtype=np.float32),
        class_id=np.zeros(len(boxes), dtype=int),
    )


def process_video(
    video_path: str,
    model_path: str,
    homography_path: str,
    output_csv: str,
    output_meta: str,
    k1: float = -1.5,
    k2: float = 0.5,
    sample_every: int = 5,
    max_frames: int = None,
    confidence: float = 0.2,
    field_length: float = 100.0,
    field_width: float = 64.0,
    slice_rows: int = 2,
    slice_cols: int = 4,
    device: str = "cuda",
):
    """
    Procesa el vídeo y guarda la tabla de posiciones.

    Args:
        video_path: ruta al vídeo
        model_path: ruta al modelo YOLO (.pt)
        homography_path: ruta a la matriz H (.npy)
        output_csv: dónde guardar la tabla de posiciones
        output_meta: dónde guardar los metadatos
        k1, k2: coeficientes de distorsión de lente
        sample_every: procesar 1 de cada N frames (submuestreo)
        max_frames: limitar nº de frames originales a recorrer (None = todo)
        confidence: umbral de confianza del detector
        field_length, field_width: dimensiones del campo en metros
        slice_rows, slice_cols: divisiones de SAHI (filas x columnas)
        device: 'cuda' en Colab con GPU, 'cpu' en local
    """
    # ── Cargar homografía, modelo SAHI, tracker y clasificador ──
    from sahi import AutoDetectionModel

    H = np.load(homography_path)

    modelo_sahi = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=model_path,
        confidence_threshold=confidence,
        device=device,
    )

    # Mantenemos ByteTrack para los IDs (igual que antes)
    tracker = sv.ByteTrack(
        track_activation_threshold=confidence,
        lost_track_buffer=150,
        minimum_matching_threshold=0.8,
        frame_rate=30,
    )

    classifier = TeamClassifier(n_teams=2)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: no se puede abrir {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Vídeo {w}x{h} @ {fps}fps, {total} frames")
    print(f"SAHI: {slice_rows}x{slice_cols} trozos, umbral {confidence}")

    # Tamaño de cada trozo de SAHI
    slice_h = h // slice_rows
    slice_w = w // slice_cols

    # ── Preparar la corrección de distorsión ──
    K = _build_camera_matrix(w, h)
    dist = np.array([k1, k2, 0, 0, 0], dtype=np.float64)

    # ── Recorrer el vídeo ──
    filas = []
    training_frames = []
    classifier_fitted = False
    frame_idx = 0
    procesados = 0

    print("Procesando...")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if max_frames and frame_idx >= max_frames:
            break

        # Submuestreo: solo procesamos 1 de cada sample_every
        if frame_idx % sample_every != 0:
            frame_idx += 1
            continue

        # 1. Corregir distorsión
        frame = cv2.undistort(frame, K, dist)

        # 2. Detectar con SAHI
        from sahi.predict import get_sliced_prediction

        sahi_result = get_sliced_prediction(
            frame,
            modelo_sahi,
            slice_height=slice_h,
            slice_width=slice_w,
            overlap_height_ratio=0.2,
            overlap_width_ratio=0.2,
            verbose=0,
        )
        detections = _sahi_to_detections(sahi_result)

        # 3. Trackear (IDs) con ByteTrack
        detections = tracker.update_with_detections(detections)

        # 4. Entrenar el clasificador de equipos (primeros 30 frames válidos)
        if not classifier_fitted:
            if len(detections) >= 3:
                training_frames.append((frame.copy(), detections))
            if len(training_frames) >= 30:
                classifier.fit_multiple(
                    [f for f, d in training_frames],
                    [d for f, d in training_frames],
                )
                classifier_fitted = True
                print(f"  Clasificador entrenado ({len(training_frames)} frames)")

        # 5. Clasificar equipos
        if classifier_fitted and len(detections) > 0:
            team_ids = classifier.predict(frame, detections)
        else:
            team_ids = np.zeros(len(detections), dtype=int)

        # 6. Proyectar cada jugador y guardar una fila
        for i, (bbox, tid) in enumerate(zip(detections.xyxy, detections.tracker_id)):
            if tid is None:
                continue
            x1, y1, x2, y2 = bbox
            pies_x = (x1 + x2) / 2.0
            pies_y = y2
            mx, my = project_point(pies_x, pies_y, H)
            # Solo guardamos si cae dentro del campo (con margen)
            if -5 <= mx <= field_length + 5 and -5 <= my <= field_width + 5:
                equipo = int(team_ids[i]) if len(team_ids) > i else 0
                filas.append(
                    {
                        "frame": frame_idx,
                        "tiempo_s": round(frame_idx / fps, 2),
                        "id_jugador": int(tid),
                        "equipo": equipo,
                        "x_m": round(mx, 2),
                        "y_m": round(my, 2),
                    }
                )

        procesados += 1
        frame_idx += 1
        if procesados % 50 == 0:
            print(f"  {procesados} frames procesados ({frame_idx}/{total})")

    cap.release()

    # ── Guardar resultados ──
    df = pd.DataFrame(filas)
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)

    meta = {
        "video": Path(video_path).name,
        "fecha_proceso": datetime.now().isoformat(timespec="seconds"),
        "fps_original": fps,
        "sample_every": sample_every,
        "fps_efectivo": round(fps / sample_every, 2),
        "resolucion": [w, h],
        "frames_procesados": procesados,
        "distorsion": {"k1": k1, "k2": k2},
        "homografia": Path(homography_path).name,
        "campo_m": [field_length, field_width],
        "deteccion": "SAHI",
        "sahi_slices": [slice_rows, slice_cols],
        "confidence": confidence,
        "total_detecciones": len(filas),
        "ids_unicos": int(df["id_jugador"].nunique()) if len(df) else 0,
    }
    with open(output_meta, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n✓ Guardadas {len(filas)} posiciones en {output_csv}")
    print(f"✓ Metadatos en {output_meta}")
    print(f"  IDs únicos detectados: {meta['ids_unicos']}")
    return df


# ══════════════════════════════════════════════════════════════════════
# PIPELINE V2 (integración end-to-end)
# vídeo → [detección SAHI + caché]  →  tracking por PERFIL  →  equipos
# → CSV + meta. El tramo de detección solo corre en Colab (GPU); en local
# se parte de los cachés. El flujo viejo (process_video) queda intacto
# como fallback (pipeline: legacy en configs/processor.yaml).
# ══════════════════════════════════════════════════════════════════════


# Claves obligatorias de la config por modo (rutas con puntos). Se validan
# al arrancar para fallar con un mensaje claro en vez de un KeyError críptico
# a mitad de proceso. Plantilla completa: configs/processor_ejemplo.yaml
_CLAVES_DESDE_CACHE = (
    "rutas.cache",
    "rutas.cache_colores",
    "rutas.homografia",
    "rutas.salida_csv",
    "rutas.salida_meta",
    "tracking.perfil",
    "campo_m.largo",
    "campo_m.ancho",
    "campo_m.margen",
)
_CLAVES_FULL = (
    "rutas.video",
    "rutas.cache",
    "rutas.cache_colores",
    "rutas.homografia",
    "deteccion.modelo",
    "deteccion.confianza",
    "deteccion.max_area_caja",
    "deteccion.sahi.filas",
    "deteccion.sahi.columnas",
    "deteccion.sahi.solape",
    "deteccion.device",
    "distorsion.k1",
    "distorsion.k2",
    "muestreo.sample_every",
)


def _obtener_clave(cfg: dict, ruta: str):
    """Navega una clave con puntos ('rutas.cache') o devuelve None."""
    nodo = cfg
    for parte in ruta.split("."):
        if not isinstance(nodo, dict) or parte not in nodo:
            return None
        nodo = nodo[parte]
    return nodo


def validar_config(cfg: dict, claves_obligatorias: tuple) -> None:
    """Valida la config al arrancar y aplica defaults razonables.

    Defaults (se aplican in-place, con aviso en el log):
    - config_tracking → configs/tracking.yaml (el archivo canónico de
      parámetros de tracking; no tiene sentido obligar a repetirlo).
    - equipos.activo → true.

    Raises:
        ValueError: con la LISTA COMPLETA de claves obligatorias ausentes
            y la referencia a la plantilla, en vez de un KeyError críptico
            en mitad del procesado.
    """
    if "config_tracking" not in cfg:
        cfg["config_tracking"] = "configs/tracking.yaml"
        logger.info("config_tracking no especificado → configs/tracking.yaml")
    cfg.setdefault("equipos", {"activo": True})

    faltan = [c for c in claves_obligatorias if _obtener_clave(cfg, c) is None]
    if faltan:
        raise ValueError(
            "Config del procesador incompleta. Faltan estas claves "
            f"obligatorias: {faltan}. Usa configs/processor_ejemplo.yaml "
            "como plantilla."
        )


def _rango_de_frames(cfg_muestreo: dict, fps: float) -> tuple[int, int | None]:
    """Rango [frame_ini, frame_fin) de frames ORIGINALES a procesar.

    Soporta dos límites combinables en configs/processor.yaml (muestreo):
    - tramo: {min_ini, dur_seg} → procesar solo esa ventana del partido
      (caso real: saltar el descanso, validar con un tramo corto).
    - max_frames: tope de frames originales a recorrer desde el inicio
      del tramo (o del vídeo si no hay tramo).

    Los frame_idx resultantes siguen siendo GLOBALES del vídeo (el formato
    del caché los usa así: min 5 a 25 fps → frame 7500), por eso el tramo
    solo posiciona el lector, nunca renumera.

    Returns:
        (frame_ini, frame_fin): fin exclusivo, None = hasta el final.
    """
    frame_ini = 0
    frame_fin = None
    tramo = cfg_muestreo.get("tramo") or {}
    if tramo:
        frame_ini = int(round(tramo["min_ini"] * 60.0 * fps))
        frame_fin = frame_ini + int(round(tramo["dur_seg"] * fps))
    max_frames = cfg_muestreo.get("max_frames")
    if max_frames is not None:
        fin_por_max = frame_ini + int(max_frames)
        frame_fin = fin_por_max if frame_fin is None else min(frame_fin, fin_por_max)
    return frame_ini, frame_fin


def _filtrar_detecciones_v2(dets, confianza_min, max_area_frac, area_frame):
    """Filtros validados: confianza mínima y descarte de cajas gigantes.

    dets: lista de (mx, my, x1, y1, x2, y2, conf). Las cajas que ocupan
    más de max_area_frac del frame son falsos positivos (gradas, bancos).
    """
    filtradas = []
    for d in dets:
        mx, my, x1, y1, x2, y2, conf = d
        if conf < confianza_min:
            continue
        if (x2 - x1) * (y2 - y1) > max_area_frac * area_frame:
            continue
        filtradas.append(d)
    return filtradas


def posicionar_en_frame(cap, objetivo: int) -> int:
    """Deja el vídeo justo antes del frame `objetivo`. Devuelve dónde quedó.

    `cap.set(CAP_PROP_POS_FRAMES, n)` NO es fiable con vídeo comprimido:
    salta al fotograma clave más cercano, que puede estar muy lejos. En
    el partido del benjamín, pedir el frame 8991 dejaba el vídeo en el
    9292 — **301 frames, 10 segundos de desincronía**. El efecto es
    traicionero porque no rompe nada: pinta cajas correctas sobre el
    fotograma equivocado, y el desajuste se ve pequeño en los jugadores
    lejanos (pocos píxeles por frame) y enorme en los cercanos.

    Por eso el salto se VERIFICA siempre y, si no cayó donde debía, se
    rebobina y se avanza decodificando. No se decodifica SIEMPRE porque
    cuesta caro: llegar al minuto 5 de este partido son 27 s, y en un
    partido entero, minutos.

    Ojo con una trampa: `cap.set` acepta un frame que no existe y luego
    `cap.get` devuelve tan campante la posición pedida, así que la
    comprobación de POS_FRAMES por sí sola no basta y hay que mirar
    además cuántos frames tiene el vídeo.
    """
    if objetivo <= 0:
        return 0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total > 0 and objetivo >= total:
        raise RuntimeError(
            f"No se pudo posicionar en el frame {objetivo}: el vídeo solo "
            f"tiene {total}. ¿El tramo (muestreo.tramo) cae fuera del vídeo?"
        )
    cap.set(cv2.CAP_PROP_POS_FRAMES, objetivo)
    pos = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    if pos == objetivo:
        return pos
    logger.warning(
        "El salto al frame %d cayó en el %d: se reposiciona decodificando "
        "(sin esto, las cajas irían sobre el fotograma equivocado)",
        objetivo,
        pos,
    )
    if pos > objetivo:  # se pasó: no hay marcha atrás, hay que rebobinar
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        pos = 0
    while pos < objetivo and cap.grab():
        pos += 1
    if pos != objetivo:
        raise RuntimeError(
            f"No se pudo posicionar en el frame {objetivo} (se llegó al {pos}): "
            "¿el vídeo es más corto que el tramo pedido?"
        )
    return pos


def detectar_y_cachear(cfg: dict) -> tuple[dict, dict]:
    """Modo FULL (Colab GPU): vídeo → detección SAHI → cachés en disco.

    Produce EXACTAMENTE los artefactos que consume el modo desde-caché:
    - caché de detecciones {cache, fps, sample, wh} (formato de cache_io)
    - caché de colores {(frame_idx, det_idx): feature 256}

    Returns:
        (datos_cache, colores)
    """
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction

    from src.team_classification.color_classifier import extraer_color_torso
    from src.team_classification.feature_v2 import extraer_color_torso_v2

    # Versión de la feature de color. La v2 añade V (desbloquea el
    # arquetipo negro del catálogo arbitral) y el histograma del
    # pantalón, y sus 256 primeros valores son EXACTAMENTE la v1, así que
    # ningún umbral calibrado cambia de escala. Se elige por config
    # porque cambiarla obliga a regenerar los cachés.
    version_color = int(cfg.get("deteccion", {}).get("version_color", 1))
    extractor = extraer_color_torso_v2 if version_color >= 2 else extraer_color_torso
    logger.info("Feature de color v%d (la v2 añade V y pantalón)", version_color)

    validar_config(cfg, _CLAVES_FULL)
    cfg_det = cfg["deteccion"]
    H = np.load(cfg["rutas"]["homografia"])

    modelo = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=cfg_det["modelo"],
        confidence_threshold=cfg_det["confianza"],
        device=cfg_det["device"],
    )

    cap = cv2.VideoCapture(cfg["rutas"]["video"])
    if not cap.isOpened():
        raise FileNotFoundError(f"No se puede abrir {cfg['rutas']['video']}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sample = cfg["muestreo"]["sample_every"]
    K = _build_camera_matrix(w, h)
    dist_lente = np.array(
        [cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], dtype=np.float64
    )
    filas_sahi = cfg_det["sahi"]["filas"]
    cols_sahi = cfg_det["sahi"]["columnas"]

    # Tramo/límite opcional (muestreo.tramo / muestreo.max_frames)
    frame_ini, frame_fin = _rango_de_frames(cfg["muestreo"], fps)
    if frame_ini > 0:
        posicionar_en_frame(cap, frame_ini)
        logger.info(
            "Tramo: arrancando en el frame %d (t=%.1f s)%s",
            frame_ini,
            frame_ini / fps,
            f", hasta el {frame_fin}" if frame_fin is not None else "",
        )

    cache, colores = [], {}
    frame_idx = frame_ini
    while True:
        if frame_fin is not None and frame_idx >= frame_fin:
            break
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample != 0:
            frame_idx += 1
            continue
        frame = cv2.undistort(frame, K, dist_lente)
        resultado = get_sliced_prediction(
            frame,
            modelo,
            slice_height=h // filas_sahi,
            slice_width=w // cols_sahi,
            overlap_height_ratio=cfg_det["sahi"]["solape"],
            overlap_width_ratio=cfg_det["sahi"]["solape"],
            verbose=0,
        )
        dets = []
        for pred in resultado.object_prediction_list:
            b = pred.bbox
            mx, my = project_point((b.minx + b.maxx) / 2.0, b.maxy, H)
            dets.append((mx, my, b.minx, b.miny, b.maxx, b.maxy, pred.score.value))
        dets = _filtrar_detecciones_v2(
            dets, cfg_det["confianza"], cfg_det["max_area_caja"], w * h
        )
        # Feature de color de cada recorte (misma feature que el caché de Colab)
        for det_idx, d in enumerate(dets):
            x1, y1, x2, y2 = (int(v) for v in d[2:6])
            y1, x1 = max(y1, 0), max(x1, 0)
            crop = frame[y1:y2, x1:x2]
            if crop.size > 0:
                # ÚNICA función de extracción del repo (normalización L2,
                # la escala en la que están calibrados todos los umbrales)
                feat = extractor(crop)
                if feat.sum() > 0:
                    colores[(frame_idx, det_idx)] = feat
        cache.append({"frame_idx": frame_idx, "t": frame_idx / fps, "dets": dets})
        frame_idx += 1
    cap.release()

    datos = {"cache": cache, "fps": fps, "sample": sample, "wh": (w, h)}
    Path(cfg["rutas"]["cache"]).parent.mkdir(parents=True, exist_ok=True)
    with open(cfg["rutas"]["cache"], "wb") as f:
        pickle.dump(datos, f)
    with open(cfg["rutas"]["cache_colores"], "wb") as f:
        pickle.dump(colores, f)
    logger.info(
        "Detección cacheada: %d frames, %d features de color", len(cache), len(colores)
    )
    return datos, colores


def procesar_desde_cache(cfg: dict) -> pd.DataFrame:
    """Modo DESDE-CACHÉ (local, CPU): cachés → tracking → equipos → CSV+meta."""
    from src.team_classification.pipeline_equipos import (
        cargar_config_equipos,
        clasificar_identidades,
        entrenar_clasificador,
    )
    from src.tracking.cache_io import cargar_cache
    from src.tracking.filtro_confianza import filtrar_por_confianza
    from src.tracking.perfiles import correr_perfil

    validar_config(cfg, _CLAVES_DESDE_CACHE)
    with open(cfg["config_tracking"]) as f:
        cfg_tracking = yaml.safe_load(f)

    datos = cargar_cache(cfg["rutas"]["cache"])
    ruta_colores = Path(cfg["rutas"]["cache_colores"])
    colores = None
    if ruta_colores.exists():
        with open(ruta_colores, "rb") as f:
            colores = pickle.load(f)

    # Filtro de confianza ANTES de entrenar nada: el clasificador debe
    # ajustarse a la población de detecciones que va a ver el tracker, no
    # a una que se acaba de descartar.
    conf_min = float(cfg_tracking.get("confianza_min", 0.0) or 0.0)
    if conf_min > 0:
        datos["cache"], colores = filtrar_por_confianza(
            datos["cache"], colores, conf_min
        )

    clasificador = None
    cfg_equipos = {}
    if colores is not None and cfg.get("equipos", {}).get("activo", True):
        # Ruta configurable: cada campo tiene su propia config de equipos
        # (áreas de portería, eje de profundidad, dimensiones).
        cfg_equipos = cargar_config_equipos(
            cfg.get("config_equipos", "configs/team_classification.yaml")
        )
        clasificador = entrenar_clasificador(colores, cfg_equipos, datos["cache"])

    identidades = correr_perfil(
        datos["cache"],
        datos["fps"],
        datos["sample"],
        cfg_tracking,
        perfil=cfg["tracking"]["perfil"],
        colores=colores,
        clasificador=clasificador,
        cfg_equipos=cfg_equipos,
    )

    equipos: dict[int, str] = {}
    if clasificador is not None:
        equipos = clasificar_identidades(
            identidades, colores, clasificador, cfg_equipos
        )

    # Fase post-clasificación (consolidación + interpolación), compartida
    # con el banco: src/tracking/perfiles.py::postprocesar.
    from src.tracking.perfiles import postprocesar
    from src.tracking.resolucion import desde_config

    # Escalado por resolución local: sin él, los umbrales en m/s valen lo
    # mismo donde 1 píxel son 2 cm que donde son 44 (ver el bloque
    # `escalado_resolucion` de configs/tracking_benja.yaml). Es None
    # salvo que la config lo pida, así que el F11 no cambia.
    resolucion = desde_config(
        cfg_tracking,
        cfg["rutas"]["homografia"],
        cfg["campo_m"]["largo"],
        cfg["campo_m"]["ancho"],
    )
    frames_ts = [(e["frame_idx"], e["t"]) for e in datos["cache"]]
    # El suavizado necesita el dt REAL de este caché (varía con fps y
    # submuestreo), no un valor por defecto.
    if cfg_tracking.get("suavizado", {}).get("activo", False):
        cfg_tracking["suavizado"]["dt"] = (
            datos["sample"] / datos["fps"] if datos["fps"] else 0.12
        )

    trayectorias, equipos = postprocesar(
        identidades,
        equipos,
        frames_ts,
        cfg_tracking,
        resolucion=resolucion,
        perfil=cfg["tracking"]["perfil"],
    )

    # Colores REALES de cada equipo (del prototipo del clasificador), para
    # que el replay no tenga que pintar de azul y rojo por convenio.
    colores_equipo = clasificador.colores_equipos() if clasificador else {}

    return exportar_posiciones(
        trayectorias,
        equipos,
        datos,
        cfg,
        trayectorias=trayectorias,
        colores_equipo=colores_equipo,
    )


def exportar_posiciones(
    identidades,
    equipos: dict[int, str],
    datos: dict,
    cfg: dict,
    trayectorias=None,
    colores_equipo: dict | None = None,
) -> pd.DataFrame:
    """Escribe el CSV de posiciones y el meta JSON (formato compatible).

    Columnas: frame, tiempo_s, id_jugador, equipo (0=A, 1=B, 2=otro;
    porteros con su equipo) y etiqueta (A/B/portero_A/portero_B/otro).

    Args:
        trayectorias: salida de interpolar_identidades (una lista de
            (frame_idx, pos, es_real) por identidad, en el MISMO orden que
            `identidades`). Si se pasa, el CSV sale de las trayectorias
            (posiciones reales + interpoladas); si no, de los tracklets.
    """
    fps = datos["fps"]
    largo, ancho = cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]
    margen = cfg["campo_m"]["margen"]

    # Observaciones (frame, pos, es_real) por identidad
    if trayectorias is not None:
        observaciones = [list(tray) for tray in trayectorias]
    else:
        observaciones = [
            [
                (frame_idx, pos, True)
                for tracklet in identidad
                for pos, (frame_idx, _det) in zip(tracklet.pos, tracklet.det_idxs)
            ]
            for identidad in identidades
        ]

    filas = []
    for id_identidad, obs_identidad in enumerate(observaciones, start=1):
        etiqueta = equipos.get(id_identidad, "otro")
        entero = EQUIPO_A_ENTERO.get(etiqueta, 2)
        for frame_idx, pos, es_real in obs_identidad:
            mx, my = float(pos[0]), float(pos[1])
            if not (-margen <= mx <= largo + margen):
                continue
            if not (-margen <= my <= ancho + margen):
                continue
            filas.append(
                {
                    "frame": int(frame_idx),
                    "tiempo_s": round(frame_idx / fps, 2),
                    "id_jugador": id_identidad,
                    "equipo": entero,
                    "etiqueta": etiqueta,
                    "x_m": round(mx, 2),
                    "y_m": round(my, 2),
                    # 1 = detección real; 0 = posición interpolada. El
                    # informe las usa todas (cobertura); el replay filtra
                    # las interpoladas "viejas" para no pintar ficción.
                    "es_real": int(bool(es_real)),
                }
            )
    df = pd.DataFrame(filas).sort_values(["frame", "id_jugador"])

    Path(cfg["rutas"]["salida_csv"]).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cfg["rutas"]["salida_csv"], index=False)

    meta = {
        "fecha_proceso": datetime.now().isoformat(timespec="seconds"),
        "fps_original": datos["fps"],
        "sample_every": datos["sample"],
        "fps_efectivo": round(datos["fps"] / datos["sample"], 2),
        "resolucion": list(datos["wh"]),
        "frames_procesados": len(datos["cache"]),
        "homografia": Path(cfg["rutas"]["homografia"]).name,
        "campo_m": [largo, ancho],
        "total_detecciones": len(filas),
        "ids_unicos": int(df["id_jugador"].nunique()) if len(df) else 0,
        # Campos nuevos del pipeline v2
        "pipeline_version": "v2",
        "perfil_tracking": cfg["tracking"]["perfil"],
        "interpolacion": trayectorias is not None,
        # Color de camiseta de cada equipo, derivado del clasificador
        "colores_equipo": colores_equipo or {},
        "n_identidades": len(identidades),
        "equipos": {
            etiqueta: sum(1 for e in equipos.values() if e == etiqueta)
            for etiqueta in sorted(set(equipos.values()))
        },
    }
    with open(cfg["rutas"]["salida_meta"], "w") as f:
        json.dump(meta, f, indent=2)
    # Las identidades escritas NO son todas las que salieron del tracker:
    # el export descarta las que no dejan ninguna fila válida. Decirlo con
    # `len(identidades)` engaña —86 frente a 40 en el benjamín del v4—, y
    # es la cifra que uno lee para juzgar si hay exceso de fragmentos.
    logger.info(
        "Exportadas %d posiciones de %d identidades (de %d que dio el tracker) (%s)",
        len(filas),
        meta["ids_unicos"],
        len(identidades),
        cfg["rutas"]["salida_csv"],
    )
    return df


def procesar_partido(
    config_path: str = "configs/processor.yaml", modo: str | None = None
) -> pd.DataFrame:
    """Punto de entrada único: despacha según configs/processor.yaml.

    `modo` sobrescribe el del yaml. Existe para poder correr en local
    (desde_cache, sin GPU) el MISMO config que se usa en Colab (full),
    sin duplicarlo ni editarlo cada vez.
    """
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    if modo is not None:
        cfg["modo"] = modo

    if cfg["pipeline"] == "legacy":
        logger.info("Pipeline LEGACY (fallback) — process_video clásico")
        return process_video(
            video_path=cfg["rutas"]["video"],
            model_path=cfg["deteccion"]["modelo"],
            homography_path=cfg["rutas"]["homografia"],
            output_csv=cfg["rutas"]["salida_csv"],
            output_meta=cfg["rutas"]["salida_meta"],
            sample_every=cfg["muestreo"]["sample_every"],
            confidence=cfg["deteccion"]["confianza"],
            device=cfg["deteccion"]["device"],
        )

    if cfg["modo"] == "full":
        detectar_y_cachear(cfg)  # deja los cachés en disco y sigue
    return procesar_desde_cache(cfg)
