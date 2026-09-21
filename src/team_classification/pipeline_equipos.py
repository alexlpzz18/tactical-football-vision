"""Pipeline de clasificación de equipos por identidad (compartido banco↔producción).

Compone las piezas validadas y medidas:
1. TeamClassifierColor entrenado con TODAS las features del caché de colores.
2. Agregación por identidad con preferencia por recortes CERCANOS
   (my < umbral): donde el jugador es grande el color es señal; lejos es
   ruido (medido: accuracy 1.000 con ≥20 recortes cercanos vs 0.472 sin
   ninguno).
3. Regla de porteros por posición (sobrescribe al color).
"""

import logging
from pathlib import Path

import numpy as np
import yaml

from src.team_classification.color_classifier import (
    ParametrosClasificadorColor,
    TeamClassifierColor,
)
from src.campo_modelo import MODELO_F11, EjeProfundidad, cargar_modelo
from src.team_classification.arbitro import identificar_arbitros, un_solo_arbitro
from src.team_classification.oclusion import color_medio_limpio
from src.team_classification.porteros import (
    ReglaPorteros,
    ReglaPorteroUltimoHombre,
    aplicar_regla_porteros,
    aplicar_regla_portero_ultimo_hombre,
    deducir_lados,
)
from src.team_classification.staff import ReglaStaff, aplicar_regla_staff
from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)

RUTA_CONFIG_DEFECTO = Path("configs/team_classification.yaml")


def cargar_config_equipos(ruta: str | Path = RUTA_CONFIG_DEFECTO) -> dict:
    """Carga configs/team_classification.yaml (dict vacío si no existe)."""
    ruta = Path(ruta)
    if not ruta.exists():
        logger.warning("Sin %s: se usan los defaults del clasificador.", ruta)
        return {}
    with open(ruta) as f:
        return yaml.safe_load(f)


def _profundidad_configurada(cfg_equipos: dict):
    """(modelo de campo, eje de profundidad) según el config de equipos.

    Sin sección `campo` ni `profundidad`, devuelve el F11 de Villaviciosa
    con la profundidad en el eje ancho: exactamente el comportamiento
    histórico.
    """
    cfg_campo = cfg_equipos.get("campo", {})
    if "config" in cfg_campo:
        modelo = cargar_modelo(config=cfg_campo["config"])
    elif "tipo" in cfg_campo:
        modelo = cargar_modelo(cfg_campo["tipo"])
        if "largo" in cfg_campo and "ancho" in cfg_campo:
            modelo = modelo.con_dimensiones(cfg_campo["largo"], cfg_campo["ancho"])
    else:
        modelo = MODELO_F11
    return modelo, EjeProfundidad.desde_dict(cfg_equipos.get("profundidad"))


