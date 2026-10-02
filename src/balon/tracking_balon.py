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

import bisect
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
    # ⚠️ ESTE UMBRAL ESTABA EN 25 m Y NO PODÍA DISPARARSE. Medido sobre la
    # parte entera, la distancia del balón REAL al jugador más cercano
    # tiene mediana 1,6 m, p95 8,3, p99 17,2 y **máximo 25,7**: el umbral
    # estaba por encima de casi todo lo observado, así que la guarda
    # existía sin poder actuar nunca (0,07 % de los instantes). Es el
    # mismo fracaso que `cota_plantilla.activa`, pero disfrazado de
    # número en vez de de interruptor: parecía proteger.
    #
    # Ahora sale de la ANCHURA DEL CAMPO —un cuarto— porque eso sí viaja
    # a otro partido: 10 m en fútbol 7 (40 m de ancho) y 16 en un F11 de
    # 64. A 10 m la guarda puede actuar sobre el 4 % de los instantes, y
    # deja intacto el 95 % del balón real, que está a menos de 8,3 m de
    # alguien.
    #
    # ⚠️ El grueso del trabajo lo hace ahora `marcas_estaticas`, que quita
    # las marcas pintadas del campo por su firma propia. Esta guarda solo
    # cubre lo que aquélla no ve.
    fraccion_ancho_campo: float = 0.25
    dist_max_jugadores: float = 10.0  # m; = fraccion_ancho_campo x 40 m
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
    # Relleno de huecos SIN detección, manteniendo la última posición. Los
    # dos umbrales están en el CENTRO de la meseta medida sobre los 622
    # huecos de la parte entera (`docs/relleno_de_huecos_balon.md`): entre
    # 0,3-0,5 s y 2-5 m/s el acierto se queda en 90-92 % y el peor 10 %
    # del error en 1,5-2,0 m. A partir de 0,6 s se cae.
    # ⚠️ Ninguno de los dos vale solo: por duración sola son 74 % y por
    # velocidad sola 82 %; juntos, 91 %. Poner cualquiera a 0 apaga el
    # relleno entero.
    max_hueco_relleno_s: float = 0.4
    vel_max_relleno_m_s: float = 4.0
    # El suavizado solo promedia dentro de un TRAMO continuo de suelo: un
    # vuelo o un hueco de detecciones mayor que esto lo corta. 0,15 y 0,2 s
    # dan el mismo resultado; a 0,3 s ya se cuelan filas (0,4 % a más de 1 m
    # de toda detección). Sin este corte, el 12,1 % de las filas "reales" del
    # partido entero no era ninguna detección (docs/balon_sin_alas.md).
    # ── relleno de huecos MIRANDO AL FUTURO (docs/balon_con_futuro.md, BACKLOG 30) ──
    # Se procesa en diferido: en un hueco ya se sabe dónde REAPARECE el balón.
    # Una recta por tiempo entre el punto de antes y el de después acierta el
    # 83 % a menos de 2 m contra el 51 % de mantener la posición (huecos reales,
    # reponderados; 97 % en los de 0,7-1,2 s). Con estas guardas cubre ~1.200
    # frames contra los ~395 de mantener, con un 99 % esperado a menos de 2 m.
    # Los rellenos NO son medidas: es_real=False y fuera de contactos y posesión.
    interp_futuro_max_hueco_s: float = 1.2  # 0 = apagado
    interp_futuro_vel_max_m_s: float = 12.0  # entre los extremos: más es otro balón
    # Zona cercana a la cámara: allí muchos huecos son balón FUERA de encuadre y
    # la recta inventaría un trayecto por césped vacío. Es de ESTE campo (62 m).
    interp_futuro_x_min_m: float = 20.0
    max_hueco_suavizado_s: float = 0.2
    # ── puerta de continuidad EN PÍXELES (docs/balon_sin_alas.md, BACKLOG 28) ──
    # Un salto imposible en metros puede ser un vuelo o un CAMBIO DE CANDIDATO
    # (dos detecciones que no son el mismo balón), y en metros no se distinguen:
    # `detectar_fases_aereas` marca como aéreo cualquier salto por velocidad.
    # En píxeles sí: 44 "vuelos" de extremos imposibles saltaban una mediana de
    # 539 px (2.105 px/s) contra 33 px (86 px/s) de 651 vuelos físicos. A
    # 1.000 px/s se cazan 38 de 44 tocando al 1,4 % de los físicos; entre pares
    # de suelo contiguos solo 17 de 4.919 (0,35 %) la superan.
    # ⚠️ Los 9 físicos afectados pueden ser también cambios de candidato: no hay
    # GT del balón para saberlo.
    vel_max_px_s: float = 1000.0
    dt_max_puerta_par_s: float = 0.3  # entre dos filas de suelo contiguas
    dt_max_puerta_vuelo_s: float = 6.0  # entre los extremos de un vuelo
    # ── selección por CONTINUIDAD (Viterbi, docs/selector_balon.md, Plan 1b/1c) ──
    # Elegir frame a frame acertaba 16 de 38 desempates y saltaba de objeto
    # 53 veces por minuto. Con continuidad se busca la secuencia más coherente
    # del partido entero (`_viterbi_de_continuidad`), con la MISMA puerta de
    # píxeles de arriba. Adoptado el 1-oct-2026 con 1c: GT 16 → 31 de 38,
    # 53 → 2 cambios de objeto por minuto, y en los dos tramos etiquetados a
    # ojo el balón elegido sube de 219 a 239 frames y lo que no es balón baja
    # de 79 a 3. Cuesta 903 frames con "balón" (−11 %): casi todos botas y
    # objetos diminutos (3 de 40 al azar eran balón real).
    continuidad_activa: bool = True
    continuidad_dt_max_s: float = 0.5  # hueco máximo para seguir la misma pista
    continuidad_holgura_px: float = 20.0  # temblor de la caja a velocidad cero
    # Lo que cuesta saltar a un objeto que no es continuación de la pista,
    # en FRAMES "sin balón": el único parámetro de 1b. Centro geométrico de
    # la meseta de cambios por minuto (0,5-16, todos 2-3/min); a 32 ya
    # pierde balón real.
    continuidad_coste_salto: float = 3.0
    # ── 1c: lo que es DEMASIADO PEQUEÑO para ser el balón en esa fila ──
    # Con continuidad sola quedan dos fallos: la bota pegada al balón (están
    # dentro de la misma puerta y desempata la cercanía al jugador, que gana
    # la bota) y un objeto quieto que se detecta más que el balón (el zapato
    # del entrenador). Los dos son PEQUEÑOS: el tamaño esperado sale de la
    # física, un balón de `diametro_balon_m` proyectado con la homografía en
    # ese punto. Medido en los 36 balones del GT, lado/esperado tiene mediana
    # 1,90 (p10 1,77, p90 2,19); lo que no es balón, 0,87.
    continuidad_desempate_por_tamano: bool = True  # el más grande gana el empate
    # lado/esperado por debajo = pequeño; 0 = apagado. Meseta 0,8-1,8 (GT,
    # tramos y cambios iguales); a 2,0 ya castiga balones. 1,2 es su centro.
    continuidad_umbral_pequeno: float = 1.2
    # Un candidato pequeño vale lo mismo que no ver nada: no es un número
    # ajustado, es la definición de "no sirve como balón".
    continuidad_coste_pequeno: float = 1.0
    diametro_balon_m: float = 0.20  # balón del número 4 (fútbol base)
    # ── Plan 2: el balón de un STAFF fuera del campo no es el del partido ──
    # Un niño del banquillo juega con otro balón fuera de la banda; mientras
    # el del partido no se detecta, es el ÚNICO candidato y es grande y real:
    # ni la continuidad ni el tamaño lo quitan (183 frames en 4 episodios).
    # Se quita lo que está FUERA del campo, con un staff más cerca que
    # cualquier jugador y ningún jugador a `dist_max_contacto` (nadie puede
    # estar tocándolo). Coste medido: 5 frames de balón en juego disputado en
    # la línea delante del entrenador (docs/selector_balon.md).
    quitar_balon_de_staff: bool = True

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosBalon":
        if not d:
            return cls()
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def seleccionar_balon_activo(
    detecciones: dict,
    posiciones_jugadores: dict,
    params: ParametrosBalon,
    tiempos: dict | None = None,
    homografia=None,
    posiciones_staff: dict | None = None,
    dimensiones_campo: tuple[float, float] | None = None,
) -> dict:
    """Se queda con UNA detección de balón por frame: la del partido.

    Args:
        detecciones: {frame_idx: [(mx, my, x1, y1, x2, y2, conf), ...]}.
        posiciones_jugadores: {frame_idx: [(mx, my), ...]}.
        params: ver ParametrosBalon.
        tiempos: {frame_idx: segundos}; solo hace falta con
            `params.continuidad_activa`.
        homografia: matriz 3x3 de píxeles a metros; solo hace falta con
            `params.continuidad_umbral_pequeno` > 0.
        posiciones_staff, dimensiones_campo: {frame: [(mx, my)]} del staff y
            (largo, ancho) en metros; solo hacen falta con
            `params.quitar_balon_de_staff`.

    Returns:
        {frame_idx: deteccion} con como mucho una por frame.

    El criterio es de comportamiento, no de apariencia: los balones
    parados lejos del juego se descartan aunque el detector esté
    segurísimo de que son balones — porque lo son, solo que no el del
    partido.
    """
    if params.quitar_balon_de_staff:
        if posiciones_staff is None or dimensiones_campo is None:
            raise ValueError(
                "Quitar el balón del staff necesita las posiciones del staff y el campo"
            )
        detecciones = quitar_balones_de_staff(
            detecciones,
            posiciones_jugadores,
            posiciones_staff,
            dimensiones_campo,
            params,
        )

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

    # ── DESEMPATE cuando sobreviven varios candidatos ────────────────
    #
    # Pasa en el 23,4 % de los frames con balón, así que no es un caso
    # raro. Antes ganaba la CONFIANZA, que es un criterio de APARIENCIA —
    # justo lo que el docstring de esta función dice que no sirve, porque
    # una marca pintada del campo es tan "balón" como un balón.
    #
    # Gana la CERCANÍA A UN JUGADOR, que es de comportamiento: el balón
    # del partido vive entre los pies de alguien (mediana 1,8 m) y una
    # marca no (13,8 m). Medido sobre los 2.374 desempates de la parte
    # entera, con las marcas conocidas como verdad:
    #
    #   | criterio | acierta |
    #   |---|---|
    #   | confianza (el anterior) | 71,5 % |
    #   | **cercanía a un jugador** | **77,5 %** |
    #   | movimiento del candidato | 68,5 % |
    #   | cercanía + movimiento | 77,3 % |
    #
    # ⚠️ DOS NEGATIVOS que conviene no volver a intentar. El MOVIMIENTO
    # desempata PEOR que la confianza, aunque sea la señal que separa las
    # marcas en el filtro de arriba: los candidatos que llegan al
    # desempate son justo los que ya sobrevivieron a esa señal, así que
    # ahí no discrimina. Y sumarle movimiento a la cercanía no aporta
    # nada (77,3 contra 77,5).
    def _dist_a_jugador(frame, det):
        jugadores = posiciones_jugadores.get(frame)
        if not jugadores:
            return float("inf")  # sin jugadores no se puede juzgar
        d = np.linalg.norm(np.array(jugadores) - np.array(det[:2]), axis=1)
        return float(d.min())

    # Todos los supervivientes de cada frame, ORDENADOS por ese criterio: el
    # primero es el que se elige frame a frame. La selección por continuidad
    # (`_viterbi_de_continuidad`) usa la lista entera y el orden solo para
    # desempatar. Con todo empatado a infinito (sin posiciones de jugadores)
    # se cae a la confianza: es lo único que queda, no un segundo criterio
    # con voz propia. El orden es estable, así que en un empate total gana
    # el primero que apareció, como antes.
    por_frame: dict[int, list] = {}
    for i, cand in enumerate(candidatos):
        if i not in activos:
            continue
        for frame, det in cand:
            por_frame.setdefault(frame, []).append((_dist_a_jugador(frame, det), det))
    ordenados = {
        f: [det for _d, det in sorted(lista, key=lambda x: (x[0], -x[1][6]))]
        for f, lista in por_frame.items()
    }
    if params.continuidad_activa:
        if tiempos is None:
            raise ValueError(
                "La selección por continuidad necesita los tiempos de cada frame"
            )
        if params.continuidad_umbral_pequeno > 0 and homografia is None:
            raise ValueError("Juzgar si un candidato es pequeño necesita la homografía")
        return _viterbi_de_continuidad(ordenados, tiempos, params, homografia)
    return {f: lista[0] for f, lista in ordenados.items()}


