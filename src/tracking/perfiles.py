"""Perfiles de tracking: composición nombrada del pipeline completo.

Este módulo es el ÚNICO lugar donde se compone el pipeline de tracking
(Etapa A → cosido → filtros → exclusión → cota). Lo usan tanto el banco
de evaluación como el procesador de producción, de modo que el banco mide
LITERALMENTE el mismo código que corre en producción y adoptar un perfil
es una decisión de configuración, no un rewrite.

Perfiles:
- "oficial": el pipeline validado conservador (Etapa A con min_frames=3 +
  cosido goloso). Baseline: 89 identidades, HOTA 0.106, cobertura 0.140.
- "candidato": la pila de la Tarea 3 (rescate de cortos + cosido global +
  exclusión espacial con salvaguarda de marcaje + cota blanda de
  plantilla). 58 identidades, HOTA 0.172, cobertura 0.384.
- "bytetrack": la base NUEVA (11-ago-2026). La asociación la hace
  ByteTrack sobre nuestras detecciones y encima va el cosido por PUREZA,
  sin cota de plantilla. Medido contra el mismo banco: cobertura 0.558,
  concurrencia 23 (GT 22), IDF1 0.443, tasa de IDSW 0.147 y 5 quimeras,
  frente a 0.551 / 34 / 0.259 / 0.301 / 23 del candidato. Domina al
  candidato en todo salvo un empate técnico en cobertura.

Los parámetros finos de cada pieza viven en configs/tracking.yaml; el
perfil decide QUÉ piezas se activan y con qué overrides.
"""

import logging

import numpy as np

