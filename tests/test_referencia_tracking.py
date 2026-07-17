"""Test de regresión: la migración debe reproducir los números del notebook.

Sobre el caché real del tramo min 5-6, el código VERBATIM del notebook
(verificado el 12-jul-2026 ejecutándolo tal cual junto a esta migración) da:
  - Etapa A → 309 tracklets puros (coincide con la validación de Colab)
  - Cosido solo-movimiento → 89 identidades

Nota: la cifra "~127 sin color" que se citó como referencia corresponde
probablemente a una variante anterior del cosido (v1); el código v2 migrado
aquí da 89 sin color, coherente con las 94 validadas CON color (el veto de
color elimina ~5 uniones dudosas → más identidades).

Si estos números cambian, la lógica se desvió del notebook.
El test se salta automáticamente si el caché no está copiado en data/.
"""

from pathlib import Path

import pytest
import yaml

from src.tracking.cache_io import cargar_cache
from src.tracking.field_tracker import ConservativeTracker, ParametrosEtapaA
from src.tracking.stitcher import ParametrosCosido, TrackletStitcher

RUTA_CACHE = Path("data/tracking/cache_detecciones_min5_60s.pkl")
RUTA_CONFIG = Path("configs/tracking.yaml")

pytestmark = pytest.mark.skipif(
    not RUTA_CACHE.exists(),
    reason="Falta el caché de detecciones (copiar de Drive a data/tracking/)",
)


@pytest.fixture(scope="module")
def resultado_pipeline():
    """Corre Etapa A + cosido con los parámetros de configs/tracking.yaml."""
    with open(RUTA_CONFIG) as f:
        config = yaml.safe_load(f)
    datos = cargar_cache(RUTA_CACHE)
    tracker = ConservativeTracker(ParametrosEtapaA.desde_dict(config["etapa_a"]))
    tracklets = tracker.procesar(datos["cache"], datos["fps"], datos["sample"])
    stitcher = TrackletStitcher(ParametrosCosido.desde_dict(config["cosido"]))
    identidades = stitcher.coser(tracklets)  # sin color: baseline solo-movimiento
    return tracklets, identidades


def test_etapa_a_reproduce_309_tracklets(resultado_pipeline):
    tracklets, _ = resultado_pipeline
    assert len(tracklets) == 309, f"Esperados 309 tracklets, hay {len(tracklets)}"


def test_cosido_reproduce_89_identidades(resultado_pipeline):
    _, identidades = resultado_pipeline
    assert len(identidades) == 89, f"Esperadas 89 identidades, hay {len(identidades)}"


def test_identidades_conservan_todos_los_tracklets(resultado_pipeline):
    """El cosido solo agrupa: ningún tracklet se pierde ni se duplica."""
    tracklets, identidades = resultado_pipeline
    ids_en_identidades = [tr.id for ident in identidades for tr in ident]
    assert sorted(ids_en_identidades) == sorted(tr.id for tr in tracklets)


RUTA_COLORES = Path("data/tracking/cache_colores_min5_60s.pkl")


@pytest.mark.skipif(
    not RUTA_COLORES.exists(),
    reason="Falta el caché de colores (copiar de Drive a data/tracking/)",
)
def test_cosido_con_color_reproduce_94_identidades(resultado_pipeline):
    """Con el veto de color, el cosido debe dar las 94 identidades validadas."""
    import pickle

    import numpy as np

    tracklets, _ = resultado_pipeline
    with open(RUTA_COLORES, "rb") as f:
        colores = pickle.load(f)
    color_medio = {}
    for tr in tracklets:
        feats = [colores[par] for par in tr.det_idxs if par in colores]
        if feats:
            color_medio[tr.id] = np.mean(feats, axis=0)
    with open(RUTA_CONFIG) as f:
        config = yaml.safe_load(f)
    stitcher = TrackletStitcher(ParametrosCosido.desde_dict(config["cosido"]))
    identidades = stitcher.coser(tracklets, color_medio)
    assert (
        len(identidades) == 94
    ), f"Esperadas 94 identidades con color, hay {len(identidades)}"