def quitar_balones_de_staff(
    detecciones: dict,
    posiciones_jugadores: dict,
    posiciones_staff: dict,
    dimensiones_campo: tuple[float, float],
    params: "ParametrosBalon",
) -> dict:
    """Quita los balones FUERA del campo que son de un staff, no de un jugador.

    Tres condiciones a la vez (ver `ParametrosBalon.quitar_balon_de_staff`):
    fuera de las líneas, un staff más cerca que cualquier jugador, y ningún
    jugador a `dist_max_contacto`.
    """
    largo, ancho = dimensiones_campo
    salida, quitadas = {}, 0
    for frame, dets in detecciones.items():
        jug = np.array(posiciones_jugadores.get(frame) or [], dtype=float).reshape(
            -1, 2
        )
        staff = np.array(posiciones_staff.get(frame) or [], dtype=float).reshape(-1, 2)
        buenas = []
        for det in dets:
            p = np.array(det[:2], dtype=float)
            fuera = not (0.0 <= p[0] <= largo and 0.0 <= p[1] <= ancho)
            d_jug = float(np.linalg.norm(jug - p, axis=1).min()) if len(jug) else np.inf
            d_staff = (
                float(np.linalg.norm(staff - p, axis=1).min()) if len(staff) else np.inf
            )
            if fuera and d_staff < d_jug and d_jug > params.dist_max_contacto:
                quitadas += 1
            else:
                buenas.append(det)
        if buenas:
            salida[frame] = buenas
    if quitadas:
        logger.info(
            "Balones de staff fuera del campo quitados: %d detecciones", quitadas
        )
    return salida


