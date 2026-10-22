"""Guarda del DECODIFICADOR: antes de medir color, reproducir la caché de producción.

En macOS `cv2.VideoCapture` decodifica con AVFoundation y no coincide con producción (0,27 % de
features idénticas); con el ffmpeg de línea de comandos, el 100 % (`docs/diagnostico_22oct_c.md`,
bloque 0). Este test recalcula la feature de 50 frames FIJOS con `leer_frames_ffmpeg` y exige que
≥ 99 % de las cajas coincidan con la caché. Necesita el vídeo y las cachés del benjamín (viven en
Drive): sin ellos se salta.
"""

from pathlib import Path

import numpy as np
import pytest

R = Path(__file__).resolve().parent.parent
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
N_FRAMES = 50
HASTA_FRAME = 1800  # primer minuto: decodificarlo cuesta ~7 s
MIN_IDENTICAS = 0.99


def _rutas():
    import yaml

    cfg = yaml.safe_load(open(CONFIG))
    rutas = {k: R / cfg["rutas"][k] for k in ("video", "cache", "cache_colores")}
    if not all(p.exists() for p in rutas.values()):
        pytest.skip("faltan el vídeo o las cachés del benjamín (viven en Drive)")
    return rutas


def frames_fijos(frames_cache: list[int]) -> list[int]:
    """50 frames del caché repartidos por igual en el primer minuto (siempre los mismos)."""
    candidatos = sorted(f for f in frames_cache if f < HASTA_FRAME)
    idx = np.linspace(0, len(candidatos) - 1, N_FRAMES).round().astype(int)
    return [candidatos[i] for i in idx]


def test_frames_fijos_son_50_distintos_y_estables():
    fs = frames_fijos(list(range(0, 3000, 3)))
    assert len(set(fs)) == N_FRAMES
    assert fs == frames_fijos(list(range(0, 3000, 3)))


def test_ffmpeg_reproduce_la_cache_de_produccion():
    import pickle

    from src.team_classification.color_classifier import extraer_color_torso
    from src.tracking.cache_io import cargar_cache
    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    rutas = _rutas()
    cache = {e["frame_idx"]: e["dets"] for e in cargar_cache(rutas["cache"])["cache"]}
    produccion = pickle.load(open(rutas["cache_colores"], "rb"))
    iguales, total = 0, 0
    for f, img in leer_frames_ffmpeg(rutas["video"], frames_fijos(list(cache))):
        for k, d in enumerate(cache[f]):
            if (f, k) not in produccion:
                continue
            x1, y1, x2, y2 = (int(v) for v in d[2:6])
            crop = img[max(y1, 0) : y2, max(x1, 0) : x2]  # noqa: E203
            if crop.size == 0:
                continue
            total += 1
            iguales += (
                float(np.linalg.norm(extraer_color_torso(crop) - produccion[(f, k)]))
                < 1e-6
            )
    assert total > 500, f"muy pocas cajas comparadas ({total})"
    assert iguales / total >= MIN_IDENTICAS, (
        f"solo {iguales}/{total} features coinciden con producción: el decodificador o el "
        "recorte no son los de producción. No midas color con este montaje."
    )
