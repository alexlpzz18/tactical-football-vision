"""El processor ENTERO con cachés de feature v2.

Nace de un bug de Colab: la generación v2 funcionaba, pero
`color_dominante()` reventaba al derivar los colores de equipo
(`reshape(16,16)` sobre un vector de 336). El fallo visible era ese, pero
el silencioso era peor: ningún consumidor recortaba al bloque HS, así que
el fit, el veto de color (1,2) y las firmas habrían medido distancias en
otra escala **sin avisar** — y los umbrales calibrados habrían dejado de
significar lo que dicen.

Por eso el test no comprueba solo que no pete: comprueba que un caché v2
produce EXACTAMENTE el mismo resultado que uno v1. Es el "paso 0 de
control" del plan de re-medición, ejecutable sin GPU.
"""

import pickle

import numpy as np
import pandas as pd
import pytest
import yaml

from src.team_classification.feature_v2 import (
    LONGITUD_V1,
    LONGITUD_V2,
    parte_camiseta_hs,
)


def _hs_base():
    """Los bloques HS, generados UNA vez y compartidos por las dos
    versiones. Generarlos dentro de cada caché gastaba el RNG de forma
    distinta y las features dejaban de ser equivalentes: el test fallaba
    por culpa del fixture, no del código."""
    rng = np.random.default_rng(7)
    hs = {}
    for k in range(60):
        for j in range(8):
            v = np.zeros(LONGITUD_V1)
            v[10 if j % 2 == 0 else 200] = 1.0  # dos "equipaciones"
            v = v + rng.normal(0, 0.01, LONGITUD_V1).clip(0)
            hs[(100 + 3 * k, j)] = v / np.linalg.norm(v)
    return hs


HS_BASE = _hs_base()


def _cache_sintetico(tmp_path, v2: bool):
    """Dos equipos que se mueven, con features v1 o v2 equivalentes.

    Las v2 llevan EXACTAMENTE la misma parte HS que las v1 y bloques
    nuevos con contenido distinto: si algún consumidor mirase más allá
    del bloque HS, los resultados divergirían y el test lo cazaría.
    """
    extra_rng = np.random.default_rng(99)
    fps, sample = 30.0, 3
    cache, colores = [], {}
    for k in range(60):
        dets = []
        for j in range(8):
            mx = 20.0 + j * 6 + k * 0.1
            my = 15.0 + (j % 4) * 6
            x = 200 + j * 150
            dets.append((mx, my, x, 400.0, x + 30, 480.0, 0.9))
            hs = HS_BASE[(100 + 3 * k, j)]
            if v2:
                extra = extra_rng.random(LONGITUD_V2 - LONGITUD_V1)
                colores[(100 + 3 * k, j)] = np.concatenate([hs, extra])
            else:
                colores[(100 + 3 * k, j)] = hs
        cache.append({"frame_idx": 100 + 3 * k, "t": k * sample / fps, "dets": dets})

    sufijo = "v2" if v2 else "v1"
    ruta_c = tmp_path / f"cache_{sufijo}.pkl"
    ruta_col = tmp_path / f"colores_{sufijo}.pkl"
    with open(ruta_c, "wb") as f:
        pickle.dump(
            {"cache": cache, "fps": fps, "sample": sample, "wh": (1920, 1080)}, f
        )
    with open(ruta_col, "wb") as f:
        pickle.dump(colores, f)
    return ruta_c, ruta_col


def _config(tmp_path, ruta_c, ruta_col, sufijo):
    base = yaml.safe_load(open("configs/processor_benja.yaml"))
    base["modo"] = "desde_cache"
    base["rutas"]["cache"] = str(ruta_c)
    base["rutas"]["cache_colores"] = str(ruta_col)
    base["rutas"]["salida_csv"] = str(tmp_path / f"pos_{sufijo}.csv")
    base["rutas"]["salida_meta"] = str(tmp_path / f"meta_{sufijo}.json")
    ruta = tmp_path / f"cfg_{sufijo}.yaml"
    with open(ruta, "w") as f:
        yaml.safe_dump(base, f, allow_unicode=True)
    return ruta


@pytest.mark.parametrize("v2", [False, True])
def test_el_processor_entero_corre_con_las_dos_versiones(tmp_path, v2):
    """El crash de Colab: con v2 reventaba al derivar los colores."""
    from src.tracking_data.processor import procesar_desde_cache

    ruta_c, ruta_col = _cache_sintetico(tmp_path, v2)
    cfg = _config(tmp_path, ruta_c, ruta_col, "v2" if v2 else "v1")
    df = procesar_desde_cache(yaml.safe_load(open(cfg)))
    assert len(df) > 0


def test_un_cache_v2_da_EXACTAMENTE_lo_mismo_que_uno_v1(tmp_path):
    """El paso 0 de control. Si esto falla, algún consumidor está mirando
    más allá del bloque HS y los umbrales calibrados han cambiado de
    escala sin que nadie lo haya decidido."""
    from src.tracking_data.processor import procesar_desde_cache

    salidas = {}
    for v2 in (False, True):
        ruta_c, ruta_col = _cache_sintetico(tmp_path, v2)
        cfg = _config(tmp_path, ruta_c, ruta_col, "v2" if v2 else "v1")
        salidas[v2] = procesar_desde_cache(yaml.safe_load(open(cfg)))

    a, b = salidas[False], salidas[True]
    assert len(a) == len(b), "el número de posiciones no puede depender de la versión"
    pd.testing.assert_frame_equal(
        a.reset_index(drop=True), b.reset_index(drop=True), check_exact=False, rtol=1e-9
    )


def test_los_bloques_extra_de_la_v2_se_ignoran_de_verdad(tmp_path):
    """Contraprueba directa: cambiar los bloques nuevos NO debe cambiar
    ninguna distancia del sistema calibrado."""
    from src.team_classification.color_classifier import _solo_hs

    hs = np.zeros(LONGITUD_V1)
    hs[42] = 1.0
    uno = np.concatenate([hs, np.zeros(LONGITUD_V2 - LONGITUD_V1)])
    otro = np.concatenate([hs, np.ones(LONGITUD_V2 - LONGITUD_V1)])
    assert np.array_equal(_solo_hs(uno), _solo_hs(otro))
    assert np.array_equal(_solo_hs(uno), parte_camiseta_hs(otro))
    assert np.array_equal(_solo_hs(hs), hs), "la v1 pasa intacta"