def entrenar_clasificador(
    colores: dict,
    cfg_equipos: dict | None = None,
    cache: list[dict] | None = None,
) -> TeamClassifierColor:
    """Entrena TeamClassifierColor. ÚNICO camino de entrenamiento del repo.

    FIT CON RECORTES CERCANOS (bug de producción del 12-jul-2026): entrenar
    con TODOS los recortes era estructuralmente frágil — la masa de
    recortes lejanos (jugadores <28 px, histogramas-ruido) emborronaba la
    separación y la fusión automática podía colapsar en un solo equipo
    (visto en Colab: A=10571/B=204). Filtrando el fit a recortes cercanos
    (my < umbral, donde la señal de color existe) los dos equipos separan
    equilibrados (1242/1233 en el tramo de validación) y la cobertura
    colectiva sube de 0.376 a 0.456. Config: sección `entrenamiento` de
    team_classification.yaml. Si tras filtrar quedan menos de
    `min_features`, se usa todo (con aviso): mejor un fit borroso que
    ninguno.

    Args:
        colores: caché de colores {(frame_idx, det_idx): feature}.
        cfg_equipos: contenido de team_classification.yaml.
        cache: lista de frames del caché de detecciones (para conocer la
            profundidad my de cada recorte). OBLIGATORIO si el filtro de
            entrenamiento está activo.
    """
    cfg_equipos = cfg_equipos or {}
    params = None
    if "clasificador_color" in cfg_equipos:
        params = ParametrosClasificadorColor.desde_dict(
            cfg_equipos["clasificador_color"]
        )

    cfg_fit = cfg_equipos.get("entrenamiento", {})
    solo_cercanos = cfg_fit.get("solo_cercanos", True)
    # `umbral_profundidad_m` es el nombre nuevo (metros DESDE LA CÁMARA);
    # `umbral_my` se acepta por compatibilidad con el config del F11.
    umbral = cfg_fit.get("umbral_profundidad_m", cfg_fit.get("umbral_my", 34.0))
    min_features = cfg_fit.get("min_features", 300)
    modelo, profundidad = _profundidad_configurada(cfg_equipos)

    # ── Recortar el fit en el TIEMPO (entrenamiento.desde_s) ─────────
    #
    # Los primeros minutos de un partido son otro régimen: saque inicial,
    # jugadores colocándose, gente entrando al campo. Medido en la parte
    # entera del benjamín, el fit del tramo 0-5 se desvía un 35 % de la
    # distancia A−B contra un nulo de remuestreo del 2,2 % — 16 veces el
    # ruido (docs/verificacion_adversarial_27ago.md).
    #
    # Con `desde_s` el fit ignora esos minutos. Se deja en None (todo) por
    # defecto: activarlo es una decisión de producto que hay que MEDIR,
    # no un ajuste gratis, porque quitar minutos también quita muestra.
    desde_s = cfg_fit.get("desde_s")
    if desde_s is not None:
        if cache is None:
            raise ValueError(
                "entrenar_clasificador: entrenamiento.desde_s necesita el "
                "caché de detecciones para saber el tiempo de cada recorte."
            )
        t_de_frame = {e["frame_idx"]: e["t"] for e in cache}
        antes = len(colores)
        colores = {
            clave: feature
            for clave, feature in colores.items()
            if t_de_frame.get(clave[0], 0.0) >= float(desde_s)
        }
        logger.info(
            "Fit recortado a t >= %.0f s: %d recortes de %d",
            float(desde_s),
            len(colores),
            antes,
        )

    features = np.array(list(colores.values()))
    if solo_cercanos:
        if cache is None:
            raise ValueError(
                "entrenar_clasificador: el fit con recortes cercanos está "
                "activo (entrenamiento.solo_cercanos) y requiere el caché "
                "de detecciones para conocer la profundidad de cada recorte. "
                "Pásalo (cache=datos['cache']) o desactiva el filtro."
            )
        prof_por_clave = {
            (entrada["frame_idx"], det_idx): profundidad.de((det[0], det[1]), modelo)
            for entrada in cache
            for det_idx, det in enumerate(entrada["dets"])
        }
        cercanas = np.array(
            [
                feature
                for clave, feature in colores.items()
                if prof_por_clave.get(clave, float("inf")) < umbral
            ]
        )
        if len(cercanas) >= min_features:
            features = cercanas
            logger.info(
                "Fit del clasificador con %d recortes a menos de %.0f m "
                "de la cámara (eje %s) de %d totales",
                len(cercanas),
                umbral,
                profundidad.eje,
                len(colores),
            )
        else:
            logger.warning(
                "Solo %d recortes cercanos (<%d): fit con TODAS las "
                "features (posible fusión frágil).",
                len(cercanas),
                min_features,
            )

    clasificador = TeamClassifierColor(params)
    clasificador.fit_features(features)
    return clasificador


