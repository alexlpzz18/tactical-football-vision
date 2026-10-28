"""La etiqueta del balón de los clips no puede pisar la de ÁRBITRO (render_clips_26oct.py)."""

import importlib.util
from pathlib import Path

R = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "render_clips_26oct", R / "scripts/render_clips_26oct.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_sin_choques_va_encima_del_circulo():
    m = _mod()
    x, y = m.colocar_etiqueta(500, 400, 16, 100, 20, [])
    assert y + 20 <= 400 - 16  # entera por encima del círculo


def test_no_pisa_arbitro_a_la_derecha_ni_encima():
    m = _mod()
    # el caso que vio Alex: ÁRBITRO justo donde iba antes la etiqueta (derecha) y otra encima
    arbitro = (515, 385, 640, 410)
    encima = (440, 350, 560, 382)
    x, y = m.colocar_etiqueta(500, 400, 16, 100, 20, [arbitro, encima])
    caja = (x, y, x + 100, y + 20)
    assert not m._se_solapan(caja, arbitro)
    assert not m._se_solapan(caja, encima)


def test_si_todo_choca_sube_hasta_encontrar_hueco():
    m = _mod()
    ocupadas = [(300, 330, 700, 470)]  # tapa las cuatro posiciones básicas
    x, y = m.colocar_etiqueta(500, 400, 16, 100, 20, ocupadas)
    assert not m._se_solapan((x, y, x + 100, y + 20), ocupadas[0])
    assert y + 20 <= 330
