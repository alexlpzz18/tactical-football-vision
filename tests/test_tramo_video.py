"""Tests de unidad del recorte de tramo del modo full (_rango_de_frames).

El helper es puro (no necesita vídeo ni GPU): calcula el rango
[frame_ini, frame_fin) de frames ORIGINALES a procesar a partir de la
config de muestreo y los fps del vídeo.
"""

import pytest

from src.tracking_data.processor import _rango_de_frames


def test_sin_limites_procesa_todo():
    assert _rango_de_frames({"sample_every": 3}, fps=25.0) == (0, None)


def test_tramo_min5_60s_reproduce_el_tramo_de_validacion():
    """min 5 durante 60 s a 25 fps → frames globales [7500, 9000)."""
    cfg = {"sample_every": 3, "tramo": {"min_ini": 5.0, "dur_seg": 60.0}}
    assert _rango_de_frames(cfg, fps=25.0) == (7500, 9000)


def test_max_frames_solo():
    cfg = {"sample_every": 3, "max_frames": 1500}
    assert _rango_de_frames(cfg, fps=25.0) == (0, 1500)


def test_tramo_y_max_frames_manda_el_mas_corto():
    """max_frames acota DENTRO del tramo (fin relativo al inicio del tramo)."""
    cfg = {
        "sample_every": 3,
        "tramo": {"min_ini": 5.0, "dur_seg": 60.0},
        "max_frames": 500,
    }
    assert _rango_de_frames(cfg, fps=25.0) == (7500, 8000)
    # y si max_frames es más largo que el tramo, manda el tramo
    cfg["max_frames"] = 99999
    assert _rango_de_frames(cfg, fps=25.0) == (7500, 9000)


def test_fps_no_entero_redondea():
    """A 29.97 fps el inicio cae en el frame entero más cercano."""
    cfg = {"sample_every": 3, "tramo": {"min_ini": 1.0, "dur_seg": 10.0}}
    ini, fin = _rango_de_frames(cfg, fps=29.97)
    assert ini == round(60 * 29.97)  # 1798
    assert fin == ini + round(10 * 29.97)  # +300


def test_tramo_nulo_equivale_a_ausente():
    """tramo: null en el yaml no debe romper (dict vacío u omitido)."""
    assert _rango_de_frames({"sample_every": 3, "tramo": None}, fps=25.0) == (0, None)


def test_tramo_fraccional():
    """min_ini admite fracciones de minuto (p. ej. 2.5 = min 2:30)."""
    cfg = {"sample_every": 3, "tramo": {"min_ini": 2.5, "dur_seg": 30.0}}
    ini, fin = _rango_de_frames(cfg, fps=25.0)
    assert ini == pytest.approx(3750)
    assert fin == pytest.approx(3750 + 750)


# ── posicionamiento en el vídeo ───────────────────────────────────────


def _video_sintetico(ruta, n_frames=90, w=160, h=120):
    """Vídeo donde cada frame lleva ESCRITO su número, en su propio brillo.

    Cada frame es de un gris uniforme igual a 2·i, así se puede saber sin
    ambigüedad qué frame se ha leído. El paso de 2 y el frame uniforme
    dejan margen de sobra para el ruido del códec.
    """
    import cv2
    import numpy as np

    for fourcc, ext in (("avc1", ".mp4"), ("mp4v", ".mp4"), ("MJPG", ".avi")):
        destino = ruta.with_suffix(ext)
        escritor = cv2.VideoWriter(
            str(destino), cv2.VideoWriter_fourcc(*fourcc), 30, (w, h)
        )
        if not escritor.isOpened():
            escritor.release()
            continue
        for i in range(n_frames):
            escritor.write(np.full((h, w, 3), 2 * i, dtype=np.uint8))
        escritor.release()
        if cv2.VideoCapture(str(destino)).read()[0]:
            return destino
    pytest.skip("ningún códec disponible para escribir el vídeo de prueba")


def test_posicionar_deja_el_video_en_el_frame_pedido(tmp_path):
    """Regresión del bug del benjamín (10-ago-2026).

    `cap.set(POS_FRAMES, 8991)` dejaba el vídeo en el 9292 — 301 frames,
    10 segundos — y el vídeo de diagnóstico pintaba cajas correctas sobre
    el fotograma equivocado. El desajuste parecía espacial (creciente
    hacia los bordes) porque los jugadores cercanos recorren muchos más
    píxeles por frame que los lejanos.
    """
    import cv2

    from src.tracking_data.processor import posicionar_en_frame

    ruta = _video_sintetico(tmp_path / "v.mp4")
    for objetivo in (0, 1, 37, 64, 89):
        cap = cv2.VideoCapture(str(ruta))
        posicionar_en_frame(cap, objetivo)
        ok, frame = cap.read()
        cap.release()
        assert ok, f"no se pudo leer tras posicionar en {objetivo}"
        leido = int(round(float(frame.mean()) / 2))
        assert leido == objetivo, (
            f"se pidió el frame {objetivo} y se leyó el {leido}: "
            "las cajas irían sobre el fotograma equivocado"
        )


def test_posicionar_avisa_si_el_tramo_excede_el_video(tmp_path):
    import cv2

    from src.tracking_data.processor import posicionar_en_frame

    ruta = _video_sintetico(tmp_path / "v.mp4", n_frames=30)
    cap = cv2.VideoCapture(str(ruta))
    with pytest.raises(RuntimeError, match="No se pudo posicionar"):
        posicionar_en_frame(cap, 500)
    cap.release()
