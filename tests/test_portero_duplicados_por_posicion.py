"""La puerta de duplicados del portero mira POSICIÓN, no solo frame.

21-sep-2026 (docs/baile_y_oclusion.md, BACKLOG 26). La id 420 del benjamín es
el portero de A (camiseta negra, un "1", dentro de su área): último hombre
0,97 y pisa el área el 100 %. Solo caía en la puerta de duplicados, porque el
69 % de sus frames ya los cubría un fragmento coronado DUDOSO (pisa 0,7,
último hombre 0,6). Pero en esos frames los dos estaban a más de 1,5 m: no eran
el mismo cuerpo, y el catálogo arbitral se lo llevaba a `otro` (el azul
eléctrico es el color de su camiseta negra en el histograma HS).
"""

import numpy as np

from src.campo_modelo import cargar_modelo
from src.team_classification.porteros import (
    ReglaPorteroUltimoHombre,
    _frames_nuevos,
    aplicar_regla_portero_ultimo_hombre,
)
from src.tracking.field_tracker import Tracklet


def _campo():
    return cargar_modelo("f7").con_dimensiones(62.0, 40.0)


def _quieta(x, y, frames, dt=0.12):
    """Identidad quieta en (x, y) presente exactamente en esos frames."""
    frames = list(frames)
    tr = Tracklet(1, frames[0] * dt, np.array([x, y]), 0, frames[0])
    for f in frames[1:]:
        tr.anadir(f * dt, np.array([x, y]), 0, f)
    return [tr]


def _coronar(identidades, equipos, **kwargs):
    return aplicar_regla_portero_ultimo_hombre(
        equipos,
        identidades,
        _campo(),
        {"A": -1},
        ReglaPorteroUltimoHombre(activo=True, **kwargs),
    )


def _caso_420():
    """Un fragmento grande a 12 m de la línea y el portero de verdad, más al fondo.

    Comparten los frames 200-300 pero a 8 m el uno del otro: no son el mismo cuerpo.
    """
    grande = _quieta(12.0, 20.0, range(0, 300))  # en el borde del área
    portero = _quieta(4.0, 20.0, range(200, 320))  # el más profundo en los suyos
    campo = _quieta(30.0, 20.0, range(0, 320))
    return [grande, portero, campo], {1: "A", 2: "otro", 3: "A"}


def test_el_portero_que_solo_comparte_frames_con_OTRA_persona_se_reclama():
    identidades, equipos = _caso_420()
    salida = _coronar(identidades, equipos)
    assert salida[2] == "portero_A", "el portero real se quedó en su etiqueta de color"
    assert salida[1] == "portero_A"  # el grande ya entraba
    assert salida[3] == "A"


def test_con_el_criterio_antiguo_solo_por_frame_se_quedaba_fuera():
    """El control: reproduce el fallo que se arregla."""
    identidades, equipos = _caso_420()
    salida = _coronar(identidades, equipos, dup_dist_m=0.0)
    assert salida[2] == "otro", "el control ya no reproduce el bug de la 420"


def test_un_duplicado_de_verdad_en_el_mismo_sitio_SIGUE_cayendo():
    """El mismo portero detectado dos veces: 0,3 m de diferencia, misma persona."""
    entero = _quieta(4.0, 20.0, range(0, 1000))
    duplicado = _quieta(4.3, 20.0, range(100, 460))
    campo = _quieta(30.0, 20.0, range(0, 1000))
    salida = _coronar([entero, duplicado, campo], {1: "otro", 2: "otro", 3: "A"})
    coronados = [k for k, v in salida.items() if str(v).startswith("portero_")]
    assert coronados == [1]


def test_la_puerta_de_ultimo_hombre_sigue_protegiendo_de_los_impostores():
    """Un jugador a 8 m del portero, presente a la vez, NO pasa a portero.

    Ya no lo frena la puerta de duplicados (está en otro sitio) pero sí la de
    último hombre: el portero está más al fondo en cada frame que comparten.
    """
    portero = _quieta(4.0, 20.0, range(0, 1000))
    defensa = _quieta(
        12.0, 20.0, range(0, 1000)
    )  # pisa el área con margen, pero no es el último
    campo = _quieta(30.0, 20.0, range(0, 1000))
    salida = _coronar([portero, defensa, campo], {1: "otro", 2: "A", 3: "A"})
    assert salida[1] == "portero_A"
    assert salida[2] == "A", "un defensa se coló de portero"


def test_el_umbral_de_distancia_es_un_parametro_y_manda():
    """A 8 m son personas distintas; con un umbral de 20 m serían el mismo cuerpo."""
    identidades, equipos = _caso_420()
    lejos = _coronar(identidades, equipos, dup_dist_m=20.0)
    assert lejos[2] == "otro"


def test_un_frame_con_DOS_personas_en_el_conjunto_es_duplicado_si_UNA_esta_cerca():
    """El conteo, aislado: basta una persona cerca; la otra, lejos, no lo hace nuevo."""
    conjunto = {5: [(4.0, 20.0), (12.0, 20.0)]}  # el portero y otro fragmento coronado
    assert _frames_nuevos({5: (4.3, 20.0)}, conjunto, 2.0) == 0  # duplicado del portero
    assert (
        _frames_nuevos({5: (8.0, 20.0)}, conjunto, 2.0) == 1
    )  # a 4 m de ambos: persona nueva
    assert _frames_nuevos({6: (4.0, 20.0)}, conjunto, 2.0) == 1  # frame sin nadie
