"""La verdad por caja a partir de las marcas de Alex (scripts/medir_arbitro_tono_brillo.py)."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "mat",
    Path(__file__).resolve().parent.parent / "scripts/medir_arbitro_tono_brillo.py",
)
mat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mat)


def test_verdad_de_caja():
    v = mat.verdad_de_caja
    assert (
        v("B", {"equipo_correcto": "arbitro"}, True) == "arbitro"
    )  # el árbitro pintado como B
    assert v("otro", None, True) == "arbitro"  # otro sin marcar, dentro del campo
    assert v("otro", None, False) is None  # otro fuera del campo: no cuenta
    assert v("A", None, True) == "jugador"  # sin marcar: la etiqueta se da por buena
    assert v("B", {"equipo_correcto": "A"}, True) == "jugador"
    assert v("A", {"equipo_correcto": "no_es_persona"}, True) is None
    assert (
        v("B", {"equipo_correcto": ""}, True) is None
    )  # marca sin equipo: como dudoso
    assert v("sin fila", None, True) is None
