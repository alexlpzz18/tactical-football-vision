"""El flag `staff_dentro_del_campo` tiene que CAMBIAR la etiqueta, y solo donde dice.

Una identidad de staff (la 590 del benjamín) empezaba siendo el entrenador en la banda y saltaba al
lateral derecho de A: la regla de staff, que decide por identidad entera, lo pintaba de gris en una
salida de balón (docs/staff_dentro_del_campo.md). Con el flag, sus observaciones DENTRO del campo
que se mueven como un jugador se etiquetan por color; las de fuera y las de alguien plantado junto
a la banda siguen siendo staff.
"""

import numpy as np
import pytest

import src.team_classification.pipeline_equipos as pe
from src.tracking.field_tracker import Tracklet


class _Clasificador:
    """Siempre dice A: aquí solo importa QUÉ observaciones se etiquetan, no con qué."""

    def predict_color(self, media, solo_equipos=True):
        return "A"


def _identidad(puntos):
    """Un tracklet con [(t, x, y)], una detección por frame (frame = 10·t)."""
    t0, x0, y0 = puntos[0]
    tr = Tracklet(1, t0, np.array([x0, y0]), 0, int(round(10 * t0)))
    for t, x, y in puntos[1:]:
        tr.anadir(t, np.array([x, y]), 0, int(round(10 * t)))  # (det_idx, frame_idx)
    return [tr]


def _cfg(activo):
    return {
        "campo": {"config": "configs/campo_benja.yaml"},
        "staff": {"vel_max_lento": 2.75},
        "agregacion": {
            "por_observacion": {
                "activo": True,
                "ventana_s": 1.5,
                "staff_dentro_del_campo": {
                    "activo": activo,
                    "margen_m": 1.0,
                    "solo_trozos_rapidos": True,
                    "hueco_trozo_s": 1.0,
                },
            }
        },
    }


@pytest.fixture
def escena(monkeypatch):
    monkeypatch.setattr(pe, "color_medio_limpio", lambda cerca, _o: np.ones(3))
    puntos = (
        [(0.1 * k, 33.0, -0.7) for k in range(30)]  # fuera de la banda: el entrenador
        + [(3.0 + 0.1 * k, 33.0, 1.5) for k in range(20)]  # dentro, PLANTADO a 1,5 m
        + [
            (6.0 + 0.1 * k, 30.0 + 0.5 * k, 10.0) for k in range(30)
        ]  # dentro, corriendo 5 m/s
    )
    identidad = _identidad(puntos)
    colores = {(int(round(10 * t)), 0): np.ones(3) for t, _x, _y in puntos}
    return [identidad], {1: "staff"}, colores


def test_apagado_no_toca_al_staff(escena):
    identidades, equipos, colores = escena
    salida = pe.etiquetar_por_observacion(
        identidades, equipos, colores, _Clasificador(), _cfg(False)
    )
    assert salida == {}


def test_encendido_solo_etiqueta_al_que_corre_dentro(escena):
    identidades, equipos, colores = escena
    salida = pe.etiquetar_por_observacion(
        identidades, equipos, colores, _Clasificador(), _cfg(True)
    )
    frames = sorted(f for (_i, f) in salida)
    # solo el trozo que corre dentro (t = 6,0-8,9 s → frames 60-89); ni el de fuera ni el plantado
    assert frames == list(range(60, 90))
    assert set(salida.values()) == {"A"}
