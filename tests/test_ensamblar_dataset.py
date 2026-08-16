"""Tests del ensamblaje del dataset v4.

El riesgo real de este paso no es que falten archivos: es que dos
personas etiqueten con criterios distintos. Eso no rompe nada, envenena
el entrenamiento en silencio y se descubre cuando el modelo ya está
entrenado. Por eso los tests van sobre la DETECCIÓN de esa divergencia.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ensamblar_dataset_v4 import (  # noqa: E402
    auditar,
    comparar_lotes,
    leer_lote,
    muestra_para_revision,
)


def _lote(tmp_path, nombre, n_imgs, cajas_por_img, alto=0.08, clase=0):
    carpeta = tmp_path / nombre
    (carpeta / "images").mkdir(parents=True)
    (carpeta / "labels").mkdir(parents=True)
    for i in range(n_imgs):
        (carpeta / "images" / f"f{i:04d}.jpg").write_bytes(b"\xff\xd8\xff")
        filas = [
            f"{clase} {0.1 + 0.05 * j:.4f} 0.5 0.02 {alto:.4f}"
            for j in range(cajas_por_img)
        ]
        (carpeta / "labels" / f"f{i:04d}.txt").write_text("\n".join(filas))
    return carpeta


def test_audita_lo_basico(tmp_path):
    a = auditar(leer_lote(_lote(tmp_path, "lote_a", 10, 18)), "lote_a")
    assert a["n_imagenes"] == 10 and a["n_etiquetadas"] == 10
    assert a["cajas"] == 180 and a["cajas_por_frame"] == pytest.approx(18.0)
    assert a["problemas"] == []


def test_caza_al_etiquetador_que_se_deja_jugadores(tmp_path):
    """El fallo típico del lote nuevo: los del fondo, diminutos, no se
    etiquetan. No rompe nada — solo enseña al modelo que ahí no hay
    nadie."""
    a = auditar(leer_lote(_lote(tmp_path, "alex_478", 20, 18)), "alex_478")
    b = auditar(leer_lote(_lote(tmp_path, "ayudante_360", 20, 12)), "ayudante_360")
    alertas = comparar_lotes([a, b])
    assert any("cajas por frame" in x for x in alertas)


def test_caza_el_criterio_de_encuadre_distinto(tmp_path):
    """Cajas sistemáticamente más apretadas: otro criterio al encuadrar
    (piernas dentro o fuera)."""
    a = auditar(leer_lote(_lote(tmp_path, "alex", 20, 18, alto=0.08)), "alex")
    b = auditar(leer_lote(_lote(tmp_path, "ayudante", 20, 18, alto=0.05)), "ayudante")
    assert any("altura mediana" in x for x in comparar_lotes([a, b]))


def test_caza_una_numeracion_de_clases_distinta(tmp_path):
    a = auditar(leer_lote(_lote(tmp_path, "alex", 10, 18, clase=0)), "alex")
    b = auditar(leer_lote(_lote(tmp_path, "ayudante", 10, 18, clase=1)), "ayudante")
    assert any("clases distintas" in x for x in comparar_lotes([a, b]))


def test_dos_lotes_coherentes_no_dan_alertas(tmp_path):
    """Contraprueba: la auditoría no puede ser un detector de humo que
    salta siempre, o se ignora."""
    a = auditar(leer_lote(_lote(tmp_path, "alex", 20, 18)), "alex")
    b = auditar(leer_lote(_lote(tmp_path, "ayudante", 20, 17)), "ayudante")
    assert comparar_lotes([a, b]) == []


def test_detecta_cajas_degeneradas_y_fuera_de_rango(tmp_path):
    carpeta = _lote(tmp_path, "roto", 3, 2)
    (carpeta / "labels" / "f0000.txt").write_text(
        "0 0.5 0.5 0.0 0.0\n0 1.5 0.5 0.02 0.08"
    )
    a = auditar(leer_lote(carpeta), "roto")
    assert any("tamaño ~0" in p for p in a["problemas"])
    assert any("fuera de [0,1]" in p for p in a["problemas"])


def test_la_muestra_del_2pct_saca_de_TODOS_los_lotes(tmp_path):
    """Si la muestra saliera de un solo lote, no serviría para comparar
    criterios, que es justo para lo que está."""
    lotes = [
        leer_lote(_lote(tmp_path, "alex_478", 100, 18)),
        leer_lote(_lote(tmp_path, "ayudante_360", 100, 18)),
    ]
    destino, n = muestra_para_revision(lotes, tmp_path / "out", fraccion=0.02)
    nombres = [f.name for f in destino.glob("*.jpg")]
    assert n == 4  # 2 % de 100, en cada lote
    assert any(x.startswith("alex_478__") for x in nombres)
    assert any(x.startswith("ayudante_360__") for x in nombres)
    # Cada imagen va con su etiqueta, para poder juzgar el encuadre
    for img in destino.glob("*.jpg"):
        assert img.with_suffix(".txt").exists()
