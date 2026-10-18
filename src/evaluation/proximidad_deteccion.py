"""¿El detector separa a dos personas cuando están CERCA en la imagen?

25-sep-2026 (docs/proximidad_deteccion.md, BACKLOG 19). La revisión manual de la hoja
de recuento (`scripts/hoja_revision_recuento.py`) encontró 5 casos concretos de una
caja que funde a dos personas CLARAMENTE visibles (torso, cara, color de camiseta
todo distinguible) — no es oclusión de "tapado, no se ve", es el postproceso de SAHI
(`GREEDYNMM` + métrica `IOS`, BACKLOG 19) fusionando dos cajas próximas en píxeles.

Este módulo mide la relación exacta: para cada persona del GT, la distancia en
PÍXELES a su vecino más cercano (también del GT), contra si el detector la encontró
(una detección CRUDA del caché, 1-a-1 por Hungarian, dentro de un radio en metros).

⚠️ Los porteros se excluyen de la lectura de "proximidad": el portero A vive solo
cerca de su portería (vecino lejano en píxeles) y falla por el encuadre cercano a la
cámara (`docs/portero_cortado.md`), no por proximidad — mezclarlo invierte la curva.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PersonaGT:
    """Una persona del GT en un frame: su posición en píxeles y en metros."""

    track_id: int
    equipo: str  # tal cual viene del GT (puede llevar 'portero_')
    pixel: tuple[float, float]  # el pie, en píxeles de la imagen ORIGINAL
    metros: tuple[float, float]


def personas_gt_por_frame(
    tracks, homografia: np.ndarray, frame_offset: int, paso_gt: int
):
    """{frame_global: [PersonaGT, ...]} — solo tracks de jugador (no árbitro)."""
    from src.evaluation.gt_parser import proyectar_punto

    por_frame: dict[int, list[PersonaGT]] = {}
    for track in tracks:
        if track.label != "player":
            continue
        for caja in track.cajas:
            equipo = caja.team if caja.team is not None else track.team
            if equipo is None:
                continue
            frame_global = frame_offset + paso_gt * caja.frame_local
            mx, my = proyectar_punto(*caja.pie, homografia)
            por_frame.setdefault(frame_global, []).append(
                PersonaGT(
                    track.track_id, equipo, tuple(caja.pie), (float(mx), float(my))
                )
            )
    return por_frame


def vecino_mas_cercano_px(personas: list[PersonaGT]) -> np.ndarray:
    """Distancia en píxeles de cada persona a la OTRA persona del GT más próxima.

    `inf` si está sola en el frame.
    """
    n = len(personas)
    if n < 2:
        return np.full(n, np.inf)
    P = np.array([p.pixel for p in personas])
    D = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1])
    np.fill_diagonal(D, np.inf)
    return D.min(axis=1)


def encontrado_en_deteccion(
    personas: list[PersonaGT], detecciones: np.ndarray, radio_m: float = 2.0
) -> np.ndarray:
    """¿Hay una detección CRUDA (caché) casada 1-a-1 con cada persona, dentro de `radio_m`?

    Casado húngaro en METROS, igual que el resto del proyecto (`comparar_escalas.py`,
    `desglose_error.py`): una detección no puede servir a dos personas.
    """
    from scipy.optimize import linear_sum_assignment

    n = len(personas)
    encontrado = np.zeros(n, dtype=bool)
    if n == 0 or len(detecciones) == 0:
        return encontrado
    M = np.array([p.metros for p in personas])
    D = np.asarray(detecciones)[:, :2]
    coste = np.hypot(M[:, None, 0] - D[None, :, 0], M[:, None, 1] - D[None, :, 1])
    coste_g = np.where(coste > radio_m, 1e6, coste)
    for i, j in zip(*linear_sum_assignment(coste_g)):
        if coste_g[i, j] < 1e6:
            encontrado[i] = True
    return encontrado


def es_portero(equipo: str) -> bool:
    return str(equipo).startswith("portero_")


def tabla_proximidad(
    por_frame: dict[int, list[PersonaGT]], cache: dict, radio_m: float = 2.0
):
    """Una fila por persona-frame: vecino_px, encontrado, si es portero.

    `cache`: {frame: array de detecciones crudas, columnas [mx, my, x1, y1, x2, y2, conf]}.
    """
    filas = []
    for frame, personas in sorted(por_frame.items()):
        vecino = vecino_mas_cercano_px(personas)
        dets = cache.get(frame, np.zeros((0, 7)))
        hallado = encontrado_en_deteccion(personas, dets, radio_m)
        for p, v, h in zip(personas, vecino, hallado):
            filas.append(
                {
                    "frame": frame,
                    "track_id": p.track_id,
                    "equipo": p.equipo,
                    "portero": es_portero(p.equipo),
                    "vecino_px": float(v),
                    "encontrado": bool(h),
                }
            )
    return filas
