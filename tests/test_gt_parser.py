"""Tests del parser de ground truth CVAT con un XML mínimo de juguete."""

import numpy as np
import pytest

from src.evaluation.alineacion import distancia_media_gt_cache, frames_comunes
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat, proyectar_punto

# XML de juguete: 2 tracks (player equipo A y referee), 2 frames.
# El player tiene una tercera caja con outside="1" que debe descartarse.
XML_JUGUETE = """<?xml version="1.0" encoding="utf-8"?>
<annotations>
  <version>1.1</version>
  <meta><task><name>juguete</name><size>3</size></task></meta>
  <track id="0" label="player" source="manual">
    <box frame="0" keyframe="1" outside="0" occluded="0"
         xtl="100.0" ytl="200.0" xbr="120.0" ybr="240.0" z_order="0">
      <attribute name="team">A</attribute>
    </box>
    <box frame="1" keyframe="1" outside="0" occluded="0"
         xtl="110.0" ytl="200.0" xbr="130.0" ybr="240.0" z_order="0">
      <attribute name="team">A</attribute>
    </box>
    <box frame="2" keyframe="1" outside="1" occluded="0"
         xtl="120.0" ytl="200.0" xbr="140.0" ybr="240.0" z_order="0">
      <attribute name="team">A</attribute>
    </box>
  </track>
  <track id="1" label="referee" source="manual">
    <box frame="0" keyframe="1" outside="0" occluded="0"
         xtl="300.0" ytl="100.0" xbr="316.0" ybr="150.0" z_order="0"/>
  </track>
</annotations>
"""


@pytest.fixture
def ruta_xml(tmp_path):
    ruta = tmp_path / "annotations.xml"
    ruta.write_text(XML_JUGUETE)
    return ruta


def test_parsea_tracks_y_labels(ruta_xml):
    tracks = parsear_cvat(ruta_xml)
    assert len(tracks) == 2
    assert tracks[0].label == "player"
    assert tracks[0].team == "A"
    assert tracks[1].label == "referee"
    assert tracks[1].team is None


def test_descarta_cajas_outside(ruta_xml):
    """La caja con outside='1' no es una observación real."""
    tracks = parsear_cvat(ruta_xml)
    assert len(tracks[0].cajas) == 2  # la tercera (outside) se descarta
    assert [c.frame_local for c in tracks[0].cajas] == [0, 1]


def test_pie_de_la_caja(ruta_xml):
    """El pie es el punto medio del borde inferior."""
    tracks = parsear_cvat(ruta_xml)
    assert tracks[0].cajas[0].pie == (110.0, 240.0)


def test_proyeccion_con_homografia():
    """Con una homografía de escala 0.1, los píxeles pasan a 'metros'."""
    escala = np.diag([0.1, 0.1, 1.0])
    pos = proyectar_punto(110.0, 240.0, escala)
    np.testing.assert_allclose(pos, [11.0, 24.0])


def test_gt_a_por_frame_traduce_frames(ruta_xml):
    """frame_global = offset + paso * frame_local, con posiciones en metros."""
    tracks = parsear_cvat(ruta_xml)
    escala = np.diag([0.1, 0.1, 1.0])
    por_frame = gt_a_por_frame(tracks, escala, frame_offset=7500, paso_gt=15)
    assert set(por_frame) == {7500, 7515}
    # Frame 7500: player + referee; frame 7515: solo player
    assert len(por_frame[7500]) == 2
    assert len(por_frame[7515]) == 1
    obs_player = [o for o in por_frame[7500] if o.label == "player"][0]
    assert obs_player.obj_id == 0
    assert obs_player.team == "A"
    np.testing.assert_allclose(obs_player.pos, [11.0, 24.0])


def test_frames_comunes(ruta_xml):
    tracks = parsear_cvat(ruta_xml)
    escala = np.diag([0.1, 0.1, 1.0])
    por_frame = gt_a_por_frame(tracks, escala, frame_offset=7500, paso_gt=15)
    # El caché tiene paso 3: 7500, 7503, ..., solo 7500 y 7515 son comunes
    frames_cache = list(range(7500, 7530, 3))
    assert frames_comunes(por_frame, frames_cache) == [7500, 7515]


def test_frames_comunes_vacio_lanza_error(ruta_xml):
    tracks = parsear_cvat(ruta_xml)
    escala = np.diag([0.1, 0.1, 1.0])
    por_frame = gt_a_por_frame(tracks, escala, frame_offset=7500, paso_gt=15)
    with pytest.raises(ValueError, match="frames comunes"):
        frames_comunes(por_frame, [1, 2, 3])


def test_distancia_media_alineacion(ruta_xml):
    """Con detecciones exactamente sobre el GT, la distancia media es 0."""
    tracks = parsear_cvat(ruta_xml)
    escala = np.diag([0.1, 0.1, 1.0])
    por_frame = gt_a_por_frame(tracks, escala, frame_offset=7500, paso_gt=15)
    dets = {
        frame: np.array([obs.pos for obs in observaciones])
        for frame, observaciones in por_frame.items()
    }
    media = distancia_media_gt_cache(por_frame, dets, [7500, 7515])
    assert media == pytest.approx(0.0)


def test_xml_inexistente():
    with pytest.raises(FileNotFoundError):
        parsear_cvat("no_existe.xml")