def clasificar_identidades(
    identidades: list[list[Tracklet]],
    colores: dict,
    clasificador: TeamClassifierColor,
    cfg_equipos: dict | None = None,
    ocluidas: set[tuple[int, int]] | None = None,
) -> dict[int, str]:
    """Etiqueta cada identidad: A / B / otro / portero_A / portero_B.

    Ids de identidad = 1..N en el orden de la lista (el mismo criterio que
    el adaptador de evaluación y el export de producción).

    `ocluidas` son los recortes que se pisan con otra detección: su color
    es una mezcla de dos equipaciones, así que no votan (ver
    src/team_classification/oclusion.py).
    """
    cfg_equipos = cfg_equipos or {}
    cfg_agg = cfg_equipos.get("agregacion", {})
    solo_cercanos = cfg_agg.get("solo_cercanos", True)
    umbral = cfg_agg.get("umbral_profundidad_m", cfg_agg.get("umbral_my", 45.0))
    modelo, profundidad = _profundidad_configurada(cfg_equipos)

    equipos: dict[int, str] = {}
    for id_identidad, identidad in enumerate(identidades, start=1):
        todos, cercanos = [], []
        for tracklet in identidad:
            for pos, par in zip(tracklet.pos, tracklet.det_idxs):
                if par not in colores:
                    continue
                todos.append((par, colores[par]))
                if profundidad.de(pos, modelo) < umbral:
                    cercanos.append((par, colores[par]))
        feats = cercanos if (solo_cercanos and cercanos) else todos
        media = color_medio_limpio(feats, ocluidas)
        if media is not None:
            etiqueta = clasificador.predict_color(
                media, dist_max=cfg_agg.get("dist_max_prototipo")
            )
            # El prototipo 'otro' es un imán para las medias ruidosas de
            # identidades cortas. Medido en Villaviciosa: cuatro
            # identidades de 1, 7, 14 y 16 observaciones acababan ahí
            # siendo jugadores reales de campo — y con UNA observación la
            # media de color es ruido puro. Por debajo del mínimo se
            # fuerza la elección entre A y B, que acierta ~50 % por azar
            # en vez del 0 % actual.
            min_otro = cfg_agg.get("min_obs_para_otro", 0)
            if etiqueta == "otro" and 0 < len(feats) < min_otro:
                etiqueta = clasificador.predict_color(media, solo_equipos=True)
            equipos[id_identidad] = etiqueta

    # Catálogo ABSOLUTO de equipaciones arbitrales. Va ANTES de la regla
    # de porteros a propósito: un portero con equipación llamativa cae en
    # un arquetipo (en el benjamín, azul eléctrico), y quien manda sobre
    # él es su POSICIÓN, no su color.
    if cfg_equipos.get("arbitro", {}).get("activo", False):
        arbitros = identificar_arbitros(
            identidades,
            colores,
            [clasificador._prototipos.a, clasificador._prototipos.b],
            min_observaciones=cfg_equipos["arbitro"].get("min_observaciones", 25),
            margen_equipo=cfg_equipos["arbitro"].get("margen_equipo", 0.0),
        )
        for indice in arbitros:
            equipos[indice] = "otro"

    cfg_porteros = cfg_equipos.get("porteros", {})
    if cfg_porteros.get("activo", False):
        lados = None
        opciones = {
            k: v
            for k, v in cfg_porteros.items()
            if k
            not in (
                "activo",
                "desde_modelo",
                "margen_m",
                "deducir_lados",
                # claves del método por ÚLTIMO HOMBRE: no son de ReglaPorteros
                "metodo",
                "min_pisa_area",
                "min_presencia",
                "min_ultimo_hombre",
                "min_frames_nuevos",
                "margen_area_m",
                "dup_dist_m",
            )
        }
        # Qué equipo defiende cada portería NO se configura a mano: se
        # deduce de las posiciones. Configurarlo era la causa de que en
        # el benjamín los porteros salieran cruzados (nadie puede
        # verificar esas dos claves mirando un replay).
        if cfg_porteros.get("deducir_lados", True):
            # Se construye primero una regla provisional solo para saber
            # QUIÉN vive en un área y excluirlo del voto (un portero vota
            # al revés que su equipo).
            provisional = (
                ReglaPorteros.desde_modelo(
                    modelo, margen=cfg_porteros.get("margen_m", 2.0)
                )
                if cfg_porteros.get("desde_modelo", False)
                else ReglaPorteros.desde_dict(opciones)
            )
            lados = deducir_lados(
                equipos,
                identidades,
                modelo.largo,
                regla=provisional,
                ancho=modelo.ancho,
            )
            if lados is not None:
                opciones["equipo_mx_bajo"], opciones["equipo_mx_alto"] = lados
        if cfg_porteros.get("desde_modelo", False):
            # Áreas DERIVADAS del campo (F7 y cualquier campo no estándar):
            # los rangos a mano del F11 no valen en otras medidas.
            regla = ReglaPorteros.desde_modelo(
                modelo,
                margen=cfg_porteros.get("margen_m", 2.0),
                **{k: v for k, v in opciones.items() if k.startswith("equipo_")},
            )
        else:
            regla = ReglaPorteros.desde_dict(opciones)

        # ── Qué método decide quién es el portero ────────────────────
        #
        # ORDEN, que Alex pidió comprobar y no es indiferente: el
        # catálogo arbitral ya ha corrido y puede haber mandado al
        # portero al cajón 'otro' (en el benjamín lo hace: viste azul
        # eléctrico). Las dos reglas de portero corren DESPUÉS y
        # sobrescriben esa etiqueta, así que **la posición manda sobre el
        # color**, que es lo acordado. Y ninguna de las dos vuelve a
        # mirar el color, así que el catálogo no puede pisarlas luego.
        metodo = cfg_porteros.get("metodo", "area")
        if metodo == "ultimo_hombre":
            lados_eq = None
            if lados is not None:
                lados_eq = {lados[0]: -1, lados[1]: +1}
            elif "equipo_mx_bajo" in opciones:
                lados_eq = {
                    opciones["equipo_mx_bajo"]: -1,
                    opciones["equipo_mx_alto"]: +1,
                }
            equipos = aplicar_regla_portero_ultimo_hombre(
                equipos,
                identidades,
                modelo,
                lados_eq or {},
                ReglaPorteroUltimoHombre.desde_dict(
                    {
                        **{
                            k: v
                            for k, v in cfg_porteros.items()
                            if k
                            in (
                                "min_pisa_area",
                                "min_presencia",
                                "min_ultimo_hombre",
                                "min_frames_nuevos",
                                "margen_area_m",
                                "dup_dist_m",
                            )
                        },
                        "activo": True,
                    }
                ),
            )
        else:
            equipos = aplicar_regla_porteros(equipos, identidades, regla)

    # UN SOLO ÁRBITRO dentro del campo. Va DESPUÉS de porteros y antes de
    # staff, y el orden importa: los porteros están en el tercer grupo
    # hasta que su regla los saca —el color de un portero no es fiable por
    # diseño— así que ponerlo antes hacía que un PORTERO ganase la
    # exclusividad (medido en Villaviciosa: la identidad 19, con 498
    # observaciones, se llevaba el puesto y el árbitro de verdad volvía al
    # equipo A). Lo cazó la guarda `avisar_tercer_grupo` avisando de
    # "TERCER GRUPO VACÍO".
    #
    # Y va antes de staff porque staff mira geometría, no color: quien
    # esté fuera del campo no es árbitro y da igual el orden.
    if cfg_equipos.get("arbitro", {}).get("uno_solo", True):
        equipos = un_solo_arbitro(
            equipos,
            identidades,
            colores,
            [clasificador._prototipos.a, clasificador._prototipos.b],
            modelo,
            min_observaciones=cfg_equipos.get("arbitro", {}).get(
                "min_observaciones", 25
            ),
        )

    # Regla de staff: quien vive FUERA del campo no juega (línier, cuerpo
    # técnico). Va DESPUÉS de porteros: un portero está dentro del campo,
    # así que nunca compiten, pero el orden deja la geometría de "no juega"
    # como la última palabra.
    cfg_staff = cfg_equipos.get("staff", {})
    if cfg_staff.get("activo", False):
        opciones_staff = {k: v for k, v in cfg_staff.items() if k != "activo"}
        # Si el YAML no fija las dimensiones, salen del modelo de campo
        opciones_staff.setdefault("largo", modelo.largo)
        opciones_staff.setdefault("ancho", modelo.ancho)
        regla_staff = ReglaStaff.desde_dict(opciones_staff)
        equipos = aplicar_regla_staff(equipos, identidades, regla_staff)

    logger.info(
        "Equipos por identidad: %d/%d clasificadas", len(equipos), len(identidades)
    )
    avisar_tercer_grupo(equipos, identidades, modelo)
    return equipos


