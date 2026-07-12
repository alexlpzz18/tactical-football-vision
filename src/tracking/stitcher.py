"""Etapa B del tracking en metros: cosido de tracklets en identidades.

Migración fiel del código validado en Colab (briefing, sección 2.2, v2).
Validación de referencia: 309 tracklets → 94 identidades (con color),
→ ~127 identidades cosiendo solo por movimiento (sin color).

Idea central: un tracklet B es candidato a continuar a un tracklet A si
empieza poco después de que A termine, cerca de donde A "habría llegado"
(extrapolando su velocidad) y, si hay información de color, con apariencia
compatible. Se unen golosa y ordenadamente por coste, sin conflictos, y las
cadenas resultantes son las identidades finales.
"""

import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosCosido:
    """Parámetros del cosido (valores validados como defaults).

    En producción se cargan desde configs/tracking.yaml (clave 'cosido').
    """

    max_hueco: float = 6.0  # s máximos entre el final de A y el inicio de B
    tol_base: float = 1.2  # m de tolerancia base
    tol_por_seg: float = 3.0  # m extra de tolerancia por segundo de hueco
    peso_hueco: float = 0.3  # peso del hueco en el coste
    color_max_dist: float = 1.2  # veto suave: distancia de histogramas mayor → no coser
    peso_color: float = 0.15  # peso del color en el coste

    @classmethod
    def desde_dict(cls, d: dict) -> "ParametrosCosido":
        """Crea los parámetros desde un dict (p. ej. el YAML de config)."""
        return cls(**d)


class TrackletStitcher:
    """Etapa B: cose tracklets en identidades persistentes."""

    def __init__(self, params: ParametrosCosido | None = None):
        self.params = params or ParametrosCosido()

    def coser(
        self,
        tracklets: list[Tracklet],
        color_medio: dict[int, np.ndarray] | None = None,
    ) -> list[list[Tracklet]]:
        """Une tracklets en cadenas (identidades).

        Args:
            tracklets: salida de la Etapa A.
            color_medio: dict {tracklet.id: feature de color (np.array)} o
                None para coser SOLO por movimiento. Nota: en el notebook
                original el dict iba indexado por posición en la lista; aquí
                se indexa por `tracklet.id` para que no dependa del orden
                interno (esta función reordena los tracklets por t inicial).

        Returns:
            Lista de identidades; cada identidad es la lista de tracklets
            que la componen, en orden temporal.
        """
        p = self.params
        orden = sorted(tracklets, key=lambda tr: tr.ts[0])

        # 1. Generar candidatos (A, B): B podría ser la continuación de A
        candidatos: list[tuple[float, int, int]] = []
        for i, tr_a in enumerate(orden):
            for j, tr_b in enumerate(orden):
                if i == j:
                    continue
                hueco = tr_b.ts[0] - tr_a.ts[-1]
                if hueco <= 0 or hueco > p.max_hueco:
                    continue
                # ¿Dónde estaría A tras el hueco, a velocidad constante?
                pred = tr_a.pos[-1] + tr_a.vel * hueco
                dist = np.linalg.norm(pred - tr_b.pos[0])
                # La tolerancia crece con el hueco (más tiempo = más incertidumbre)
                tol = p.tol_base + p.tol_por_seg * hueco
                if dist > tol:
                    continue
                coste_color = 0.0
                if (
                    color_medio is not None
                    and tr_a.id in color_medio
                    and tr_b.id in color_medio
                ):
                    dcol = np.linalg.norm(color_medio[tr_a.id] - color_medio[tr_b.id])
                    if dcol > p.color_max_dist:
                        continue  # veto suave: colores claramente incompatibles
                    coste_color = dcol / p.color_max_dist
                coste = (
                    dist / tol
                    + p.peso_hueco * (hueco / p.max_hueco)
                    + p.peso_color * coste_color
                )
                candidatos.append((coste, i, j))

        # 2. Unión golosa por coste creciente, sin conflictos: cada tracklet
        #    recibe como mucho una continuación y es continuación de uno.
        candidatos.sort()
        tiene: set[int] = set()  # tracklets que ya tienen continuación
        es: set[int] = set()  # tracklets que ya son continuación de otro
        union: dict[int, int] = {}
        for _, i, j in candidatos:
            if i in tiene or j in es:
                continue
            union[i] = j
            tiene.add(i)
            es.add(j)

        # 3. Seguir las cadenas desde los tracklets que no son continuación
        inicios = [i for i in range(len(orden)) if i not in es]
        identidades = []
        for ini in inicios:
            cadena = [ini]
            while cadena[-1] in union:
                cadena.append(union[cadena[-1]])
            identidades.append([orden[k] for k in cadena])

        logger.info(
            "Cosido: %d tracklets → %d identidades (%s)",
            len(tracklets),
            len(identidades),
            "con color" if color_medio else "solo movimiento",
        )
        return identidades
