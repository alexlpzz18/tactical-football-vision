"""Etapa A del tracking en metros: tracklets conservadores.

Migración fiel del código validado en Colab (briefing, sección 2.1).
Validación de referencia: 309 tracklets puros sobre el tramo min 5-6.

Idea central: asociamos detecciones a tracks POR DISTANCIA EN METROS (no en
píxeles), con un radio físicamente plausible, y con una regla anti-robo:
si una asociación es ambigua (hay otra opción casi igual de buena), NO
asociamos y dejamos que el tracklet se corte. Preferimos fragmentar limpio
a contaminar una identidad — la Etapa B (cosido) reunirá los fragmentos.
"""

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

logger = logging.getLogger(__name__)


@dataclass
class ParametrosEtapaA:
    """Parámetros físicos de la Etapa A (valores validados como defaults).

    En producción se cargan desde configs/tracking.yaml (clave 'etapa_a');
    los defaults existen para tests y uso exploratorio.
    """

    v_max: float = 7.0  # m/s máximos de un jugador
    margen: float = 0.8  # m de ruido de detección/proyección
    ambig_factor: float = 0.7  # anti-robo: 2ª opción a <70% de dist extra → cortar
    max_gap_dts: float = 3.0  # cierre: sin verse > max_gap_dts * dt segundos
    min_frames: int = 3  # filtro final: tracklets con menos frames se descartan

    @classmethod
    def desde_dict(cls, d: dict) -> "ParametrosEtapaA":
        """Crea los parámetros desde un dict (p. ej. el YAML de config)."""
        return cls(**d)


class Tracklet:
    """Fragmento de trayectoria de UN jugador, en coordenadas de campo (metros).

    Guarda, frame a frame, el tiempo, la posición y qué detección del caché
    le corresponde (imprescindible para pintar sin bugs y extraer colores).
    """

    def __init__(
        self,
        tid: int,
        t: float,
        pos: np.ndarray,
        det_idx: int,
        frame_idx: int,
    ):
        self.id = tid
        self.ts: list[float] = [t]
        self.pos: list[np.ndarray] = [np.array(pos)]
        # (frame_idx global, índice de la detección dentro de ese frame)
        self.det_idxs: list[tuple[int, int]] = [(frame_idx, det_idx)]
        # Velocidad suavizada (media móvil exponencial 0.6/0.4)
        self.vel = np.zeros(2)

    def predecir(self, t: float) -> np.ndarray:
        """Posición esperada en el instante t asumiendo velocidad constante."""
        return self.pos[-1] + self.vel * (t - self.ts[-1])

    def anadir(self, t: float, pos: np.ndarray, det_idx: int, frame_idx: int) -> None:
        """Añade una observación nueva y actualiza la velocidad suavizada."""
        pos = np.array(pos)
        dt_real = t - self.ts[-1]
        if dt_real > 0:
            v = (pos - self.pos[-1]) / dt_real
            self.vel = 0.6 * self.vel + 0.4 * v
        self.ts.append(t)
        self.pos.append(pos)
        self.det_idxs.append((frame_idx, det_idx))

    def __len__(self) -> int:
        return len(self.ts)

    def __repr__(self) -> str:
        return (
            f"Tracklet(id={self.id}, frames={len(self.ts)}, "
            f"t0={self.ts[0]:.2f}, t1={self.ts[-1]:.2f})"
        )


class ConservativeTracker:
    """Etapa A: construye tracklets conservadores a partir del caché.

    Asociación por frame: matriz de distancias predicción↔detecciones en
    METROS + algoritmo húngaro, con radio físico y regla anti-robo.
    """

    def __init__(self, params: ParametrosEtapaA | None = None):
        self.params = params or ParametrosEtapaA()

    def procesar(self, cache: list[dict], fps: float, sample: int) -> list[Tracklet]:
        """Corre la Etapa A sobre el caché de detecciones.

        Args:
            cache: lista de entradas {"frame_idx", "t", "dets"} (ver cache_io).
            fps: fps del vídeo original.
            sample: el caché tiene 1 de cada `sample` frames.

        Returns:
            Tracklets con al menos `min_frames` observaciones, puros
            (sin mezclar jugadores) por construcción conservadora.
        """
        p = self.params
        dt = sample / fps
        # Radio de búsqueda físicamente plausible entre dos frames del caché
        radio = p.v_max * dt + p.margen
        max_gap = p.max_gap_dts * dt

        activos: list[Tracklet] = []
        cerrados: list[Tracklet] = []
        next_id = 1

        for entry in cache:
            t = entry["t"]
            dets = [(d[0], d[1]) for d in entry["dets"]]  # (mx, my) en metros

            # Cerrar tracks que llevan demasiado tiempo sin verse
            aun = []
            for tr in activos:
                (cerrados if t - tr.ts[-1] > max_gap else aun).append(tr)
            activos = aun

            if not dets:
                continue

            det_arr = np.array(dets)
            asignadas: set[int] = set()

            if activos:
                pred = np.array([tr.predecir(t) for tr in activos])
                # Matriz de distancias en metros: filas=tracks, columnas=dets
                dist = np.linalg.norm(pred[:, None, :] - det_arr[None, :, :], axis=2)
                filas, cols = linear_sum_assignment(dist)
                for r, c in zip(filas, cols):
                    if dist[r, c] > radio:
                        continue
                    # Regla anti-robo: si la 2ª mejor opción (en la fila o en
                    # la columna) está a menos de ambig_factor*radio de
                    # distancia extra, la asociación es ambigua → NO asociar.
                    # Conservador: cortar antes que arriesgar un robo de ID.
                    fila = np.sort(dist[r, :])
                    col = np.sort(dist[:, c])
                    ambigua = (
                        len(fila) > 1 and fila[1] < dist[r, c] + p.ambig_factor * radio
                    ) or (len(col) > 1 and col[1] < dist[r, c] + p.ambig_factor * radio)
                    if ambigua:
                        continue
                    activos[r].anadir(t, det_arr[c], c, entry["frame_idx"])
                    asignadas.add(c)

            # Cada detección no asignada abre un tracklet nuevo
            for c in range(len(dets)):
                if c not in asignadas:
                    activos.append(
                        Tracklet(next_id, t, det_arr[c], c, entry["frame_idx"])
                    )
                    next_id += 1

        cerrados.extend(activos)
        resultado = [tr for tr in cerrados if len(tr.ts) >= p.min_frames]
        logger.info(
            "Etapa A: %d tracklets creados, %d tras filtrar < %d frames",
            len(cerrados),
            len(resultado),
            p.min_frames,
        )
        return resultado