def avisar_tercer_grupo(equipos: dict[int, str], identidades, modelo) -> int:
    """Comprueba que en el TERCER GRUPO quede exactamente una persona.

    La guarda que pidió Alex, y protege de un umbral frágil. El árbitro no
    se identifica con ninguna señal de comportamiento —los cinco medidos
    fallan (docs/arbitro.md)— sino **por eliminación**: dentro del campo,
    quitando los dos equipos, los dos porteros y el staff, debería quedar
    él y nadie más. Medido: queda exactamente 1 en las dos patas.

    Pero eso depende de `arbitro.margen_equipo`, cuya ventana en el
    benjamín es de solo 0,62-0,75, con acantilado en 0,78. En otro campo
    puede caerse, y el síntoma sería silencioso: o el árbitro se cuela en
    un equipo (0 en el tercer grupo) o el catálogo roba jugadores (2 o
    más). Las dos cosas salen por el log.

    No corrige nada a propósito: solo avisa. Corregir a ciegas con una
    señal que no separa es exactamente lo que este proyecto lleva
    aprendiendo a no hacer.

    Returns:
        Cuántas identidades quedan en el tercer grupo.
    """
    quedan = []
    for indice, identidad in enumerate(identidades, start=1):
        etiqueta = str(equipos.get(indice, "otro"))
        if etiqueta in ("A", "B") or etiqueta.startswith("portero"):
            continue
        if etiqueta == "staff":
            continue
        posiciones = np.array([pos for tr in identidad for pos in tr.pos])
        if len(posiciones) < 25:
            continue
        mx = float(np.median(posiciones[:, 0]))
        my = float(np.median(posiciones[:, 1]))
        if not (0.0 <= mx <= modelo.largo and 0.0 <= my <= modelo.ancho):
            continue
        quedan.append((indice, len(posiciones), mx, my))

    if len(quedan) == 1:
        logger.info(
            "Tercer grupo: 1 identidad (la %d, %d obs en (%.1f, %.1f)) — "
            "el árbitro sale por eliminación",
            *quedan[0],
        )
    elif not quedan:
        logger.warning(
            "TERCER GRUPO VACÍO: no queda nadie dentro del campo que no sea "
            "jugador, portero o staff. Si hay árbitro en este partido, está "
            "contando para un equipo. Revisa arbitro.margen_equipo (ventana "
            "medida: 0,62-0,75)."
        )
    else:
        detalle = ", ".join(
            f"{i} ({n} obs en {mx:.0f},{my:.0f})" for i, n, mx, my in quedan
        )
        logger.warning(
            "TERCER GRUPO CON %d IDENTIDADES: debería quedar solo el árbitro. "
            "Puede que el catálogo esté robando jugadores. Candidatas: %s. "
            "Revisa arbitro.margen_equipo (ventana medida: 0,62-0,75).",
            len(quedan),
            detalle,
        )
    return len(quedan)


