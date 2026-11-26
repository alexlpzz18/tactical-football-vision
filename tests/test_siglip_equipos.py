"""SigLIP elegido por partido (docs/plan_siglip_por_partido.md)."""

from types import SimpleNamespace

import numpy as np

from src.team_classification.pipeline_equipos import etiquetar_por_observacion
from src.team_classification.siglip_equipos import alinear_por_caja, nombrar


def test_alinear_por_caja_sigue_a_la_deteccion_aunque_cambie_el_indice():
    crudo = [
        {"frame_idx": 3, "dets": [(0, 0, 1, 1, 9, 9, 0.2), (0, 0, 20, 20, 30, 40, 0.9)]}
    ]
    filtrado = [
        {"frame_idx": 3, "dets": [(0, 0, 20, 20, 30, 40, 0.9)]}
    ]  # la 0 se filtró
    assert alinear_por_caja({(3, 0): 0, (3, 1): 1}, crudo, filtrado) == {(3, 0): 1}


class _Clf:
    """HS: A si la primera componente es positiva."""

    def predict_color(self, f, solo_equipos=False, dist_max=None):
        return "A" if f[0] > 0 else "B"


def test_nombrar_llama_A_al_grupo_que_coincide_con_A_del_color():
    colores = {(1, k): np.array([1.0 if k < 5 else -1.0]) for k in range(10)}
    sig = {
        (1, k): (1 if k < 5 else 0) for k in range(10)
    }  # el grupo 1 es el A del color
    nombres = nombrar(sig, colores, _Clf())
    assert nombres[(1, 0)] == "A" and nombres[(1, 9)] == "B"


def test_el_voto_por_ventana_usa_las_etiquetas_externas_si_se_pasan():
    tr = SimpleNamespace(
        ts=[0.0, 0.1, 0.2], det_idxs=[(1, 0), (2, 0), (3, 0)], pos=[(0, 0)] * 3
    )
    colores = {(f, 0): np.array([1.0]) for f in (1, 2, 3)}  # el color dice A
    cfg = {"agregacion": {"por_observacion": {"activo": True, "ventana_s": 1.5}}}
    externas = {(f, 0): "B" for f in (1, 2, 3)}

    class Clf(_Clf):
        _prototipos = None

    sin = etiquetar_por_observacion([[tr]], {1: "A"}, colores, Clf(), cfg)
    con = etiquetar_por_observacion(
        [[tr]], {1: "A"}, colores, Clf(), cfg, etiquetas_externas=externas
    )
    assert set(sin.values()) == {"A"}
    assert set(con.values()) == {"B"}
