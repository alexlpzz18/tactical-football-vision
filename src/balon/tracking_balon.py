"""Tracking del balón: selección del activo, fases aéreas y contactos.

El balón no es "un jugador más pequeño" y tratarlo como tal falla por
tres motivos que este módulo aborda de frente:

1. **Puede haber varios.** En un campo de fútbol base hay balones de
   calentamiento parados en las bandas y en las porterías. El detector
   los encuentra todos y son indistinguibles del bueno por apariencia.
   Lo que los distingue es el COMPORTAMIENTO: el balón del partido se
   mueve y vive cerca del flujo de jugadores.

2. **Vuela.** La homografía proyecta el punto de apoyo suponiendo que
   está EN EL SUELO. Un balón por el aire viola esa suposición, y su
   posición proyectada se va metros — no es ruido, es que la geometría
   deja de aplicar. Marcarlo es más honesto que suavizarlo: en fase
   aérea la posición no se corrige, se declara no fiable.

3. **Los contactos son el dato.** Para el análisis táctico, dónde está
   el balón importa menos que quién lo toca y cuándo. Un contacto es un
   cambio brusco de dirección, y eso sí se puede detectar sin más señal
   que la trayectoria.
"""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ParametrosBalon:
    """Parámetros del tracking de balón, en unidades físicas."""

    # ── selección del balón activo ──
    # Un balón parado durante más de esto y lejos de los jugadores no es
    # el del partido (calentamiento, red de portería).
    v_min_activo: float = 0.5  # m/s de mediana para considerarlo en juego
    dist_max_jugadores: float = 25.0  # m al jugador más cercano
    # ── fases aéreas ──
    # Velocidad proyectada por encima de la cual la suposición de "está
    # en el suelo" es insostenible. Un balón raso rápido va a 15-20 m/s;
    # por encima, o vuela o la proyección ya no significa nada.
    v_max_raso: float = 20.0
    # Un balón por el aire se ve MÁS GRANDE de lo que le tocaría por su
    # distancia proyectada (está más cerca de la cámara que el punto del
    # suelo al que se le proyecta). Este es el factor de incoherencia a
    # partir del cual se sospecha vuelo.
    factor_tamano_aereo: float = 1.6
    duracion_min_aerea: float = 0.15  # s: por debajo es ruido, no un vuelo
    # ── contactos ──
    angulo_min_contacto: float = 45.0  # grados de cambio de dirección
    v_min_contacto: float = 2.0  # m/s: por debajo el ángulo es ruido
    dist_max_contacto: float = 3.0  # m al jugador que se le atribuye
    # ── suavizado e interpolación ──
    ventana_suavizado_s: float = 0.2  # corta: el balón cambia rápido
    max_hueco_interp_s: float = 0.4  # huecos cortos; el balón acelera

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosBalon":
        if not d:
            return cls()
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def seleccionar_balon_activo(
    detecciones: dict, posiciones_jugadores: dict, params: ParametrosBalon
) -> dict:
    """Se queda con UNA detección de balón por frame: la del partido.

    Args:
        detecciones: {frame_idx: [(mx, my, x1, y1, x2, y2, conf), ...]}.
        posiciones_jugadores: {frame_idx: [(mx, my), ...]}.
        params: ver ParametrosBalon.

    Returns:
        {frame_idx: deteccion} con como mucho una por frame.

    El criterio es de comportamiento, no de apariencia: los balones
    parados lejos del juego se descartan aunque el detector esté
    segurísimo de que son balones — porque lo son, solo que no el del
    partido.
    """
    # Agrupar detecciones en "candidatos" por continuidad espacial, para
    # poder medir si cada uno se mueve o está parado.
    candidatos: list[list[tuple]] = []
    for frame in sorted(detecciones):
        for det in detecciones[frame]:
            pos = np.array(det[:2])
            mejor = None
            for cand in candidatos:
                f_ult, d_ult = cand[-1]
                if frame - f_ult > 30:
                    continue
                if np.linalg.norm(np.array(d_ult[:2]) - pos) < 8.0:
                    mejor = cand
                    break
            (
                mejor if mejor is not None else candidatos.append([]) or candidatos[-1]
            ).append((frame, det))

    activos = set()
    for i, cand in enumerate(candidatos):
        if len(cand) < 3:
            activos.add(i)  # muy corto para juzgarlo: no se descarta
            continue
        pos = np.array([d[:2] for _f, d in cand])
        desplazamiento = float(np.median(np.linalg.norm(np.diff(pos, axis=0), axis=1)))
        cerca = []
        for frame, det in cand:
            jugadores = posiciones_jugadores.get(frame)
            if jugadores:
                d = np.linalg.norm(np.array(jugadores) - np.array(det[:2]), axis=1)
                cerca.append(float(d.min()))
        dist_tipica = float(np.median(cerca)) if cerca else 0.0
        # Se descarta solo si está quieto Y lejos: cualquiera de las dos
        # cosas por separado le pasa al balón bueno (parado en un saque,
        # o lejos en un despeje largo).
        if desplazamiento < 0.05 and dist_tipica > params.dist_max_jugadores:
            logger.info(
                "Balón candidato descartado: quieto (%.2f m/paso) y a %.0f m "
                "del jugador más cercano — es de calentamiento",
                desplazamiento,
                dist_tipica,
            )
            continue
        activos.add(i)

    resultado: dict[int, tuple] = {}
    for i, cand in enumerate(candidatos):
        if i not in activos:
            continue
        for frame, det in cand:
            # Si dos activos coinciden en un frame, gana la confianza
            if frame not in resultado or det[6] > resultado[frame][6]:
                resultado[frame] = det
    return resultado


