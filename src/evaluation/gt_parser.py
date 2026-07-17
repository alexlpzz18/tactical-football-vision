"""Parser del ground truth de tracking en formato "CVAT for video 1.1".

El XML contiene <track> con identidad persistente; cada track tiene <box>
por frame (frames LOCALES 0..N-1 de la tarea de CVAT). Labels: 'player'
(con atributo 'team': A / B / portero_A / portero_B) y 'referee'.

Para evaluar en metros, el PIE de cada caja GT (punto medio del borde
inferior) se proyecta con la misma homografía que usa el pipeline.
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.evaluation.modelo import Observacion, PorFrame

logger = logging.getLogger(__name__)


@dataclass
class CajaGT:
    """Una caja del GT en un frame local de CVAT (píxeles)."""

    frame_local: int
    xtl: float
    ytl: float
    xbr: float
    ybr: float
    team: str | None = None

    @property
    def pie(self) -> tuple[float, float]:
        """Punto de apoyo del jugador: centro del borde inferior de la caja."""
        return ((self.xtl + self.xbr) / 2.0, self.ybr)


@dataclass
class TrackGT:
    """Un track del GT: identidad persistente con sus cajas por frame."""

    track_id: int
    label: str  # 'player' o 'referee'
    cajas: list[CajaGT] = field(default_factory=list)

    @property
    def team(self) -> str | None:
        """Equipo del track (el atributo es constante a lo largo del track)."""
        for caja in self.cajas:
            if caja.team is not None:
                return caja.team
        return None


def parsear_cvat(ruta_xml: str | Path) -> list[TrackGT]:
    """Lee un annotations.xml de CVAT for video 1.1 y devuelve los tracks.

    Las cajas con outside="1" se descartan (en CVAT marcan que el objeto ya
    no está visible; no son observaciones reales).

    Raises:
        FileNotFoundError: si el XML no existe.
        ValueError: si el XML no contiene ningún <track>.
    """
    ruta_xml = Path(ruta_xml)
    if not ruta_xml.exists():
        raise FileNotFoundError(
            f"No existe el ground truth: {ruta_xml}. "
            "Cópialo desde Google Drive a data/annotations/ground_truth_tracking/."
        )

    raiz = ET.parse(ruta_xml).getroot()
    tracks = []
    for nodo_track in raiz.findall("track"):
        track = TrackGT(
            track_id=int(nodo_track.get("id")),
            label=nodo_track.get("label"),
        )
        for nodo_box in nodo_track.findall("box"):
            if nodo_box.get("outside") == "1":
                continue
            team = None
            for attr in nodo_box.findall("attribute"):
                if attr.get("name") == "team":
                    team = attr.text
            track.cajas.append(
                CajaGT(
                    frame_local=int(nodo_box.get("frame")),
                    xtl=float(nodo_box.get("xtl")),
                    ytl=float(nodo_box.get("ytl")),
                    xbr=float(nodo_box.get("xbr")),
                    ybr=float(nodo_box.get("ybr")),
                    team=team,
                )
            )
        tracks.append(track)

    if not tracks:
        raise ValueError(f"El XML {ruta_xml} no contiene ningún <track>.")

    logger.info(
        "GT parseado: %d tracks (%s)",
        len(tracks),
        ", ".join(f"{t.label}#{t.track_id}" for t in tracks[:5]) + "...",
    )
    return tracks


def proyectar_punto(x: float, y: float, homografia: np.ndarray) -> np.ndarray:
    """Proyecta un punto en píxeles a metros con la homografía 3x3."""
    p = homografia @ np.array([x, y, 1.0])
    return p[:2] / p[2]


def gt_a_por_frame(
    tracks: list[TrackGT],
    homografia: np.ndarray,
    frame_offset: int,
    paso_gt: int,
) -> PorFrame:
    """Convierte los tracks GT al formato común de evaluación.

    Proyecta el pie de cada caja a metros y traduce el frame local de CVAT
    a frame global del vídeo: frame_global = frame_offset + paso_gt * local.

    Args:
        tracks: salida de parsear_cvat().
        homografia: matriz 3x3 píxel→metros (la misma del pipeline).
        frame_offset: frame global del vídeo que corresponde al local 0.
        paso_gt: el GT tiene 1 de cada `paso_gt` frames reales.

    Returns:
        {frame_global: [Observacion, ...]}
    """
    por_frame: PorFrame = {}
    for track in tracks:
        for caja in track.cajas:
            frame_global = frame_offset + paso_gt * caja.frame_local
            pos = proyectar_punto(*caja.pie, homografia)
            por_frame.setdefault(frame_global, []).append(
                Observacion(
                    obj_id=track.track_id,
                    pos=pos,
                    team=caja.team if caja.team is not None else track.team,
                    label=track.label,
                )
            )
    return por_frame
