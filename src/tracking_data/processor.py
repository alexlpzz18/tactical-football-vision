"""
Procesador de vídeo → tracking data.
Recorre un vídeo, corrige distorsión, detecta jugadores con SAHI (inferencia
por recortes), los trackea, clasifica equipos y proyecta posiciones a metros
con la homografía. Produce una tabla de posiciones (CSV) + metadatos (JSON).
"""

import hashlib
import json
import logging
import os
import pickle
import tempfile
import time
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
        frame = _corregir_distorsion(frame, K, dist)

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


def _corregir_distorsion(frame, K, dist):
    """Corrige la distorsión de lente, SALTÁNDOSE el trabajo si no hay.

    Con k1=k2=0 el mapa de `cv2.undistort` es la identidad y devuelve el
    frame bit a bit igual (comprobado sobre 10 frames reales del vídeo del
    benjamín), pero el remap se hace igual: 27,8 ms por frame a 1080p en
    este Mac. Sobre los 11.988 frames de una parte entera son **5,6
    minutos de CPU tirados**, y en Colab la CPU es la que alimenta a la
    GPU. La cámara del benjamín no es gran angular y su config tiene
    k1=k2=0 a propósito, así que este atajo es todo el ahorro y ningún
    cambio de resultado. Villaviciosa sí distorsiona y no entra por aquí.
    """
    if float(dist[0]) == 0.0 and float(dist[1]) == 0.0:
        return frame
    return cv2.undistort(frame, K, dist)


def _firma_de_deteccion(cfg: dict) -> dict:
    """Lo que tiene que coincidir para poder REANUDAR un caché a medias.

    Reanudar sobre un caché hecho con otro modelo, otra confianza u otro
    tramo mezclaría dos detectores en el mismo fichero, y los umbrales de
    asociación van pegados al detector (CLAUDE.md). Antes que arriesgar
    eso se rehace la pasada.
    """
    # La homografía va por CONTENIDO, no por ruta: recalibrar no cambia el
    # nombre del fichero, y es lo que produce (mx, my). Medido: reanudar
    # con una H desplazada 3 px mete un salto de 12,23 m entre la parte
    # vieja y la nueva del MISMO caché — indistinguible de un fallo de
    # asociación.
    huella_h = None
    try:
        huella_h = hashlib.sha256(
            np.load(cfg["rutas"]["homografia"]).tobytes()
        ).hexdigest()
    except (OSError, ValueError, KeyError):
        huella_h = str(cfg["rutas"].get("homografia"))
    firma = {
        "video": cfg["rutas"]["video"],
        "homografia": huella_h,
        # Cambiar la versión de la feature cambia su LONGITUD (256 vs
        # 336): reanudar mezclaría vectores de dos tamaños bajo las
        # mismas claves.
        "version_color": cfg["deteccion"].get("version_color"),
        "modelo": cfg["deteccion"]["modelo"],
        "confianza": cfg["deteccion"]["confianza"],
        "max_area_caja": cfg["deteccion"]["max_area_caja"],
        "sahi": dict(cfg["deteccion"]["sahi"]),
        "k1": cfg["distorsion"]["k1"],
        "k2": cfg["distorsion"]["k2"],
        "sample_every": cfg["muestreo"]["sample_every"],
        "tramo": dict(cfg["muestreo"].get("tramo") or {}),
        "max_frames": cfg["muestreo"].get("max_frames"),
    }
    # La banda del chaleco entra en la firma SOLO si está puesta: así una caché sin chaleco (F11)
    # conserva su firma y su reanudación, y no se reanuda una pasada con chaleco sobre otra que no
    # lo tenía (quedaría a medias).
    if banda_chaleco(cfg) is not None:
        firma["chaleco_banda"] = list(banda_chaleco(cfg))
    return firma


