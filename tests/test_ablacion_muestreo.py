"""Piezas puras de la ablación 1/3 contra 1/1 (scripts/ablacion_muestreo.py)."""

import importlib.util
from pathlib import Path

import yaml

_RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ablacion_muestreo", _RAIZ / "scripts/ablacion_muestreo.py"
)
ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ab)


def test_convertir_multiplica_solo_los_recuentos_y_no_toca_el_original():
    cfg = yaml.safe_load(open(_RAIZ / "configs/team_classification_benja.yaml"))
    antes = (
        cfg["staff"]["min_observaciones"],
        cfg["agregacion"]["por_observacion"]["ventana_s"],
    )
    nuevo = ab.convertir_configs(cfg, 3)
    assert nuevo["staff"]["min_observaciones"] == 3 * antes[0]
    assert nuevo["staff"]["min_obs_lento"] == 3 * cfg["staff"]["min_obs_lento"]
    assert (
        nuevo["arbitro"]["min_observaciones"] == 3 * cfg["arbitro"]["min_observaciones"]
    )
    assert (
        nuevo["agregacion"]["min_obs_para_otro"]
        == 3 * cfg["agregacion"]["min_obs_para_otro"]
    )
    # lo que ya está en segundos no se toca, y el original queda intacto
    assert nuevo["agregacion"]["por_observacion"]["ventana_s"] == antes[1]
    assert cfg["staff"]["min_observaciones"] == antes[0]


def test_submuestrear_por_fase_sin_reindexar():
    datos = {
        "cache": [{"frame_idx": f, "dets": [f]} for f in range(9, 21)],
        "sample": 1,
    }
    colores = {(f, 0): f for f in range(9, 21)}
    for fase in (0, 1, 2):
        sub, col = ab.submuestrear(datos, colores, fase)
        frames = [e["frame_idx"] for e in sub["cache"]]
        assert frames and all(f % 3 == fase for f in frames)
        assert sub["sample"] == 3
        assert set(k[0] for k in col) == set(frames)
    # las tres fases juntas son el 1/1 entero, sin solaparse
    todas = sorted(
        e["frame_idx"]
        for fase in (0, 1, 2)
        for e in ab.submuestrear(datos, None, fase)[0]["cache"]
    )
    assert todas == list(range(9, 21))


def test_frame_de_evaluacion_a_un_frame_como_mucho():
    assert ab.frame_de_evaluacion(9750, 0) == 9750
    assert ab.frame_de_evaluacion(9750, 1) == 9751
    assert ab.frame_de_evaluacion(9750, 2) == 9749


def test_parche_de_velocidad_se_aplica_y_se_retira():
    import src.tracking.cosido_pureza as cp

    original = cp._velocidad_final
    vistas = []

    def espia(identidad, ventana=3):
        vistas.append(ventana)

    cp._velocidad_final = espia
    try:
        with ab.velocidad_final_en_segundos(3):
            cp._velocidad_final(None)
        assert vistas == [9]
        assert cp._velocidad_final is espia
    finally:
        cp._velocidad_final = original


def _m(**k):
    base = {n: 0.0 for n in ab.METRICAS}
    base.update(k)
    return base


def test_veredicto_con_el_ruido_de_las_fases():
    fases = [_m(faltan_por_equipo_frame=0.76, IDF1=0.35), _m(faltan_por_equipo_frame=0.74,
             IDF1=0.36), _m(faltan_por_equipo_frame=0.78, IDF1=0.34)]  # fmt: skip
    # mejora de faltan e IDF1 por encima del ruido (0,04 y 0,02)
    assert ab.veredicto(_m(faltan_por_equipo_frame=0.60, IDF1=0.40), fases)[
        "veredicto"
    ].startswith("PASA")
    # mejora de faltan dentro del ruido → no se adopta
    assert (
        "faltantes"
        in ab.veredicto(_m(faltan_por_equipo_frame=0.73, IDF1=0.40), fases)["veredicto"]
    )
    # algo empeora más que el ruido → no se adopta aunque lo demás mejore
    r = ab.veredicto(_m(faltan_por_equipo_frame=0.60, IDF1=0.40, quimeras=5.0), fases)
    assert r["veredicto"].startswith("NO SE ADOPTA (empeora")
    # el control de detecciones cambia → banco roto
    r = ab.veredicto(
        _m(dets_en_campo_por_frame=1.0, faltan_por_equipo_frame=0.6), fases
    )
    assert r["veredicto"].startswith("NO CONCLUYENTE")


def test_quimeras_e_identidades_por_persona():
    # id 1: persona 10 en 5 frames y persona 11 en 3 → quimera; id 2: solo persona 11
    pares = [(1, 10)] * 5 + [(1, 11)] * 3 + [(2, 11)] * 4
    q, ids = ab.quimeras_e_ids(pares, min_segunda=3)
    assert q == 1
    assert ids == 1.5  # persona 10 → {1}; persona 11 → {1, 2}
    assert ab.quimeras_e_ids(pares, min_segunda=4)[0] == 0
