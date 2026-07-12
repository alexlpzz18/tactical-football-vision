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
    colores: dict, cfg_equipos: dict | None = None
) -> TeamClassifierColor:
    """Entrena TeamClassifierColor con todas las features del caché."""
    cfg_equipos = cfg_equipos or {}
    params = None
    if "clasificador_color" in cfg_equipos:
        params = ParametrosClasificadorColor.desde_dict(
            cfg_equipos["clasificador_color"]
        )
    clasificador = TeamClassifierColor(params)
    clasificador.fit_features(np.array(list(colores.values())))
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
