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


# ── Atajo de distorsión nula ─────────────────────────────────────────
#
# La cámara del benjamín no distorsiona (k1=k2=0 en su config), y ahí
# `cv2.undistort` es la identidad: hace un remap completo del frame para
# devolverlo igual. Medido a 1080p: 27,8 ms por frame, que sobre los
# 11.988 frames de una parte entera son 5,6 minutos de CPU.


def test_distorsion_nula_devuelve_el_frame_intacto():
    """Con k1=k2=0 no se toca el frame: el MISMO objeto, sin copiar."""
    import numpy as np

    from src.tracking_data.processor import _build_camera_matrix, _corregir_distorsion

    frame = np.random.default_rng(0).integers(0, 255, (48, 64, 3), dtype=np.uint8)
    K = _build_camera_matrix(64, 48)
    salida = _corregir_distorsion(frame, K, np.array([0.0, 0.0, 0, 0, 0], float))
    assert salida is frame


def test_atajo_bit_a_bit_igual_que_undistort():
    """El atajo no cambia el resultado: se compara contra cv2.undistort."""
    import cv2
    import numpy as np

    from src.tracking_data.processor import _build_camera_matrix, _corregir_distorsion

    frame = np.random.default_rng(1).integers(0, 255, (120, 160, 3), dtype=np.uint8)
    K = _build_camera_matrix(160, 120)
    cero = np.array([0.0, 0.0, 0, 0, 0], float)
    assert np.array_equal(
        _corregir_distorsion(frame, K, cero), cv2.undistort(frame, K, cero)
    )


def test_con_distorsion_real_si_corrige():
    """Con k1≠0 el atajo NO se activa y el frame cambia (Villaviciosa)."""
    import numpy as np

    from src.tracking_data.processor import _build_camera_matrix, _corregir_distorsion

    frame = np.random.default_rng(2).integers(0, 255, (120, 160, 3), dtype=np.uint8)
    K = _build_camera_matrix(160, 120)
    salida = _corregir_distorsion(frame, K, np.array([-0.30, 0.10, 0, 0, 0], float))
    assert salida is not frame
    assert not np.array_equal(salida, frame)


# ── Checkpoint del modo full ─────────────────────────────────────────
#
# El caché se escribía UNA vez, al final del bucle: una caída de sesión
# en el minuto 55 de una pasada de 60 lo perdía todo. Estos tests cubren
# lo que no necesita GPU: la firma que decide si un caché a medias es
# reanudable, y el volcado atómico.


def _cfg_full(tmp_path, **cambios):
    cfg = {
        "rutas": {
            "video": "v.mp4",
            "cache": str(tmp_path / "det.pkl"),
            "cache_colores": str(tmp_path / "col.pkl"),
        },
        "deteccion": {
            "modelo": "m.pt",
            "confianza": 0.3,
            "max_area_caja": 0.05,
            "sahi": {"filas": 2, "columnas": 4, "solape": 0.2},
        },
        "distorsion": {"k1": 0.0, "k2": 0.0},
        "muestreo": {"sample_every": 3},
    }
    for ruta, valor in cambios.items():
        nodo = cfg
        partes = ruta.split(".")
        for parte in partes[:-1]:
            nodo = nodo[parte]
        nodo[partes[-1]] = valor
    return cfg


def test_volcado_atomico_no_deja_temporales(tmp_path):
    from src.tracking_data.processor import _volcar

    destino = tmp_path / "sub" / "x.pkl"
    _volcar(str(destino), {"hola": 1})
    assert destino.exists()
    assert list(tmp_path.rglob("*.tmp")) == []


def test_la_firma_cambia_con_el_modelo_y_con_el_tramo(tmp_path):
    """Reanudar con otro detector mezclaría dos detectores en un fichero."""
    from src.tracking_data.processor import _firma_de_deteccion

    base = _firma_de_deteccion(_cfg_full(tmp_path))
    assert base == _firma_de_deteccion(_cfg_full(tmp_path))
    otro = _firma_de_deteccion(_cfg_full(tmp_path, **{"deteccion.modelo": "v4.pt"}))
    assert otro != base
    conf = _firma_de_deteccion(_cfg_full(tmp_path, **{"deteccion.confianza": 0.45}))
    assert conf != base
    tramo = _firma_de_deteccion(
        _cfg_full(tmp_path, **{"muestreo.tramo": {"min_ini": 5.0, "dur_seg": 60.0}})
    )
    assert tramo != base


def _guardar(tmp_path, firma, completo, frames=(0, 3, 6)):
    from src.tracking_data.processor import _guardar_caches

    cache = [{"frame_idx": f, "t": f / 30.0, "dets": []} for f in frames]
    _guardar_caches(
        _cfg_full(tmp_path), cache, {"c": 1}, 30.0, 3, (1920, 1080), completo, firma
    )
    return cache


def test_reanuda_un_checkpoint_compatible(tmp_path):
    from src.tracking_data.processor import _firma_de_deteccion, _reanudar

    firma = _firma_de_deteccion(_cfg_full(tmp_path))
    _guardar(tmp_path, firma, completo=False)
    cache, colores = _reanudar(_cfg_full(tmp_path), firma)
    assert cache is not None and cache[-1]["frame_idx"] == 6
    assert colores == {"c": 1}


def test_NO_reanuda_si_el_detector_es_otro(tmp_path):
    """Lo importante del checkpoint: negarse antes que mezclar detectores."""
    from src.tracking_data.processor import _firma_de_deteccion, _reanudar

    _guardar(tmp_path, _firma_de_deteccion(_cfg_full(tmp_path)), completo=False)
    otra = _firma_de_deteccion(_cfg_full(tmp_path, **{"deteccion.modelo": "v4.pt"}))
    assert _reanudar(_cfg_full(tmp_path), otra) == (None, None)


def test_NO_reanuda_un_cache_ya_completo(tmp_path):
    from src.tracking_data.processor import _firma_de_deteccion, _reanudar

    firma = _firma_de_deteccion(_cfg_full(tmp_path))
    _guardar(tmp_path, firma, completo=True)
    assert _reanudar(_cfg_full(tmp_path), firma) == (None, None)


def test_sin_cache_previo_no_reanuda_nada(tmp_path):
    from src.tracking_data.processor import _firma_de_deteccion, _reanudar

    firma = _firma_de_deteccion(_cfg_full(tmp_path))
    assert _reanudar(_cfg_full(tmp_path), firma) == (None, None)


def test_el_checkpoint_sigue_siendo_un_cache_valido(tmp_path):
    """Un checkpoint a medias tiene que poder cargarse con cargar_cache."""
    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import _firma_de_deteccion

    firma = _firma_de_deteccion(_cfg_full(tmp_path))
    _guardar(tmp_path, firma, completo=False)
    datos = cargar_cache(str(tmp_path / "det.pkl"))
    assert len(datos["cache"]) == 3 and datos["sample"] == 3
