"""Cortar en los cruces y reenlazar (flag `tracking.corte_cruces`, apagado). 22-oct g, B2."""

from pathlib import Path

import numpy as np
import yaml

from src.tracking.corte_en_cruces import ParametrosCorteCruces, cortar_y_reenlazar
from src.tracking.field_tracker import Tracklet

R = Path(__file__).resolve().parent.parent


def _escena():
    """P (rojo) va hacia +x y Q (azul) hacia −x; se cruzan en los frames 14-15.

    En el caché, la detección 0 es siempre P y la 1 es siempre Q. ByteTrack las INTERCAMBIA en
    el cruce: la identidad 1 es P hasta el frame 15 y Q después; la 2, al revés.
    """
    cache, colores = [], {}
    for f in range(30):
        p = (10 + 0.1 * f, 10.0, 100 + 10 * f, 100, 120 + 10 * f, 140, 0.9)
        q = (12.9 - 0.1 * f, 10.0, 390 - 10 * f, 100, 410 - 10 * f, 140, 0.9)
        cache.append({"frame_idx": f, "t": f * 0.1, "dets": [p, q]})
        colores[(f, 0)] = np.eye(256)[5]
        colores[(f, 1)] = np.eye(256)[200]

    def pista(tid, antes, despues):
        d = cache[0]["dets"][antes]
        tr = Tracklet(tid, 0.0, np.array(d[:2]), antes, 0)
        for f in range(1, 30):
            j = antes if f <= 15 else despues
            dd = cache[f]["dets"][j]
            tr.anadir(f * 0.1, np.array(dd[:2]), j, f)
        return [tr]

    return cache, colores, [pista(1, 0, 1), pista(2, 1, 0)]


def test_apagado_en_los_configs_de_produccion():
    for ruta in ("configs/tracking_benja.yaml", "configs/tracking.yaml"):
        assert yaml.safe_load(open(R / ruta))["corte_cruces"]["activo"] is False
    assert ParametrosCorteCruces().activo is False


def test_deshace_el_cambio_de_persona_en_el_cruce():
    cache, colores, idents = _escena()
    salida = cortar_y_reenlazar(
        idents, cache, colores, 1.0, ParametrosCorteCruces(activo=True)
    )
    personas = [
        {par[1] for tr in ident for par in tr.det_idxs if par[0] not in (14, 15)}
        for ident in salida
    ]
    assert sorted(len(s) for s in personas) == [1, 1]  # cada identidad, UNA persona
    assert len(salida) == 2


def test_con_el_color_permutado_no_puede_decidir_igual():
    """Con colores sin información (iguales), solo queda el movimiento: sigue sin mezclar aquí
    porque P y Q van en sentidos opuestos; el test fija que la función no se rompe."""
    cache, colores, idents = _escena()
    iguales = {k: np.eye(256)[5] for k in colores}
    salida = cortar_y_reenlazar(
        idents, cache, iguales, 1.0, ParametrosCorteCruces(activo=True)
    )
    assert sum(len(tr.det_idxs) for ident in salida for tr in ident) == 60