def _centro_px(det) -> tuple[float, float]:
    return ((det[2] + det[4]) / 2.0, (det[3] + det[5]) / 2.0)


def _lado_px(det) -> float:
    return float(max(det[4] - det[2], det[5] - det[3]))


def escala_px_por_m(homografia, cx: float, cy: float) -> float:
    """Píxeles por metro en HORIZONTAL de la imagen, en el punto (cx, cy) del suelo.

    Se usa la horizontal porque una esfera no se acorta con la perspectiva
    como el césped: su anchura en la imagen es la de un segmento horizontal
    a su misma distancia. Diferencia finita de 1 px con la homografía.
    """
    h = np.asarray(homografia, dtype=float)
    p = np.array([[cx, cy, 1.0], [cx + 1.0, cy, 1.0]]) @ h.T
    m = p[:, :2] / p[:, 2:3]
    paso_m = float(np.linalg.norm(m[1] - m[0]))
    return 1.0 / paso_m if paso_m > 0 else float("inf")


def tamano_relativo(det, homografia, diametro_m: float = 0.20) -> float:
    """Lado de la caja / lo que mediría un balón de `diametro_m` en su sitio.

    Se mide en el PIE de la caja (el punto que toca el suelo). En los balones
    del GT sale ~1,9 (la caja del detector es más holgada que el balón).
    """
    cx = (det[2] + det[4]) / 2.0
    return _lado_px(det) / (diametro_m * escala_px_por_m(homografia, cx, det[5]))


