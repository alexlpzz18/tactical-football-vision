"""
Procesador de vídeo → tracking data.
Recorre un vídeo, corrige distorsión, detecta/trackea jugadores,
clasifica equipos y proyecta posiciones a metros con la homografía.
Produce una tabla de posiciones (CSV) + metadatos (JSON).
"""

import cv2
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

from src.tracking.tracker import PlayerTracker
from src.team_classification.classifier import TeamClassifier


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
    confidence: float = 0.3,
    field_length: float = 100.0,
    field_width: float = 64.0,
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
    """
    # ── Cargar homografía, modelo y clasificador ──
    H = np.load(homography_path)
    tracker = PlayerTracker(model_path, confidence)
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

        # 2. Detectar y trackear
        detections = tracker.detect_and_track(frame)

        # 3. Entrenar el clasificador de equipos (primeros 30 frames válidos)
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

        # 4. Clasificar equipos
        if classifier_fitted and len(detections) > 0:
            team_ids = classifier.predict(frame, detections)
        else:
            team_ids = np.zeros(len(detections), dtype=int)

        # 5. Proyectar cada jugador y guardar una fila
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
        "total_detecciones": len(filas),
        "ids_unicos": int(df["id_jugador"].nunique()) if len(df) else 0,
    }
    with open(output_meta, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n✓ Guardadas {len(filas)} posiciones en {output_csv}")
    print(f"✓ Metadatos en {output_meta}")
    print(f"  IDs únicos detectados: {meta['ids_unicos']}")
    return df
