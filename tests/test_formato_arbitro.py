"""El árbitro por Viterbi, encendido por el FORMATO del partido (adopción preparada, 23-oct e).

El formato sale de UN solo campo: el `tipo` del modelo de campo del config de equipos. F7 → la pista
corre por defecto; F11 → no. Una clave `activo` explícita manda.

Como pide `tests/test_interruptores_de_config.py`, el interruptor se EJERCE: con la caché real de
60 s del benjamín, el valor por defecto tiene que cambiar el CSV respecto a `activo: false`.
"""

import copy
from pathlib import Path

import pytest
import yaml

from src.campo_modelo import DEFECTOS_POR_FORMATO, cargar_modelo
from src.team_classification.pipeline_equipos import formato_del_partido
from src.tracking_data.processor import procesar_desde_cache, viterbi_activo

R = Path(__file__).resolve().parent.parent
CFG_BENJA = R / "configs/processor_benja.yaml"


def _equipos_benja() -> dict:
    return yaml.safe_load(open(R / "configs/team_classification_benja.yaml"))


def test_el_formato_sale_del_modelo_de_campo():
    assert cargar_modelo(config=R / "configs/campo_benja.yaml").formato == "f7"
    assert formato_del_partido(_equipos_benja()) == "f7"
    assert formato_del_partido({}) == "f11"  # sin sección campo: el F11 de Villaviciosa
    assert formato_del_partido(
        yaml.safe_load(open(R / "configs/team_classification.yaml"))
    ) == ("f11")


def test_tabla_de_defectos_por_formato():
    assert DEFECTOS_POR_FORMATO["f7"]["arbitro_viterbi"] is True
    assert DEFECTOS_POR_FORMATO["f11"]["arbitro_viterbi"] is False


def test_viterbi_activo_por_formato_y_clave_explicita():
    f7 = _equipos_benja()
    assert "activo" not in f7["arbitro"]["viterbi"]  # lo decide el formato
    assert viterbi_activo(f7) is True
    apagado = copy.deepcopy(f7)
    apagado["arbitro"]["viterbi"]["activo"] = False
    assert viterbi_activo(apagado) is False
    f11 = copy.deepcopy(f7)
    f11["campo"] = {"tipo": "f11"}
    assert viterbi_activo(f11) is False
    f11["arbitro"]["viterbi"]["activo"] = True
    assert viterbi_activo(f11) is True


def _cfg_60s(tmp_path, nombre, equipos_ruta):
    cfg = yaml.safe_load(open(CFG_BENJA))
    cfg["modo"] = "desde_cache"
    cfg["config_equipos"] = str(equipos_ruta)
    cfg["rutas"]["salida_csv"] = str(tmp_path / f"{nombre}.csv")
    cfg["rutas"]["salida_meta"] = str(tmp_path / f"{nombre}_meta.json")
    return cfg


_datos = yaml.safe_load(open(CFG_BENJA))["rutas"]
_hay_datos = all(
    (R / _datos[k]).exists() for k in ("cache", "cache_colores", "cache_chaleco")
)


@pytest.mark.skipif(
    not _hay_datos, reason="Faltan las cachés del benjamín (copiar de Drive)"
)
def test_el_formato_enciende_la_pista_de_verdad(tmp_path):
    eq = _equipos_benja()
    apagado = copy.deepcopy(eq)
    apagado["arbitro"]["viterbi"]["activo"] = False
    rutas = {}
    for nombre, datos in (("defecto", eq), ("apagado", apagado)):
        ruta = tmp_path / f"equipos_{nombre}.yaml"
        ruta.write_text(yaml.safe_dump(datos, allow_unicode=True))
        rutas[nombre] = ruta
    df_def = procesar_desde_cache(_cfg_60s(tmp_path, "defecto", rutas["defecto"]))
    df_apa = procesar_desde_cache(_cfg_60s(tmp_path, "apagado", rutas["apagado"]))
    assert not df_def.reset_index(drop=True).equals(df_apa.reset_index(drop=True))
    # y la pista solo AÑADE filas a 'otro' (variante 2): nunca saca a nadie de 'otro'
    j = df_apa.merge(df_def, on=["frame", "id_jugador"], suffixes=("_a", "_d"))
    cambian = j[j.etiqueta_a != j.etiqueta_d]
    assert len(cambian) > 0
    assert (cambian.etiqueta_d == "otro").all()

    sin_chaleco = _cfg_60s(tmp_path, "sin", rutas["defecto"])
    del sin_chaleco["rutas"]["cache_chaleco"]
    with pytest.raises(ValueError, match="cache_chaleco"):
        procesar_desde_cache(sin_chaleco)
