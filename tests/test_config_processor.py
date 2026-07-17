"""Tests de la validación de config del procesador (fallos claros, no KeyError)."""

import pytest
import yaml

from src.tracking_data.processor import (
    _CLAVES_DESDE_CACHE,
    _CLAVES_FULL,
    validar_config,
)


def _cfg_desde_cache_completa():
    return {
        "tracking": {"perfil": "oficial"},
        "campo_m": {"largo": 105.0, "ancho": 68.0, "margen": 8.0},
        "rutas": {
            "cache": "x.pkl",
            "cache_colores": "c.pkl",
            "homografia": "h.npy",
            "salida_csv": "out.csv",
            "salida_meta": "out.json",
        },
    }


def test_config_completa_pasa_y_aplica_defaults():
    """Sin config_tracking ni equipos, la validación los rellena (no falla)."""
    cfg = _cfg_desde_cache_completa()
    validar_config(cfg, _CLAVES_DESDE_CACHE)
    assert cfg["config_tracking"] == "configs/tracking.yaml"  # default
    assert cfg["equipos"] == {"activo": True}  # default


def test_config_tracking_explicito_se_respeta():
    cfg = _cfg_desde_cache_completa()
    cfg["config_tracking"] = "otro/tracking.yaml"
    validar_config(cfg, _CLAVES_DESDE_CACHE)
    assert cfg["config_tracking"] == "otro/tracking.yaml"


def test_clave_ausente_falla_con_mensaje_claro():
    cfg = _cfg_desde_cache_completa()
    del cfg["rutas"]["salida_csv"]
    with pytest.raises(ValueError, match="rutas.salida_csv"):
        validar_config(cfg, _CLAVES_DESDE_CACHE)


def test_lista_todas_las_claves_que_faltan():
    """El error enumera TODO lo que falta, no solo la primera clave."""
    cfg = _cfg_desde_cache_completa()
    del cfg["tracking"]
    del cfg["campo_m"]["margen"]
    with pytest.raises(ValueError) as exc:
        validar_config(cfg, _CLAVES_DESDE_CACHE)
    mensaje = str(exc.value)
    assert "tracking.perfil" in mensaje
    assert "campo_m.margen" in mensaje
    assert "processor_ejemplo.yaml" in mensaje  # apunta a la plantilla


def test_modo_full_exige_video_y_deteccion():
    cfg = _cfg_desde_cache_completa()  # sin video ni deteccion
    with pytest.raises(ValueError) as exc:
        validar_config(cfg, _CLAVES_FULL)
    mensaje = str(exc.value)
    assert "rutas.video" in mensaje
    assert "deteccion.modelo" in mensaje


def test_la_plantilla_de_ejemplo_valida_en_ambos_modos():
    """configs/processor_ejemplo.yaml debe pasar la validación tal cual."""
    with open("configs/processor_ejemplo.yaml") as f:
        cfg = yaml.safe_load(f)
    validar_config(dict(cfg), _CLAVES_DESDE_CACHE)
    validar_config(dict(cfg), _CLAVES_FULL)


def test_config_oficial_del_repo_valida():
    """configs/processor.yaml (la config real) también pasa."""
    with open("configs/processor.yaml") as f:
        cfg = yaml.safe_load(f)
    validar_config(dict(cfg), _CLAVES_DESDE_CACHE)
