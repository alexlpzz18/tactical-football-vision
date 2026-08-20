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
    # Velocidad a partir de la cual la posición NO es defendible pase lo
    # que pase. El filtro de duración mínima existe para no llamar vuelo
    # a un parpadeo, pero desmarcaba justo los saltos de un frame — que
    # son los que producen el zigzag "de snitch" en el replay. Por encima
    # de esto, la observación se descarta aunque dure un solo frame.
    v_indefendible: float = 40.0
    # ── contactos ──
    # Endurecidos tras el piloto (16-ago-2026): con 45° y 2 m/s salían
    # 415 contactos en 5 min, o sea 83 por minuto, cuando un partido real
    # tiene 20-30 toques por minuto. El balón se muestrea a 15 fps y su
    # posición tiembla, así que el criterio laxo dispara con ruido.
    angulo_min_contacto: float = 70.0  # grados de cambio de dirección
    v_min_contacto: float = 4.0  # m/s: por debajo el ángulo es ruido
    # El cambio debe SOSTENERSE: un giro real cambia la dirección de los
    # siguientes frames, un pico de ruido vuelve a la trayectoria previa.
    frames_persistencia: int = 2
    dist_max_contacto: float = 3.0  # m al jugador que se le atribuye
    # ── contactos por OSCILACIÓN DE VELOCIDAD ──
    # El criterio del ángulo solo ve pases, tiros y rebotes: medido en el
    # GT de Alex, durante una conducción el balón va prácticamente recto
    # (ángulo mediano entre pasos: 5°, y solo 2 de 72 pasos superan los
    # 70°). Los toques de conducción necesitan otra señal, y la evidente
    # es que cada toque ACELERA el balón y entre toques se frena.
    aceleracion_min: float = 3.0  # m/s de subida en un paso
    separacion_min_contacto: float = 0.20  # s entre dos toques del mismo pie
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

    # Los saltos indefendibles se marcan aparte y NO los toca el filtro
    # de duración: son de un frame por naturaleza.
    indefendible = [False] * n
    for i in range(1, n):
        f0, p0 = trayectoria[i - 1][0], np.array(trayectoria[i - 1][1])
        f1, p1 = trayectoria[i][0], np.array(trayectoria[i][1])
        dt = tiempos.get(f1, 0) - tiempos.get(f0, 0)
        if dt > 0 and float(np.linalg.norm(p1 - p0)) / dt > params.v_indefendible:
            indefendible[i] = True

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

    for k in range(n):
        if indefendible[k]:
            aereo[k] = True
    return aereo


