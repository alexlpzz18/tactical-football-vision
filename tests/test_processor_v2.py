"""Tests de humo del pipeline v2 de processor.py (con los cachés reales)."""

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.metrics.collective import compute_collective_metrics
from src.tracking.perfiles import PERFILES
from src.tracking_data.processor import EQUIPO_A_ENTERO, procesar_desde_cache

RUTA_CACHE = Path("data/tracking/cache_detecciones_min5_60s.pkl")
RUTA_COLORES = Path("data/tracking/cache_colores_min5_60s.pkl")

pytestmark = pytest.mark.skipif(
    not (RUTA_CACHE.exists() and RUTA_COLORES.exists()),
    reason="Faltan los cachés de detecciones/colores (copiar de Drive)",
)

COLUMNAS = [
    "frame",
    "tiempo_s",
    "id_jugador",
    "equipo",
    "etiqueta",
    "x_m",
    "y_m",
    "es_real",
]


def _cfg(tmp_path, perfil):
    return {
        "pipeline": "nuevo",
        "modo": "desde_cache",
        "tracking": {"perfil": perfil},
        "config_tracking": "configs/tracking.yaml",
        "equipos": {"activo": True},
        "campo_m": {"largo": 105.0, "ancho": 68.0, "margen": 8.0},
        "rutas": {
            "cache": str(RUTA_CACHE),
            "cache_colores": str(RUTA_COLORES),
            "homografia": "data/calibracion/homografia.npy",
            "salida_csv": str(tmp_path / "pos.csv"),
            "salida_meta": str(tmp_path / "pos_meta.json"),
        },
    }


