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

import bisect
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
    # Método de selección de uniones: "goloso" (original, validado) o
    # "global" (asignación óptima en grafo, Tarea 3)
    metodo: str = "goloso"
    # Solo para metodo=global: coste de dejar un tracklet sin continuación.
    # Debe superar el coste máximo de un candidato real (~1.45 con los pesos
    # actuales) para que la asignación prefiera unir siempre que pueda.
    coste_no_union: float = 2.0
    # Consistencia de velocidad en la unión (Tarea 3, off por defecto):
    # v_salto = (inicio_B - fin_A) / hueco es la velocidad que el jugador
    # habría necesitado para cubrir el salto.
    # - v_max_salto: veto físico; si ||v_salto|| lo supera, no coser
    #   (None = sin veto). Un jugador no corre a más de ~7 m/s.
    v_max_salto: float | None = None
    # - peso_vel: peso del término ||v_salto - vel_A|| / v_ref en el coste
    #   (0 = off). Penaliza uniones que exigen cambios bruscos de velocidad.
    peso_vel: float = 0.0
    # - v_ref: normalizador del término de velocidad (m/s)
    v_ref: float = 7.0

    @classmethod
    def desde_dict(cls, d: dict) -> "ParametrosCosido":
        """Crea los parámetros desde un dict (p. ej. el YAML de config)."""
        return cls(**d)


def fusionar_identidad(identidad: list[Tracklet]) -> Tracklet:
    """Une una identidad (cadena de tracklets) en UN tracklet continuo.

    Necesario para la segunda pasada de cosido (Tarea 3c): cada identidad
    de la primera pasada se convierte en un "super-tracklet" y se vuelve a
    coser con huecos más largos. La velocidad se recalcula con la misma
    media móvil exponencial que usa la Etapa A, recorriendo todas las
    observaciones en orden.
    """
    observaciones = []
    for tracklet in identidad:
        for t, pos, (frame_idx, det_idx) in zip(
            tracklet.ts, tracklet.pos, tracklet.det_idxs
        ):
            observaciones.append((t, pos, det_idx, frame_idx))
    observaciones.sort(key=lambda x: x[0])

    t0, pos0, det0, frame0 = observaciones[0]
    fusionado = Tracklet(identidad[0].id, t0, pos0, det0, frame0)
    for t, pos, det_idx, frame_idx in observaciones[1:]:
        fusionado.anadir(t, pos, det_idx, frame_idx)
    return fusionado


