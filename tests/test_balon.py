"""Tests del tracking de balón.

El balón no es "un jugador pequeño": puede haber varios, vuela (y
entonces la homografía deja de aplicar) y lo que importa de verdad son
los contactos. Estos tests fijan esas tres cosas.
"""

import numpy as np

from src.balon.tracking_balon import (
    ParametrosBalon,
    detectar_contactos,
    detectar_fases_aereas,
    seleccionar_balon_activo,
)

DT = 1 / 15.0
TIEMPOS = {k: k * DT for k in range(0, 400)}


def _det(mx, my, alto_px=8, conf=0.8):
    return (mx, my, 100.0, 100.0, 100.0 + alto_px, 100.0 + alto_px, conf)


# ── selección del balón activo ───────────────────────────────────────


def test_descarta_el_balon_parado_lejos_del_juego():
    """Un balón de calentamiento en la banda es un balón perfecto: lo que
    lo delata no es su aspecto sino que no se mueve y nadie lo rodea."""
    detecciones, jugadores = {}, {}
    for k in range(60):
        detecciones[k] = [
            _det(30.0 + 0.3 * k, 20.0),  # el del partido, moviéndose
            _det(5.0, 39.0),  # parado en la banda
        ]
        jugadores[k] = [(30.0 + 0.3 * k + 1.0, 20.5), (28.0, 19.0)]
    activo = seleccionar_balon_activo(detecciones, jugadores, ParametrosBalon())
    assert len(activo) == 60
    for k in range(60):
        assert abs(activo[k][0] - (30.0 + 0.3 * k)) < 0.01


def test_un_balon_parado_pero_CERCA_no_se_descarta():
    """El balón bueno también se para: un saque de banda, una falta. Si se
    descartara por estar quieto, se perdería justo el momento previo a la
    jugada."""
    detecciones = {k: [_det(30.0, 20.0)] for k in range(60)}
    jugadores = {k: [(31.0, 20.0)] for k in range(60)}
    activo = seleccionar_balon_activo(detecciones, jugadores, ParametrosBalon())
    assert len(activo) == 60


# ── fases aéreas ─────────────────────────────────────────────────────


def test_la_velocidad_imposible_marca_fase_aerea():
    """La proyección supone que el balón está EN EL SUELO. Un vuelo viola
    esa suposición y produce saltos que ningún balón raso da."""
    tray = [(k, np.array([10.0 + 0.3 * k, 20.0]), 8, 0.9) for k in range(10)]
    tray += [(10 + k, np.array([13.0 + 5.0 * k, 20.0]), 8, 0.9) for k in range(5)]
    tray += [(15 + k, np.array([38.0 + 0.3 * k, 20.0]), 8, 0.9) for k in range(10)]
    aereo = detectar_fases_aereas(tray, TIEMPOS, ParametrosBalon())
    assert any(aereo[10:15]), "el tramo rápido debe marcarse aéreo"
    assert not aereo[0] and not aereo[-1]


def test_el_tamano_incoherente_marca_fase_aerea():
    """La señal más específica: un balón por el aire está más cerca de la
    cámara que el punto del suelo al que se le proyecta, así que se ve
    MÁS GRANDE de lo que le tocaría por su distancia. No depende de la
    velocidad, así que caza también los globos lentos."""
    tray = [(k, np.array([float(40 + k * 0.1), 20.0]), 6, 0.9) for k in range(20)]
    # Mismo sitio, misma velocidad, pero de golpe se ve el triple
    for i in range(8, 13):
        f, p, _alto, c = tray[i]
        tray[i] = (f, p, 20, c)
    aereo = detectar_fases_aereas(tray, TIEMPOS, ParametrosBalon())
    assert any(aereo[8:13])
    assert not aereo[0]


def test_un_parpadeo_PLAUSIBLE_no_es_un_vuelo():
    """Una observación algo desviada pero físicamente posible es ruido del
    detector, no una fase aérea."""
    tray = [(k, np.array([10.0 + 0.3 * k, 20.0]), 8, 0.9) for k in range(20)]
    f, _p, a, c = tray[10]
    tray[10] = (f, np.array([13.0, 20.8]), a, c)  # ~12 m/s: un pase raso
    aereo = detectar_fases_aereas(
        tray, TIEMPOS, ParametrosBalon(duracion_min_aerea=0.5)
    )
    assert not any(aereo)


