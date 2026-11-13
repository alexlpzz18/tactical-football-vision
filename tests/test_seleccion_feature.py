"""Selección automática de la feature de equipo por consistencia física.

docs/plan_equipos_consistencia.md.

Dos partidos sintéticos, uno de cada tipo:
- «alevín»: los equipos solo se distinguen por el BRILLO y el pantalón, y el TONO cambia con la
  profundidad (neblina). Agrupar por tono separa cerca/lejos ⇒ la misma persona cambia de grupo al
  moverse ⇒ tiene que elegir la alternativa.
- «benjamín»: los equipos se distinguen por el TONO, y brillo y pantalón cambian con la profundidad
  ⇒ la alternativa separa cerca/lejos ⇒ tiene que quedarse la base.
"""

from types import SimpleNamespace

import numpy as np

from src.team_classification.seleccion_feature import _kappa, elegir_feature

CFG = {
    "entrenamiento": {"seleccion_automatica": {"activo": True}},
    "clasificador_color": {},
}


def _feature(bin_hs: int, bin_v: int, bin_pant: int, rng) -> np.ndarray:
    hs = np.zeros(256)
    hs[bin_hs] = 1.0
    v = np.zeros(16)
    v[bin_v] = 1.0
    pant = np.zeros(64)
    pant[bin_pant] = 1.0
    f = np.concatenate([hs, v, pant]) + rng.normal(0, 0.02, 336).clip(0)
    return f


def _partido(tipo: str, n_jugadores: int = 10, dur_s: float = 120.0, dt: float = 0.3):
    """Jugadores aislados (10 m entre ellos) que van y vienen en profundidad de 5 a 35 m."""
    rng = np.random.default_rng(0)
    cache, colores, identidades = [], {}, []
    tiempos = np.arange(0, dur_s, dt)
    tracklets = [SimpleNamespace(ts=[], det_idxs=[]) for _ in range(n_jugadores)]
    for n_f, t in enumerate(tiempos):
        dets = []
        for j in range(n_jugadores):
            equipo = j % 2
            prof = 20 + 15 * np.sin(2 * np.pi * t / 30 + j)
            dets.append((10.0 * j + 5, prof, 0, 0, 1, 1, 0.9))
            lejos = prof > 20
            if tipo == "alevin":
                f = _feature(
                    bin_hs=40 if lejos else 10,
                    bin_v=12 if equipo else 3,
                    bin_pant=50 if equipo else 5,
                    rng=rng,
                )
            else:
                f = _feature(
                    bin_hs=100 if equipo else 20,
                    bin_v=12 if lejos else 3,
                    bin_pant=50 if lejos else 5,
                    rng=rng,
                )
            colores[(n_f, j)] = f
            tracklets[j].ts.append(float(t))
            tracklets[j].det_idxs.append((n_f, j))
        cache.append({"frame_idx": n_f, "t": float(t), "dets": dets})
    identidades = [[tr] for tr in tracklets]
    return identidades, colores, cache


def _elegir(tipo, cfg=CFG):
    identidades, colores, cache = _partido(tipo)
    return elegir_feature(
        identidades,
        colores,
        cache,
        cfg,
        dentro=lambda p: 0 <= p[0] <= 100 and 0 <= p[1] <= 64,
        profundidad_de=lambda p: p[1],
    )


def test_kappa_corrige_el_azar():
    a = np.array([0, 0, 1, 1])
    assert _kappa(a, a) == 1.0
    assert abs(_kappa(a, 1 - a) + 1.0) < 1e-9


def test_si_los_equipos_solo_se_distinguen_por_brillo_elige_la_alternativa():
    cfg, informe = _elegir("alevin")
    assert informe["eleccion"] == "alternativa", informe
    assert cfg["clasificador_color"]["peso_v_pecho"] == 1.0
    assert cfg["entrenamiento"]["medias_por_ventana_s"] == 1.5
    # no toca la config de entrada
    assert "peso_v_pecho" not in CFG["clasificador_color"]


def test_si_el_brillo_cambia_con_la_profundidad_se_queda_la_base():
    cfg, informe = _elegir("benja")
    assert informe["eleccion"] == "base", informe
    assert cfg is CFG


def test_sin_parejas_suficientes_se_queda_la_base():
    cfg_pocas = {
        "entrenamiento": {
            "seleccion_automatica": {"activo": True, "min_parejas": 10**6}
        },
        "clasificador_color": {},
    }
    cfg, informe = _elegir("alevin", cfg_pocas)
    assert informe["eleccion"] == "base"
    assert "kappa_base" not in informe


def test_el_processor_entero_corre_con_la_seleccion_y_la_apunta_en_el_meta(tmp_path):
    """Integración: el interruptor encendido recorre el camino entero del processor y deja la
    decisión en el meta (un error de cableado aquí solo se veía al correr el banco)."""
    import json

    import yaml

    from src.tracking_data.processor import procesar_desde_cache
    from test_feature_v2_integracion import _cache_sintetico, _config

    ruta_c, ruta_col = _cache_sintetico(tmp_path, True)
    cfg = yaml.safe_load(open(_config(tmp_path, ruta_c, ruta_col, "sel")))
    eq = yaml.safe_load(open(cfg["config_equipos"]))
    eq.setdefault("entrenamiento", {})["seleccion_automatica"] = {"activo": True}
    ruta_eq = tmp_path / "equipos_sel.yaml"
    ruta_eq.write_text(yaml.safe_dump(eq, allow_unicode=True))
    cfg["config_equipos"] = str(ruta_eq)
    df = procesar_desde_cache(cfg)
    assert len(df) > 0
    meta = json.loads(open(cfg["rutas"]["salida_meta"]).read())
    assert meta["seleccion_feature"]["eleccion"] in ("base", "alternativa")
    assert "parejas" in meta["seleccion_feature"]
