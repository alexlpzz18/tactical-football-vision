"""Regla de porteros por POSICIÓN (independiente del color).

El clasificador de color no puede asignar equipo a los porteros (visten
distinto que su equipo), pero su posición los delata: una identidad cuya
posición MEDIANA vive dentro de un área de penalti es el portero del
equipo que defiende ese lado. La mediana (no la media) hace la regla
robusta a observaciones sueltas fuera del área.

Verificado sobre el GT del tramo de validación: portero_A (defiende el
lado de mx alto) tiene mediana mx=90.9 [85.1-95.5]; portero_B (mx bajo)
mediana mx=15.4 [11.9-17.9]; ningún jugador de campo tiene su mediana
dentro de esas zonas. Qué equipo defiende cada lado se indica en config
(en un partido real cambia al descanso; la automatización de ese mapeo
queda para la integración end-to-end).
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ReglaPorteros:
    """Áreas de penalti en metros (ejes de la homografía del partido)."""

    # Rango mx del área del lado bajo (portería izquierda en esta cámara)
    area_mx_bajo: tuple[float, float] = (0.0, 19.0)
    # Rango mx del área del lado alto
    area_mx_alto: tuple[float, float] = (86.0, 110.0)
    # Rango my común (ancho del área, generoso alrededor de la portería)
    area_my: tuple[float, float] = (20.0, 55.0)
    # Qué equipo defiende cada lado en este tramo
    equipo_mx_alto: str = "A"
    equipo_mx_bajo: str = "B"

    @classmethod
    def desde_dict(cls, d: dict) -> "ReglaPorteros":
        d = dict(d)
        for clave in ("area_mx_bajo", "area_mx_alto", "area_my"):
            if clave in d:
                d[clave] = tuple(d[clave])
        return cls(**d)

    @classmethod
    def desde_modelo(
        cls,
        modelo,
        margen: float = 2.0,
        equipo_mx_alto: str = "A",
        equipo_mx_bajo: str = "B",
    ) -> "ReglaPorteros":
        """Deriva las áreas del MODELO de campo en vez de hardcodearlas.

        Los valores por defecto de esta clase son los del F11 de
        Villaviciosa, ajustados a mano contra su ground truth. En un campo
        de otra medida no significan nada: un corte en mx=88,5 no existe
        en un campo de 62 m de largo. Con esto, la regla sale del
        reglamento de la modalidad y de las dimensiones reales del campo.
        """
        areas = modelo.areas_porteria(margen=margen)
        return cls(
            area_mx_bajo=areas["bajo"][0],
            area_mx_alto=areas["alto"][0],
            area_my=areas["bajo"][1],
            equipo_mx_alto=equipo_mx_alto,
            equipo_mx_bajo=equipo_mx_bajo,
        )


def _mediana(identidad: list[Tracklet]) -> tuple[float, float]:
    """Posición mediana de la identidad (mx, my)."""
    posiciones = np.array([pos for tr in identidad for pos in tr.pos])
    mediana = np.median(posiciones, axis=0)
    return float(mediana[0]), float(mediana[1])


def _en_area(mx: float, my: float, regla: "ReglaPorteros") -> str | None:
    """'bajo', 'alto' o None según en qué área de portería vive."""
    if not (regla.area_my[0] <= my <= regla.area_my[1]):
        return None
    if regla.area_mx_bajo[0] <= mx <= regla.area_mx_bajo[1]:
        return "bajo"
    if regla.area_mx_alto[0] <= mx <= regla.area_mx_alto[1]:
        return "alto"
    return None


def deducir_lados(
    equipos: dict[int, str],
    identidades: list[list[Tracklet]],
    largo: float,
    regla: "ReglaPorteros | None" = None,
    ancho: float | None = None,
    separacion_min_frac: float = 0.02,
) -> tuple[str, str] | None:
    """Qué equipo defiende cada portería, DEDUCIDO de las posiciones.

    Antes esto era un par de claves de config que había que "ajustar al
    partido" a mano. No funciona: nadie puede verificarlo a ojo sobre un
    replay, y en el benjamín estaba al revés — los porteros salían
    cruzados (el portero_A era en realidad el del equipo B).

    La señal que sí decide: el equipo que defiende la portería x=0 tiene
    a sus jugadores, en promedio, más cerca de ella que el rival, porque
    sus defensas viven ahí. Medido en el benjamín: A 30,0 m vs B 34,1 m
    sobre un campo de 62, una separación de 4,2 m que no deja duda y que
    da el lado CORRECTO (el contrario del que estaba configurado).

    Se usa el eje LARGO (pos[0]), que es donde están las porterías, sea
    cual sea el eje de profundidad de la cámara.

    ⚠️ Los propios porteros NO pueden votar, y por eso hace falta `regla`.
    El motivo no es que "voten al equipo contrario", sino que su etiqueta
    de color es basura: un portero viste distinto a sus compañeros, así
    que el clasificador le asigna un equipo prácticamente al azar. Y como
    además vive en un extremo del campo, ese voto aleatorio arrastra la
    media de quien le toque. Medido en el benjamín: dejándolos votar sale
    A 42,4 vs B 34,2 (invertido); excluyéndolos, A 30,0 vs B 34,1
    (correcto, y coincide con la verificación visual).

    Args:
        equipos: {id: etiqueta} del clasificador de color.
        identidades: las identidades, en el mismo orden 1..N.
        largo: largo del campo en metros.
        regla: si se pasa, las identidades que viven en un área de
            portería quedan EXCLUIDAS del voto (ver arriba).
        ancho: ancho del campo. Con él solo votan las posiciones DENTRO
            del campo — imprescindible, porque esta deducción corre antes
            que la regla de staff y en el fondo de la imagen hay público
            y suplentes proyectados a x=71, 80 y hasta 95 m sobre un
            campo de 62. Con ellos dentro, la media de su equipo se
            dispara y el signo vuelve a salir invertido.
        separacion_min_frac: separación mínima entre las medias, como
            fracción del largo, para fiarse. Por debajo se devuelve None
            y manda la config.

    Returns:
        (equipo_bajo, equipo_alto) o None si la señal no es concluyente.
    """
    posiciones: dict[str, list[float]] = {"A": [], "B": []}
    for indice, identidad in enumerate(identidades, start=1):
        etiqueta = equipos.get(indice)
        if etiqueta not in posiciones:
            continue  # porteros ya marcados, staff, 'otro': no votan
        if regla is not None and _en_area(*_mediana(identidad), regla) is not None:
            continue  # vive en un área: es portero, y su voto invierte el signo
        for tracklet in identidad:
            for pos in tracklet.pos:
                mx, my = float(pos[0]), float(pos[1])
                if not 0.0 <= mx <= largo:
                    continue
                if ancho is not None and not 0.0 <= my <= ancho:
                    continue
                posiciones[etiqueta].append(mx)

    if not posiciones["A"] or not posiciones["B"]:
        return None
    media_a = float(np.mean(posiciones["A"]))
    media_b = float(np.mean(posiciones["B"]))
    if abs(media_a - media_b) < separacion_min_frac * largo:
        logger.warning(
            "Lados de portería no concluyentes (A %.1f m vs B %.1f m, "
            "separación < %.0f %% del campo): se usa lo configurado",
            media_a,
            media_b,
            100 * separacion_min_frac,
        )
        return None

    bajo, alto = ("A", "B") if media_a < media_b else ("B", "A")
    logger.info(
        "Lados deducidos de las posiciones: %s defiende x=0 y %s x=%.0f "
        "(x media: A %.1f m, B %.1f m)",
        bajo,
        alto,
        largo,
        media_a,
        media_b,
    )
    return bajo, alto


def aplicar_regla_porteros(
    equipos: dict[int, str],
    identidades: list[list[Tracklet]],
    regla: ReglaPorteros,
) -> dict[int, str]:
    """Reetiqueta como portero_X las identidades que viven en un área.

    Args:
        equipos: {id_identidad (1..N): 'A'/'B'/'otro'} del clasificador de
            color. La regla SOBRESCRIBE la etiqueta de color (los porteros
            visten distinto y el color no es fiable para ellos).
        identidades: las identidades cosidas, en el mismo orden 1..N.
        regla: áreas y mapeo lado→equipo.

    Returns:
        Copia de `equipos` con las identidades de área reetiquetadas como
        'portero_A' / 'portero_B'.
    """
    resultado = dict(equipos)

    # EXCLUSIVIDAD: un solo portero por área. Antes, cualquier identidad
    # cuya mediana cayera en el área se convertía en portero, así que un
    # defensa que pasa el rato ahí —o un delantero que presiona— salía
    # reetiquetado. Caso real del benjamín: el id 55, un jugador de campo
    # del equipo B, se lo comió la regla.
    #
    # El criterio para elegir entre candidatos es la PERMANENCIA: el
    # portero es quien más observaciones acumula dentro del área, y por
    # goleada. Los demás se quedan con su etiqueta de color.
    candidatos: dict[str, list[tuple[int, int]]] = {"bajo": [], "alto": []}
    for id_identidad, identidad in enumerate(identidades, start=1):
        lado = _en_area(*_mediana(identidad), regla)
        if lado is None:
            continue
        dentro = sum(
            1
            for tracklet in identidad
            for pos in tracklet.pos
            if _en_area(float(pos[0]), float(pos[1]), regla) == lado
        )
        candidatos[lado].append((dentro, id_identidad))

    n_reetiquetadas = 0
    for lado, lista in candidatos.items():
        if not lista:
            continue
        lista.sort(reverse=True)
        dentro, id_identidad = lista[0]
        equipo = regla.equipo_mx_bajo if lado == "bajo" else regla.equipo_mx_alto
        resultado[id_identidad] = f"portero_{equipo}"
        n_reetiquetadas += 1
        for otros_dentro, otro_id in lista[1:]:
            logger.info(
                "Identidad %d vive en el área %s (%d obs) pero NO es portero: "
                "la %d lleva %d. Se queda con su etiqueta de color (%s)",
                otro_id,
                lado,
                otros_dentro,
                id_identidad,
                dentro,
                resultado.get(otro_id),
            )
    logger.info("Regla de porteros: %d identidades reetiquetadas", n_reetiquetadas)
    return resultado


# ─────────── El portero por COMPORTAMIENTO: el último hombre ───────────
#
# Por qué existe, y son tres hallazgos que costó medir (docs/portero.md):
#
# (a) **Pedirle al color que identifique al portero es circular.** Viste
#     distinto por reglamento, así que su color es justo el poco fiable —
#     que es la razón de buscarlo por comportamiento. En el benjamín el
#     catálogo arbitral lo manda al cajón 'otro' (azul eléctrico), y un
#     ranking que solo mirase identidades A/B **no puede encontrarlo**.
#     Por eso el voto incluye a las 'otro'.
#
# (b) **Y tienen que competir en LOS DOS lados**, no solo en el de su
#     etiqueta. Medido: al perturbar el caché, el clasificador metió a un
#     portero en el equipo contrario; como su voto solo contaba en el
#     lado de su etiqueta, sacó 0 de 494 y la regla se abstuvo teniéndolo
#     delante. El LADO dice el equipo, igual que en la regla de área.
#
# (c) **Ninguna salvaguarda separa sola, pero cada impostor falla al
#     menos una.** Es la misma forma que la regla del staff lento: dos
#     señales débiles que juntas son fuertes. Un impostor vive dentro del
#     área el 100 % del tiempo (un fragmento de 21 frames detrás de la
#     portería) y otro tiene el 99 % de presencia (un defensa); exigiendo
#     las dos salen 8 de 8 en las dos patas.
#
# Y lo que gana sobre la regla de área: esta NO necesita que la mediana
# caiga dentro del área, así que no se come al jugador de campo que pasa
# el rato ahí (el id 55), y funciona con el portero adelantado —medido
# contra el GT: en el 20 % de frames en que más sube sigue siendo último
# hombre el 100 % de las veces—.

Z_WILSON = 1.96


@dataclass
class ReglaPorteroUltimoHombre:
    """Parámetros del portero por comportamiento."""

    activo: bool = False
    # Fracción mínima de sus observaciones dentro de su propia área.
    # Umbrales sacados de la separación medida (porteros 99-100 %,
    # impostores 0-100 %; el hueco útil va de 27 a 98 %), no de números
    # que suenen bien.
    min_pisa_area: float = 0.50
    # Cota de Wilson mínima de "es el último hombre de su lado" para que
    # un fragmento entre en el CONJUNTO del portero. Ventana medida sobre
    # las dos patas y las dos longitudes: el portero del GT nunca baja de
    # 0,791 y el impostor verificado más alto llega a 0,341, así que la
    # ventana común es (0,34 · 0,79) y 0,55 es su centro. Por arriba el
    # límite es duro: con 0,80 el piloto de 5 min pierde al portero_B de
    # verdad, y con 0,90 se abstiene.
    min_ultimo_hombre: float = 0.55
    # Fracción mínima de frames NUEVOS que un fragmento tiene que aportar
    # al conjunto para entrar. Es una restricción FÍSICA, no un umbral
    # afinado: dos fragmentos presentes en el mismo frame no son el
    # portero antes y después, son el portero detectado DOS VECES, y
    # coronar los dos lo mete dos veces en el centroide de su equipo.
    # Medido: en el benjamín los cinco fragmentos del lado A solapan 0
    # frames entre sí (son consecutivos); en Villaviciosa el id 40 solapa
    # el 100 % de los suyos con el id 15 y el GT dice que los dos son el
    # `obj 1`. La separación es 0 % contra 100 %, así que el valor solo
    # tiene que caer en medio.
    min_frames_nuevos: float = 0.50
    # Fracción mínima del tramo en la que hay ALGÚN trozo del portero.
    # Se mide sobre la UNIÓN de los frames del conjunto, no fragmento a
    # fragmento: es lo único de las tres señales que depende de lo largo
    # que sea el tramo, y medirla por fragmento es lo que rompía la regla
    # a los 5 minutos (docs/portero.md).
    min_presencia: float = 0.50
    margen_area_m: float = 2.0

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ReglaPorteroUltimoHombre":
        return cls(**(d or {}))


def _wilson(exitos: int, total: int) -> float:
    """Cota inferior de Wilson al 95 %.

    No se usa el ratio a secas porque un fragmento con UNA observación en
    la que resulta ser último hombre puntuaría 1/1 = 100 % y le ganaría al
    portero real con 55/60. Y filtrar por un mínimo de presencia vacía el
    ranking, porque los fragmentos son cortos por definición: hay que
    ponderar por presencia, no filtrar por ella.
    """
    if total <= 0:
        return 0.0
    p = exitos / total
    centro = p + Z_WILSON**2 / (2 * total)
    margen = Z_WILSON * (
        (p * (1 - p) / total + Z_WILSON**2 / (4 * total * total)) ** 0.5
    )
    return max((centro - margen) / (1 + Z_WILSON**2 / total), 0.0)


def censar_candidatas(identidades, equipos, modelo):
    """Quién puede optar a portero y en qué frames se le ve. Sin decidir nada.

    Se separa del resto para que el banco de medida pueda ver la MISMA
    tabla que ve la regla, sin reimplementarla: una tabla reimplementada
    en un script mide otra cosa que la que corre en producción.

    Returns:
        (candidatas, por_frame, frames_de, n_frames), o None si no hay
        ninguna candidata.
    """
    candidatas = []
    for k, ident in enumerate(identidades, start=1):
        if str(equipos.get(k, "otro")) == "staff":
            continue
        pos = np.array([p for tracklet in ident for p in tracklet.pos])
        mx, my = float(np.median(pos[:, 0])), float(np.median(pos[:, 1]))
        if not (0.0 <= mx <= modelo.largo and 0.0 <= my <= modelo.ancho):
            continue
        candidatas.append(k)
    if not candidatas:
        return None

    # Posiciones por frame de cada candidata (una por frame aunque tenga
    # dos cajas: si no, una identidad duplicada votaría dos veces).
    por_frame: dict[int, dict[int, float]] = {}
    frames_de: dict[int, set] = {k: set() for k in candidatas}
    for k in candidatas:
        for tracklet in identidades[k - 1]:
            for pos, par in zip(tracklet.pos, tracklet.det_idxs):
                por_frame.setdefault(par[0], {})
                frames_de[k].add(par[0])
                por_frame[par[0]][k] = float(pos[0])
    return candidatas, por_frame, frames_de, max(len(por_frame), 1)


def puntuar_candidatas(identidades, censo, areas, lado):
    """Tabla de las candidatas de UN lado, ordenada por último hombre.

    Cada fila: `id`, `veces` (frames en que fue el último hombre de ese
    lado), `vista` (frames en que se la ve), `ultimo_hombre` (cota de
    Wilson de veces/vista), `pisa` (fracción de sus posiciones dentro del
    área) y `presencia` (fracción del tramo).

    Las tres señales son de naturaleza distinta a propósito: `pisa` y
    `ultimo_hombre` se normalizan por la propia identidad y **no dependen
    de lo largo que sea el tramo**; `presencia` sí. Por eso `presencia`
    no puede usarse por fragmento (docs/portero.md).
    """
    candidatas, por_frame, frames_de, n_frames = censo
    veces = {k: 0 for k in candidatas}
    for _f, gente in por_frame.items():
        if not gente:
            continue
        veces[min(gente, key=lambda k: -lado * gente[k])] += 1
    rx, ry = areas["bajo" if lado == -1 else "alto"]
    filas = []
    for k in candidatas:
        pos = np.array([p for tr in identidades[k - 1] for p in tr.pos])
        filas.append(
            {
                "id": k,
                "veces": veces[k],
                "vista": len(frames_de[k]),
                "ultimo_hombre": _wilson(veces[k], len(frames_de[k])),
                "pisa": float(
                    np.mean(
                        [rx[0] <= x <= rx[1] and ry[0] <= y <= ry[1] for x, y in pos]
                    )
                ),
                "presencia": len(frames_de[k]) / n_frames,
            }
        )
    filas.sort(key=lambda f: -f["ultimo_hombre"])
    return filas


def aplicar_regla_portero_ultimo_hombre(
    equipos: dict[int, str],
    identidades: list[list[Tracklet]],
    modelo,
    lados: dict[str, int],
    params: ReglaPorteroUltimoHombre,
) -> dict[int, str]:
    """Etiqueta como portero_X a quien más veces sea el último hombre de un lado.

    Args:
        equipos: {id: etiqueta} tal y como salen del color y del catálogo
            arbitral. Solo se excluyen del voto las marcadas 'staff'.
        identidades: las identidades, en el mismo orden 1..N.
        modelo: modelo de campo (da las áreas y el largo).
        lados: {equipo: -1 si defiende x=0, +1 si defiende x=largo}.
        params: umbrales.

    Returns:
        Copia de `equipos` con como mucho UN portero por lado. Si nadie
        cumple las dos salvaguardas en un lado, **no se corona a nadie**:
        la abstención es parte de la regla, no un fallo.
    """
    resultado = dict(equipos)
    if not params.activo or not lados:
        return resultado

    areas = modelo.areas_porteria(margen=params.margen_area_m)

    # ⚠️ El filtro de "fuera del campo" es GEOMÉTRICO y va aquí dentro, no
    # heredado de la etiqueta 'staff'. Motivo: en `clasificar_identidades`
    # la regla de staff corre DESPUÉS de esta, así que cuando esto se
    # ejecuta todavía no hay nadie marcado 'staff' y competían las
    # identidades del fondo lejano —público y árboles proyectados a x=79,
    # 101 y hasta 176 m sobre un campo de 62—. Como son las que más x
    # tienen, ganaban la votación del lado lejano y la regla se abstenía
    # teniendo al portero delante con 283/296.
    #
    # No se reordenan las reglas para arreglarlo: que la geometría de "no
    # juega" sea la última palabra está puesto a propósito.
    censo = censar_candidatas(identidades, equipos, modelo)
    if censo is None:
        return resultado

    _candidatas, _por_frame, frames_de, n_frames = censo
    for equipo, lado in lados.items():
        filas = puntuar_candidatas(identidades, censo, areas, lado)
        # EL PORTERO ES UN CONJUNTO, no una identidad. Sobre 20 minutos se
        # parte en trozos —medido en el piloto de 5 min: cuatro trozos en
        # el lado A (49/14/7/5 % de presencia) y dos en el B (66/26 %),
        # todos en el mismo metro cuadrado delante de su portería— y
        # coronar solo al mayor deja a los demás con su etiqueta de color,
        # que es justo el riesgo que esta regla existe para tapar.
        union: set = set()
        elegidos = []
        for f in filas:
            if (
                f["pisa"] < params.min_pisa_area
                or f["ultimo_hombre"] < params.min_ultimo_hombre
            ):
                continue
            propios = frames_de[f["id"]]
            nuevos = len(propios - union)
            if nuevos < params.min_frames_nuevos * len(propios):
                # Está a la vez que otro trozo ya coronado: es el mismo
                # portero detectado dos veces, no su continuación.
                logger.debug(
                    "Fragmento %d descartado del portero de %s: solo aporta "
                    "%d frames nuevos de %d",
                    f["id"],
                    equipo,
                    nuevos,
                    len(propios),
                )
                continue
            elegidos.append(f)
            union |= propios
        presencia = len(union) / n_frames
        if not elegidos or presencia < params.min_presencia:
            # WARNING y no INFO a propósito: abstenerse NO es gratis. El
            # portero de ese lado, si existe, se queda con su etiqueta de
            # COLOR, y la de un portero es poco fiable por diseño — puede
            # acabar contando para el equipo contrario y moviendo su
            # centroide. Es un riesgo conocido y aceptado (docs/portero.md),
            # pero si empieza a pasar en partidos reales hay que enterarse
            # por el log y no por el replay.
            mejor = filas[0]
            logger.warning(
                "SIN PORTERO en el lado de %s: %d fragmento(s) pasan las dos "
                "puertas y entre todos cubren el %.0f %% del tramo (mínimo "
                "%.0f %%). La mejor candidata es la identidad %d (último "
                "hombre %.2f, área %.0f %%). Si hay portero ahí, se quedará "
                "con su etiqueta de color y puede contar para el equipo "
                "contrario.",
                equipo,
                len(elegidos),
                100 * presencia,
                100 * params.min_presencia,
                mejor["id"],
                mejor["ultimo_hombre"],
                100 * mejor["pisa"],
            )
            continue
        for f in elegidos:
            resultado[f["id"]] = f"portero_{equipo}"
        logger.info(
            "Portero de %s: %d fragmento(s) %s, presencia conjunta %.0f %% "
            "(el mayor: último hombre %d/%d, área %.0f %%)",
            equipo,
            len(elegidos),
            [f["id"] for f in elegidos],
            100 * presencia,
            filas[0]["veces"],
            filas[0]["vista"],
            100 * filas[0]["pisa"],
        )
    return resultado