def _recortes_para_votar(
    cerca: list,
    obs: list,
    t_actual: float,
    colores: dict,
    ocluidas: set[tuple[int, int]],
    ampliar_s: float,
) -> list:
    """Los recortes de la ventana que pueden votar color, sin los ocluidos.

    1. Si hay recortes limpios en la ventana, solo votan ellos.
    2. Si TODOS están ocluidos y `ampliar_s` > 0, se buscan limpios de la misma
       identidad hasta `ampliar_s / 2` a cada lado.
    3. Si no hay ninguno, votan todos (como antes: mejor un voto contaminado que
       ninguno, o la observación se queda sin etiqueta).
    """
    limpios = [(p, c) for p, c in cerca if p not in ocluidas]
    if limpios:
        return limpios
    if ampliar_s > 0:
        ampliados = [
            (p, colores[p])
            for t2, p in obs
            if abs(t2 - t_actual) <= ampliar_s / 2
            and p in colores
            and p not in ocluidas
        ]
        if ampliados:
            return ampliados
    return cerca


def etiquetar_por_observacion(
    identidades,
    equipos: dict[int, str],
    colores: dict,
    clasificador,
    cfg_equipos: dict | None = None,
    ocluidas: set[tuple[int, int]] | None = None,
) -> dict[tuple[int, int], str]:
    """{(id_identidad, frame_idx): etiqueta} decidida por VENTANA de color.

    Por qué existe: hoy la etiqueta de equipo la decide un voto sobre TODA
    la identidad, así que una identidad que mezcla dos personas manda a
    todas sus observaciones al equipo de la dominante. Medido en el
    benjamín: **116 de 747 observaciones tienen el equipo equivocado
    (15,5 %) y 11 identidades mezclan los dos equipos**; decidiendo por
    ventana corta bajan a 3,2 %.

    ⚠️ **NO se activa por defecto, y el motivo es que NO VIAJA.** Medido
    contra las métricas de producto en las dos patas:

    | estrategia | benjamín centroide | Villaviciosa centroide |
    |---|---|---|
    | voto por identidad | 1,30 m | **3,55 m** |
    | ventana 1-2 s | **0,36 m** | 3,94 m |

    En el benjamín divide el error por 3,6 y en Villaviciosa lo empeora.
    La causa está medida: allí el color de cada recorte es MUCHO menos
    fiable —los jugadores están a 0,19-0,80 de su prototipo, contra
    0,27-0,56 en el benjamín— porque media plantilla juega en la mitad
    lejana. Donde el recorte es señal, decidir por recorte gana; donde es
    ruido, lo que salva es promediar.

    Con dos partidos no se puede derivar un selector automático sin
    ajustarlo a dos puntos, así que se deja como decisión POR PARTIDO en
    el config (`agregacion.por_observacion`).

    Las reglas posicionales mandan: un portero es portero en todas sus
    observaciones y el staff no juega en ninguna. Lo que pasa a decidirse
    por ventana es solo el A/B del color.

    `ocluidas` ({(frame, det_idx)} de los recortes que se pisan con otra caja,
    ver `oclusion.py`) solo se usa si `por_observacion.excluir_ocluidas` está
    activo: entonces los recortes ocluidos NO votan en la media de la ventana.
    Con `ampliar_ventana_s` > 0, una ventana en la que TODOS los recortes están
    ocluidos busca recortes limpios de la misma identidad hasta esa distancia
    (y si no hay ninguno, se cae a todos, como antes). Es lo que se ataca del
    baile de colores: el 73 % de los cambios A↔B cae en una caja solapada
    (`docs/arbitro_y_baile_de_colores.md`). ⚠️ El negativo de agosto sobre
    excluir ocluidos (`docs/experimentos_tracking.md`, 3a) era POR IDENTIDAD,
    donde una minoría contaminada se promedia sola; aquí la ventana es de
    ~15 recortes y un solape de un segundo la contamina entera.
    """
    cfg_equipos = cfg_equipos or {}
    cfg = cfg_equipos.get("agregacion", {}).get("por_observacion", {})
    if not cfg.get("activo", False):
        return {}
    ventana = float(cfg.get("ventana_s", 1.5))
    forzar = bool(cfg.get("forzar_ab", True))
    excluir_ocluidas = bool(cfg.get("excluir_ocluidas", False)) and bool(ocluidas)
    ampliar_s = float(cfg.get("ampliar_ventana_s", 0.0)) if excluir_ocluidas else 0.0

    # ── EL CATÁLOGO ARBITRAL, TAMBIÉN POR OBSERVACIÓN (28-ago-2026) ──
    #
    # `identificar_arbitros` juzga la MEDIA DE TODA LA IDENTIDAD, y eso lo
    # rompe una identidad contaminada: el id 292 del benjamín mezcla al
    # árbitro con jugadores naranjas, su media da un tono intermedio
    # (H=28 S=72) que no cae en ningún arquetipo, y con **3.187 recortes**
    # no dispara. **No es cantidad, es PUREZA.**
    #
    # Y la señal está: el 68 % de los recortes de esa identidad están MÁS
    # LEJOS de los dos prototipos de equipo que los prototipos entre sí
    # (mediana 1,12 contra una separación A−B de 0,98). Lo que fallaba era
    # preguntar "¿a cuál de los dos se parece más?" —que siempre tiene
    # respuesta— en vez de "¿se parece a alguno?".
    #
    # Aquí se pregunta lo segundo sobre la MISMA ventana que ya se calcula
    # para el A/B, así que no cuesta una pasada extra. Una observación
    # suelta no convierte a nadie en árbitro: manda la media de la ventana.
    catalogo = bool(cfg.get("catalogo_arbitral", False))
    # `solo_catalogo` separa las dos preguntas que esta función hace sobre
    # la MISMA ventana. Están acopladas en el código pero no en la
    # naturaleza, y medido en Villaviciosa van en direcciones opuestas:
    # la ventana A/B empeora el centroide (4,37 → 4,67) porque allí el
    # recorte suelto es ruido, mientras el catálogo lo mejora (→ 4,10)
    # porque saca de los equipos a quien no es jugador. Con esto se puede
    # tener lo segundo sin lo primero.
    solo_catalogo = bool(cfg.get("solo_catalogo", False))
    activos = ()
    if catalogo:
        from src.team_classification.arbitro import (
            ARQUETIPOS,
            arquetipos_activos,
            brillo_medio,
            tono_dominante,
        )

        pr = getattr(clasificador, "_prototipos", None)
        if pr is not None:
            activos = arquetipos_activos([pr.a, pr.b], ARQUETIPOS)
        if not activos:
            catalogo = False

    salida: dict[tuple[int, int], str] = {}
    n_cambios = 0
    n_arbitro = 0
    for id_identidad, identidad in enumerate(identidades, start=1):
        etiqueta = str(equipos.get(id_identidad, "otro"))
        if etiqueta not in ("A", "B"):
            continue  # portero, staff y 'otro' los decide la posición
        obs = sorted(
            (
                (t, tuple(par))
                for tracklet in identidad
                for t, par in zip(tracklet.ts, tracklet.det_idxs)
            ),
            key=lambda o: o[0],
        )
        for t_actual, par in obs:
            cerca = [
                (p, colores[p])
                for t2, p in obs
                if abs(t2 - t_actual) <= ventana / 2 and p in colores
            ]
            if not cerca:
                continue
            if excluir_ocluidas:
                cerca = _recortes_para_votar(
                    cerca, obs, t_actual, colores, ocluidas, ampliar_s
                )
            media = color_medio_limpio(cerca, None)
            if media is None:
                continue
            # Primero: ¿esta ventana viste de árbitro? Si sí, la
            # observación sale del cómputo de equipos (va al tercer
            # grupo) y NO se le pregunta a qué equipo se parece más.
            if catalogo:
                tono = tono_dominante(media)
                if tono is not None:
                    brillo = brillo_medio(media)
                    if any(a.contiene(tono[0], tono[1], brillo) for a in activos):
                        salida[(id_identidad, par[0])] = "otro"
                        n_arbitro += 1
                        continue
            if solo_catalogo:
                continue  # el A/B lo sigue decidiendo el voto de la identidad
            nueva = clasificador.predict_color(media, solo_equipos=forzar)
            salida[(id_identidad, par[0])] = nueva
            n_cambios += nueva != etiqueta
    if salida:
        logger.info(
            "Etiqueta por observación (ventana %.1f s): %d observaciones "
            "etiquetadas, %d cambian respecto al voto de su identidad"
            "%s",
            ventana,
            len(salida),
            n_cambios,
            (
                f", {n_arbitro} sacadas de los equipos por el catálogo arbitral"
                if n_arbitro
                else ""
            ),
        )
    return salida
