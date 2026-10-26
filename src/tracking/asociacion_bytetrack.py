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
    umbral_emparejamiento: float = 0.995
    # Si es True, se le dice a ByteTrack el fps EFECTIVO del caché
    # (fps/sample) en vez del fps del vídeo. Es lo físicamente correcto:
    # entre dos frames del caché pasa `sample` veces más tiempo, y su
    # filtro de Kalman necesita saberlo.
    usar_fps_efectivo: bool = True
    # Frames seguidos que una detección debe verse para abrir identidad.
    # Sube la pureza a costa de perder apariciones cortas.
    min_frames_consecutivos: int = 1

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosByteTrack":
        if not d:
            return cls()
        conocidos = {c: d[c] for c in cls.__dataclass_fields__ if c in d}
        return cls(**conocidos)


@dataclass
class ParametrosCosteColor:
    """Término de COLOR en la asociación (flag `tracking.coste_color`, docs/diagnostico_22oct_g.md).

    APAGADO por defecto. Encendido, el coste de emparejar una pista con una detección pasa a ser el
    de ByteTrack (1 − IoU, fusionado con la confianza) + `lambda_rel` · d / sep, donde d es la
    distancia entre el MODELO de color de la pista y la feature de la detección, y sep la distancia
    entre los prototipos A y B del partido. Si d / sep > `umbral_rel`, no se pueden emparejar.

    Por qué relativo a sep: un número en unidades de histograma no viaja entre partidos (lo enseñó
    `dist_max_prototipo`, CLAUDE.md); lo que separa a dos equipos sí es una escala del problema.

    El color de un recorte SOLAPADO es una mezcla de dos camisetas: en esos frames (IoU >
    `iou_solape` con otra caja) el modelo de la pista no se actualiza y el término no se usa.
    """

    activo: bool = False
    lambda_rel: float = 0.5
    umbral_rel: float = float("inf")
    alfa: float = 0.2  # media móvil exponencial del modelo de color de la pista
    iou_solape: float = 0.1
    # SOLO para el control del diagnóstico: permuta los vectores de color entre las detecciones
    # del mismo frame. Si el término mejora igual, la mejora no viene del color.
    control_permutar_semilla: int | None = None

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosCosteColor":
        if not d:
            return cls()
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