from src.tracking.asociacion_bytetrack import (
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cosido_pureza import ParametrosCosidoPureza, coser_por_pureza
from src.tracking.cota_plantilla import fusionar_hasta_cota
from src.tracking.exclusion_espacial import fusionar_identidades_duplicadas
from src.tracking.field_tracker import ConservativeTracker, ParametrosEtapaA, Tracklet
from src.tracking.stitcher import (
    ParametrosCosido,
    TrackletStitcher,
    filtrar_identidades_cortas,
)

logger = logging.getLogger(__name__)

PERFILES = ("oficial", "candidato", "bytetrack")

# Perfiles a los que NO se les aplica la fase reparadora del post-proceso
# (consolidación y corte de velocidad). Esas dos piezas se construyeron
# para tapar defectos de NUESTRA asociación —racimos de fichas duplicadas
# y cadenas quimera que teletransportan— y sobre una asociación que no los
# tiene solo restan. Medido sobre la base ByteTrack (11-ago-2026):
#
#   solo interpolación        cob. 0.558  IDF1 0.443  quimeras 5
#   + corte de velocidad      cob. 0.553  IDF1 0.402  quimeras 5
#   + post-proceso completo   cob. 0.459  IDF1 0.433  quimeras 2
#
# El corte pierde IDF1 sin ganar pureza, y la consolidación se lleva por
# delante un 18 % de la cobertura.
_SOLO_INTERPOLA = ("bytetrack",)

# Umbral de "recorte cercano" para las firmas de la salvaguarda de marcaje
# (coherente con la agregación del clasificador de equipos)
_UMBRAL_MY_FIRMA = 45.0
_COLOR_MAX_DIST_FIRMA = 1.2


def correr_perfil(
    cache: list[dict],
    fps: float,
    sample: int,
    cfg_tracking: dict,
    perfil: str = "oficial",
    colores: dict | None = None,
    clasificador=None,
    cfg_equipos: dict | None = None,
) -> list[list[Tracklet]]:
    """Corre el pipeline de tracking completo según el perfil.

    Args:
        cache: lista de frames del caché de detecciones (ver cache_io).
        fps, sample: metadatos del caché.
        cfg_tracking: contenido de configs/tracking.yaml.
        perfil: 'oficial' o 'candidato'.
        colores: caché de colores {(frame_idx, det_idx): feature} — solo lo
            usa el candidato para la salvaguarda de marcaje (opcional).
        clasificador: TeamClassifierColor YA entrenado, para las firmas de
            la salvaguarda (opcional; sin él no hay salvaguarda).

    Returns:
        Identidades (listas de tracklets), listas para el adaptador de
        evaluación o para el export de producción.
    """
    if perfil not in PERFILES:
        raise ValueError(f"Perfil desconocido: {perfil!r} (usa uno de {PERFILES})")

    if perfil == "bytetrack":
        return _perfil_bytetrack(cache, fps, sample, cfg_tracking, colores)

    params_a = dict(cfg_tracking["etapa_a"])
    params_cosido = dict(cfg_tracking["cosido"])
    if perfil == "candidato":
        params_a["min_frames"] = 1  # rescate de cortos
        params_cosido["metodo"] = "global"

    tracker = ConservativeTracker(ParametrosEtapaA.desde_dict(params_a))
    tracklets = tracker.procesar(cache, fps, sample)

    stitcher = TrackletStitcher(ParametrosCosido.desde_dict(params_cosido))
    identidades = stitcher.coser(tracklets)  # sin veto de color (medido: no aporta)

    if perfil == "candidato":
        cfg_rescate = cfg_tracking.get("rescate_cortos", {})
        identidades = filtrar_identidades_cortas(
            identidades, cfg_rescate.get("min_frames_identidad", 3)
        )

        firmas = _firmas_de_marcaje(identidades, colores, clasificador, cfg_equipos)
        cfg_excl = cfg_tracking.get("exclusion_espacial", {})
        identidades = fusionar_identidades_duplicadas(
            identidades,
            cfg_excl.get("dist_max", 1.5),
            cfg_excl.get("min_frames_comunes", 3),
            firmas=firmas,
            color_max_dist=_COLOR_MAX_DIST_FIRMA,
        )

        cfg_cota = cfg_tracking.get("cota_plantilla", {})
        identidades = fusionar_hasta_cota(
            identidades,
            cfg_cota.get("cota", 23),
            cfg_cota.get("coste_max", 4.0),
        )

    logger.info("Perfil %s: %d identidades", perfil, len(identidades))
    return identidades


def _perfil_bytetrack(
    cache: list[dict],
    fps: float,
    sample: int,
    cfg_tracking: dict,
    colores: dict | None,
) -> list[list[Tracklet]]:
    """Asociación con ByteTrack + cosido por pureza (sin cota de plantilla).

    No pasa por la Etapa A ni por el cosido/exclusión/cota del candidato:
    esas piezas existían para arreglar los defectos de NUESTRA asociación
    y, medidas sobre una asociación que no los tiene, solo restan (ver
    docs/experimentos_tracking.md, "¿Aporta nuestro tracking...?": el
    post-proceso completo bajaba la cobertura de ByteTrack de 0.516 a
    0.441).
    """
    identidades = asociar_con_bytetrack(
        cache,
        fps,
        sample,
        ParametrosByteTrack.desde_dict(cfg_tracking.get("bytetrack")),
    )
    resolucion = cfg_tracking.get("_resolucion")  # lo inyecta el processor
    return coser_por_pureza(
        identidades,
        colores,
        ParametrosCosidoPureza.desde_dict(cfg_tracking.get("cosido_pureza")),
        resolucion=resolucion,
        jitter_px=_jitter(cfg_tracking, uso="cosido"),
        dt=sample / fps if fps else 0.12,
    )


def _jitter(cfg_tracking: dict, uso: str = "corte") -> float:
    """Vibración de la caja del detector en píxeles, según para qué.

    El mismo número NO sirve para las dos cosas, y medirlo lo dejó claro
    (benjamín, 10-ago-2026):

    - El **corte de velocidad** pregunta "¿este salto cabe dentro del
      ruido?". Ahí hay que usar el ruido REAL medido (3,5 px de
      desplazamiento entre frames), o se trocean identidades sanas.
    - La **consolidación** pregunta algo distinto: "¿estas dos fichas son
      la misma persona?". Ensancharla con todo el margen de ruido
      sobre-fusiona jugadores distintos, y esas quimeras acaban
      troceadas por el propio corte. Medido: con jitter 3,5 en ambos, la
      vida mediana de las identidades del medio campo caía de 13,5 s a
      6,9 s frente a usar 2,0 solo en la consolidación.

    Por eso `jitter_px_consolidacion` se puede fijar aparte; si no está,
    se hereda `jitter_px` (comportamiento de antes).
    """
    cfg = cfg_tracking.get("escalado_resolucion", {})
    base = cfg.get("jitter_px", 2.0)
    if uso == "consolidacion":
        return cfg.get("jitter_px_consolidacion", base)
    return base


def postprocesar(
    identidades: list[list[Tracklet]],
    equipos: dict[int, str],
    frames_ts: list[tuple[int, float]],
    cfg_tracking: dict,
    resolucion=None,
    perfil: str = "candidato",
) -> tuple[list, dict[int, str]]:
    """Fase POST-clasificación, compartida banco↔producción.

    Orden medido (docs/experimentos_tracking.md, "concurrencia"):
      1. identidades → trayectorias crudas (todo observación real)
      2. CONSOLIDACIÓN de fichas del mismo equipo montadas — antes de
         interpolar, para que la fusión se decida con observaciones reales
         y la identidad resultante llegue más densa a la interpolación
      3. INTERPOLACIÓN de los huecos que queden

    Consolidar DESPUÉS de interpolar es peor (medido): se comparan estelas
    interpoladas entre sí y la fusión hereda los fantasmas.

    Args:
        identidades: salida de correr_perfil.
        equipos: {id_identidad: etiqueta} ya clasificado (con porteros y
            staff aplicados).
        frames_ts: [(frame_idx, t), ...] de todos los frames del caché.
        cfg_tracking: contenido de configs/tracking.yaml.
        resolucion: ResolucionCampo opcional (src/tracking/resolucion.py).
            Con ella los umbrales de corte, consolidación e interpolación
            se adaptan a los metros-por-píxel de cada zona, en vez de ser
            los mismos junto a la cámara y en el fondo.
        perfil: qué asociación produjo las identidades. Con "bytetrack"
            se saltan la consolidación y el corte de velocidad (ver
            _SOLO_INTERPOLA).

    Returns:
        (trayectorias, equipos) — los equipos se renumeran si la
        consolidación fusiona identidades.
    """
    from src.tracking.consolidacion import consolidar_colocadas
    from src.tracking.corte_velocidad import cortar_por_velocidad
    from src.tracking.interpolacion import (
        identidades_a_trayectorias,
        interpolar_trayectorias,
    )

    trayectorias = identidades_a_trayectorias(identidades)
    reparadoras = perfil not in _SOLO_INTERPOLA

    cfg_consol = cfg_tracking.get("consolidacion", {})
    if reparadoras and cfg_consol.get("activa", False):
        trayectorias, equipos = consolidar_colocadas(
            trayectorias,
            equipos,
            dist_max=cfg_consol.get("dist_max", 6.0),
            min_frames_comunes=cfg_consol.get("min_frames_comunes", 20),
            resolucion=resolucion,
            jitter_px=_jitter(cfg_tracking, "consolidacion"),
        )

    # Corte de teletransportes: va DESPUÉS de consolidar (una fusión puede
    # crear un salto) y ANTES de interpolar (para no rellenar el salto).
    cfg_corte = cfg_tracking.get("corte_velocidad", {})
    if reparadoras and cfg_corte.get("activo", False):
        trayectorias, equipos = cortar_por_velocidad(
            trayectorias,
            equipos,
            dict(frames_ts),
            v_max=cfg_corte.get("v_max", 8.5),
            duracion_min=cfg_corte.get("duracion_min", 0.5),
            min_observaciones=cfg_corte.get("min_observaciones", 3),
            v_teleport=cfg_corte.get("v_teleport", 60.0),
            resolucion=resolucion,
            jitter_px=_jitter(cfg_tracking),
        )

    cfg_interp = cfg_tracking.get("interpolacion", {})
    if cfg_interp.get("activa", False):
        trayectorias = interpolar_trayectorias(
            trayectorias,
            frames_ts,
            cfg_interp.get("max_hueco", 6.0),
            resolucion=resolucion,
            hueco_min=cfg_interp.get("hueco_min", 1.0),
        )

    return trayectorias, equipos


def _firmas_de_marcaje(
    identidades: list[list[Tracklet]],
    colores: dict | None,
    clasificador,
    cfg_equipos: dict | None = None,
) -> dict[int, tuple[str, np.ndarray]] | None:
    """Firma fiable por identidad para la salvaguarda de marcaje.

    (etiqueta de equipo, color medio) construidos SOLO con recortes
    cercanos (my < umbral), donde el color es señal. Identidades sin
    recortes cercanos no tienen firma (no se puede juzgar).
    """
    if colores is None or clasificador is None:
        return None
    # El eje de PROFUNDIDAD depende de dónde esté la cámara (banda vs
    # detrás de portería): con el eje equivocado, "recorte cercano"
    # selecciona por una coordenada que no mide la distancia.
    from src.team_classification.pipeline_equipos import _profundidad_configurada

    modelo, profundidad = _profundidad_configurada(cfg_equipos or {})
    umbral = (
        (cfg_equipos or {})
        .get("agregacion", {})
        .get("umbral_profundidad_m", _UMBRAL_MY_FIRMA)
    )
    firmas = {}
    for indice, identidad in enumerate(identidades):
        cercanos = [
            colores[par]
            for tracklet in identidad
            for pos, par in zip(tracklet.pos, tracklet.det_idxs)
            if par in colores and profundidad.de(pos, modelo) < umbral
        ]
        if cercanos:
            media = np.mean(cercanos, axis=0)
            firmas[indice] = (clasificador.predict_color(media), media)
    logger.info(
        "Salvaguarda de marcaje: firma fiable para %d/%d identidades",
        len(firmas),
        len(identidades),
    )
    return firmas
