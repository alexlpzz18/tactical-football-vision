import numpy as np
import cv2
from sklearn.cluster import KMeans
from typing import List, Tuple
import supervision as sv


class TeamClassifier:
    """
    Clasifica jugadores en equipos basándose en el color de su camiseta.
    Usa K-Means clustering en el espacio de color HSV.
    """

    def __init__(self, n_teams: int = 2):
        """
        Args:
            n_teams: número de equipos a detectar.
            Usamos 3 por defecto: equipo A, equipo B y árbitro.
        """
        # n_teams + 1 porque incluimos al árbitro como cluster separado
        self.n_clusters = n_teams + 1
        self.kmeans = None
        self.is_fitted = False

    def _extract_torso_color(
        self,
        frame: np.ndarray,
        bbox: np.ndarray
    ) -> np.ndarray:
        """
        Extrae el color dominante del torso de un jugador.

        Args:
            frame: imagen completa en formato BGR
            bbox: bounding box en formato [x1, y1, x2, y2]

        Returns:
            array con el color HSV dominante del torso
        """
        x1, y1, x2, y2 = map(int, bbox)

        # Calculamos la altura del bounding box
        height = y2 - y1

        # Recortamos solo el tercio central (zona del torso)
        # Ignoramos el primer tercio (cabeza) y el último tercio (piernas)
        torso_y1 = y1 + height // 3
        torso_y2 = y1 + (height * 2) // 3

        # Recortamos el torso de la imagen
        torso = frame[torso_y1:torso_y2, x1:x2]

        # Si el recorte está vacío (bbox muy pequeño) devolvemos negro
        if torso.size == 0:
            return np.array([0, 0, 0])

        # Convertimos de BGR (formato OpenCV) a HSV
        torso_hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)

        # Calculamos el color medio del torso en HSV
        mean_color = np.mean(torso_hsv.reshape(-1, 3), axis=0)

        return mean_color

    def fit(
        self,
        frame: np.ndarray,
        detections: sv.Detections
    ) -> None:
        """
        Entrena el clasificador con las detecciones del primer frame.
        K-Means aprende qué colores corresponden a cada equipo.

        Args:
            frame: primer frame del vídeo
            detections: detecciones de jugadores en ese frame
        """
        if len(detections) == 0:
            return

        # Extraemos el color del torso de cada jugador detectado
        colors = []
        for bbox in detections.xyxy:
            color = self._extract_torso_color(frame, bbox)
            colors.append(color)

        colors = np.array(colors)

        # Entrenamos K-Means con los colores extraídos
        self.kmeans = KMeans(
            n_clusters=self.n_clusters,
            random_state=42,
            n_init=10
        )
        self.kmeans.fit(colors)
        self.is_fitted = True

    def predict(
        self,
        frame: np.ndarray,
        detections: sv.Detections
    ) -> np.ndarray:
        """
        Predice el equipo de cada jugador detectado.

        Args:
            frame: frame actual
            detections: detecciones de jugadores

        Returns:
            array con el ID de equipo (0, 1, o 2) para cada jugador
        """
        if not self.is_fitted or len(detections) == 0:
            return np.array([])

        # Extraemos colores de todos los jugadores
        colors = []
        for bbox in detections.xyxy:
            color = self._extract_torso_color(frame, bbox)
            colors.append(color)

        colors = np.array(colors)

        # Predecimos el cluster de cada jugador
        team_ids = self.kmeans.predict(colors)

        return team_ids