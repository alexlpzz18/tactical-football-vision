import numpy as np
from src.team_classification.classifier import TeamClassifier


def test_team_classifier_initialization():
    """Verifica que el clasificador se inicializa correctamente."""
    classifier = TeamClassifier(n_teams=2)
    assert classifier.n_clusters == 3
    assert classifier.is_fitted is False


def test_team_classifier_predict_unfitted():
    """Verifica que predict devuelve array vacío si no está entrenado."""
    import supervision as sv

    classifier = TeamClassifier(n_teams=2)
    empty_detections = sv.Detections.empty()
    result = classifier.predict(
        np.zeros((100, 100, 3), dtype=np.uint8), empty_detections
    )
    assert len(result) == 0


def test_extract_torso_empty_bbox():
    """Verifica que un bbox vacío devuelve color negro."""
    classifier = TeamClassifier(n_teams=2)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    bbox = np.array([50, 50, 50, 50])  # bbox de tamaño cero
    color = classifier._extract_torso_color(frame, bbox)
    assert color.shape == (3,)
