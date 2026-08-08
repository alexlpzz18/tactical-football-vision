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

Los parámetros finos de cada pieza viven en configs/tracking.yaml; el
perfil decide QUÉ piezas se activan y con qué overrides.
"""

import logging

import numpy as np

from src.tracking.cota_plantilla import fusionar_hasta_cota
from src.tracking.exclusion_espacial import fusionar_identidades_duplicadas
from src.tracking.field_tracker import ConservativeTracker, ParametrosEtapaA, Tracklet
from src.tracking.stitcher import (
    ParametrosCosido,
    TrackletStitcher,
    filtrar_identidades_cortas,
)

logger = logging.getLogger(__name__)

PERFILES = ("oficial", "candidato")

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

        firmas = _firmas_de_marcaje(identidades, colores, clasificador)
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


def postprocesar(
    identidades: list[list[Tracklet]],
    equipos: dict[int, str],
    frames_ts: list[tuple[int, float]],
    cfg_tracking: dict,
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

    cfg_consol = cfg_tracking.get("consolidacion", {})
    if cfg_consol.get("activa", False):
        trayectorias, equipos = consolidar_colocadas(
            trayectorias,
            equipos,
            dist_max=cfg_consol.get("dist_max", 6.0),
            min_frames_comunes=cfg_consol.get("min_frames_comunes", 20),
        )

    # Corte de teletransportes: va DESPUÉS de consolidar (una fusión puede
    # crear un salto) y ANTES de interpolar (para no rellenar el salto).
    cfg_corte = cfg_tracking.get("corte_velocidad", {})
    if cfg_corte.get("activo", False):
        trayectorias, equipos = cortar_por_velocidad(
            trayectorias,
            equipos,
            dict(frames_ts),
            v_max=cfg_corte.get("v_max", 8.5),
            duracion_min=cfg_corte.get("duracion_min", 0.5),
            min_observaciones=cfg_corte.get("min_observaciones", 3),
            v_teleport=cfg_corte.get("v_teleport", 60.0),
        )

    cfg_interp = cfg_tracking.get("interpolacion", {})
    if cfg_interp.get("activa", False):
        trayectorias = interpolar_trayectorias(
            trayectorias, frames_ts, cfg_interp.get("max_hueco", 6.0)
        )

    return trayectorias, equipos


def _firmas_de_marcaje(
    identidades: list[list[Tracklet]],
    colores: dict | None,
    clasificador,
) -> dict[int, tuple[str, np.ndarray]] | None:
    """Firma fiable por identidad para la salvaguarda de marcaje.

    (etiqueta de equipo, color medio) construidos SOLO con recortes
    cercanos (my < umbral), donde el color es señal. Identidades sin
    recortes cercanos no tienen firma (no se puede juzgar).
    """
    if colores is None or clasificador is None:
        return None
    firmas = {}
    for indice, identidad in enumerate(identidades):
        cercanos = [
            colores[par]
            for tracklet in identidad
            for pos, par in zip(tracklet.pos, tracklet.det_idxs)
            if par in colores and pos[1] < _UMBRAL_MY_FIRMA
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