def _iou_maximo(cajas: np.ndarray) -> np.ndarray:
    """Para cada caja, el IoU máximo con cualquier OTRA caja del frame."""
    if len(cajas) < 2:
        return np.zeros(len(cajas))
    x1 = np.maximum(cajas[:, None, 0], cajas[None, :, 0])
    y1 = np.maximum(cajas[:, None, 1], cajas[None, :, 1])
    x2 = np.minimum(cajas[:, None, 2], cajas[None, :, 2])
    y2 = np.minimum(cajas[:, None, 3], cajas[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = (cajas[:, 2] - cajas[:, 0]) * (cajas[:, 3] - cajas[:, 1])
    iou = inter / (area[:, None] + area[None, :] - inter + 1e-9)
    np.fill_diagonal(iou, 0.0)
    return iou.max(axis=1)


def asociar_con_bytetrack(
    cache: list[dict],
    fps: float,
    sample: int,
    params: ParametrosByteTrack | None = None,
    colores: dict | None = None,
    separacion: float | None = None,
    params_color: ParametrosCosteColor | None = None,
) -> list[list[Tracklet]]:
    """Identidades de ByteTrack sobre las detecciones ya cacheadas.

    Args:
        cache: entradas {"frame_idx", "t", "dets"} con
            dets = [(mx, my, x1, y1, x2, y2, conf), ...]. (mx, my) está en
            METROS y (x1..y2) en píxeles.
        fps: fps del vídeo original.
        sample: 1 de cada `sample` frames está en el caché.
        params: ver ParametrosByteTrack.
        colores, separacion, params_color: solo con el término de color encendido
            (`ParametrosCosteColor`): la caché de color {(frame, det): feature} y ‖A − B‖.

    Returns:
        Lista de identidades en el formato del resto del pipeline: cada
        identidad es una lista de Tracklet (aquí siempre uno, porque
        ByteTrack ya entrega la identidad entera; el cosido posterior es
        el que agrupa varios).
    """
    import supervision as sv

    params = params or ParametrosByteTrack()
    fps_efectivo = fps / sample if params.usar_fps_efectivo else fps
    # ⚠️ La librería NO usa `lost_track_buffer` como número de frames:
    # calcula `max_time_lost = int(frame_rate / 30 * lost_track_buffer)`.
    # Multiplicarlo aquí por el fps efectivo lo escalaba DOS veces, y la
    # memoria real se quedaba en 4 frames (0,5 s) cuando se pedían 2 s.
    # Despejando, para una memoria de T segundos hace falta T · 30,
    # independientemente del frame_rate.
    buffer_frames = max(1, int(round(params.buffer_perdido_s * 30)))

    with warnings.catch_warnings():
        # La 0.28 avisa de la deprecación en cada construcción; el aviso
        # ya está explicado en el docstring del módulo.
        warnings.simplefilter("ignore")
        tracker = sv.ByteTrack(
            track_activation_threshold=params.umbral_activacion,
            lost_track_buffer=buffer_frames,
            minimum_matching_threshold=params.umbral_emparejamiento,
            frame_rate=max(1, int(round(fps_efectivo))),
            minimum_consecutive_frames=params.min_frames_consecutivos,
        )

    con_color = params_color is not None and params_color.activo
    if con_color and (not colores or not separacion):
        raise ValueError(
            "El término de color necesita la caché de color y la separación A−B"
        )
    if con_color:
        from supervision.tracker.byte_tracker import matching

        from src.team_classification.color_classifier import _solo_hs

        iou_original = matching.iou_distance
        modelos: dict[int, np.ndarray] = {}  # {track_id externo: modelo de color}
        rng = (
            np.random.default_rng(int(params_color.control_permutar_semilla))
            if params_color.control_permutar_semilla is not None
            else None
        )

    # {track_id: [(t, pos_m, det_idx, frame_idx)]}
    observaciones: dict[int, list[tuple]] = {}
    for entrada in cache:
        dets = entrada["dets"]
        if not dets:
            continue
        if con_color:
            cajas = np.array([d[2:6] for d in dets], dtype=float)
            iou_max = _iou_maximo(cajas)
            feats = [
                (
                    _solo_hs(colores[(entrada["frame_idx"], j)])
                    if (entrada["frame_idx"], j) in colores
                    else None
                )
                for j in range(len(dets))
            ]
            if rng is not None:
                feats = [feats[k] for k in rng.permutation(len(feats))]

            def iou_con_color(
                atracks, btracks, _cajas=cajas, _feats=feats, _iou=iou_max
            ):
                base = iou_original(atracks, btracks)
                if base.size == 0 or isinstance(atracks[0], np.ndarray):
                    return base
                # solo entre PISTAS y DETECCIONES de este frame (las detecciones aún no
                # tienen id): `remove_duplicate_tracks` también llama aquí con dos pistas
                if any(
                    b.external_track_id != b.external_id_counter.NO_ID for b in btracks
                ):
                    return base
                base = base.copy()
                for bi, b in enumerate(btracks):
                    j = int(np.argmin(np.abs(_cajas - np.asarray(b.tlbr)).sum(axis=1)))
                    if _feats[j] is None or _iou[j] > params_color.iou_solape:
                        continue  # caja solapada o sin color: el coste de siempre
                    for ai, a in enumerate(atracks):
                        m = modelos.get(int(a.external_track_id))
                        if m is None:
                            continue
                        d = float(np.linalg.norm(m - _feats[j])) / separacion
                        if d > params_color.umbral_rel:
                            base[ai, bi] = 2.0  # la puerta: no se pueden emparejar
                        else:
                            base[ai, bi] += params_color.lambda_rel * d
                return base

            matching.iou_distance = iou_con_color
        detecciones = sv.Detections(
            xyxy=np.array([[d[2], d[3], d[4], d[5]] for d in dets], dtype=np.float32),
            confidence=np.array([d[6] for d in dets], dtype=np.float32),
            class_id=np.zeros(len(dets), dtype=int),
            # El índice viaja CON la detección: así se recupera exacto al
            # otro lado, sin tener que reconocer la caja por su geometría.
            data={"det_idx": np.arange(len(dets))},
        )
        try:
            seguidas = tracker.update_with_detections(detecciones)
        finally:
            if con_color:
                matching.iou_distance = iou_original
        for track_id, det_idx in zip(
            seguidas.tracker_id, seguidas.data.get("det_idx", [])
        ):
            if track_id is None:
                continue
            if con_color:
                # el modelo de la pista solo aprende de recortes LIMPIOS, con peso 1 − IoU
                j = int(det_idx)
                if feats[j] is not None and iou_max[j] <= params_color.iou_solape:
                    w = params_color.alfa * (1.0 - float(iou_max[j]))
                    previo = modelos.get(int(track_id))
                    modelos[int(track_id)] = (
                        feats[j] if previo is None else (1 - w) * previo + w * feats[j]
                    )
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
