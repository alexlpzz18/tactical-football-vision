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
from src.team_classification.porteros import ReglaPorteros, aplicar_regla_porteros
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
    umbral_my = cfg_fit.get("umbral_my", 34.0)
    min_features = cfg_fit.get("min_features", 300)

    features = np.array(list(colores.values()))
    if solo_cercanos:
        if cache is None:
            raise ValueError(
                "entrenar_clasificador: el fit con recortes cercanos está "
                "activo (entrenamiento.solo_cercanos) y requiere el caché "
                "de detecciones para conocer la profundidad de cada recorte. "
                "Pásalo (cache=datos['cache']) o desactiva el filtro."
            )
        my_por_clave = {
            (entrada["frame_idx"], det_idx): det[1]
            for entrada in cache
            for det_idx, det in enumerate(entrada["dets"])
        }
        cercanas = np.array(
            [
                feature
                for clave, feature in colores.items()
                if my_por_clave.get(clave, float("inf")) < umbral_my
            ]
        )
        if len(cercanas) >= min_features:
            features = cercanas
            logger.info(
                "Fit del clasificador con %d recortes cercanos (my<%.0f) "
                "de %d totales",
                len(cercanas),
                umbral_my,
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
) -> dict[int, str]:
    """Etiqueta cada identidad: A / B / otro / portero_A / portero_B.

    Ids de identidad = 1..N en el orden de la lista (el mismo criterio que
    el adaptador de evaluación y el export de producción).
    """
    cfg_equipos = cfg_equipos or {}
    cfg_agg = cfg_equipos.get("agregacion", {})
    solo_cercanos = cfg_agg.get("solo_cercanos", True)
    umbral_my = cfg_agg.get("umbral_my", 45.0)

    equipos: dict[int, str] = {}
    for id_identidad, identidad in enumerate(identidades, start=1):
        todos, cercanos = [], []
        for tracklet in identidad:
            for pos, par in zip(tracklet.pos, tracklet.det_idxs):
                if par not in colores:
                    continue
                todos.append(colores[par])
                if pos[1] < umbral_my:
                    cercanos.append(colores[par])
        feats = cercanos if (solo_cercanos and cercanos) else todos
        if feats:
            equipos[id_identidad] = clasificador.predict_color(np.mean(feats, axis=0))

    cfg_porteros = cfg_equipos.get("porteros", {})
    if cfg_porteros.get("activo", False):
        regla = ReglaPorteros.desde_dict(
            {k: v for k, v in cfg_porteros.items() if k != "activo"}
        )
        equipos = aplicar_regla_porteros(equipos, identidades, regla)

    logger.info(
        "Equipos por identidad: %d/%d clasificadas", len(equipos), len(identidades)
    )
    return equipos