def _volcar(ruta: str, objeto) -> None:
    """Escribe un pickle de forma ATÓMICA (temporal + rename).

    Un checkpoint que se corta a medias es peor que no tener checkpoint:
    dejaría un .pkl truncado donde antes había uno bueno. Con el rename
    del final, o está el anterior o está el nuevo, nunca medio fichero.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # Nombre ÚNICO por escritor: con un `.tmp` fijo, dos procesos sobre la
    # misma config abren el mismo fichero en modo "wb" e intercalan bytes
    # en el mismo inodo. El resultado carga sin error y mezcla contenido
    # de los dos (medido: 1 de cada 12 intentos con 4 procesos).
    descriptor, tmp = tempfile.mkstemp(dir=str(ruta.parent), suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as f:
            pickle.dump(objeto, f)
        os.replace(tmp, ruta)
    except BaseException:
        # Un volcado a medias no deja basura: el fichero bueno anterior
        # sigue en su sitio y el temporal se borra.
        Path(tmp).unlink(missing_ok=True)
        raise


def _guardar_caches(
    cfg, cache, colores, fps, sample, wh, completo, firma, chaleco=None
) -> None:
    """Vuelca los dos cachés. `completo` distingue final de checkpoint.

    ⚠️ EL ORDEN NO ES INDIFERENTE: los colores PRIMERO y las detecciones
    AL FINAL. El ancla de la reanudación es el caché de detecciones (es
    el que lleva la firma y el último `frame_idx`), así que tiene que ser
    lo último que toca el disco.

    Al revés —detecciones primero— una muerte de sesión entre los dos
    volcados deja las detecciones POR DELANTE de los colores, `_reanudar`
    acepta el checkpoint porque firma y `completo` están bien, y la
    pasada termina con un caché que se marca `completo: True` y tiene
    AGUJEROS: frames con detecciones y sin feature de color. Nadie se
    queja aguas abajo —`pipeline_equipos`, `arbitro` y `puerta_reentrada`
    descartan en silencio la observación sin feature— así que esas
    detecciones simplemente no reciben etiqueta de equipo.

    Y la ventana no es estrecha: el caché de colores pesa más de 20× el
    de detecciones, así que era la mayor parte de cada volcado. Con este
    orden, una muerte a mitad deja los COLORES por delante, que es
    inocuo: se reprocesan y se sobrescriben.
    """
    _volcar(cfg["rutas"]["cache_colores"], colores)
    datos = {
        "cache": cache,
        "fps": fps,
        "sample": sample,
        "wh": wh,
        "completo": completo,
        "firma": firma,
    }
    # La puntuación de chaleco va DENTRO de la caché de detección (es pequeña: ~3 MB en una
    # parte entera), así que llega a disco en el mismo volcado que su ancla.
    if chaleco is not None and banda_chaleco(cfg) is not None:
        datos["chaleco"] = chaleco
    _volcar(cfg["rutas"]["cache"], datos)


def _chaleco_previo(cfg) -> dict:
    """La puntuación de chaleco del checkpoint (o {} si no la tenía)."""
    try:
        with open(cfg["rutas"]["cache"], "rb") as f:
            return dict(pickle.load(f).get("chaleco") or {})
    except (OSError, pickle.UnpicklingError, EOFError):
        return {}


def _reanudar(cfg, firma):
    """Recupera un checkpoint compatible, o (None, None) si no lo hay."""
    ruta = Path(cfg["rutas"]["cache"])
    if not ruta.exists():
        return None, None
    try:
        with open(ruta, "rb") as f:
            previo = pickle.load(f)
        with open(cfg["rutas"]["cache_colores"], "rb") as f:
            colores = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError) as err:
        logger.warning("No se pudo leer el caché previo (%s); se rehace.", err)
        return None, None
    if previo.get("firma") != firma:
        logger.warning(
            "Hay un caché en %s hecho con OTRA configuración de detección: "
            "se ignora y se SOBRESCRIBE. (Si lo querías, muévelo antes.)",
            ruta,
        )
        return None, None
    if previo.get("completo"):
        logger.warning(
            "Hay un caché COMPLETO en %s con esta misma configuración: se "
            "sobrescribe. (Si lo querías, muévelo antes.)",
            ruta,
        )
        return None, None
    if not previo.get("cache"):
        return None, None
    return previo["cache"], colores


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


def banda_chaleco(cfg: dict):
    """La banda HSV del chaleco del árbitro (`deteccion.chaleco_banda`) o None si no está puesta."""
    banda = (cfg.get("deteccion") or {}).get("chaleco_banda")
    if banda is None:
        return None
    if len(banda) != 4:
        raise ValueError(
            f"deteccion.chaleco_banda tiene que ser [H0, H1, S0, V0]: {banda!r}"
        )
    return tuple(float(v) for v in banda)


def features_del_frame(frame, frame_idx, dets, extractor, rango=None, banda=None):
    """Lo que se calcula de cada detección DESPUÉS de SAHI, sobre el mismo fotograma corregido.

    - la feature de color (la ÚNICA función de extracción del repo);
    - con `banda`, la puntuación de chaleco del árbitro (src/team_classification/chaleco.py).

    Está aparte del bucle para poder probarlo sin GPU: con las cajas de una caché y los fotogramas
    del decodificador de producción tiene que dar lo mismo que la pasada original
    (docs/diagnostico_23oct_f.md, bloque 1).

    Returns:
        (colores {(frame, det): feature}, chaleco {(frame, det): fracción} o {} sin banda)
    """
    colores = {}
    for det_idx, d in enumerate(dets):
        x1, y1, x2, y2 = (int(v) for v in d[2:6])
        y1, x1 = max(y1, 0), max(x1, 0)
        crop = frame[y1:y2, x1:x2]
        if crop.size > 0:
            # ÚNICA función de extracción del repo (normalización L2,
            # la escala en la que están calibrados todos los umbrales)
            feat = (
                extractor(crop)
                if rango is None
                else extractor(crop, rango_cesped=rango)
            )
            if feat.sum() > 0:
                colores[(frame_idx, det_idx)] = feat
    chaleco = {}
    if banda is not None:
        from src.team_classification.chaleco import puntuaciones_del_frame

        chaleco = puntuaciones_del_frame(frame, frame_idx, dets, banda)
    return colores, chaleco


def comprobar_chaleco_antes_de_detectar(cfg: dict) -> None:
    """Falla ANTES de gastar GPU si el config es incoherente con la pista del árbitro.

    Pasó el 25-oct en Colab (docs/diagnostico_25oct_chaleco_colab.md): un config F7 (pista
    encendida por el formato) con `deteccion.chaleco_banda: null` y sin `rutas.cache_chaleco` hacía
    la pasada de detección ENTERA y solo al final, en `desde_cache`, descubría que no había
    puntuación de chaleco. La tabla por formato solo se consultaba en la ruta de caché.

    Raises:
        ValueError: pista encendida, sin banda y sin caché de chaleco aparte.
    """
    from src.team_classification.pipeline_equipos import cargar_config_equipos

    cfg_equipos = (
        cargar_config_equipos(cfg["config_equipos"])
        if cfg.get("config_equipos")
        else {}
    )
    if not viterbi_activo(cfg_equipos):
        return
    if banda_chaleco(cfg) is not None or (cfg.get("rutas") or {}).get("cache_chaleco"):
        return
    raise ValueError(
        "Config INCOHERENTE, antes de detectar: arbitro.viterbi está ENCENDIDO (por el formato "
        "del partido o por el YAML de equipos) pero `deteccion.chaleco_banda` es null y no hay "
        "`rutas.cache_chaleco`, así que la pasada no guardaría la puntuación de chaleco y "
        "`desde_cache` fallaría al final. Pon la banda (F7: [38, 48, 112, 173]), o "
        "`rutas.cache_chaleco`, o apaga la pista con `arbitro.viterbi.activo: false`."
    )


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
    # Máscara de la feature: «verde» (la de siempre, por defecto) o «posicion»
    # (el césped medido en cada frame; docs/diagnostico_22oct_b.md, bloque 3).
    mascara_color = str(cfg.get("deteccion", {}).get("mascara_color", "verde"))
    if mascara_color not in ("verde", "posicion"):
        raise ValueError(f"deteccion.mascara_color desconocida: {mascara_color!r}")
    if mascara_color == "posicion" and version_color >= 2:
        raise ValueError(
            "La máscara por posición solo está implementada para la feature v1"
        )

    validar_config(cfg, _CLAVES_FULL)
    comprobar_chaleco_antes_de_detectar(cfg)  # antes de cargar el modelo y gastar GPU
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

    # ── Checkpoint y progreso ────────────────────────────────────────
    #
    # Antes de esto el caché se escribía UNA vez, al final del bucle, y no
    # se imprimía nada mientras corría. Sobre una parte entera son 45-60
    # min de GPU en los que una caída de sesión lo perdía todo y en los
    # que no se distinguía "va bien" de "colgado".
    cfg_ck = cfg.get("checkpoint") or {}
    cada = int(cfg_ck.get("cada_frames", 500) or 0)
    firma = _firma_de_deteccion(cfg)

    # Puntuación de chaleco del árbitro (F7; en F11 no hay banda medida y no se calcula)
    banda = banda_chaleco(cfg)
    cache, colores, chaleco = [], {}, {}
    frame_idx = frame_ini
    if cada and cfg_ck.get("reanudar", True):
        previo, colores_previos = _reanudar(cfg, firma)
        if previo:
            cache, colores = previo, colores_previos
            chaleco = _chaleco_previo(cfg)
            frame_idx = cache[-1]["frame_idx"] + 1
            # Si el checkpoint cayó justo en el último frame no queda nada
            # que hacer. Sin esto, `posicionar_en_frame` lanza culpando al
            # `tramo`, que no tiene nada que ver, y encima en la pasada que
            # ya estaba terminada.
            total_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fin_previsto = frame_fin if frame_fin is not None else total_video
            if fin_previsto and frame_idx >= fin_previsto:
                cap.release()
                logger.info(
                    "El checkpoint ya llegaba al final (%d frames): se cierra "
                    "sin reprocesar nada.",
                    len(cache),
                )
                _guardar_caches(
                    cfg, cache, colores, fps, sample, (w, h), True, firma, chaleco
                )
                return (
                    {"cache": cache, "fps": fps, "sample": sample, "wh": (w, h)},
                    colores,
                )
            posicionar_en_frame(cap, frame_idx)
            logger.info(
                "REANUDANDO: %d frames ya cacheados, se sigue desde el %d "
                "(t=%.1f s)",
                len(cache),
                frame_idx,
                frame_idx / fps,
            )

    # Cuántos frames se van a procesar en total, para el porcentaje y la
    # estimación. Si no hay tope, manda la longitud del vídeo.
    fin_real = frame_fin
    if fin_real is None:
        total_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fin_real = total_video if total_video > 0 else None
    a_procesar = (fin_real - frame_ini) // sample if fin_real else None
    t_arranque = time.time()
    hechos_esta_sesion = 0

    while True:
        if frame_fin is not None and frame_idx >= frame_fin:
            break
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample != 0:
            frame_idx += 1
            continue
        frame = _corregir_distorsion(frame, K, dist_lente)
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
        rango = None
        if mascara_color == "posicion":
            from src.team_classification.mascara_posicion import rango_cesped_del_frame

            rango = rango_cesped_del_frame(
                frame,
                [d[2:6] for d in dets],
                lambda u, v: project_point(u, v, H),
                (cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]),
            )
        colores_f, chaleco_f = features_del_frame(
            frame, frame_idx, dets, extractor, rango, banda
        )
        colores.update(colores_f)
        chaleco.update(chaleco_f)
        cache.append({"frame_idx": frame_idx, "t": frame_idx / fps, "dets": dets})
        frame_idx += 1
        hechos_esta_sesion += 1
        if cada and hechos_esta_sesion % cada == 0:
            _guardar_caches(
                cfg, cache, colores, fps, sample, (w, h), False, firma, chaleco
            )
            ritmo = (time.time() - t_arranque) / hechos_esta_sesion
            if a_procesar:
                faltan = max(a_procesar - len(cache), 0) * ritmo
                logger.info(
                    "%d/%d frames (%.0f %%) · %.0f ms/frame · faltan ~%.0f min "
                    "· checkpoint guardado",
                    len(cache),
                    a_procesar,
                    100 * len(cache) / a_procesar,
                    1000 * ritmo,
                    faltan / 60,
                )
            else:
                logger.info(
                    "%d frames · %.0f ms/frame · checkpoint guardado",
                    len(cache),
                    1000 * ritmo,
                )
    cap.release()

    _guardar_caches(cfg, cache, colores, fps, sample, (w, h), True, firma, chaleco)
    datos = {"cache": cache, "fps": fps, "sample": sample, "wh": (w, h)}
    if banda is not None:
        datos["chaleco"] = chaleco
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
        etiquetar_por_observacion,
    )
    from src.tracking.cache_io import cargar_cache
    from src.tracking.filtro_confianza import filtrar_por_confianza
    from src.tracking.plausibilidad_fisica import filtrar_por_plausibilidad
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

    # Filtro de PLAUSIBILIDAD FÍSICA, en el mismo sitio y por la misma
    # razón. Usa la escala del suelo que da la homografía para preguntar
    # cuánto mide en metros lo que hay dentro de cada caja: una línea del
    # campo mide 0,22 m de ancho y la persona real más estrecha 0,39, así
    # que hay hueco. Ver src/tracking/plausibilidad_fisica.py.
    cfg_fisica = cfg_tracking.get("plausibilidad_fisica", {}) or {}
    if cfg_fisica.get("activo", False):
        homografia_f = np.load(cfg["rutas"]["homografia"])
        datos["cache"], colores, _n = filtrar_por_plausibilidad(
            datos["cache"],
            colores,
            homografia_f,
            **{k: v for k, v in cfg_fisica.items() if k != "activo"},
        )

    # Caché de embeddings de apariencia (opcional). Se filtra con el
    # MISMO criterio de confianza que el resto: si no, sus det_idx
    # apuntarían a otras cajas — el fallo silencioso de siempre.
    embeddings = None
    ruta_emb = cfg["rutas"].get("cache_embeddings")
    if ruta_emb and Path(ruta_emb).exists():
        with open(ruta_emb, "rb") as f:
            d_emb = pickle.load(f)
        V = np.asarray(d_emb["embeddings"], dtype=np.float32)
        crudo = {tuple(c): V[i] for i, c in enumerate(d_emb["claves"])}
        if conf_min > 0:
            datos_crudos = cargar_cache(cfg["rutas"]["cache"])
            embeddings = {}
            for e in datos_crudos["cache"]:
                fr, j = e["frame_idx"], 0
                for i, det in enumerate(e["dets"]):
                    if det[6] < conf_min:
                        continue
                    if (fr, i) in crudo:
                        embeddings[(fr, j)] = crudo[(fr, i)]
                    j += 1
        else:
            embeddings = crudo
        logger.info(
            "Caché de embeddings: %s (%d vectores, backbone %s)",
            ruta_emb,
            len(embeddings),
            d_emb.get("backbone", "?"),
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
        embeddings=embeddings,
    )

    equipos: dict[int, str] = {}
    if clasificador is not None:
        equipos = clasificar_identidades(
            identidades, colores, clasificador, cfg_equipos
        )
    # TOPE DE CARDINALIDAD (docs/diagnostico_22oct_e.md, bloque 1), APAGADO por defecto: las
    # identidades se etiquetan juntas respetando «≤ 7 por equipo y ≤ 1 árbitro» en cada frame.
    # Porteros y staff se quedan como los decidieron sus reglas. Con él encendido, la etiqueta es
    # por identidad y no se corre el voto por observación (rompería los topes).
    cfg_tope = (cfg.get("equipos") or {}).get("tope_cardinalidad") or {}
    tope_activo = clasificador is not None and bool(cfg_tope.get("activo", False))
    if tope_activo:
        from src.team_classification.tope_cardinalidad import etiquetar_con_tope

        equipos, etiquetas_tope = etiquetar_con_tope(
            identidades, equipos, colores, clasificador, cfg_equipos, cfg_tope
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

    # Etiqueta por OBSERVACIÓN, si el config de este partido la pide. Se
    # calcula ANTES del post-proceso porque necesita los recortes, y el
    # post-proceso ya trabaja con trayectorias interpoladas.
    ocluidas_obs = None
    cfg_por_obs = (cfg_equipos or {}).get("agregacion", {}).get("por_observacion", {})
    if cfg_por_obs.get("excluir_ocluidas", False):
        from src.team_classification.oclusion import detecciones_ocluidas

        ocluidas_obs = detecciones_ocluidas(
            datos["cache"], iou_max=float(cfg_por_obs.get("ocluidas_iou", 0.10))
        )
    # Puerta de calidad de caja (flag apagado; docs/diagnostico_28oct_g.md): las cajas anormales
    # para su posición no votan el color de la ventana.
    anormales_obs = None
    cfg_anormales = cfg_por_obs.get("excluir_cajas_anormales") or {}
    if cfg_anormales.get("activo", False):
        from src.team_classification.calidad_caja import cajas_anormales

        anormales_obs = cajas_anormales(
            datos["cache"],
            alto_max=float(cfg_anormales["alto_max"]),
            ancho_max=float(cfg_anormales["ancho_max"]),
            alto_min=float(cfg_anormales["alto_min"]),
        )
    if tope_activo:
        etiquetas_por_obs = etiquetas_tope  # vacío con `unidad: identidad`
    else:
        etiquetas_por_obs = (
            etiquetar_por_observacion(
                identidades,
                equipos,
                colores,
                clasificador,
                cfg_equipos,
                ocluidas_obs,
                anormales_obs,
            )
            if clasificador is not None
            else {}
        )

    # EL ÁRBITRO COMO SEGUIMIENTO DE UN ÚNICO OBJETO (flag `arbitro.viterbi` del YAML de
    # equipos, apagado; docs/diagnostico_23oct_c.md): una sola pista por partido, por el chaleco
    # visto en píxeles (caché de chaleco) y la continuidad de movimiento. Sus filas pasan a 'otro'.
    # ADOPCIÓN PREPARADA (rama `adopcion-viterbi`, docs/diagnostico_23oct_e.md): si el YAML no dice
    # `activo`, lo decide el FORMATO del partido (src/campo_modelo.py::DEFECTOS_POR_FORMATO):
    # encendido en F7, apagado en F11. Una clave `activo` explícita manda.
    cfg_vit = ((cfg_equipos or {}).get("arbitro") or {}).get("viterbi") or {}
    if clasificador is not None and viterbi_activo(cfg_equipos):
        from src.team_classification.arbitro_viterbi import (
            ParametrosArbitroViterbi,
            aplicar_pista,
            cargar_modelo_emision,
            pista_del_arbitro,
            reindexar_chaleco,
        )

        params_vit = ParametrosArbitroViterbi.desde_dict({**cfg_vit, "activo": True})
        crudo = cargar_cache(cfg["rutas"]["cache"])
        chaleco = reindexar_chaleco(
            puntuacion_chaleco(cfg, crudo), crudo["cache"], datos["cache"]
        )
        pista = pista_del_arbitro(
            datos["cache"],
            chaleco,
            cargar_modelo_emision(params_vit.modelo_emision),
            params_vit,
            (cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]),
        )
        etiquetas_por_obs = aplicar_pista(
            identidades,
            equipos,
            etiquetas_por_obs,
            pista,
            colores,
            clasificador,
            params_vit,
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
        etiquetas_por_obs=etiquetas_por_obs,
    )


def puntuacion_chaleco(cfg: dict, datos_crudos: dict) -> dict:
    """La puntuación de chaleco por detección, de la caché aparte o de la de detección.

    Por orden: `rutas.cache_chaleco` (la pasada aparte de CPU, `scripts/cache_chaleco.py`) y, si no
    está, la clave `chaleco` de la caché de detección (la escribe el modo `full` cuando el config
    tiene `deteccion.chaleco_banda`). Las dos están indexadas sobre la caché CRUDA.

    Raises:
        ValueError: si no hay ninguna de las dos (la pista está encendida y no puede correr).
    """
    ruta = cfg["rutas"].get("cache_chaleco")
    if ruta:
        with open(ruta, "rb") as fh:
            return pickle.load(fh)
    if datos_crudos.get("chaleco"):
        return datos_crudos["chaleco"]
    raise ValueError(
        "arbitro.viterbi está ENCENDIDO (por el formato del partido o por el YAML) y no hay "
        "puntuación de chaleco: ni rutas.cache_chaleco ni la clave `chaleco` en la caché de "
        "detección. Dos formas de arreglarlo: (1) correr el modo full con "
        "`deteccion.chaleco_banda` en el config, o (2) generar la caché aparte con "
        "scripts/cache_chaleco.py. O apagar la pista con `arbitro.viterbi.activo: false`."
    )


def viterbi_activo(cfg_equipos: dict | None) -> bool:
    """¿Corre la pista del árbitro? La clave `arbitro.viterbi.activo` si está; si no, el FORMATO.

    El formato sale del modelo de campo del config de equipos (`formato_del_partido`) y su valor
    por defecto, de `src/campo_modelo.py::DEFECTOS_POR_FORMATO` (F7 encendido, F11 apagado).
    """
    from src.campo_modelo import defecto_de_formato
    from src.team_classification.pipeline_equipos import formato_del_partido

    cfg_vit = ((cfg_equipos or {}).get("arbitro") or {}).get("viterbi") or {}
    if cfg_vit.get("activo") is not None:
        return bool(cfg_vit["activo"])
    return bool(defecto_de_formato(formato_del_partido(cfg_equipos), "arbitro_viterbi"))


def exportar_posiciones(
    identidades,
    equipos: dict[int, str],
    datos: dict,
    cfg: dict,
    trayectorias=None,
    colores_equipo: dict | None = None,
    etiquetas_por_obs: dict | None = None,
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
        etiqueta_ident = equipos.get(id_identidad, "otro")
        for frame_idx, pos, es_real in obs_identidad:
            # La etiqueta por observación, si la hay, manda sobre la de la
            # identidad. Las posiciones INTERPOLADAS no tienen recorte, así
            # que se quedan con la de su identidad.
            etiqueta = (etiquetas_por_obs or {}).get(
                (id_identidad, frame_idx)
            ) or etiqueta_ident
            entero = EQUIPO_A_ENTERO.get(etiqueta, 2)
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
