"""Tests de la Etapa A (tracklets conservadores) con trayectorias sintéticas.

Construimos cachés artificiales donde SABEMOS la trayectoria real de cada
jugador y comprobamos que el tracker no mezcla identidades.
"""

import numpy as np

from src.tracking.field_tracker import ConservativeTracker, ParametrosEtapaA, Tracklet

# Mismo muestreo que el caché real: fps=25, 1 de cada 3 frames → dt=0.12 s
FPS = 25.0
SAMPLE = 3
DT = SAMPLE / FPS


def _cache_desde_trayectorias(trayectorias: list[list[tuple[float, float] | None]]):
    """Convierte trayectorias por jugador en un caché sintético.

    Args:
        trayectorias: lista (una por jugador) de posiciones (mx, my) por
            frame; None = el jugador no fue detectado en ese frame.

    Returns:
        (cache, etiquetas): el caché en el formato real, y un dict
        {(frame_idx, det_idx): jugador} para verificar pureza después.
    """
    n_frames = len(trayectorias[0])
    cache = []
    etiquetas = {}
    for k in range(n_frames):
        frame_idx = k * SAMPLE
        dets = []
        for jugador, tray in enumerate(trayectorias):
            if tray[k] is None:
                continue
            mx, my = tray[k]
            # Caja en píxeles ficticia y confianza fija: la Etapa A solo usa (mx, my)
            etiquetas[(frame_idx, len(dets))] = jugador
            dets.append((mx, my, 0.0, 0.0, 10.0, 20.0, 0.9))
        cache.append({"frame_idx": frame_idx, "t": k * DT, "dets": dets})
    return cache, etiquetas


def _pureza(tracklets: list[Tracklet], etiquetas: dict) -> bool:
    """True si ningún tracklet mezcla detecciones de dos jugadores."""
    for tr in tracklets:
        duenos = {etiquetas[par] for par in tr.det_idxs}
        if len(duenos) > 1:
            return False
    return True


def test_jugador_recto_un_tracklet():
    """Un jugador en línea recta debe producir UN solo tracklet completo."""
    n = 30
    tray = [(1.0 * k * DT * 3, 10.0) for k in range(n)]  # 3 m/s en x
    cache, _ = _cache_desde_trayectorias([tray])
    tracklets = ConservativeTracker().procesar(cache, FPS, SAMPLE)
    assert len(tracklets) == 1
    assert len(tracklets[0]) == n


def test_cruce_sin_robo_de_id():
    """Dos jugadores que se cruzan: puede haber cortes, pero NUNCA mezcla.

    La regla anti-robo debe cortar los tracklets en la zona ambigua del
    cruce en lugar de arriesgarse a intercambiar identidades.
    """
    n = 40
    # Jugador 0: de x=0 a x=14 por y=10. Jugador 1: de x=14 a x=0 por y=10.4.
    # Se cruzan hacia la mitad; en el cruce están a < 0.5 m (zona ambigua).
    tray0 = [(14.0 * k / (n - 1), 10.0) for k in range(n)]
    tray1 = [(14.0 - 14.0 * k / (n - 1), 10.4) for k in range(n)]
    cache, etiquetas = _cache_desde_trayectorias([tray0, tray1])
    tracklets = ConservativeTracker().procesar(cache, FPS, SAMPLE)
    # Lo esencial: pureza (ningún tracklet contiene puntos de ambos jugadores)
    assert _pureza(tracklets, etiquetas)
    # Y todo lo detectable quedó en algún tracklet razonable
    assert len(tracklets) >= 2


def test_filtro_min_frames():
    """Una detección espuria de 2 frames debe descartarse (min_frames=3)."""
    n = 20
    tray_real = [(2.0 + 0.3 * k, 5.0) for k in range(n)]
    # Ruido: aparece solo en los frames 4 y 5, lejos del jugador real
    tray_ruido: list = [None] * n
    tray_ruido[4] = (40.0, 40.0)
    tray_ruido[5] = (40.1, 40.0)
    cache, _ = _cache_desde_trayectorias([tray_real, tray_ruido])
    tracklets = ConservativeTracker().procesar(cache, FPS, SAMPLE)
    assert len(tracklets) == 1
    assert len(tracklets[0]) == n


def test_hueco_largo_corta_el_track():
    """Si un jugador desaparece más de max_gap, el track se cierra y al
    reaparecer se abre un tracklet NUEVO (coserlos es trabajo de la Etapa B)."""
    n = 30
    tray: list = [(1.0 + 0.2 * k, 8.0) for k in range(n)]
    for k in range(10, 16):  # desaparece 6 frames = 0.72 s > max_gap = 0.36 s
        tray[k] = None
    cache, _ = _cache_desde_trayectorias([tray])
    tracklets = ConservativeTracker().procesar(cache, FPS, SAMPLE)
    assert len(tracklets) == 2


def test_predecir_usa_velocidad():
    """predecir() debe extrapolar con la velocidad suavizada."""
    tr = Tracklet(1, 0.0, np.array([0.0, 0.0]), 0, 0)
    tr.anadir(1.0, np.array([2.0, 0.0]), 0, 3)  # 2 m/s en x → vel = 0.8 (EMA)
    pred = tr.predecir(2.0)
    assert pred[0] > tr.pos[-1][0]  # extrapola hacia adelante
    np.testing.assert_allclose(pred, [2.0 + 0.8, 0.0])


def test_parametros_desde_dict():
    """Los parámetros deben poder construirse desde el YAML de config."""
    p = ParametrosEtapaA.desde_dict(
        {
            "v_max": 6.0,
            "margen": 1.0,
            "ambig_factor": 0.5,
            "max_gap_dts": 2.0,
            "min_frames": 4,
        }
    )
    assert p.v_max == 6.0
    assert p.min_frames == 4