def _viterbi_de_continuidad(
    ordenados: dict, tiempos: dict, params: "ParametrosBalon", homografia=None
) -> dict:
    """Elige la secuencia de candidatos más COHERENTE de todo el partido.

    Se procesa en diferido, así que para decidir un frame se puede mirar el
    pasado y el futuro. En cada frame con candidatos el estado es "el
    candidato i" o "sin balón" (docs/selector_balon.md, Plan 1b):

    - Seguir la pista (de un candidato a otro hasta `continuidad_dt_max_s`
      después) es GRATIS si el salto cabe en la puerta de píxeles de siempre,
      `vel_max_px_s` × dt + `continuidad_holgura_px`. Los frames intermedios
      cuentan como "sin balón".
    - Cada frame "sin balón" cuesta 1.
    - Empezar una pista que no es continuación de la anterior (un SALTO a otro
      objeto) cuesta `continuidad_coste_salto`, en las mismas unidades: un
      objeto lejano solo gana si cubre más frames de los que cuesta saltar a
      él y volver.

    ⚠️ Con solo el coste de "sin balón" el problema no tiene parámetro: si
    todo lo demás es gratis, multiplicarlo por cualquier λ da la misma
    solución. Lo que se elige es la RELACIÓN entre los dos costes, y se lee
    en frames: cuánto tiene que durar un objeto que aparece lejos de la pista
    para creérselo.

    Desempate (segunda cifra del coste, solo cuenta a igualdad de la
    primera): preferir lo que elegiría el criterio frame a frame. Así, donde
    la continuidad no dice nada, el resultado es exactamente el de antes.
    Con `continuidad_desempate_por_tamano`, el preferido es el más GRANDE
    (1c): la bota pegada al balón está más cerca del jugador, pero es menor.

    1c, además: un candidato con `tamano_relativo` por debajo de
    `continuidad_umbral_pequeno` cuesta `continuidad_coste_pequeno` (lo mismo
    que un frame sin balón), así que un objeto pequeño ya no gana por
    detectarse mucho.

    Args:
        ordenados: {frame: [det, ...]} supervivientes, el preferido primero.
        tiempos: {frame: segundos}.
        params: ver ParametrosBalon.

    Returns:
        {frame: det} con como mucho uno por frame; los frames "sin balón" no
        aparecen.
    """
    frames = sorted(ordenados)
    centros = [[np.array(_centro_px(d)) for d in ordenados[f]] for f in frames]
    salto = float(params.continuidad_coste_salto)
    # El preferido de cada frame para el desempate, y el coste propio de
    # cada candidato (0, o el de "pequeño").
    preferido = [
        (
            int(np.argmax([_lado_px(d) for d in ordenados[f]]))
            if params.continuidad_desempate_por_tamano
            else 0
        )
        for f in frames
    ]
    propio = [
        [
            (
                params.continuidad_coste_pequeno
                if params.continuidad_umbral_pequeno > 0
                and tamano_relativo(d, homografia, params.diametro_balon_m)
                < params.continuidad_umbral_pequeno
                else 0.0
            )
            for d in ordenados[f]
        ]
        for f in frames
    ]
    # coste[k][j] = (primaria, desempate) del mejor camino que acaba en el
    # candidato j del frame k; atras[k][j] = de dónde viene: (k2, i) o
    # (k2, None) si viene de "sin balón" en k2. Igual para nulo[k].
    coste: list[list[tuple]] = []
    atras: list[list[tuple]] = []
    nulo: list[tuple] = []
    atras_nulo: list[tuple] = []
    inicio = (0.0, 0)
    for k, f in enumerate(frames):
        t = tiempos[f]
        previo_nulo = nulo[k - 1] if k else inicio
        fila, fila_atras = [], []
        for j, c in enumerate(centros[k]):
            desempate = 0 if j == preferido[k] else 1
            mejor = (previo_nulo[0] + salto + propio[k][j], previo_nulo[1] + desempate)
            de_donde = (k - 1, None)
            k2 = k - 1
            while k2 >= 0 and t - tiempos[frames[k2]] <= params.continuidad_dt_max_s:
                dt = t - tiempos[frames[k2]]
                puerta = params.vel_max_px_s * dt + params.continuidad_holgura_px
                for i, c2 in enumerate(centros[k2]):
                    if float(np.linalg.norm(c - c2)) <= puerta:
                        opcion = (
                            coste[k2][i][0] + (k - k2 - 1) + propio[k][j],
                            coste[k2][i][1] + desempate,
                        )
                        if opcion < mejor:
                            mejor, de_donde = opcion, (k2, i)
                k2 -= 1
            fila.append(mejor)
            fila_atras.append(de_donde)
        coste.append(fila)
        atras.append(fila_atras)
        # "sin balón" en k: se llega desde cualquier estado de k-1.
        opciones = [(previo_nulo, (k - 1, None))]
        if k:
            opciones += [
                (coste[k - 1][i], (k - 1, i)) for i in range(len(coste[k - 1]))
            ]
        mejor_previo, de_donde = min(opciones, key=lambda x: x[0])
        nulo.append((mejor_previo[0] + 1, mejor_previo[1] + 1))
        atras_nulo.append(de_donde)

    if not frames:
        return {}
    ultimo = len(frames) - 1
    finales = [(nulo[ultimo], (ultimo, None))] + [
        (coste[ultimo][i], (ultimo, i)) for i in range(len(coste[ultimo]))
    ]
    _c, (k, j) = min(finales, key=lambda x: x[0])
    resultado: dict[int, tuple] = {}
    while k >= 0:
        if j is None:
            k, j = atras_nulo[k]
        else:
            resultado[frames[k]] = ordenados[frames[k]][j]
            k, j = atras[k][j]
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


