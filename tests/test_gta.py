"""Postproceso global tipo GTA-link (docs/plan_literatura.md, método 2)."""

import numpy as np
import pandas as pd

from src.tracking.gta import ParametrosGTA, partir_por_equipo_sostenido, postproceso_gta

DT = 0.12


def _ficha(ident, etiquetas, t0, origen, vel=(2.0, 0.0)):
    n = len(etiquetas)
    t = t0 + np.arange(n) * DT
    return pd.DataFrame(
        {
            "frame": np.round(t / DT).astype(int) * 3,
            "tiempo_s": np.round(t, 4),
            "id_jugador": ident,
            "equipo": [0 if e.endswith("A") else 1 for e in etiquetas],
            "etiqueta": etiquetas,
            "x_m": origen[0] + (t - t0) * vel[0],
            "y_m": origen[1] + (t - t0) * vel[1],
            "es_real": 1,
        }
    )


def _fondo(t1):
    return _ficha(999, ["B"] * int(t1 / DT), 0.0, (90.0, 60.0), vel=(0.0, 0.0))


def test_solo_parte_las_rachas_largas_del_otro_equipo():
    corta = ["A"] * 20 + ["B"] * 5 + ["A"] * 20  # 0,6 s de B: ruido
    larga = ["A"] * 20 + ["B"] * 20  # 2,4 s de B: otra persona
    df = pd.concat([_ficha(1, corta, 0.0, (10, 10)), _ficha(2, larga, 0.0, (40, 40))])
    df, cortes = partir_por_equipo_sostenido(df, 1.5)
    assert cortes == 1
    assert df.id_jugador.nunique() == 3


def test_une_a_traves_de_un_trozo_intercalado_y_nunca_lo_solapado():
    # una persona: 0-3 s, hueco, 4-7 s; otra ficha A solapa con la primera y no puede unirse
    a1 = _ficha(1, ["A"] * 25, 0.0, (10, 20))
    a2 = _ficha(2, ["A"] * 25, 25 * DT + 1.0, (10 + (25 * DT + 1.0) * 2, 20))
    solapa = _ficha(3, ["A"] * 25, 1.0, (12.0, 25))  # a 5 m, AL MISMO TIEMPO que a1
    df, inf = postproceso_gta(pd.concat([a1, a2, solapa, _fondo(10.0)]))
    ids = df[df.etiqueta == "A"].groupby("id_jugador").tiempo_s.agg(["min", "max"])
    # a1 y a2 en una ficha; la que solapa no se ha unido a esa ficha
    assert len(ids) == 2
    duracion = (ids["max"] - ids["min"]).sort_values()
    assert duracion.iloc[-1] > 6.0


def test_no_une_rivales_ni_lo_que_no_cabe_fisicamente():
    a = _ficha(1, ["A"] * 25, 0.0, (10, 20))
    rival = _ficha(2, ["B"] * 25, 25 * DT + 0.5, (10 + (25 * DT + 0.5) * 2, 20))
    lejos = _ficha(3, ["A"] * 25, 25 * DT + 0.5, (10 + (25 * DT + 0.5) * 2, 40))
    df, inf = postproceso_gta(pd.concat([a, rival, lejos, _fondo(8.0)]))
    assert inf["fichas_despues"] == inf["fichas_antes"]


def test_parametros():
    assert ParametrosGTA.desde_dict({"v_max_ms": 7.0}).v_max_ms == 7.0


def test_interruptor_real_en_el_processor(tmp_path):
    """`fichas.gta.activo` recorre el processor y deja su informe en el meta; apagado, None."""
    import json

    import yaml
    from test_feature_v2_integracion import _cache_sintetico, _config

    from src.tracking_data.processor import procesar_desde_cache

    ruta_c, ruta_col = _cache_sintetico(tmp_path, False)
    metas = {}
    for activo in (False, True):
        cfg = yaml.safe_load(open(_config(tmp_path, ruta_c, ruta_col, f"g{activo}")))
        tr = yaml.safe_load(open(cfg["config_tracking"]))
        tr["fichas"] = {"gta": {"activo": activo}}
        ruta_tr = tmp_path / f"tracking_g{activo}.yaml"
        ruta_tr.write_text(yaml.safe_dump(tr, allow_unicode=True))
        cfg["config_tracking"] = str(ruta_tr)
        assert len(procesar_desde_cache(cfg)) > 0
        metas[activo] = json.loads(open(cfg["rutas"]["salida_meta"]).read())["fichas"]
    assert metas[False] is None
    assert "cortes" in metas[True] and metas[True]["fichas_antes"] >= 1
