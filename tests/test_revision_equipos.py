"""Plantilla y lector de revision.csv (scripts/revision_equipos.py)."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "rev", Path(__file__).resolve().parent.parent / "scripts/revision_equipos.py"
)
rev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rev)

CAJAS = {("azar", "00_16-04.0.jpg"): {0, 1, 2}}


def _fila(**k):
    base = dict(
        ventana="azar",
        imagen="00_16-04.0.jpg",
        caja="1",
        equipo_correcto="arbitro",
        causa="arbitro",
        nota="",
    )
    base.update(k)
    return base


def test_la_plantilla_no_sobrescribe(tmp_path):
    ruta = tmp_path / "revision.csv"
    assert rev.crear_plantilla(ruta)
    ruta.write_text(ruta.read_text() + "azar,x.jpg,0,A,otra,mia\n")
    assert not rev.crear_plantilla(ruta)
    assert "mia" in ruta.read_text()


def test_acepta_los_valores_de_la_lista():
    assert (
        rev.validar(
            [_fila(), _fila(caja="2", equipo_correcto="B", causa="color_limpio")], CAJAS
        )
        == []
    )


def test_avisa_de_valores_fuera_de_lista_y_de_cajas_que_no_existen():
    avisos = rev.validar(
        [
            _fila(equipo_correcto="Arbitro"),
            _fila(causa="fundida", caja="2"),
            _fila(caja="9"),
            _fila(imagen="99.jpg", caja="0"),
            _fila(caja="x"),
            _fila(),
        ],
        CAJAS,
    )
    texto = " | ".join(avisos)
    assert "equipo_correcto «Arbitro»" in texto
    assert "causa «fundida»" in texto
    assert "no tiene caja 9" in texto
    assert "«99.jpg» no está" in texto
    assert "«x» no es un número" in texto
    assert "ya estaba marcada" in texto
