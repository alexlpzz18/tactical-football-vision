"""`_validar_cache` tiene que comprobar el CONTENIDO, no la ortografía.

Hasta el 28-ago-2026 solo miraba que estuvieran las claves y que la
primera detección tuviera 7 campos. Una auditoría adversarial le metió
siete corrupciones y **las siete pasaron**, entre ellas multiplicar las
posiciones por 20 —el caché deja de estar en metros y todo el pipeline lo
trata como si lo estuviera— y vaciar todos los frames menos el primero.

Es la función que encarna el control de *"¿lo que he recuperado es de
verdad lo que creo?"*, así que era el peor sitio del repo para comprobar
solo la forma. Y el daño es caro: un caché corrupto que se da por bueno
son horas de GPU tiradas y, peor, medidas que parecen sanas.

⚠️ ESTE FICHERO ES LA GUARDA, y sigue las dos reglas del molde:
  1. Comprueba COMPORTAMIENTO: cada test corrompe el caché y exige que la
     validación lo cace. Renombrar algo no lo esquiva.
  2. NACE HACIENDO SALTAR la guarda: si alguien vacía `_validar_contenido`,
     estos tests fallan uno a uno.

Una corrupción nueva que se descubra se añade aquí.
"""

import copy
import pickle

import pytest

FRAMES = 60


@pytest.fixture
def cache_sano(tmp_path):
    """Un caché mínimo pero VÁLIDO, con las propiedades de uno real."""
    datos = {
        "cache": [
            {
                "frame_idx": f,
                "t": f / 30.0,
                "dets": [(30.0 + i, 20.0, 100, 200, 120, 260, 0.8) for i in range(5)],
            }
            for f in range(0, FRAMES * 3, 3)
        ],
        "fps": 30.0,
        "sample": 3,
        "wh": (1920, 1080),
    }
    return datos, tmp_path


def _guardar_y_cargar(datos, tmp_path, nombre="c.pkl"):
    from src.tracking.cache_io import cargar_cache

    ruta = tmp_path / nombre
    with open(ruta, "wb") as f:
        pickle.dump(datos, f)
    return cargar_cache(str(ruta))


def test_el_cache_sano_carga(cache_sano):
    """Control del propio test: si el sano no cargara, no probaría nada."""
    datos, tmp_path = cache_sano
    assert len(_guardar_y_cargar(datos, tmp_path)["cache"]) == FRAMES


def test_caza_posiciones_que_ya_no_estan_en_METROS(cache_sano):
    """La peor: el caché pasa a píxeles y nadie se entera.

    No se comprueba con un tope sobre el MÁXIMO: la proyección se dispara
    legítimamente en el fondo del campo (medido: |mx| de hasta 6808 m en
    un caché sano). Se comprueba la MEDIANA, que en los once cachés del
    repo va de 35 a 62 m y con un ×20 se va a 695.
    """
    datos, tmp_path = cache_sano
    roto = copy.deepcopy(datos)
    for e in roto["cache"]:
        e["dets"] = [(a * 20, b * 20) + tuple(r) for a, b, *r in e["dets"]]
    with pytest.raises(ValueError, match="METROS"):
        _guardar_y_cargar(roto, tmp_path, "roto.pkl")


def test_caza_un_cache_casi_vacio(cache_sano):
    """El '✓ engañoso': una pasada que no detectó nada y se da por buena."""
    datos, tmp_path = cache_sano
    roto = copy.deepcopy(datos)
    for e in roto["cache"][1:]:
        e["dets"] = []
    with pytest.raises(ValueError, match="pasada fallida"):
        _guardar_y_cargar(roto, tmp_path, "roto.pkl")


def test_caza_frame_idx_desordenados(cache_sano):
    datos, tmp_path = cache_sano
    roto = copy.deepcopy(datos)
    roto["cache"].reverse()
    with pytest.raises(ValueError, match="ordenado"):
        _guardar_y_cargar(roto, tmp_path, "roto.pkl")


def test_caza_un_sample_que_no_cuadra_con_los_saltos(cache_sano):
    """Dice sample=3 y los frames van de 1 en 1: o miente, o son dos cachés."""
    datos, tmp_path = cache_sano
    roto = copy.deepcopy(datos)
    for i, e in enumerate(roto["cache"]):
        e["frame_idx"] = i
    with pytest.raises(ValueError, match="múltiplos"):
        _guardar_y_cargar(roto, tmp_path, "roto.pkl")


def test_caza_confianzas_imposibles(cache_sano):
    datos, tmp_path = cache_sano
    roto = copy.deepcopy(datos)
    for e in roto["cache"]:
        e["dets"] = [d[:6] + (99.0,) for d in e["dets"]]
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        _guardar_y_cargar(roto, tmp_path, "roto.pkl")


def test_caza_cajas_invertidas(cache_sano):
    datos, tmp_path = cache_sano
    roto = copy.deepcopy(datos)
    for e in roto["cache"]:
        e["dets"] = [(a, b, x2, y1, x1, y2, c) for a, b, x1, y1, x2, y2, c in e["dets"]]
    with pytest.raises(ValueError, match="invertidas"):
        _guardar_y_cargar(roto, tmp_path, "roto.pkl")


def test_un_hueco_por_el_medio_AVISA_pero_no_rompe(cache_sano, caplog):
    """Un caché fusionado puede tener huecos de verdad: aviso, no error."""
    import logging

    datos, tmp_path = cache_sano
    roto = copy.deepcopy(datos)
    roto["cache"] = roto["cache"][:5] + roto["cache"][40:]
    with caplog.at_level(logging.WARNING):
        _guardar_y_cargar(roto, tmp_path, "roto.pkl")
    assert any(
        "salto" in r.message for r in caplog.records
    ), "un caché con medio tramo borrado tiene que avisar"


def test_los_caches_REALES_del_repo_siguen_cargando():
    """La otra mitad del molde: una guarda que rechaza lo bueno no sirve."""
    import glob

    from src.tracking.cache_io import cargar_cache

    reales = [
        p
        for p in sorted(glob.glob("data/tracking*/cache_*.pkl"))
        if "colores" not in p and "emb" not in p
    ]
    if not reales:
        pytest.skip("no hay cachés reales en este entorno")
    for ruta in reales:
        cargar_cache(ruta)
