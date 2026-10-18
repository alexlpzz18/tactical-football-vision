"""El suavizado del balón no puede cruzar un vuelo ni un hueco.

Encontrado el 21-sep-2026 al buscar las "alas" del balón: `preparar_para_replay`
suavizaba la lista de observaciones de SUELO como si fueran consecutivas, y esa
lista se salta los vuelos y los huecos. En el borde de un vuelo promediaba el
punto de despegue con el de aterrizaje, y la fila resultante —marcada
`es_real=1`— no era ninguna detección: el 12,1 % de las filas reales del
partido entero estaba a más de 1 m de toda detección, y 270 pasos superaban
los 40 m/s. Sin cruzar tramos: 0,1 % y 30 (docs/balon_sin_alas.md).
"""

import numpy as np

from src.balon.tracking_balon import ParametrosBalon, preparar_para_replay

PASO_S = 0.0667  # 2 frames a 29,97 fps


def _serie(posiciones, aereo=None, huecos_s=None):
    """(trayectoria, aereo, tiempos) con una muestra cada PASO_S.

    `huecos_s` = {indice: segundos extra ANTES de esa muestra}: simula
    detecciones perdidas sin marcar la muestra como aérea.
    """
    huecos_s = huecos_s or {}
    trayectoria, tiempos, t = [], {}, 0.0
    for i, p in enumerate(posiciones):
        t += PASO_S + huecos_s.get(i, 0.0)
        frame = i * 2
        tiempos[frame] = t
        trayectoria.append((frame, np.array(p, dtype=float), 14.0, 0.9))
    return trayectoria, list(aereo or [False] * len(posiciones)), tiempos


def _reales_suelo(salida):
    return [(f, p) for f, p, aereo, real in salida if real and not aereo]


def _dist_a_deteccion_mas_cercana(salida, trayectoria):
    crudas = {f: np.array(p) for f, p, _a, _c in trayectoria}
    return [float(np.linalg.norm(p - crudas[f])) for f, p in _reales_suelo(salida)]


def test_un_vuelo_no_arrastra_el_suelo_hacia_el_otro_lado():
    """Despegue en x=10, aterrizaje en x=40: el suelo pegado al vuelo NO se mezcla."""
    antes = [(10.0, 20.0)] * 6
    vuelo = [(25.0, 20.0)] * 4
    despues = [(40.0, 20.0)] * 6
    tray, aereo, tiempos = _serie(
        antes + vuelo + despues, [False] * 6 + [True] * 4 + [False] * 6
    )
    salida = preparar_para_replay(tray, aereo, tiempos, ParametrosBalon())
    cerca = _dist_a_deteccion_mas_cercana(salida, tray)
    assert max(cerca) < 0.5, (
        f"una fila de suelo cae a {max(cerca):.1f} m de su detección: el "
        "suavizado está promediando el despegue con el aterrizaje"
    )


def test_un_hueco_de_detecciones_tampoco_se_cruza():
    """Sin fase aérea de por medio, un hueco de 1 s separa dos tramos igual."""
    posiciones = [(10.0, 20.0)] * 6 + [(30.0, 20.0)] * 6
    tray, aereo, tiempos = _serie(posiciones, huecos_s={6: 1.0})
    salida = preparar_para_replay(tray, aereo, tiempos, ParametrosBalon())
    assert max(_dist_a_deteccion_mas_cercana(salida, tray)) < 0.5


def test_ningun_paso_de_suelo_supera_lo_que_hizo_el_balon():
    """La propiedad de fondo: el suavizado no inventa velocidades."""
    antes = [(10.0 + 0.1 * i, 20.0) for i in range(8)]
    despues = [(45.0 + 0.1 * i, 20.0) for i in range(8)]
    tray, aereo, tiempos = _serie(
        antes + [(30.0, 20.0)] * 3 + despues, [False] * 8 + [True] * 3 + [False] * 8
    )
    salida = preparar_para_replay(tray, aereo, tiempos, ParametrosBalon())
    suelo = sorted(_reales_suelo(salida), key=lambda x: x[0])
    for (f0, p0), (f1, p1) in zip(suelo, suelo[1:]):
        if f1 - f0 == 2:  # muestras contiguas: un paso normal, sin vuelo entre medias
            v = np.linalg.norm(p1 - p0) / (tiempos[f1] - tiempos[f0])
            assert v < 10.0, f"paso de {v:.0f} m/s entre muestras contiguas"


