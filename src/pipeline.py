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
    """
    Dibuja bounding boxes, IDs de tracking y colores de equipo
    encima del frame.

    Args:
        frame: imagen original
        detections: detecciones con IDs de tracking
        team_ids: array con el equipo de cada jugador

    Returns:
        frame con las anotaciones dibujadas
    """
    annotated = frame.copy()

    for i, (bbox, tracker_id) in enumerate(
        zip(detections.xyxy, detections.tracker_id)
    ):
        if tracker_id is None:
            continue

        x1, y1, x2, y2 = map(int, bbox)

        # Obtenemos el color del equipo
        team_id = int(team_ids[i]) if len(team_ids) > i else 0
        color = TEAM_COLORS.get(team_id, (255, 255, 255))

        # Dibujamos el bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        # Dibujamos el ID del jugador encima del bounding box
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
    """
    Ejecuta el pipeline completo sobre un vídeo.

    Args:
        video_path: ruta al vídeo de entrada
        model_path: ruta al modelo YOLOv8 entrenado
        output_path: ruta donde guardar el vídeo de salida
        confidence: umbral de confianza para las detecciones
    """
    # Inicializamos los componentes
    tracker = PlayerTracker(model_path, confidence)
    classifier = TeamClassifier(n_teams=2)

    # Abrimos el vídeo
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"Error: no se puede abrir el vídeo {video_path}")
        return

    # Obtenemos propiedades del vídeo
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"Vídeo: {video_path}")
    print(f"Resolución: {width}x{height} @ {fps}fps")
    print(f"Total frames: {total_frames}")

    # Configuramos el escritor de vídeo de salida
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_count = 0
    classifier_fitted = False

    print("Procesando vídeo...")

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        # Detectamos y trackeamos jugadores
        detections = tracker.detect_and_track(frame)

        # Entrenamos el clasificador con el primer frame
        # que tenga suficientes jugadores detectados
        if not classifier_fitted and len(detections) >= 6:
            classifier.fit(frame, detections)
            classifier_fitted = True
            print(f"Clasificador entrenado en frame {frame_count}")

        # Clasificamos equipos si el clasificador está entrenado
        if classifier_fitted:
            team_ids = classifier.predict(frame, detections)
        else:
            team_ids = np.zeros(len(detections), dtype=int)

        # Anotamos el frame
        annotated_frame = annotate_frame(frame, detections, team_ids)

        # Escribimos el frame anotado en el vídeo de salida
        out.write(annotated_frame)

        frame_count += 1

        # Mostramos progreso cada 100 frames
        if frame_count % 100 == 0:
            progress = (frame_count / total_frames) * 100
            print(f"Progreso: {progress:.1f}% ({frame_count}/{total_frames})")

    # Liberamos recursos
    cap.release()
    out.release()

    print(f"Vídeo procesado guardado en: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline completo de análisis táctico de fútbol"
    )
    parser.add_argument(
        "--video",
        required=True,
        help="Ruta al vídeo de entrada"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Ruta al modelo YOLOv8 entrenado (.pt)"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Ruta donde guardar el vídeo de salida"
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.3,
        help="Umbral de confianza (default: 0.3)"
    )
    args = parser.parse_args()

    run_pipeline(
        video_path=args.video,
        model_path=args.model,
        output_path=args.output,
        confidence=args.confidence
    )


if __name__ == "__main__":
    main()