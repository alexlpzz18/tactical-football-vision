"""Guarda de CAJA FUNDIDA: detecta cambios de persona dentro de una identidad y la parte.

SOLO MEDICIÓN (docs/plan_guarda_caja_fundida.md). No la usa producción: la inyecta
`scripts/medir_guarda_caja_fundida.py` antes del cosido por pureza.

Un corte necesita, entre dos observaciones consecutivas de la identidad:

(a) SALTO: > `salto_m` metros en un paso (dt ≤ `dt_paso`), dentro del campo, y
    PERSISTENTE: la mediana de posición del segundo siguiente está a > `salto_m` de la
    del segundo anterior (un pie que tiembla vuelve; una persona distinta no);
(b) CAJA FUNDIDA (si se pide): en la observación del salto o en la anterior, la caja
    mide ≥ `factor_alto` de alto o ≥ `factor_ancho` de ancho respecto a la mediana de
    ESA identidad en ±`ventana_ref_s` (dos cuerpos en una caja);
(c) SE MUEVE LA CAJA ENTERA (si se pide): el borde superior se desplaza, de forma
    persistente, al menos `fraccion_cabeza` veces lo que el inferior. Cuando las
    piernas se tapan o reaparecen solo se mueve el pie; cuando entra otra persona se
    mueve también la cabeza. Es relativo, así que no depende de la profundidad.
"""

from dataclasses import dataclass

import numpy as np

# Una observación: (t, pos (2,), clave (frame, det_idx))
# Una caja: (x1, y1, x2, y2) en píxeles


@dataclass
class ParametrosGuarda:
    salto_m: float = 3.0
    dt_paso: float = 0.35
    ventana_s: float = 1.0
    min_obs_lado: int = 3
    ventana_ref_s: float = 2.0
    factor_alto: float = 1.25
    factor_ancho: float = 1.5
    fraccion_cabeza: float = 0.5
    usar_fundida: bool = True
    usar_entera: bool = True
    # Campo en metros: [0, largo] × [-margen_y, ancho + margen_y]
    largo: float = 62.0
    ancho: float = 40.0
    margen_y: float = 1.0


def observaciones(identidad) -> list[tuple[float, np.ndarray, tuple[int, int]]]:
    """(t, pos, (frame, det_idx)) de una identidad (lista de Tracklet), en orden."""
    obs = [
        (float(t), np.asarray(p, float), tuple(par))
        for tr in identidad
        for t, p, par in zip(tr.ts, tr.pos, tr.det_idxs)
    ]
    obs.sort(key=lambda o: o[0])
    return obs


def _lados(ts: np.ndarray, i: int, ventana: float) -> tuple[np.ndarray, np.ndarray]:
    """Máscaras del segundo ANTERIOR (hasta i-1) y SIGUIENTE (desde i) al paso i-1→i."""
    antes = (ts >= ts[i - 1] - ventana) & (np.arange(len(ts)) < i)
    despues = (ts <= ts[i] + ventana) & (np.arange(len(ts)) >= i)
    return antes, despues


def posiciones_validas(obs, p: ParametrosGuarda) -> list[int]:
    """Índices i donde CABE un corte (i-1 → i): paso corto, lados medibles, en campo.

    Son las condiciones mecánicas, sin ninguna señal: el control al azar sortea
    entre estas mismas posiciones.
    """
    if len(obs) < 2 * p.min_obs_lado:
        return []
    ts = np.array([o[0] for o in obs])
    ps = np.array([o[1] for o in obs])
    validas = []
    for i in range(1, len(obs)):
        if ts[i] - ts[i - 1] > p.dt_paso:
            continue
        antes, despues = _lados(ts, i, p.ventana_s)
        if antes.sum() < p.min_obs_lado or despues.sum() < p.min_obs_lado:
            continue
        x, y = np.median(ps[antes], axis=0)
        if 0 <= x <= p.largo and -p.margen_y <= y <= p.ancho + p.margen_y:
            validas.append(i)
    return validas


