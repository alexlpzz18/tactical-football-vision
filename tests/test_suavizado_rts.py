"""Suavizado RTS con ruido local medido (docs/registro_mision.md, H1). Tests de comportamiento."""

import numpy as np

from src.tracking.suavizado_rts import ParametrosRTS, RuidoLocal, rts_1d, suavizar_rts

DT = 0.12


def _trayectoria(verdad: np.ndarray, sigma, rng, f0: int = 0):
    """[(frame, pos, True)] con ruido gaussiano de `sigma` (escalar o por eje) sobre `verdad`."""
    ruido = rng.normal(0, 1, verdad.shape) * np.asarray(sigma)
    return [(f0 + i, verdad[i] + ruido[i], True) for i in range(len(verdad))]


def _recta(n: int, origen, velocidad) -> np.ndarray:
    return np.asarray(origen, float) + np.outer(np.arange(n) * DT, velocidad)


def _tiempos(n: int) -> dict:
    return {i: i * DT for i in range(n)}


def test_el_ruido_local_se_recupera_de_los_datos_y_por_eje():
    """Lejos (y > 40) el eje y tiembla 1,0 m y el x 0,3; cerca, 0,05 los dos."""
    rng = np.random.default_rng(0)
    tray = []
    for k in range(40):
        tray.append(
            _trayectoria(_recta(200, (10 + k, 50), (1.0, 0.0)), (0.3, 1.0), rng)
        )
        tray.append(
            _trayectoria(_recta(200, (10 + k, 10), (1.0, 0.0)), (0.05, 0.05), rng)
        )
    ruido = RuidoLocal(tray, _tiempos(200), ParametrosRTS())
    lejos = ruido.sigma(np.array([[30.0, 50.0]]))[0]
    cerca = ruido.sigma(np.array([[30.0, 10.0]]))[0]
    assert abs(lejos[0] - 0.3) < 0.1 and abs(lejos[1] - 1.0) < 0.3, lejos
    assert abs(cerca[0] - 0.05) < 0.02 and abs(cerca[1] - 0.05) < 0.02, cerca


def test_lejos_quita_los_saltos_y_cerca_no_mueve_la_ficha():
    rng = np.random.default_rng(1)
    verdad_lejos = _recta(300, (20, 55), (3.0, 0.0))
    verdad_cerca = _recta(300, (20, 8), (3.0, 0.5))
    tray = [
        _trayectoria(verdad_lejos, (0.4, 1.2), rng),
        _trayectoria(verdad_cerca, (0.04, 0.04), rng),
    ] * 1
    # más trayectorias para que cada celda tenga muestras
    for k in range(30):
        tray.append(
            _trayectoria(_recta(300, (20, 55 - k % 3), (3.0, 0.0)), (0.4, 1.2), rng)
        )
        tray.append(
            _trayectoria(_recta(300, (20, 8 + k % 3), (3.0, 0.5)), (0.04, 0.04), rng)
        )
    suave = suavizar_rts(tray, _tiempos(300))
    lejos = np.array([p for _f, p, _r in suave[0]])
    cerca = np.array([p for _f, p, _r in suave[1]])
    cruda_cerca = np.array([p for _f, p, _r in tray[1]])
    # lejos: ningún paso a más de 9 m/s (crudo: decenas) y error mucho menor que el de la medida
    v = np.linalg.norm(np.diff(lejos, axis=0), axis=1) / DT
    assert v.max() < 9.0, v.max()
    assert np.abs(lejos[20:-20] - verdad_lejos[20:-20])[:, 1].std() < 0.5
    # cerca: la ficha se queda sobre su propia detección
    assert np.linalg.norm(cerca - cruda_cerca, axis=1).max() < 0.15
    # ni añade ni quita puntos
    assert [len(a) for a in suave] == [len(a) for a in tray]


def test_un_giro_de_90_grados_a_6_ms_no_se_corta_mas_de_un_metro():
    """Lo que el suavizado podría inventar: un jugador que no gira (criterio c)."""
    n = 100
    verdad = np.zeros((2 * n, 2))
    verdad[:n] = _recta(n, (20, 30), (6.0, 0.0))
    verdad[n:] = verdad[n - 1] + np.outer(np.arange(1, n + 1) * DT, (0.0, 6.0))
    for sigma in (0.05, 0.4, 1.0):
        s = rts_1d(
            np.arange(2 * n) * DT, verdad[:, 0], np.full(2 * n, sigma), q=4.0**2
        ), rts_1d(
            np.arange(2 * n) * DT, verdad[:, 1], np.full(2 * n, sigma), q=4.0**2
        )
        error = np.hypot(s[0] - verdad[:, 0], s[1] - verdad[:, 1]).max()
        assert error < 1.0, (sigma, error)


def test_respeta_los_huecos_de_tiempo():
    """Dos tramos separados 2 s: el suavizado no mezcla las muestras de un lado con las del otro
    como si fueran seguidas (la media móvil por muestras sí lo hacía)."""
    t = np.r_[np.arange(30) * DT, 30 * DT + 2.0 + np.arange(30) * DT]
    z = np.r_[
        np.zeros(30), np.full(30, 10.0)
    ]  # parado en 0, y tras el hueco, parado en 10
    s = rts_1d(t, z, np.full(60, 0.3), q=16.0)
    assert abs(s[25]) < 1.0 and abs(s[35] - 10.0) < 1.0, (s[25], s[35])


def test_interruptor_real_en_postprocesar():
    """`suavizado.metodo: rts` cambia el resultado; sin él, el camino de siempre (mutación viva)."""
    from types import SimpleNamespace

    from src.tracking.perfiles import postprocesar

    rng = np.random.default_rng(3)
    verdad = _recta(200, (20, 50), (2.0, 0.0))
    pos = verdad + rng.normal(0, 0.8, verdad.shape)
    identidades = [
        [SimpleNamespace(pos=list(pos), det_idxs=[(i, 0) for i in range(200)])]
    ]
    frames_ts = [(i, i * DT) for i in range(200)]
    salidas = {}
    for metodo in ("media", "rts"):
        cfg = {"suavizado": {"activo": True, "metodo": metodo, "ventana_s": 0.5}}
        tray, _ = postprocesar(
            identidades, {0: "A"}, frames_ts, cfg, perfil="bytetrack"
        )
        salidas[metodo] = np.array([p for _f, p, _r in tray[0]])
    assert not np.allclose(salidas["media"], salidas["rts"])
    assert len(salidas["media"]) == len(salidas["rts"]) == 200


def test_una_proyeccion_disparatada_no_hincha_la_rejilla():
    """Un punto proyectado a kilómetros (cerca del horizonte) no puede colgar el cálculo."""
    rng = np.random.default_rng(4)
    tray = [_trayectoria(_recta(300, (20, 30), (2.0, 0.0)), 0.2, rng) for _ in range(5)]
    lejos = _recta(300, (20, 30), (2.0, 0.0))
    lejos[150] = (5e6, -3e6)
    tray.append([(i, lejos[i], True) for i in range(300)])
    ruido = RuidoLocal(tray, _tiempos(300), ParametrosRTS())
    assert ruido._rejilla.shape[0] < 100 and ruido._rejilla.shape[1] < 100
    assert len(suavizar_rts(tray, _tiempos(300))) == 6