def filtrar_identidades_cortas(
    identidades: list[list[Tracklet]],
    min_frames_total: int,
) -> list[list[Tracklet]]:
    """Descarta identidades con menos de `min_frames_total` observaciones.

    Pensado para la variante "rescate de cortos" (Tarea 3b): la Etapa A se
    corre con min_frames=1 para que los tracklets cortos entren al cosido,
    y el filtro de calidad se aplica DESPUÉS, a nivel de identidad: un
    tracklet de 1 frame aislado se descarta igual que antes, pero si quedó
    cosido a una cadena con sustancia, se conserva.
    """
    filtradas = [
        identidad
        for identidad in identidades
        if sum(len(tr) for tr in identidad) >= min_frames_total
    ]
    logger.info(
        "Filtro de identidades cortas: %d → %d (mínimo %d frames en total)",
        len(identidades),
        len(filtradas),
        min_frames_total,
    )
    return filtradas


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

        candidatos = self._generar_candidatos(orden, color_medio)

        if p.metodo == "global":
            union = self._seleccion_global(candidatos, len(orden))
        else:
            union = self._seleccion_golosa(candidatos)

        # 3. Seguir las cadenas desde los tracklets que no son continuación
        es = set(union.values())
        inicios = [i for i in range(len(orden)) if i not in es]
        identidades = []
        for ini in inicios:
            cadena = [ini]
            while cadena[-1] in union:
                cadena.append(union[cadena[-1]])
            identidades.append([orden[k] for k in cadena])

        logger.info(
            "Cosido (%s): %d tracklets → %d identidades (%s)",
            self.params.metodo,
            len(tracklets),
            len(identidades),
            "con color" if color_medio else "solo movimiento",
        )
        return identidades

    def _generar_candidatos(
        self,
        orden: list[Tracklet],
        color_medio: dict[int, np.ndarray] | None,
    ) -> list[tuple[float, int, int]]:
        """Genera los candidatos (coste, i, j): B podría continuar a A.

        La búsqueda usa una ventana temporal por bisección sobre los
        tiempos de inicio (orden ya viene ordenado por ts[0]): solo se
        examinan los B que empiezan en (fin_de_A, fin_de_A + max_hueco].
        Mismo conjunto de candidatos que el doble bucle original, pero
        O(n·k) en vez de O(n²) — necesario para el rescate de cortos
        (miles de fragmentos).
        """
        p = self.params
        inicios = [tr.ts[0] for tr in orden]
        candidatos: list[tuple[float, int, int]] = []
        for i, tr_a in enumerate(orden):
            fin_a = tr_a.ts[-1]
            desde = bisect.bisect_right(inicios, fin_a)
            hasta = bisect.bisect_right(inicios, fin_a + p.max_hueco)
            for j in range(desde, hasta):
                if i == j:
                    continue
                tr_b = orden[j]
                hueco = tr_b.ts[0] - fin_a
                # ¿Dónde estaría A tras el hueco, a velocidad constante?
                pred = tr_a.pos[-1] + tr_a.vel * hueco
                dist = np.linalg.norm(pred - tr_b.pos[0])
                # La tolerancia crece con el hueco (más tiempo = más incertidumbre)
                tol = p.tol_base + p.tol_por_seg * hueco
                if dist > tol:
                    continue
                # Consistencia de velocidad: velocidad implicada por el salto
                v_salto = (tr_b.pos[0] - tr_a.pos[-1]) / hueco
                if (
                    p.v_max_salto is not None
                    and np.linalg.norm(v_salto) > p.v_max_salto
                ):
                    continue  # físicamente imposible: nadie corre tan rápido
                coste_vel = 0.0
                if p.peso_vel > 0:
                    coste_vel = np.linalg.norm(v_salto - tr_a.vel) / p.v_ref
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
                    + p.peso_vel * coste_vel
                )
                candidatos.append((coste, i, j))
        return candidatos

    @staticmethod
    def _seleccion_golosa(
        candidatos: list[tuple[float, int, int]],
    ) -> dict[int, int]:
        """Unión golosa por coste creciente, sin conflictos (método original):
        cada tracklet recibe como mucho una continuación y es continuación
        de uno."""
        tiene: set[int] = set()  # tracklets que ya tienen continuación
        es: set[int] = set()  # tracklets que ya son continuación de otro
        union: dict[int, int] = {}
        for _, i, j in sorted(candidatos):
            if i in tiene or j in es:
                continue
            union[i] = j
            tiene.add(i)
            es.add(j)
        return union

    def _seleccion_global(
        self,
        candidatos: list[tuple[float, int, int]],
        n: int,
    ) -> dict[int, int]:
        """Selección GLOBAL de uniones: asignación de coste mínimo en grafo.

        En vez de aceptar candidatos uno a uno por orden de coste (goloso),
        se resuelve el emparejamiento bipartito óptimo tracklet→sucesor:
        se minimiza el coste TOTAL, de modo que un conflicto se resuelve
        mirando el conjunto completo (el goloso puede bloquear con una
        unión barata otra combinación globalmente mejor).

        Implementación: matriz dispersa n×2n donde las columnas 0..n-1 son
        los sucesores reales (coste del candidato) y las columnas n..2n-1
        son "no unir" (una columna dummy por tracklet con coste
        `coste_no_union`). El emparejamiento perfecto de filas siempre
        existe gracias a los dummies; las filas asignadas a su dummy quedan
        sin continuación.
        """
        if not candidatos or n == 0:
            return {}
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import min_weight_full_bipartite_matching

        filas = [i for _, i, _ in candidatos] + list(range(n))
        columnas = [j for _, _, j in candidatos] + [n + i for i in range(n)]
        costes = [c for c, _, _ in candidatos] + [self.params.coste_no_union] * n
        matriz = csr_matrix((costes, (filas, columnas)), shape=(n, 2 * n))
        idx_filas, idx_cols = min_weight_full_bipartite_matching(matriz)
        return {i: j for i, j in zip(idx_filas, idx_cols) if j < n}
