"""Corte de teletransportes (docs/registro_mision.md, H1b). Tests de comportamiento."""

import numpy as np

from src.tracking.corte_teletransporte import ParametrosCorte, cortar_teletransportes
from src.tracking.field_tracker import Tracklet

DT = 0.12


def _identidad(pos: np.ndarray, t0: float = 0.0, f0: int = 0, tid: int = 1):
    tr = Tracklet(tid, t0, pos[0], 0, f0)
    for i in range(1, len(pos)):
        tr.anadir(t0 + i * DT, pos[i], 0, f0 + i)
    return [tr]


def _andando(n, origen, vel=(2.0, 0.0), ruido=0.1, semilla=0):
    rng = np.random.default_rng(semilla)
    return (
        np.asarray(origen, float)
        + np.outer(np.arange(n) * DT, vel)
        + rng.normal(0, ruido, (n, 2))
    )


def test_un_salto_que_se_queda_corta_la_identidad_en_el_sitio():
    a = _andando(50, (20, 30))
    b = _andando(50, (20 + 50 * DT * 2 + 9.0, 38), semilla=1)  # salta 12 m y sigue allí
    salida, n = cortar_teletransportes([_identidad(np.vstack([a, b]))])
    assert n == 1 and len(salida) == 2
    assert [len(i[0]) for i in salida] == [50, 50]
    # no se pierde ni se inventa ninguna observación
    assert sum(len(tr.det_idxs) for i in salida for tr in i) == 100


def test_un_pico_suelto_que_vuelve_no_corta():
    pos = _andando(100, (20, 30))
    pos[50] += (0.0, 8.0)  # la caja salta un fotograma y vuelve
    salida, n = cortar_teletransportes([_identidad(pos)])
    assert n == 0 and len(salida) == 1


def test_un_sprint_y_un_hueco_largo_no_cortan():
    sprint = _andando(100, (10, 30), vel=(8.5, 0.0))
    antes = _andando(30, (20, 30))
    # reaparece 2 s después, 12 m más allá: 6 m/s, posible
    despues = _andando(30, (20 + 30 * DT * 2 + 12.0, 30), semilla=2)
    tr = _identidad(antes)[0]
    for i, p in enumerate(despues):
        tr.anadir(30 * DT + 2.0 + i * DT, p, 0, 1000 + i)
    salida, n = cortar_teletransportes([_identidad(sprint, tid=1), [tr]])
    assert n == 0 and len(salida) == 2


def test_donde_la_medida_tiembla_mas_hace_falta_un_salto_mayor():
    """El mismo salto de 6 m corta con ruido de 0,05 m y no corta con ruido de 1,5 m.

    (Con ruido de 1,5 m un salto de 6 m no se distingue del temblor: el suavizado lo absorbe.)
    """

    def con_ruido(ruido):
        a = _andando(300, (20, 30), vel=(0.0, 0.0), ruido=ruido)
        b = _andando(300, (26, 30), vel=(0.0, 0.0), ruido=ruido, semilla=1)
        return cortar_teletransportes(
            [_identidad(np.vstack([a, b]))], ParametrosCorte()
        )[1]

    assert con_ruido(0.05) == 1
    assert con_ruido(1.5) == 0


def test_interruptor_real_en_el_processor(tmp_path):
    """`corte_teletransporte.activo` cambia el número de identidades; apagado, lo de siempre."""
    import pickle

    import yaml

    from src.tracking_data.processor import procesar_desde_cache

    rng = np.random.default_rng(5)
    fps, sample = 30.0, 3
    cache, colores = [], {}
    for k in range(120):
        dets = []
        for j in range(4):
            # el jugador 0 «se teletransporta» 15 m a mitad del tramo sin que cambie su caja
            salto = 15.0 if (j == 0 and k >= 60) else 0.0
            mx, my = 15.0 + j * 8 + k * 0.05, 10.0 + j * 6 + salto
            x = 200 + j * 300 + k
            dets.append((mx, my, x, 400.0, x + 30, 480.0, 0.9))
            v = np.zeros(256)
            v[10 if j % 2 == 0 else 200] = 1.0
            v = v + rng.normal(0, 0.01, 256).clip(0)
            colores[(100 + 3 * k, j)] = v / np.linalg.norm(v)
        cache.append({"frame_idx": 100 + 3 * k, "t": k * sample / fps, "dets": dets})
    ruta_c, ruta_col = tmp_path / "c.pkl", tmp_path / "col.pkl"
    pickle.dump(
        {"cache": cache, "fps": fps, "sample": sample, "wh": (1920, 1080)},
        open(ruta_c, "wb"),
    )
    pickle.dump(colores, open(ruta_col, "wb"))
    n_ids = {}
    for activo in (False, True):
        cfg = yaml.safe_load(open("configs/processor_benja.yaml"))
        cfg["modo"] = "desde_cache"
        cfg["rutas"].update(
            cache=str(ruta_c),
            cache_colores=str(ruta_col),
            salida_csv=str(tmp_path / f"pos_{activo}.csv"),
            salida_meta=str(tmp_path / f"meta_{activo}.json"),
        )
        tr = yaml.safe_load(open(cfg["config_tracking"]))
        tr["corte_teletransporte"] = {"activo": activo}
        ruta_tr = tmp_path / f"tracking_{activo}.yaml"
        ruta_tr.write_text(yaml.safe_dump(tr, allow_unicode=True))
        cfg["config_tracking"] = str(ruta_tr)
        n_ids[activo] = procesar_desde_cache(cfg).id_jugador.nunique()
    assert n_ids[True] == n_ids[False] + 1, n_ids
