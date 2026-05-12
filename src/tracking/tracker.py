import supervision as sv
from ultralytics import YOLO
import numpy as np


class PlayerTracker:
    """
    Clase que combina detección YOLOv8 con tracking ByteTrack.
    Asigna IDs persistentes a cada jugador detectado.
    """

    def __init__(self, model_path: str, confidence: float = 0.3):
        """
        Args:
            model_path: Ruta al archivo de pesos .pt del modelo entrenado
            confidence: Umbral de confianza mínimo para aceptar una detección
        """
        # Cargamos el modelo YOLOv8 entrenado
        self.model = YOLO(model_path)

        # Inicializamos ByteTracker con supervision
        # track_activation_threshold: confianza mínima para activar un nuevo track
        # lost_track_buffer: frames que esperamos antes de eliminar un track perdido
        # minimum_matching_threshold: IoU mínimo para asociar detección con track
        self.tracker = sv.ByteTracker(
            track_activation_threshold=confidence,
            lost_track_buffer=150,
            minimum_matching_threshold=0.8,
            frame_rate=30
        )

        self.confidence = confidence

    def detect_and_track(self, frame: np.ndarray) -> sv.Detections:
        """
        Procesa un frame: detecta jugadores y asigna IDs de tracking.

        Args:
            frame: imagen en formato numpy array (BGR, como la lee OpenCV)

        Returns:
            sv.Detections: objeto con bounding boxes, confianzas e IDs de tracking
        """
        # Paso 1: detección con YOLO
        results = self.model(frame, conf=self.confidence, verbose=False)[0]

        # Paso 2: convertimos el resultado de YOLO al formato de supervision
        detections = sv.Detections.from_ultralytics(results)

        # Paso 3: pasamos las detecciones por ByteTrack
        # ByteTrack asocia cada detección con un ID persistente
        tracked_detections = self.tracker.update_with_detections(detections)

        return tracked_detections