def detectar_contactos(
    trayectoria: list[tuple],
    tiempos: dict,
    posiciones_jugadores: dict,
    equipos_por_frame: dict | None,
    params: ParametrosBalon,
    aereo: list[bool] | None = None,
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
        # En fase aérea la posición proyectada no es fiable, así que
        # cualquier "cambio de dirección" ahí es paralaje, no un toque.
        if aereo is not None and (aereo[i] or aereo[i - 1] or aereo[i + 1]):
            continue
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

        # Persistencia: la dirección nueva debe mantenerse. Sin esto, un
        # solo frame ruidoso cuenta como contacto y vuelve a contar al
        # frame siguiente al deshacerse.
        k = params.frames_persistencia
        if k > 0 and i + 1 + k < len(trayectoria):
            p_fin = np.array(trayectoria[i + 1 + k][1])
            dt3 = tiempos.get(trayectoria[i + 1 + k][0], 0) - tiempos.get(f_sig, 0)
            if dt3 > 0:
                v3 = (p_fin - p_sig) / dt3
                n3 = np.linalg.norm(v3)
                if n3 > 0:
                    sigue = float(np.clip(np.dot(v2, v3) / (n2 * n3), -1.0, 1.0))
                    if float(np.degrees(np.arccos(sigue))) > 60.0:
                        continue  # no se sostiene: era ruido

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


def preparar_para_replay(
    trayectoria: list[tuple],
    aereo: list[bool],
    tiempos: dict,
    params: ParametrosBalon,
) -> list[tuple]:
    """Deja el balón listo para pintarse sin inventar coordenadas.

    Tres tratamientos, y el tercero es el importante:

    1. **Suavizado** de las posiciones de suelo, con ventana CORTA. El
       balón cambia de dirección mucho más rápido que un jugador, así que
       la ventana de 0,5 s que se usa con ellos lo aplanaría; 0,2 s quita
       el temblor sin comerse los cambios reales.
    2. **Interpolación** de los huecos cortos entre detecciones de suelo.
       El parpadeo de "aparece y desaparece" se lee como un fallo, y un
       hueco de dos frames se rellena sin inventar nada apreciable.
    3. **En fase AÉREA no se pinta la posición proyectada.** Esto no es
       cosmética: la homografía supone que el objeto está en el suelo, así
       que un balón por el aire se proyecta decenas de metros más lejos y
       da los zigzags de "snitch". La detección es correcta —la caja
       sigue al balón por el aire—, lo que no vale es la proyección.

       Entre el despegue y el bote se dibuja la RECTA que los une,
       atenuada y marcada como no real. Se probaron las tres opciones:

       - *congelar* en la última posición fiable deja al balón quieto y
         luego teletransportado al aterrizar — el salto no desaparece,
         solo se aplaza (medido: seguía habiendo un 5 % de pasos
         imposibles, todos en el aterrizaje);
       - *ocultarlo* rompe la continuidad y el entrenador pierde el hilo;
       - la *recta* es continua y no afirma nada que no se haya medido:
         une dos puntos REALES, y lo único que no sabemos —la curva por
         la que pasó— es justo lo que no se dibuja como cierto, porque va
         atenuado y con es_real=0.

    Returns:
        [(frame_idx, pos, es_aereo, es_real)] lista para el CSV.
    """
    if not trayectoria:
        return []

    suelo = [(i, t) for i, (t, a) in enumerate(zip(trayectoria, aereo)) if not a]
    if not suelo:
        return [(t[0], t[1], True, True) for t in trayectoria]

    # 1. suavizado de las posiciones de suelo
    ventana = max(3, int(round(params.ventana_suavizado_s / 0.067)))
    if ventana % 2 == 0:
        ventana += 1
    puntos = np.array([t[1] for _i, t in suelo], dtype=float)
    if len(puntos) >= ventana:
        nucleo = np.ones(ventana) / ventana
        suave = puntos.copy()
        for eje in (0, 1):
            relleno = np.pad(puntos[:, eje], ventana // 2, mode="edge")
            suave[:, eje] = np.convolve(relleno, nucleo, mode="valid")
        puntos = suave

    posicion_suelo = {idx: puntos[k] for k, (idx, _t) in enumerate(suelo)}

    # Para cada hueco aéreo, los dos extremos de suelo que lo encierran
    indices_suelo = sorted(posicion_suelo)
    salida = []
    for i, (frame, _pos, _alto, _conf) in enumerate(trayectoria):
        if i in posicion_suelo:
            salida.append((frame, posicion_suelo[i], False, True))
            continue
        previos = [k for k in indices_suelo if k < i]
        siguientes = [k for k in indices_suelo if k > i]
        if not previos:
            continue  # aún no hay ninguna posición fiable de la que partir
        a = posicion_suelo[previos[-1]]
        if not siguientes:
            salida.append((frame, a, True, False))  # no volvió al suelo
            continue
        b = posicion_suelo[siguientes[0]]
        # Recta entre despegue y bote: los dos extremos son medidas, y lo
        # de en medio va marcado como no real.
        alfa = (i - previos[-1]) / (siguientes[0] - previos[-1])
        salida.append((frame, a + alfa * (b - a), True, False))
    return salida


def detectar_contactos_por_velocidad(
    trayectoria: list[tuple],
    tiempos: dict,
    posiciones_jugadores: dict,
    equipos_por_frame: dict | None,
    params: ParametrosBalon,
    aereo: list[bool] | None = None,
) -> list[dict]:
    """Contactos por ACELERACIÓN del balón, no por cambio de dirección.

    Complementa a `detectar_contactos`, que es ciego a la conducción: un
    jugador que lleva el balón lo empuja repetidamente en la MISMA
    dirección, así que el ángulo no se entera. Lo que sí cambia en cada
    toque es la velocidad — sube de golpe y luego decae por rozamiento.

    Se buscan los picos de subida de velocidad: pasos donde el balón
    acelera más de `aceleracion_min` y esa subida es un máximo local. La
    separación mínima entre contactos evita contar dos veces el mismo
    toque cuando el pico dura dos muestras.
    """
    contactos = []
    if len(trayectoria) < 4:
        return contactos

    vel, ts = [], []
    for i in range(1, len(trayectoria)):
        f0, p0 = trayectoria[i - 1][0], np.array(trayectoria[i - 1][1])
        f1, p1 = trayectoria[i][0], np.array(trayectoria[i][1])
        dt = tiempos.get(f1, 0) - tiempos.get(f0, 0)
        vel.append(float(np.linalg.norm(p1 - p0)) / dt if dt > 0 else 0.0)
        ts.append(i)

    subidas = [0.0] + [vel[k] - vel[k - 1] for k in range(1, len(vel))]
    ultimo_t = -1e9
    for k in range(1, len(subidas) - 1):
        i = ts[k]
        if aereo is not None and (aereo[i] or aereo[i - 1]):
            continue  # en el aire la velocidad proyectada no significa nada
        if subidas[k] < params.aceleracion_min:
            continue
        if subidas[k] < subidas[k - 1] or subidas[k] < subidas[k + 1]:
            continue  # no es el pico: el toque está en el paso vecino
        frame = trayectoria[i][0]
        t = tiempos.get(frame, 0.0)
        if t - ultimo_t < params.separacion_min_contacto:
            continue
        ultimo_t = t

        pos = np.array(trayectoria[i][1])
        id_jugador, equipo, dist = None, None, None
        jugadores = posiciones_jugadores.get(frame)
        if jugadores:
            arr = np.array([j[:2] for j in jugadores])
            d = np.linalg.norm(arr - pos, axis=1)
            j = int(np.argmin(d))
            if d[j] <= params.dist_max_contacto:
                dist = float(d[j])
                if len(jugadores[j]) > 2:
                    id_jugador = jugadores[j][2]
                if equipos_por_frame:
                    equipo = equipos_por_frame.get(frame, {}).get(id_jugador)
        contactos.append(
            {
                "frame": frame,
                "t": t,
                "x_m": float(pos[0]),
                "y_m": float(pos[1]),
                "angulo": None,
                "aceleracion": float(subidas[k]),
                "criterio": "velocidad",
                "id_jugador": id_jugador,
                "equipo": equipo,
                "dist_m": dist,
            }
        )
    logger.info("Contactos por velocidad: %d", len(contactos))
    return contactos


def fusionar_contactos(por_angulo, por_velocidad, separacion=0.20):
    """Une los dos criterios sin contar dos veces el mismo toque.

    Un pase fuerte dispara los dos —cambia de dirección Y acelera—, así
    que sumarlos a secas inflaría el conteo justo en las acciones que ya
    se detectaban bien.
    """
    todos = sorted(
        [dict(c, criterio=c.get("criterio", "angulo")) for c in por_angulo]
        + list(por_velocidad),
        key=lambda c: c["t"],
    )
    fusionados = []
    for c in todos:
        if fusionados and c["t"] - fusionados[-1]["t"] < separacion:
            if fusionados[-1]["criterio"] != c["criterio"]:
                fusionados[-1]["criterio"] = "ambos"
            continue
        fusionados.append(c)
    return fusionados