@pytest.fixture(scope="module")
def salida_oficial(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("oficial")
    cfg = _cfg(tmp, "oficial")
    df = procesar_desde_cache(cfg)
    return df, cfg


def test_csv_formato_compatible(salida_oficial):
    """Columnas del CSV: las 6 clásicas + etiqueta, tipos correctos."""
    df, cfg = salida_oficial
    assert list(df.columns) == COLUMNAS
    releido = pd.read_csv(cfg["rutas"]["salida_csv"])
    assert list(releido.columns) == COLUMNAS
    assert set(releido["equipo"].unique()) <= {0, 1, 2}
    assert set(releido["etiqueta"].unique()) <= set(EQUIPO_A_ENTERO)


def test_perfil_oficial_reproduce_89_identidades(salida_oficial):
    df, cfg = salida_oficial
    assert df["id_jugador"].nunique() == 89
    meta = json.loads(Path(cfg["rutas"]["salida_meta"]).read_text())
    assert meta["n_identidades"] == 89
    assert meta["perfil_tracking"] == "oficial"
    assert meta["pipeline_version"] == "v2"
    # Claves del formato viejo que el flujo aguas abajo espera
    for clave in ("fps_original", "sample_every", "total_detecciones", "ids_unicos"):
        assert clave in meta


def test_perfil_candidato_reproduce_58_identidades():
    """El PERFIL de tracking sigue dando 58 identidades (pin de regresión).

    Se mide correr_perfil directamente: el CSV exportado lleva además la
    fase post-clasificación (consolidación + interpolación), que fusiona
    fichas y por tanto reduce el número — eso se comprueba aparte.
    """
    import pickle

    import yaml

    from src.tracking.cache_io import cargar_cache
    from src.tracking.perfiles import correr_perfil

    datos = cargar_cache(str(RUTA_CACHE))
    with open(RUTA_COLORES, "rb") as f:
        colores = pickle.load(f)
    with open("configs/tracking.yaml") as f:
        cfg_tracking = yaml.safe_load(f)
    from src.team_classification.pipeline_equipos import (
        cargar_config_equipos,
        entrenar_clasificador,
    )

    cfg_eq = cargar_config_equipos()
    clasificador = entrenar_clasificador(colores, cfg_eq, datos["cache"])
    identidades = correr_perfil(
        datos["cache"],
        datos["fps"],
        datos["sample"],
        cfg_tracking,
        perfil="candidato",
        colores=colores,
        clasificador=clasificador,
    )
    assert len(identidades) == 58


def test_postproceso_consolida_y_corta(tmp_path):
    """El CSV exportado pasa por consolidación + corte por velocidad.

    La consolidación fusiona fichas montadas (menos ids) y el corte parte
    las que teletransportan (más ids, más cortas): el número final no es
    comparable con las 58 del perfil, pero sí lo son las dos invariantes
    que importan — el CSV marca qué posiciones son reales y ninguna
    identidad conserva un salto por encima del umbral de teletransporte.
    """
    import numpy as np

    cfg = _cfg(tmp_path, "candidato")
    df = procesar_desde_cache(cfg)
    assert set(df["es_real"].unique()) <= {0, 1}
    assert 0 < df["es_real"].mean() < 1  # hay reales e interpoladas

    for _id_jugador, grupo in df.groupby("id_jugador"):
        grupo = grupo.sort_values("tiempo_s")
        dt = np.diff(grupo["tiempo_s"].to_numpy())
        dd = np.hypot(
            np.diff(grupo["x_m"].to_numpy()), np.diff(grupo["y_m"].to_numpy())
        )
        validos = dt > 0
        if validos.any():
            assert (dd[validos] / dt[validos]).max() <= 60.0 + 1e-6


def test_collective_consume_el_csv_nuevo(salida_oficial):
    """El consumidor real (metrics/collective) traga el CSV v2."""
    _, cfg = salida_oficial
    m = compute_collective_metrics(cfg["rutas"]["salida_csv"])
    # Claves que consume generate_report.py, intactas
    for clave in (
        "resumen",
        "centroide",
        "amplitud_m",
        "profundidad_m",
        "zonas",
        "heatmap",
    ):
        assert clave in m
    # Desglose nuevo por equipo, que excluye equipo=2 por construcción
    assert set(m["por_equipo"]) <= {"A", "B"}
    assert len(m["por_equipo"]) == 2


def test_exportar_posiciones_con_trayectorias(tmp_path):
    """Con trayectorias (3a adoptada), el CSV incluye las interpoladas."""
    import numpy as np

    from src.tracking.field_tracker import Tracklet
    from src.tracking_data.processor import exportar_posiciones

    # Una identidad con 2 observaciones reales y un hueco de 2 frames
    tr = Tracklet(1, 0.0, np.array([10.0, 10.0]), 0, 100)
    tr.anadir(0.36, np.array([13.0, 10.0]), 0, 109)
    identidades = [[tr]]
    datos = {"fps": 25.0, "sample": 3, "wh": (100, 100), "cache": []}
    cfg = {
        "campo_m": {"largo": 105.0, "ancho": 68.0, "margen": 8.0},
        "tracking": {"perfil": "candidato"},
        "rutas": {
            "homografia": "data/calibracion/homografia.npy",
            "salida_csv": str(tmp_path / "pos.csv"),
            "salida_meta": str(tmp_path / "meta.json"),
        },
    }
    trayectorias = [
        [
            (100, np.array([10.0, 10.0]), True),
            (103, np.array([11.0, 10.0]), False),  # interpolada
            (106, np.array([12.0, 10.0]), False),  # interpolada
            (109, np.array([13.0, 10.0]), True),
        ]
    ]
    df_crudo = exportar_posiciones(identidades, {1: "A"}, datos, cfg)
    assert len(df_crudo) == 2
    df_interp = exportar_posiciones(
        identidades, {1: "A"}, datos, cfg, trayectorias=trayectorias
    )
    assert len(df_interp) == 4  # 2 reales + 2 interpoladas
    assert df_interp["id_jugador"].nunique() == 1
    meta = json.loads(Path(cfg["rutas"]["salida_meta"]).read_text())
    assert meta["interpolacion"] is True


def test_flujo_legacy_sigue_disponible():
    """El fallback viejo no se ha roto: importable y con su firma."""
    from src.tracking_data.processor import process_video

    assert callable(process_video)


def test_config_processor_valida():
    """configs/processor.yaml parsea y trae las claves del despachador."""
    with open("configs/processor.yaml") as f:
        cfg = yaml.safe_load(f)
    assert cfg["pipeline"] in ("nuevo", "legacy")
    assert cfg["modo"] in ("full", "desde_cache")
    # bytetrack es el DEFAULT de producto desde el 11-ago-2026; oficial y
    # candidato siguen seleccionables (no se borra nada del pipeline viejo).
    assert cfg["tracking"]["perfil"] in PERFILES


def test_dimensiones_del_campo_coherentes_en_todo_el_sistema():
    """Anti-regresión del bug de escala: una sola fuente de verdad.

    La homografía mapea a un modelo métrico concreto; si el replay, el
    informe o el export usan otras dimensiones, las posiciones caen en un
    campo que no es el suyo (los jugadores se ven más juntos y los
    límites de tercios/pasillos quedan desplazados).
    """
    import inspect

    import pandas as pd

    from src.campo import ANCHO_M, LARGO_M
    from src.metrics.collective import FIELD_LENGTH, FIELD_WIDTH
    from src.report.informe_v2 import generar_informe_v2
    from src.report.replay_tactico import generar_replay

    assert (FIELD_LENGTH, FIELD_WIDTH) == (LARGO_M, ANCHO_M)

    # Desde que el campo es parametrizable, el default ya no es un número
    # suelto sino el MODELO: se comprueba que el modelo por defecto trae
    # las dimensiones de src/campo.py, que es lo que de verdad importa.
    for funcion in (generar_replay, generar_informe_v2):
        firma = inspect.signature(funcion).parameters
        assert firma["modelo"].default is None, funcion.__name__
        assert firma["largo"].default is None, funcion.__name__

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "pos.csv"
        pd.DataFrame(
            [
                dict(
                    frame=100 + 3 * k,
                    tiempo_s=round(0.12 * k, 2),
                    id_jugador=1,
                    equipo=0,
                    etiqueta="A",
                    x_m=50.0,
                    y_m=32.0,
                    es_real=1,
                )
                for k in range(40)
            ]
        ).to_csv(ruta, index=False)
        html = generar_replay(ruta, Path(tmp) / "r.html").read_text()
        campo = json.loads(html.split("const CAMPO = ")[1].split(";\n")[0])
        assert (campo["largo"], campo["ancho"]) == (LARGO_M, ANCHO_M)

    with open("configs/processor.yaml") as f:
        cfg = yaml.safe_load(f)
    assert cfg["campo_m"]["largo"] == LARGO_M
    assert cfg["campo_m"]["ancho"] == ANCHO_M

    with open("configs/team_classification.yaml") as f:
        cfg_eq = yaml.safe_load(f)
    assert cfg_eq["staff"]["largo"] == LARGO_M
    assert cfg_eq["staff"]["ancho"] == ANCHO_M