def detectar_cortes(obs, cajas: dict, p: ParametrosGuarda) -> list[dict]:
    """Saltos de una identidad que cumplen las señales pedidas. Uno por corte.

    Args:
        obs: salida de `observaciones`.
        cajas: {(frame, det_idx): (x1, y1, x2, y2)}.
    """
    validas = posiciones_validas(obs, p)
    if not validas:
        return []
    ts = np.array([o[0] for o in obs])
    ps = np.array([o[1] for o in obs])
    caja = np.array([cajas[o[2]] for o in obs], dtype=float)
    alto, anchura = caja[:, 3] - caja[:, 1], caja[:, 2] - caja[:, 0]
    arriba = np.c_[
        (caja[:, 0] + caja[:, 2]) / 2, caja[:, 1]
    ]  # centro del borde superior
    abajo = np.c_[
        (caja[:, 0] + caja[:, 2]) / 2, caja[:, 3]
    ]  # centro del borde inferior
    cortes = []
    for i in validas:
        salto = float(np.linalg.norm(ps[i] - ps[i - 1]))
        if salto <= p.salto_m:
            continue
        antes, despues = _lados(ts, i, p.ventana_s)
        d_med = float(
            np.linalg.norm(np.median(ps[despues], 0) - np.median(ps[antes], 0))
        )
        if d_med <= p.salto_m:
            continue
        fundida = _es_fundida(ts, alto, anchura, i, p)
        if p.usar_fundida and not fundida:
            continue
        d_arriba = float(
            np.linalg.norm(np.median(arriba[despues], 0) - np.median(arriba[antes], 0))
        )
        d_abajo = float(
            np.linalg.norm(np.median(abajo[despues], 0) - np.median(abajo[antes], 0))
        )
        entera = d_arriba >= p.fraccion_cabeza * d_abajo
        if p.usar_entera and not entera:
            continue
        cortes.append(
            {
                "i": i,
                "t": float(ts[i]),
                "frame": obs[i][2][0],
                "salto_m": salto,
                "d_medianas_m": d_med,
                "fundida": fundida,
                "d_arriba_px": d_arriba,
                "d_abajo_px": d_abajo,
                "x": float(ps[i - 1][0]),
                "y": float(ps[i - 1][1]),
            }
        )
    return cortes


def _es_fundida(ts, alto, anchura, i, p: ParametrosGuarda) -> bool:
    """¿La caja del salto (i) o la anterior (i-1) es anormalmente alta o ancha?"""
    for j in (i - 1, i):
        ref = (np.abs(ts - ts[j]) <= p.ventana_ref_s) & (np.arange(len(ts)) != j)
        if not ref.any():
            continue
        if alto[j] >= p.factor_alto * np.median(alto[ref]):
            return True
        if anchura[j] >= p.factor_ancho * np.median(anchura[ref]):
            return True
    return False


def partir(identidad, indices_corte: list[int]):
    """Parte una identidad (lista de Tracklet) ANTES de cada índice de observación dado.

    Devuelve una lista de identidades (listas de Tracklet), en orden temporal. Cada
    trozo conserva los tracklets originales recortados, como hace la puerta de re-entrada.
    """
    from src.tracking.puerta_reentrada import _anadir, _tracklet_de

    obs = observaciones(identidad)
    if not indices_corte:
        return [identidad]
    frames_corte = sorted(obs[i][2][0] for i in indices_corte)
    trozos = [[] for _ in range(len(frames_corte) + 1)]
    for tr in identidad:
        for k in range(len(tr.pos)):
            f = tr.det_idxs[k][0]
            destino = sum(1 for c in frames_corte if f >= c)
            nuevo = trozos[destino]
            if not nuevo or nuevo[-1].det_idxs[-1][0] > f:
                nuevo.append(_tracklet_de(tr, k))
            else:
                _anadir(nuevo[-1], tr, k)
    return [t for t in trozos if t]