def test_un_salto_INDEFENDIBLE_se_marca_aunque_dure_un_frame():
    """Cambio de criterio (16-ago-2026), y es el que ataca el zigzag.

    El filtro de duración mínima existe para no llamar vuelo a un
    parpadeo, pero desmarcaba justo los saltos de UN frame, que son los
    que producen el movimiento "de snitch" en el replay. Por encima de
    `v_indefendible` la posición no es defendible dure lo que dure.
    """
    tray = [(k, np.array([10.0 + 0.3 * k, 20.0]), 8, 0.9) for k in range(20)]
    f, _p, a, c = tray[10]
    tray[10] = (f, np.array([13.0, 26.0]), a, c)  # ~90 m/s: imposible
    aereo = detectar_fases_aereas(
        tray, TIEMPOS, ParametrosBalon(duracion_min_aerea=0.5)
    )
    assert aereo[10], "un salto imposible no puede pasar por bueno"
    assert not aereo[0] and not aereo[-1]


# ── contactos ────────────────────────────────────────────────────────


def test_un_cambio_brusco_de_direccion_es_un_contacto():
    tray = [(k, np.array([10.0 + 1.0 * k, 20.0]), 8, 0.9) for k in range(10)]
    tray += [
        (10 + k, np.array([19.0, 20.0 + 1.0 * (k + 1)]), 8, 0.9) for k in range(10)
    ]
    jugadores = {k: [(19.5, 20.5, 7)] for k in range(30)}
    contactos = detectar_contactos(tray, TIEMPOS, jugadores, None, ParametrosBalon())
    assert len(contactos) == 1
    assert contactos[0]["angulo"] > 45
    assert contactos[0]["id_jugador"] == 7


def test_un_balon_recto_no_genera_contactos():
    tray = [(k, np.array([10.0 + 1.0 * k, 20.0]), 8, 0.9) for k in range(30)]
    jugadores = {k: [(15.0, 20.0, 3)] for k in range(30)}
    assert detectar_contactos(tray, TIEMPOS, jugadores, None, ParametrosBalon()) == []


def test_el_contacto_sin_jugador_cerca_se_registra_igual():
    """Información honesta: hubo un contacto y no sabemos de quién. Es
    mejor que atribuirlo al jugador más cercano esté donde esté."""
    tray = [(k, np.array([10.0 + 1.0 * k, 20.0]), 8, 0.9) for k in range(10)]
    tray += [
        (10 + k, np.array([19.0, 20.0 + 1.0 * (k + 1)]), 8, 0.9) for k in range(10)
    ]
    jugadores = {k: [(50.0, 35.0, 3)] for k in range(30)}
    contactos = detectar_contactos(tray, TIEMPOS, jugadores, None, ParametrosBalon())
    assert len(contactos) == 1
    assert contactos[0]["id_jugador"] is None


def test_el_balon_casi_parado_no_genera_contactos_por_ruido():
    """Con el balón quieto, el ángulo entre pasos lo decide el ruido."""
    rng = np.random.default_rng(0)
    tray = [
        (k, np.array([20.0, 20.0]) + rng.normal(0, 0.02, 2), 8, 0.9) for k in range(30)
    ]
    jugadores = {k: [(20.5, 20.0, 1)] for k in range(30)}
    assert detectar_contactos(tray, TIEMPOS, jugadores, None, ParametrosBalon()) == []


# ── herramienta de mini-GT de equipos (11-ago-2026) ──────────────────


def test_las_muestras_cubren_toda_la_vida_de_la_identidad():
    """Repartir por tramos, y no coger las 8 mejores a secas, es lo que
    permite VER si una identidad cambia de persona a mitad: si todas las
    muestras salieran del momento en que mejor se ve, una quimera pasaría
    desapercibida."""
    from scripts.etiquetar_equipos_gt import elegir_muestras

    obs = [{"frame": k, "alto": 20 + (60 if 40 <= k < 50 else 0)} for k in range(100)]
    muestras = elegir_muestras(obs, 8)
    frames = [m["frame"] for m in muestras]
    assert len(muestras) == 8
    assert frames == sorted(frames)
    assert frames[0] < 15 and frames[-1] > 85, "debe cubrir principio y final"


def test_de_cada_tramo_se_coge_el_recorte_mas_grande():
    """El más grande es el más cercano a la cámara, y por tanto el más
    nítido: con jugadores de 15-40 px, esa diferencia decide si el color
    de la camiseta se distingue o no."""
    from scripts.etiquetar_equipos_gt import elegir_muestras

    obs = [{"frame": k, "alto": 90 if k % 10 == 3 else 20} for k in range(40)]
    for m in elegir_muestras(obs, 4):
        assert m["alto"] == 90


def test_una_identidad_con_recortes_discrepantes_es_quimera():
    """El punto de la interfaz por recorte: la quimera sale sola de los
    datos, sin que nadie tenga que localizarla a ojo."""
    from collections import Counter

    limpia = Counter(["B"] * 7)
    mezcla = Counter(["B"] * 4 + ["A"] * 3)
    assert len(limpia) == 1  # una sola persona
    assert len(mezcla) > 1  # dos personas en la misma identidad
    # La pureza dice CUÁNTAS observaciones son realmente de su dueño
    assert mezcla.most_common(1)[0][1] / sum(mezcla.values()) < 0.6


