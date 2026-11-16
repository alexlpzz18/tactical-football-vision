"""Partir por equipo y re-enlazar dentro del equipo (docs/registro_mision.md, H2' y H3)."""

import numpy as np
import pandas as pd

from src.tracking.reenlace import ParametrosReenlace, partir_por_equipo, reenlazar

DT = 0.12


def _ficha(ident, etiqueta, t0, n, origen, vel=(2.0, 0.0)):
    t = t0 + np.arange(n) * DT
    return pd.DataFrame(
        {
            "frame": np.round(t / DT).astype(int) * 3,
            "tiempo_s": np.round(t, 4),
            "id_jugador": ident,
            "equipo": 0 if etiqueta == "A" else 1,
            "etiqueta": etiqueta,
            "x_m": origen[0] + (t - t0) * vel[0],
            "y_m": origen[1] + (t - t0) * vel[1],
            "es_real": 1,
        }
    )


def _relleno(t0, t1):
    """Una ficha lejana que existe todo el rato, para que haya frames en los huecos."""
    return _ficha(99, "B", t0, int((t1 - t0) / DT), (90.0, 60.0), vel=(0.0, 0.0))


def test_partir_donde_la_etiqueta_cambia_de_equipo_y_no_en_portero():
    a = _ficha(1, "A", 0.0, 20, (10, 10))
    b = _ficha(1, "B", 20 * DT, 20, (10 + 20 * DT * 2, 10))
    c = _ficha(2, "A", 0.0, 10, (50, 50))
    d = _ficha(2, "portero_A", 10 * DT, 10, (50 + 10 * DT * 2, 50))
    df, cortes = partir_por_equipo(pd.concat([a, b, c, d]))
    assert cortes == 1  # A → B parte; A → portero_A es el mismo equipo
    assert df.id_jugador.nunique() == 3
    assert len(df) == 60


def test_une_la_ficha_que_muere_con_la_que_nace_en_su_camino_y_rellena_el_hueco():
    antes = _ficha(1, "A", 0.0, 30, (10, 20))
    t_nace = 30 * DT + 1.2
    despues = _ficha(2, "A", t_nace, 30, (10 + t_nace * 2.0, 20))  # sigue su recta
    df, uniones = reenlazar(pd.concat([antes, despues, _relleno(0.0, 10.0)]))
    assert uniones == 1
    jug = df[df.id_jugador != 99]
    assert jug.id_jugador.nunique() == 1
    hueco = jug[jug.es_real == 0]
    assert len(hueco) >= 8  # ~1,2 s a 0,12 s
    # el relleno va por la recta: ningún paso de la ficha unida supera los 9 m/s
    jug = jug.sort_values("tiempo_s")
    v = np.hypot(jug.x_m.diff(), jug.y_m.diff()) / jug.tiempo_s.diff()
    assert v.max() < 9.0


def test_no_une_rivales_ni_lo_que_esta_lejos_ni_huecos_largos():
    antes = _ficha(1, "A", 0.0, 30, (10, 20))
    t_nace = 30 * DT + 1.0
    rival = _ficha(2, "B", t_nace, 30, (10 + t_nace * 2.0, 20))
    lejos = _ficha(3, "A", t_nace, 30, (10 + t_nace * 2.0, 35))  # a 15 m de su camino
    tarde = _ficha(4, "A", 30 * DT + 6.0, 30, (30, 20))  # hueco de 6 s
    df, uniones = reenlazar(
        pd.concat([antes, rival, lejos, tarde, _relleno(0.0, 14.0)])
    )
    assert uniones == 0
    assert df.id_jugador.nunique() == 5


def test_la_asignacion_es_global_dos_que_mueren_y_dos_que_nacen():
    """Cada una va con la que casa con SU movimiento, aunque la otra también entre en el margen."""
    m1 = _ficha(1, "A", 0.0, 30, (10, 20), vel=(3.0, 0.0))
    m2 = _ficha(2, "A", 0.0, 30, (10, 23), vel=(3.0, 0.0))
    t_nace = 30 * DT + 0.6
    n1 = _ficha(3, "A", t_nace, 30, (10 + t_nace * 3.0, 20), vel=(3.0, 0.0))
    n2 = _ficha(4, "A", t_nace, 30, (10 + t_nace * 3.0, 23), vel=(3.0, 0.0))
    df, uniones = reenlazar(pd.concat([m1, m2, n1, n2, _relleno(0.0, 10.0)]))
    assert uniones == 2
    por_id = df[df.id_jugador != 99].groupby("id_jugador").y_m.agg(["min", "max"])
    assert (
        (por_id["max"] - por_id["min"]) < 0.5
    ).all()  # ninguna unión cruza de carril


def test_parametros_desde_dict():
    assert ParametrosReenlace.desde_dict({"max_hueco_s": 2.0}).max_hueco_s == 2.0


def test_interruptor_real_en_el_processor(tmp_path):
    """`fichas` en la config de tracking recorre el processor y queda en el meta; sin él, None."""
    import json

    import yaml
    from test_feature_v2_integracion import _cache_sintetico, _config

    from src.tracking_data.processor import procesar_desde_cache

    ruta_c, ruta_col = _cache_sintetico(tmp_path, False)
    metas = {}
    for activo in (False, True):
        cfg = yaml.safe_load(open(_config(tmp_path, ruta_c, ruta_col, f"f{activo}")))
        tr = yaml.safe_load(open(cfg["config_tracking"]))
        if activo:
            tr["fichas"] = {"partir_por_equipo": True, "reenlace": {"activo": True}}
        ruta_tr = tmp_path / f"tracking_{activo}.yaml"
        ruta_tr.write_text(yaml.safe_dump(tr, allow_unicode=True))
        cfg["config_tracking"] = str(ruta_tr)
        assert len(procesar_desde_cache(cfg)) > 0
        metas[activo] = json.loads(open(cfg["rutas"]["salida_meta"]).read())["fichas"]
    assert metas[False] is None
    assert metas[True]["fichas_antes"] >= 1 and "uniones" in metas[True]