def test_dentro_de_un_tramo_continuo_SIGUE_suavizando():
    """Control: el arreglo no apaga el suavizado, solo lo limita a un tramo."""
    rng = np.random.default_rng(0)
    ruido = rng.normal(0, 0.3, size=(40, 2))
    posiciones = [(10.0 + 0.05 * i + r[0], 20.0 + r[1]) for i, r in enumerate(ruido)]
    tray, aereo, tiempos = _serie(posiciones)
    salida = preparar_para_replay(tray, aereo, tiempos, ParametrosBalon())

    def temblor(pts):
        p = np.array(pts)
        return float(np.median(np.abs(p[2:] - 2 * p[1:-1] + p[:-2])))

    crudo = temblor([p for _f, p, _a, _c in tray])
    suave = temblor([p for _f, p in sorted(_reales_suelo(salida), key=lambda x: x[0])])
    assert suave < crudo * 0.7, f"no suaviza: {crudo:.3f} → {suave:.3f}"


def test_el_umbral_de_hueco_es_un_parametro_y_manda():
    """Con un umbral enorme se vuelve al comportamiento antiguo: el test 2 debe romperse."""
    posiciones = [(10.0, 20.0)] * 6 + [(30.0, 20.0)] * 6
    tray, aereo, tiempos = _serie(posiciones, huecos_s={6: 1.0})
    params = ParametrosBalon(max_hueco_suavizado_s=1e9)
    salida = preparar_para_replay(tray, aereo, tiempos, params)
    assert max(_dist_a_deteccion_mas_cercana(salida, tray)) > 1.0


def test_un_vuelo_de_UNA_muestra_tambien_corta_el_tramo():
    """Con un vuelo tan corto que el hueco de tiempo (0,13 s) no llega al umbral,
    solo la contigüidad en la trayectoria separa despegue y aterrizaje."""
    posiciones = [(10.0, 20.0)] * 6 + [(25.0, 20.0)] + [(40.0, 20.0)] * 6
    tray, aereo, tiempos = _serie(posiciones, [False] * 6 + [True] + [False] * 6)
    salida = preparar_para_replay(tray, aereo, tiempos, ParametrosBalon())
    assert max(_dist_a_deteccion_mas_cercana(salida, tray)) < 0.5


def test_la_recta_del_vuelo_se_reparte_por_TIEMPO_no_por_indice():
    """Una recta despegue→aterrizaje avanza a velocidad constante en el TIEMPO.

    Segundo fallo de las "alas" (21-sep-2026): `alfa` se calculaba por índice
    de muestra, y con huecos de detección dentro del vuelo unos pasos salían
    enormes y otros diminutos. De 98 vuelos con pasos imposibles, 88 tenían
    una velocidad media física entre sus extremos.
    """
    # despegue en x=0, 3 muestras aéreas y aterrizaje en x=20; hay un hueco de
    # 0,6 s antes de la última muestra aérea (detecciones perdidas en pleno vuelo)
    posiciones = [(0.0, 20.0)] * 4 + [(9.0, 20.0)] * 3 + [(20.0, 20.0)] * 4
    aereo = [False] * 4 + [True] * 3 + [False] * 4
    tray, aereo, tiempos = _serie(posiciones, aereo, huecos_s={6: 0.6})
    salida = preparar_para_replay(tray, aereo, tiempos, ParametrosBalon())
    por_frame = {f: (p, real) for f, p, _a, real in salida}
    aereas = [f for f, (_p, real) in por_frame.items() if not real]
    ini = max(f for f, (_p, real) in por_frame.items() if real and f < aereas[0])
    fin = min(f for f, (_p, real) in por_frame.items() if real and f > aereas[-1])
    t0, t1 = tiempos[ini], tiempos[fin]
    x0, x1 = por_frame[ini][0][0], por_frame[fin][0][0]
    for f in aereas:
        esperado = x0 + (x1 - x0) * (tiempos[f] - t0) / (t1 - t0)
        assert abs(por_frame[f][0][0] - esperado) < 0.05, (
            f"frame {f}: x={por_frame[f][0][0]:.2f}, esperado {esperado:.2f} "
            "si el reparto fuera por tiempo"
        )