def test_el_arbitro_marcado_como_otro_cuenta_como_acierto():
    """El sistema no tiene etiqueta 'arbitro': sacarlo del juego COMO
    'otro' es exactamente el comportamiento correcto, y la medida no debe
    penalizarlo."""
    from scripts.medir_equipos_gt import normalizar

    assert normalizar("arbitro") == normalizar("staff") == "otro"
    assert normalizar("A") == "A" and normalizar("portero_B") == "portero_B"


# ── contactos por oscilación de velocidad (16-ago-2026) ──────────────


def test_la_conduccion_recta_la_ve_la_velocidad_y_no_el_angulo():
    """El hallazgo del GT de Alex, fijado como test.

    Un jugador que conduce empuja el balón repetidamente en la MISMA
    dirección: el ángulo entre pasos es de unos pocos grados (medido:
    mediana 5°, p90 18°), así que el criterio angular es ciego. Lo que sí
    cambia en cada toque es la velocidad.
    """
    from src.balon.tracking_balon import detectar_contactos_por_velocidad

    # Balón conducido en línea recta: cada toque lo acelera y luego frena
    tray, x = [], 10.0
    for k in range(40):
        paso = 0.5 if k % 5 == 0 else 0.12  # un toque cada 5 muestras
        x += paso
        tray.append((k, np.array([x, 20.0]), 8, 0.9))
    jug = {k: [(x, 20.5, 7)] for k in range(40)}

    por_angulo = detectar_contactos(tray, TIEMPOS, jug, None, ParametrosBalon())
    assert por_angulo == [], "el ángulo no puede ver una conducción recta"

    por_vel = detectar_contactos_por_velocidad(
        tray, TIEMPOS, jug, None, ParametrosBalon(aceleracion_min=2.0)
    )
    assert len(por_vel) >= 5, "la velocidad sí ve los toques"


def test_la_fusion_no_cuenta_dos_veces_el_mismo_toque():
    """Un pase fuerte dispara los DOS criterios —cambia de dirección y
    acelera—, así que sumarlos a secas inflaría justo las acciones que ya
    se detectaban bien."""
    from src.balon.tracking_balon import fusionar_contactos

    a = [{"t": 10.0, "criterio": "angulo"}, {"t": 20.0, "criterio": "angulo"}]
    v = [{"t": 10.05, "criterio": "velocidad"}, {"t": 30.0, "criterio": "velocidad"}]
    fus = fusionar_contactos(a, v, separacion=0.20)
    assert len(fus) == 3
    assert fus[0]["criterio"] == "ambos"


def test_en_fase_aerea_no_se_detectan_contactos_por_velocidad():
    """La velocidad proyectada de un balón por el aire es paralaje."""
    from src.balon.tracking_balon import detectar_contactos_por_velocidad

    tray = [(k, np.array([10.0 + k * 2.0, 20.0]), 8, 0.9) for k in range(20)]
    jug = {k: [(10.0 + k * 2.0, 20.5, 7)] for k in range(20)}
    aereo = [True] * 20
    assert (
        detectar_contactos_por_velocidad(
            tray, TIEMPOS, jug, None, ParametrosBalon(), aereo=aereo
        )
        == []
    )


# ── selector de clips: el parón invisible (16-ago-2026) ──────────────


def test_un_tramo_con_el_balon_FUERA_DEL_PLANO_no_es_juego_continuo():
    """Fallo de método que costó medio clip de etiquetado.

    La primera versión puntuaba "balón parado" por la fracción de
    muestras con velocidad casi nula. Pero si el balón SALE DEL ENCUADRE
    no hay muestras, así que el parón no deja rastro y la ventana salía
    inmaculada. El clip elegido tenía 13 de sus 30 segundos con el balón
    fuera de cámara y parecía juego continuo perfecto.
    """
    import sys
    from pathlib import Path

    import pandas as pd

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from elegir_clip import puntuar

    def ventana(n_muestras, t0=0.0):
        filas = []
        for k in range(n_muestras):
            filas.append(
                {
                    "tiempo_s": t0 + k * 0.067,
                    "etiqueta": "balon",
                    "x_m": 20.0 + k * 0.3,
                    "y_m": 20.0,
                }
            )
        return pd.DataFrame(filas)

    esperadas = 30 / 0.067
    # Balón visible todo el rato: juego continuo
    bueno = puntuar(ventana(int(esperadas)), 0.0, 30.0, esperadas)
    # El balón desaparece a mitad: mismo movimiento, la mitad de muestras
    malo = puntuar(ventana(int(esperadas // 2)), 0.0, 30.0, esperadas)

    assert bueno["sin_deteccion"] < 0.05
    assert malo["sin_deteccion"] > 0.45, "la ausencia de balón debe verse"
    assert malo["punt"] < bueno["punt"] - 0.5, "y debe penalizar de verdad"