def _interpolacion_con_futuro(
    fila_a: tuple,
    fila_b: tuple,
    faltan: list[int],
    tiempos: dict,
    params: ParametrosBalon,
) -> list[tuple] | None:
    """Filas de relleno por una recta entre dos anclas, o None si no procede.

    Las guardas (todas deben cumplirse) son las medidas en
    `docs/balon_con_futuro.md`: hueco corto, extremos compatibles con UN solo
    balón, fuera de la zona cercana, y anclas de suelo REAL — un relleno no puede
    ser ancla de otro, ni una posición aérea proyectada.
    """
    frame_a, pos_a, aereo_a, real_a = fila_a
    frame_b, pos_b, aereo_b, real_b = fila_b
    if params.interp_futuro_max_hueco_s <= 0:
        return None
    if aereo_a or aereo_b or not (real_a and real_b):
        return None
    dt = tiempos[frame_b] - tiempos[frame_a]
    if dt <= 0 or dt > params.interp_futuro_max_hueco_s:
        return None
    pos_a, pos_b = np.asarray(pos_a, dtype=float), np.asarray(pos_b, dtype=float)
    if float(np.linalg.norm(pos_b - pos_a)) / dt > params.interp_futuro_vel_max_m_s:
        return None
    if (pos_a[0] + pos_b[0]) / 2.0 < params.interp_futuro_x_min_m:
        return None
    return [
        (
            f,
            pos_a + (pos_b - pos_a) * (tiempos[f] - tiempos[frame_a]) / dt,
            False,
            False,
        )
        for f in faltan
    ]


