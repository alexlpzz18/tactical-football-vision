"""Asociación en METROS con coste mixto geometría + apariencia.

El "camino B" completo: sustituye a ByteTrack como etapa de asociación.
Frente a lo que había:

- ByteTrack empareja por **IoU de cajas en píxeles**, la magnitud que deja
  de distinguir justo cuando dos cuerpos se solapan.
- Aquí se empareja por **distancia en metros** dentro de un radio físico,
  y la apariencia desempata — con más peso cuanto menos fiable es la
  geometría (ver `coste_asociacion.py`).

La diferencia práctica está en la re-entrada: cuando un track vuelve tras
perderse, la geometría ya no dice casi nada (a 3 s el radio es de 25 m,
donde caben varios jugadores) y es el embedding quien decide a quién
pertenece. Medido: el 42 % de las re-entradas ocurre con recortes de
menos de 20 px, donde además el color da 0,000 separando equipos.
"""

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.tracking.coste_asociacion import (
    IncertidumbrePosicion,
    ParametrosCosteMixto,
    coste,
)
from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosAsociacionApariencia:
    """Parámetros de la etapa, en unidades físicas."""

    # Cuánto se conserva un track sin verlo antes de darlo por muerto.
    buffer_perdido_s: float = 1.5
    # Detecciones consecutivas para ABRIR identidad. Con un detector bueno
    # mata fragmentos espurios sin perder cobertura (medido: quimeras 7→3).
    min_frames_consecutivos: int = 2
    # Confianza mínima para abrir; por debajo solo continúa lo existente.
    umbral_activacion: float = 0.10
    # Observaciones cuyo embedding forma la firma del track. Una sola es
    # ruido; demasiadas y la firma no sigue los cambios de iluminación.
    ventana_firma: int = 8

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosAsociacionApariencia":
        return cls(**(d or {}))


class _Track:
    """Un track vivo: su tracklet y su firma de apariencia."""

    def __init__(self, tid, t, pos, det_idx, frame_idx, emb, ventana):
        self.tracklet = Tracklet(tid, t, pos, det_idx, frame_idx)
        self.embs = [emb] if emb is not None else []
        self.ventana = ventana
        self.confirmado = False
        self.n_obs = 1

    def anadir(self, t, pos, det_idx, frame_idx, emb):
        self.tracklet.anadir(t, pos, det_idx, frame_idx)
        self.n_obs += 1
        if emb is not None:
            self.embs.append(emb)
            if len(self.embs) > self.ventana:
                self.embs.pop(0)

    @property
    def firma(self):
        """Media de los últimos embeddings. La media, y no el último,
        porque un recorte suelto puede estar ocluido o borroso."""
        return np.mean(self.embs, axis=0) if self.embs else None


def asociar_con_apariencia(
    cache: list[dict],
    fps: float,
    sample: int,
    embeddings: dict | None = None,
    params: ParametrosAsociacionApariencia | None = None,
    params_coste: ParametrosCosteMixto | None = None,
    incert: IncertidumbrePosicion | None = None,
) -> list[list[Tracklet]]:
    """Asocia las detecciones del caché en identidades.

    Args:
        cache: entradas {"frame_idx", "t", "dets"} (ver cache_io).
        embeddings: {(frame_idx, det_idx): vector} o None (solo geometría).

    Returns:
        Identidades, en el mismo formato que devuelve el perfil bytetrack.
    """
    p = params or ParametrosAsociacionApariencia()
    pc = params_coste or ParametrosCosteMixto()
    inc = incert or IncertidumbrePosicion()

    vivos: list[_Track] = []
    terminados: list[_Track] = []
    siguiente_id = 1

    for entrada in cache:
        t = float(entrada["t"])
        frame = int(entrada["frame_idx"])
        dets = entrada["dets"]

        # Enterrar los que llevan demasiado sin verse
        aun = []
        for tr in vivos:
            if t - tr.tracklet.ts[-1] > p.buffer_perdido_s:
                terminados.append(tr)
            else:
                aun.append(tr)
        vivos = aun

        if not dets:
            continue

        emb_det = [(embeddings or {}).get((frame, i)) for i in range(len(dets))]

        if vivos:
            M = np.full((len(vivos), len(dets)), np.inf)
            for r, tr in enumerate(vivos):
                dt = t - tr.tracklet.ts[-1]
                pred = tr.tracklet.predecir(t)
                firma = tr.firma
                for c, d in enumerate(dets):
                    M[r, c] = coste(pred, (d[0], d[1]), dt, firma, emb_det[c], pc, inc)
            # El húngaro no admite inf: se sustituye por un valor grande y
            # se descartan después los emparejamientos que eran imposibles.
            finito = np.where(np.isinf(M), 1e6, M)
            filas, cols = linear_sum_assignment(finito)
            asignadas = set()
            for r, c in zip(filas, cols):
                if not np.isfinite(M[r, c]):
                    continue
                d = dets[c]
                vivos[r].anadir(t, (d[0], d[1]), c, frame, emb_det[c])
                asignadas.add(c)
        else:
            asignadas = set()

        # Detecciones sin dueño: abren track nuevo si la confianza da
        for c, d in enumerate(dets):
            if c in asignadas or d[6] < p.umbral_activacion:
                continue
            vivos.append(
                _Track(
                    siguiente_id,
                    t,
                    (d[0], d[1]),
                    c,
                    frame,
                    emb_det[c],
                    p.ventana_firma,
                )
            )
            siguiente_id += 1

    terminados.extend(vivos)
    identidades = [
        [tr.tracklet] for tr in terminados if tr.n_obs >= p.min_frames_consecutivos
    ]
    n_dets = sum(len(e["dets"]) for e in cache)
    n_asig = sum(len(i[0].pos) for i in identidades)
    logger.info(
        "Asociación con apariencia: %d identidades, %d/%d detecciones "
        "asignadas (%d %%)",
        len(identidades),
        n_asig,
        n_dets,
        round(100 * n_asig / max(n_dets, 1)),
    )
    return identidades
