import cv2
import numpy as np
import supervision as sv
from pathlib import Path
import argparse

from src.tracking.tracker import PlayerTracker
from src.team_classification.classifier import TeamClassifier


# Colores para cada equipo en formato BGR (azul, verde, rojo)
TEAM_COLORS = {
    0: (255, 50, 50),    # Equipo A — azul
    1: (50, 50, 255),    # Equipo B — rojo
    2: (50, 255, 255),   # Árbitro — amarillo
}


def annotate_frame(
    frame: np.ndarray,
    detections: sv.Detections,
    team_ids: np.ndarray
) -> np.ndarray:
    annotated = frame.copy()

    for i, (bbox, tracker_id) in enumerate(
        zip(detections.xyxy, detections.tracker_id)
    ):
        if tracker_id is None:
            continue

        x1, y1, x2, y2 = map(int, bbox)

        team_id = int(team_ids[i]) if len(team_ids) > i else 0
        color = TEAM_COLORS.get(team_id, (255, 255, 255))

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        label = f"#{tracker_id}"
        cv2.putText(
            annotated,
            label,
            (x1, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2
        )

    return annotated


def run_pipeline(
    video_path: str,
    model_path: str,
    output_path: str,
    confidence: float = 0.3
) -> None:
    tracker = PlayerTracker(model_path, confidence)
    classifier = TeamClassifier(n_teams=2)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"Error: no se puede abrir el vídeo {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"Vídeo: {video_path}")
    print(f"Resolución: {width}x{height} @ {fps}fps")
    print(f"Total frames: {total_frames}")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_count = 0
    classifier_fitted = False
    training_frames = []  # acumulamos frames para entrenar con más variedad

    print("Procesando vídeo...")

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        detections = tracker.detect_and_track(frame)

        # Acumulamos los primeros 30 frames con suficientes jugadores
        if not classifier_fitted:
            if len(detections) >= 3:
                training_frames.append((frame, detections))

            if len(training_frames) >= 30:
                classifier.fit_multiple(
                    [f for f, d in training_frames],
                    [d for f, d in training_frames]
                )
                classifier_fitted = True
                print(f"Clasificador entrenado con {len(training_frames)} frames")

        if classifier_fitted:
            team_ids = classifier.predict(frame, detections)
        else:
            team_ids = np.zeros(len(detections), dtype=int)

        annotated_frame = annotate_frame(frame, detections, team_ids)
        out.write(annotated_frame)

        frame_count += 1

        if frame_count % 100 == 0:
            progress = (frame_count / total_frames) * 100
            print(f"Progreso: {progress:.1f}% ({frame_count}/{total_frames})")

    cap.release()
    out.release()

    print(f"Vídeo procesado guardado en: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline completo de análisis táctico de fútbol"
    )
    parser.add_argument("--video", required=True, help="Ruta al vídeo de entrada")
    parser.add_argument("--model", required=True, help="Ruta al modelo YOLOv8 entrenado (.pt)")
    parser.add_argument("--output", required=True, help="Ruta donde guardar el vídeo de salida")
    parser.add_argument("--confidence", type=float, default=0.3, help="Umbral de confianza (default: 0.3)")
    args = parser.parse_args()

    run_pipeline(
        video_path=args.video,
        model_path=args.model,
        output_path=args.output,
        confidence=args.confidence
    )


if __name__ == "__main__":
    main()