def _rellenar_huecos_parados(
    salida: list[tuple],
    tiempos: dict,
    params: ParametrosBalon,
    cortes: set[int] | frozenset = frozenset(),
) -> list[tuple]:
    """Rellena huecos SIN detección manteniendo la última posición.

    Idea de Alex, y sale de una etiqueta suya del GT de huecos: en el caso
    4 escribió *"el balón está quieto exactamente en el mismo sitio que en
    el primer frame, parece un balón parado, falta o algo así, pero lo
    tapan los jugadores"*. Si el balón no se movía, mantener su última
    posición no es inventar: es lo único que sí sabemos.

    Dos condiciones, y **ninguna vale sola** — medido sobre los 622 huecos
    de la parte entera, contando acierto como "el balón reaparece a menos
    de 2 m de donde se mantuvo":

    | regla | huecos | acierto | peor 10 % |
    |---|---|---|---|
    | solo duración < 0,4 s | 493 | 74 % | 4,2 m |
    | solo velocidad < 4 m/s | 213 | 82 % | 4,6 m |
    | **las dos** | 171 | **91 %** | **1,9 m** |
    | (control) rellenar todo | 622 | 65 % | 7,1 m |
    | (control) la zona prohibida | 45 | 22 % | 15,4 m |

    La última fila es la que importa: los huecos LARGOS con el balón
    RÁPIDO son 2.033 frames —un tercio de todos los frames en hueco— y
    rellenarlos acierta el 22 % con una cola de 15,4 m. Ahí está casi toda
    la protección, y es exactamente el *"no rellenar si venía volando"*.

    ⚠️ Un matiz contra la intuición, por si alguien afina esto luego: la
    banda MÁS lenta (<1 m/s) **no** es la mejor, sino la de 1-3 m/s (74 %
    contra 85 %). Tiene sentido futbolístico: un balón completamente
    parado suele estarlo porque el juego está parado, y lo siguiente que
    pasa es un saque o una falta, o sea el balón yéndose lejos.
    """
    mantener_activo = params.max_hueco_relleno_s > 0 and params.vel_max_relleno_m_s > 0
    if not mantener_activo and params.interp_futuro_max_hueco_s <= 0:
        return salida  # relleno apagado a propósito
    if len(salida) < 2:
        return salida

    muestreados = sorted(tiempos)
    rellenos = []
    n_futuro = 0
    for k in range(len(salida) - 1):
        frame_a, pos_a, aereo_a, _real_a = salida[k]
        frame_b = salida[k + 1][0]
        if frame_a not in tiempos or frame_b not in tiempos:
            continue
        # Frames que el caché SÍ muestreó y quedaron sin balón.
        i = bisect.bisect_right(muestreados, frame_a)
        j = bisect.bisect_left(muestreados, frame_b)
        faltan = muestreados[i:j]
        if not faltan:
            continue
        # Con futuro primero: la recta entre las dos anclas es mejor que mantener
        # (y contiene a mantener como caso particular: extremos iguales). Si las
        # guardas no lo permiten, se cae a la regla de mantener de siempre.
        if frame_b not in cortes:
            recta = _interpolacion_con_futuro(
                salida[k], salida[k + 1], faltan, tiempos, params
            )
            if recta is not None:
                rellenos.extend(recta)
                n_futuro += len(recta)
                continue
        if not mantener_activo:
            continue
        if tiempos[frame_b] - tiempos[frame_a] > params.max_hueco_relleno_s:
            continue
        # Un corte de la puerta de píxeles: el balón de después NO es el de
        # antes, y mantener la posición sería inventar que sigue ahí.
        if frame_b in cortes:
            continue
        # Venía volando: la posición proyectada ya no es de fiar, y es el
        # caso que el GT dice que NO hay que rellenar.
        if aereo_a:
            continue
        # Velocidad en los pasos previos. Sin pasos previos no se rellena:
        # no hay con qué comprobar que estaba parado.
        anterior = None
        for atras in range(k - 1, max(k - 4, -1) - 1, -1):
            if salida[atras][0] in tiempos and not salida[atras][2]:
                anterior = salida[atras]
                break
        if anterior is None:
            continue
        dt = tiempos[frame_a] - tiempos[anterior[0]]
        if dt <= 0:
            continue
        if float(np.linalg.norm(np.asarray(pos_a) - np.asarray(anterior[1]))) / dt > (
            params.vel_max_relleno_m_s
        ):
            continue
        # es_real=False: se mantiene una medida anterior, no se ha medido.
        rellenos.extend((f, pos_a, False, False) for f in faltan)

    if not rellenos:
        return salida
    logger.info(
        "Relleno de huecos: %d frames por recta entre anclas (hueco <= %.1f s, "
        "v <= %.0f m/s, x >= %.0f m) y %d mantenidos (hueco <= %.1f s y balón a "
        "< %.1f m/s); el resto se deja vacío a propósito.",
        n_futuro,
        params.interp_futuro_max_hueco_s,
        params.interp_futuro_vel_max_m_s,
        params.interp_futuro_x_min_m,
        len(rellenos) - n_futuro,
        params.max_hueco_relleno_s,
        params.vel_max_relleno_m_s,
    )
    return sorted(salida + rellenos, key=lambda t: t[0])


ID_BALON = -1
ID_BALON_AEREO = -2


def id_de_tramo(k: int, aereo: bool = False) -> int:
    """Identidad del balón en el tramo `k` (0 = el primero).

    Un CORTE de la puerta de píxeles abre un tramo nuevo con otra identidad,
    para que el replay no una con una recta dos detecciones que no son el
    mismo balón. El primer tramo conserva -1 (balón) y -2 (marcador aéreo);
    el resto usa -102, -104... y -103, -105..., que no pisan a nadie.
    """
    if k == 0:
        return ID_BALON_AEREO if aereo else ID_BALON
    return -(101 + 2 * k) if aereo else -(100 + 2 * k)