def detectar_fases_aereas(
    trayectoria: list[tuple], tiempos: dict, params: ParametrosBalon
) -> list[bool]:
    """Marca qué observaciones son de un balón por el AIRE.

    Dos señales independientes, y basta con una:

    - **Velocidad proyectada imposible**: la proyección supone suelo, así
      que un vuelo produce saltos que ningún balón raso daría.
    - **Tamaño incoherente con la distancia**: un balón por el aire está
      más cerca de la cámara que el punto del suelo al que se le
      proyecta, así que se ve MÁS GRANDE de lo que le tocaría. Es la
      señal más específica, porque no depende de la velocidad.

    Args:
        trayectoria: [(frame_idx, pos_m, alto_px, conf)] ordenada.
        tiempos: {frame_idx: t}.
        params: ver ParametrosBalon.

    Returns:
        Lista de booleanos, uno por observación.
    """
    n = len(trayectoria)
    if n < 3:
        return [False] * n

    aereo = [False] * n

    # Señal 1: velocidad proyectada
    for i in range(1, n):
        f0, p0 = trayectoria[i - 1][0], np.array(trayectoria[i - 1][1])
        f1, p1 = trayectoria[i][0], np.array(trayectoria[i][1])
        dt = tiempos.get(f1, 0) - tiempos.get(f0, 0)
        if dt <= 0:
            continue
        if float(np.linalg.norm(p1 - p0)) / dt > params.v_max_raso:
            aereo[i - 1] = aereo[i] = True

    # Señal 2: tamaño incoherente con la distancia proyectada.
    # Se aprende la relación tamaño↔distancia con las propias
    # observaciones (mediana por franja), en vez de suponer una cámara.
    distancias = np.array([np.linalg.norm(np.array(o[1])) for o in trayectoria])
    altos = np.array([o[2] for o in trayectoria], dtype=float)
    validos = altos > 0
    if validos.sum() >= 8:
        # Modelo simple: alto_esperado ≈ k / distancia (perspectiva)
        k = float(np.median(altos[validos] * distancias[validos]))
        for i in range(n):
            if not validos[i] or distancias[i] <= 0:
                continue
            esperado = k / distancias[i]
            if esperado > 0 and altos[i] / esperado > params.factor_tamano_aereo:
                aereo[i] = True

    # Las rachas demasiado cortas son ruido, no un vuelo
    i = 0
    while i < n:
        if not aereo[i]:
            i += 1
            continue
        j = i
        while j < n and aereo[j]:
            j += 1
        t_ini = tiempos.get(trayectoria[i][0], 0)
        t_fin = tiempos.get(trayectoria[j - 1][0], 0)
        if t_fin - t_ini < params.duracion_min_aerea:
            for k2 in range(i, j):
                aereo[k2] = False
        i = j
    return aereo


def detectar_contactos(
    trayectoria: list[tuple],
    tiempos: dict,
    posiciones_jugadores: dict,
    equipos_por_frame: dict | None,
    params: ParametrosBalon,
) -> list[dict]:
    """Contactos: cambios BRUSCOS de dirección del balón.

    Un contacto es lo único que cambia la trayectoria de un balón (más la
    fricción y el bote, que no cambian la dirección de golpe). Se
    atribuye al jugador más cercano, y si ninguno está lo bastante cerca
    se registra igualmente sin dueño: es información honesta —hubo un
    contacto y no sabemos de quién— y no un dato que inventar.

    Returns:
        [{t, frame, x_m, y_m, angulo, id_jugador, equipo, dist_m}]
    """
    contactos = []
    for i in range(1, len(trayectoria) - 1):
        f_prev, p_prev = trayectoria[i - 1][0], np.array(trayectoria[i - 1][1])
        f_act, p_act = trayectoria[i][0], np.array(trayectoria[i][1])
        f_sig, p_sig = trayectoria[i + 1][0], np.array(trayectoria[i + 1][1])
        dt1 = tiempos.get(f_act, 0) - tiempos.get(f_prev, 0)
        dt2 = tiempos.get(f_sig, 0) - tiempos.get(f_act, 0)
        if dt1 <= 0 or dt2 <= 0:
            continue
        v1, v2 = (p_act - p_prev) / dt1, (p_sig - p_act) / dt2
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        # Con el balón casi parado, el ángulo lo decide el ruido
        if min(n1, n2) < params.v_min_contacto:
            continue
        coseno = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
        angulo = float(np.degrees(np.arccos(coseno)))
        if angulo < params.angulo_min_contacto:
            continue

        id_jugador, equipo, dist = None, None, None
        jugadores = posiciones_jugadores.get(f_act)
        if jugadores:
            arr = np.array([j[:2] for j in jugadores])
            d = np.linalg.norm(arr - p_act, axis=1)
            k = int(np.argmin(d))
            if d[k] <= params.dist_max_contacto:
                dist = float(d[k])
                if len(jugadores[k]) > 2:
                    id_jugador = jugadores[k][2]
                if equipos_por_frame:
                    equipo = equipos_por_frame.get(f_act, {}).get(id_jugador)
        contactos.append(
            {
                "frame": f_act,
                "t": tiempos.get(f_act),
                "x_m": float(p_act[0]),
                "y_m": float(p_act[1]),
                "angulo": angulo,
                "id_jugador": id_jugador,
                "equipo": equipo,
                "dist_m": dist,
            }
        )
    logger.info(
        "Contactos detectados: %d (%d con jugador atribuido)",
        len(contactos),
        sum(1 for c in contactos if c["id_jugador"] is not None),
    )
    return contactos
