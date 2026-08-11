"""ByteTrack como etapa de ASOCIACIÓN del pipeline en metros.

Por qué está aquí (banco del 10-ago-2026, `scripts/comparar_tracker.py`):
sobre NUESTRAS mismas detecciones y NUESTRO mismo banco, ByteTrack tal
cual bate a nuestro tracker artesanal en todo lo que mide la calidad de
una identidad — IDF1 0,406 vs 0,334, tasa de IDSW 0,165 vs 0,339 y, sobre
todo, **5 quimeras frente a 24**.

La lección que ordena este módulo: nuestro tracker producía 52
identidades para 23 personas y ByteTrack 237, y durante meses leímos esa
diferencia como una ventaja nuestra. Era al revés. Fragmentar es un error
RECUPERABLE (dos trozos del mismo jugador se pueden coser después);
mezclar dos jugadores en una identidad NO lo es. El número de identidades
es un proxy; la pureza es la métrica.

Qué NO cambia al adoptarlo: ByteTrack decide identidades emparejando
cajas en PÍXELES, pero las posiciones que consume el resto del sistema
siguen siendo las de siempre, en METROS, proyectadas con nuestra
homografía. Aquí solo cambia quién decide qué detección es quién.

Nota sobre la librería: se usa la implementación de `supervision`, la
misma que ya estaba en el pipeline legacy del repo. Está deprecada desde
la 0.28 (avisa de que migremos a `ByteTrackTracker` del paquete
`trackers`) pero funciona, y no se instala nada nuevo: `boxmot` está
vetado en CLAUDE.md porque rompió el entorno.
"""

import logging
import warnings
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosByteTrack:
    """Los parámetros de ByteTrack, expresados en unidades físicas.

    La librería los pide en frames, que no significan lo mismo según el
    submuestreo del caché. Aquí se declaran en segundos y se traducen,
    que es lo que permite reusar la misma config en cámaras distintas.
    """

    # Confianza mínima para ABRIR una identidad nueva (las detecciones
    # por debajo aún sirven para continuar una existente: esa es
    # justamente la idea de ByteTrack). Medido: bajarlo de 0,25 a 0,10
    # sube la accuracy de equipos (0,655 → 0,674) sin coste.
    umbral_activacion: float = 0.10
    # Cuánto se conserva una identidad que ha dejado de verse.
    buffer_perdido_s: float = 2.0
    # OJO con el nombre que usa la librería: NO es un IoU mínimo, es la
    # DISTANCIA máxima (1 − IoU) admitida al emparejar, así que subirlo
    # lo vuelve MÁS permisivo. Medido en el tramo de validación:
    #
    #   0,50 → 2.125 identidades, 65 % de detecciones usadas, cob. 0,443
    #   0,80 → 262 identidades,   89 %,                        cob. 0,519
    #   0,98 → 183 identidades,   93 %,                        cob. 0,549
    #
    # El default de la librería (0,8) descarta el 11 % de nuestras
    # detecciones: sus cajas son pequeñas (jugadores de 15-40 px) y el
    # IoU entre frames consecutivos cae mucho más rápido que en los
    # vídeos con los que se calibró ByteTrack.
    umbral_emparejamiento: float = 0.98
    # Si es True, se le dice a ByteTrack el fps EFECTIVO del caché
    # (fps/sample) en vez del fps del vídeo. Es lo físicamente correcto:
    # entre dos frames del caché pasa `sample` veces más tiempo, y su
    # filtro de Kalman necesita saberlo.
    usar_fps_efectivo: bool = True

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosByteTrack":
        if not d:
            return cls()
        conocidos = {c: d[c] for c in cls.__dataclass_fields__ if c in d}
        return cls(**conocidos)


def asociar_con_bytetrack(
    cache: list[dict],
    fps: float,
    sample: int,
    params: ParametrosByteTrack | None = None,
) -> list[list[Tracklet]]:
    """Identidades de ByteTrack sobre las detecciones ya cacheadas.

    Args:
        cache: entradas {"frame_idx", "t", "dets"} con
            dets = [(mx, my, x1, y1, x2, y2, conf), ...]. (mx, my) está en
            METROS y (x1..y2) en píxeles.
        fps: fps del vídeo original.
        sample: 1 de cada `sample` frames está en el caché.
        params: ver ParametrosByteTrack.

    Returns:
        Lista de identidades en el formato del resto del pipeline: cada
        identidad es una lista de Tracklet (aquí siempre uno, porque
        ByteTrack ya entrega la identidad entera; el cosido posterior es
        el que agrupa varios).
    """
    import supervision as sv

    params = params or ParametrosByteTrack()
    fps_efectivo = fps / sample if params.usar_fps_efectivo else fps
    buffer_frames = max(1, int(round(params.buffer_perdido_s * fps_efectivo)))

    with warnings.catch_warnings():
        # La 0.28 avisa de la deprecación en cada construcción; el aviso
        # ya está explicado en el docstring del módulo.
        warnings.simplefilter("ignore")
        tracker = sv.ByteTrack(
            track_activation_threshold=params.umbral_activacion,
            lost_track_buffer=buffer_frames,
            minimum_matching_threshold=params.umbral_emparejamiento,
            frame_rate=max(1, int(round(fps_efectivo))),
        )

    # {track_id: [(t, pos_m, det_idx, frame_idx)]}
    observaciones: dict[int, list[tuple]] = {}
    for entrada in cache:
        dets = entrada["dets"]
        if not dets:
            continue
        detecciones = sv.Detections(
            xyxy=np.array([[d[2], d[3], d[4], d[5]] for d in dets], dtype=np.float32),
            confidence=np.array([d[6] for d in dets], dtype=np.float32),
            class_id=np.zeros(len(dets), dtype=int),
            # El índice viaja CON la detección: así se recupera exacto al
            # otro lado, sin tener que reconocer la caja por su geometría.
            data={"det_idx": np.arange(len(dets))},
        )
        seguidas = tracker.update_with_detections(detecciones)
        for track_id, det_idx in zip(
            seguidas.tracker_id, seguidas.data.get("det_idx", [])
        ):
            if track_id is None:
                continue
            d = dets[int(det_idx)]
            observaciones.setdefault(int(track_id), []).append(
                (
                    entrada["t"],
                    np.array([d[0], d[1]]),
                    int(det_idx),
                    entrada["frame_idx"],
                )
            )

    identidades = []
    for track_id, obs in sorted(observaciones.items()):
        obs.sort(key=lambda o: o[0])
        t0, pos0, det0, frame0 = obs[0]
        tracklet = Tracklet(track_id, t0, pos0, det0, frame0)
        for t, pos, det_idx, frame_idx in obs[1:]:
            tracklet.anadir(t, pos, det_idx, frame_idx)
        identidades.append([tracklet])

    asignadas = sum(len(o) for o in observaciones.values())
    totales = sum(len(e["dets"]) for e in cache)
    logger.info(
        "ByteTrack: %d identidades, %d/%d detecciones asignadas (%.0f %%)",
        len(identidades),
        asignadas,
        totales,
        100 * asignadas / totales if totales else 0,
    )
    return identidades