def _tramos_continuos_de_suelo(
    trayectoria: list[tuple],
    indices_suelo: list[int],
    tiempos: dict,
    max_hueco_s: float,
    cortes: set[int] | frozenset = frozenset(),
) -> list[list[int]]:
    """Agrupa los índices de suelo en tramos SIN vuelo ni hueco de por medio.

    Dos observaciones de suelo son del mismo tramo si son contiguas en la
    trayectoria (no hay una aérea entre medias) y el tiempo que las separa
    no supera `max_hueco_s` (no se perdieron detecciones entre ellas).
    """
    tramos: list[list[int]] = []
    actual: list[int] = []
    for i in indices_suelo:
        if actual:
            previo = actual[-1]
            dt = tiempos.get(trayectoria[i][0], 0.0) - tiempos.get(
                trayectoria[previo][0], 0.0
            )
            if i != previo + 1 or dt > max_hueco_s or i in cortes:
                tramos.append(actual)
                actual = []
        actual.append(i)
    if actual:
        tramos.append(actual)
    return tramos


def preparar_para_replay(
    trayectoria: list[tuple],
    aereo: list[bool],
    tiempos: dict,
    params: ParametrosBalon,
) -> list[tuple]:
    """Igual que `preparar_balon` sin la puerta de píxeles (no hay `centros_px`).

    Se conserva porque es la interfaz que ya usaban los tests y los scripts.
    """
    return preparar_balon(trayectoria, aereo, tiempos, params)[0]


def preparar_balon(
    trayectoria: list[tuple],
    aereo: list[bool],
    tiempos: dict,
    params: ParametrosBalon,
    centros_px: dict | None = None,
) -> tuple[list[tuple], set[int]]:
    """Deja el balón listo para pintarse sin inventar coordenadas.

    Tres tratamientos, y el tercero es el importante:

    1. **Suavizado** de las posiciones de suelo, con ventana CORTA. El
       balón cambia de dirección mucho más rápido que un jugador, así que
       la ventana de 0,5 s que se usa con ellos lo aplanaría; 0,2 s quita
       el temblor sin comerse los cambios reales.
    2. **Relleno de los huecos SIN detección**, manteniendo la última
       posición, y solo cuando está medido que eso acierta: hueco corto y
       balón lento. Ver `_rellenar_huecos_parados` para los números y para
       los dos controles.

       ⚠️ Este tratamiento estaba ANUNCIADO AQUÍ Y NO EXISTÍA. El
       docstring decía "interpolación de los huecos cortos" y el
       parámetro `max_hueco_interp_s` estaba declarado, pero no lo leía
       nadie: lo único que se interpolaba eran las fases AÉREAS, que es
       otra cosa (ahí el balón SÍ está detectado y lo que falla es la
       proyección). Un docstring que describe una función que no se
       ejecuta miente igual que un "✓" sobre un fichero vacío.
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

    4. **Puerta de continuidad EN PÍXELES** (si se dan `centros_px`). Una racha
       aérea cuyos extremos de suelo saltan más de `vel_max_px_s` no es un
       vuelo: son dos detecciones que no son el mismo balón. No se dibuja la
       recta ni el marcador aéreo, y el aterrizaje abre un TRAMO nuevo (un
       CORTE): el suavizado y el relleno no lo cruzan, y el CSV le da otra
       identidad (`id_de_tramo`). Lo mismo entre dos filas de suelo contiguas.

    Args:
        centros_px: {frame: (cx, cy)} del centro de la caja en píxeles. Sin
            él la puerta no actúa.

    Returns:
        ([(frame_idx, pos, es_aereo, es_real)], cortes) — las filas para el
        CSV y el conjunto de frames donde empieza un tramo nuevo.
    """
    if not trayectoria:
        return [], set()

    suelo = [(i, t) for i, (t, a) in enumerate(zip(trayectoria, aereo)) if not a]
    if not suelo:
        return [(t[0], t[1], True, True) for t in trayectoria], set()

    # ── puerta de píxeles: qué filas de suelo abren un tramo nuevo ──
    cortes_idx: set[int] = set()
    if centros_px:
        for (i1, _t1), (i2, _t2) in zip(suelo, suelo[1:]):
            f1, f2 = trayectoria[i1][0], trayectoria[i2][0]
            if f1 not in centros_px or f2 not in centros_px:
                continue
            dt = tiempos.get(f2, 0.0) - tiempos.get(f1, 0.0)
            limite = (
                params.dt_max_puerta_par_s
                if i2 == i1 + 1
                else params.dt_max_puerta_vuelo_s
            )
            if dt <= 0 or dt > limite:
                continue
            dx = centros_px[f2][0] - centros_px[f1][0]
            dy = centros_px[f2][1] - centros_px[f1][1]
            if float(np.hypot(dx, dy)) / dt > params.vel_max_px_s:
                cortes_idx.add(i2)

    # 1. suavizado de las posiciones de suelo, POR TRAMOS CONTINUOS.
    #
    # ⚠️ Antes se promediaba la lista de suelo entera como si fuera una serie
    # continua, y esa lista SE SALTA los vuelos y los huecos: en el borde de
    # un vuelo mezclaba el punto de despegue con el de aterrizaje y la fila
    # resultante, marcada es_real=1, no era ninguna detección. Eran las
    # "alas" del balón: 270 pasos por encima de 40 m/s y el 12,1 % de las
    # filas reales a más de 1 m de toda detección (docs/balon_sin_alas.md).
    ventana = max(3, int(round(params.ventana_suavizado_s / 0.067)))
    if ventana % 2 == 0:
        ventana += 1
    posicion_suelo = {}
    for tramo in _tramos_continuos_de_suelo(
        trayectoria,
        [i for i, _t in suelo],
        tiempos,
        params.max_hueco_suavizado_s,
        cortes_idx,
    ):
        puntos = np.array([trayectoria[i][1] for i in tramo], dtype=float)
        if len(puntos) >= ventana:
            nucleo = np.ones(ventana) / ventana
            suave = puntos.copy()
            for eje in (0, 1):
                relleno = np.pad(puntos[:, eje], ventana // 2, mode="edge")
                suave[:, eje] = np.convolve(relleno, nucleo, mode="valid")
            puntos = suave
        for i, punto in zip(tramo, puntos):
            posicion_suelo[i] = punto

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
        if siguientes[0] in cortes_idx:
            continue  # los extremos no son el mismo balón: no hay vuelo que dibujar
        b = posicion_suelo[siguientes[0]]
        # Recta entre despegue y bote: los dos extremos son medidas, y lo
        # de en medio va marcado como no real.
        # ⚠️ Por TIEMPO, no por índice de muestra: con detecciones perdidas
        # dentro del vuelo, el reparto por índice hacía unos pasos enormes y
        # otros diminutos (88 de 98 vuelos con pasos imposibles tenían una
        # velocidad media física entre sus extremos).
        t_ini = tiempos[trayectoria[previos[-1]][0]]
        t_fin = tiempos[trayectoria[siguientes[0]][0]]
        alfa = (
            (tiempos[trayectoria[i][0]] - t_ini) / (t_fin - t_ini)
            if t_fin > t_ini
            else (i - previos[-1]) / (siguientes[0] - previos[-1])
        )
        salida.append((frame, a + alfa * (b - a), True, False))
    cortes = {trayectoria[i][0] for i in cortes_idx}
    return _rellenar_huecos_parados(salida, tiempos, params, cortes), cortes


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


def filtrar_balon_plausible(detecciones: dict, modelo, margen_m: float = 3.0) -> dict:
    """Quita las detecciones de balón que proyectan FUERA del campo.

    Es para el balón lo que `src/tracking/plausibilidad_fisica.py` es para
    los jugadores, y hacía falta: medido sobre el caché piloto, **el
    19,8 % de las detecciones de balón caen fuera del campo**, con la x
    llegando a 1760 m en un campo de 62. Son balón aéreo proyectado con
    una homografía de SUELO (z=0) más falsos positivos, y **la confianza
    no los separa**: 0,65 dentro contra 0,60 fuera.

    Lo que producen si no se quitan, que es el ejemplo de manual de por
    qué hay que desconfiar de un número implausible: la velocidad máxima
    del balón sale a **4151 m/s**, doce veces la del sonido.

    ⚠️ `seleccionar_balon_activo` NO protege de esto: agrupa por
    continuidad espacial y conserva a propósito los candidatos de menos de
    tres detecciones ("muy corto para juzgarlo"), así que una detección a
    1760 m forma su propio candidato y sobrevive.

    El margen por defecto (3 m) es holgado a propósito: un balón sale de
    banda de verdad, y el error de proyección en el fondo es grande. No
    se filtra por VELOCIDAD aquí porque de eso ya se ocupa
    `detectar_fases_aereas`, que además distingue el vuelo del error.

    Args:
        detecciones: {frame_idx: [(mx, my, x1, y1, x2, y2, conf), ...]}.
        modelo: modelo de campo (da largo y ancho).
        margen_m: cuánto se tolera fuera de la línea.

    Returns:
        El mismo diccionario sin las detecciones implausibles.
    """
    largo, ancho = modelo.largo, modelo.ancho
    salida, quitadas, total = {}, 0, 0
    for frame, dets in detecciones.items():
        buenas = []
        for det in dets:
            total += 1
            mx, my = float(det[0]), float(det[1])
            if (
                -margen_m <= mx <= largo + margen_m
                and -margen_m <= my <= ancho + margen_m
            ):
                buenas.append(det)
            else:
                quitadas += 1
        if buenas:
            salida[frame] = buenas
    if quitadas:
        logger.info(
            "Plausibilidad del balón: %d de %d detecciones fuera del campo "
            "(%.1f %%) descartadas",
            quitadas,
            total,
            100 * quitadas / max(total, 1),
        )
    return salida
