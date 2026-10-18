"""Piezas puras de la preparación del reentreno del detector de balón.

- scripts/colab_comprobaciones_reentreno.py: el frame desde el nombre y el
  emparejado imagen↔etiqueta de los zips (lo de ultralytics solo corre en Colab).
- scripts/contar_etiquetado_pool.py: el lector del export YOLO 1.1 de CVAT y el
  criterio 1 en balones.
- scripts/preparar_pool_balon_pegado.py: la validación por minutos enteros.
"""

import random
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import colab_comprobaciones_reentreno as cr  # noqa: E402
import contar_etiquetado_pool as ce  # noqa: E402
import preparar_pool_balon_pegado as pp  # noqa: E402


def test_frame_del_nombre():
    assert cr.frame_del_nombre("benja_gredos_p1_f004430.png") == 4430
    assert cr.frame_del_nombre("img_2026_00012.jpg") == 12  # el ÚLTIMO grupo
    assert cr.frame_del_nombre("sin_numeros.png") is None
    assert cr.frame_del_nombre("frame_99999.png") is None  # no cabe en el vídeo


def test_normalizar_empareja_por_nombre_y_deja_negativos(tmp_path):
    zi, ze = tmp_path / "img.zip", tmp_path / "lab.zip"
    with zipfile.ZipFile(zi, "w") as z:
        z.writestr("frames/a/f000010.png", b"x")
        z.writestr("frames/b/f000020.png", b"x")  # sin etiqueta: negativo
    with zipfile.ZipFile(ze, "w") as z:
        z.writestr("labels/f000010.txt", "0 0.5 0.5 0.01 0.01\n")
        z.writestr("labels/classes.txt", "balon\n")
    n_img, n_lab = cr.normalizar_dataset(zi, ze, tmp_path / "ds")
    assert (n_img, n_lab) == (2, 1)
    assert (tmp_path / "ds" / "labels" / "todo" / "f000010.txt").exists()
    assert not (tmp_path / "ds" / "_crudo").exists()


def test_export_cvat_y_recuento(tmp_path):
    zp = tmp_path / "export.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("obj.names", "balon\n")
        z.writestr("obj_train_data/f000010.txt", "0 0.5 0.5 0.01 0.01\n")
        z.writestr("obj_train_data/f000020.txt", "")  # sin balón
    et = ce.leer_export_yolo(zp)
    assert et == {"f000010": ["0 0.5 0.5 0.01 0.01"], "f000020": []}
    m = pd.DataFrame({"frame": [10, 20, 30], "split": ["test", "test", "train"]})
    t = ce.contar(m, et, {"f000010": ["0 0.5 0.5 0.01 0.01"]})
    assert list(t.positivo) == [True, False, False]
    assert list(t.en_export) == [True, True, False]  # el 30 falta en el export
    assert t.sin_tocar.iloc[0]  # caja idéntica a la preanotación


def test_sin_tocar_compara_posicion_no_texto():
    pre = ["0 0.235990 0.563889 0.005244 0.009323"]
    assert ce.cajas_iguales(
        ["0 0.23599 0.563889 0.005244 0.009323"], pre
    )  # otro formato
    assert ce.cajas_iguales(["0 0.236100 0.564000 0.005300 0.009400"], pre)  # < 1 px
    assert not ce.cajas_iguales(["0 0.240680 0.563889 0.005244 0.009323"], pre)  # ~9 px
    assert not ce.cajas_iguales([], pre) and not ce.cajas_iguales(pre, None)


def test_criterio_1_en_balones_redondea_hacia_arriba():
    assert ce.balones_para_mejorar(12) == 3
    assert ce.balones_para_mejorar(13) == 4
    assert ce.balones_para_mejorar(20) == 5


def test_validacion_por_minutos_enteros_entre_15_y_20():
    por_minuto = {1: 3, 5: 7, 6: 9, 11: 10, 13: 5, 19: 10}
    val = pp.minutos_de_validacion(por_minuto, random.Random(4))
    n = sum(por_minuto[m] for m in val)
    assert 15 <= n <= 20


def test_cruce_original_pool_por_distancia_en_frames():
    import cruzar_original_pool as co

    m = pd.DataFrame({"frame": [100, 200, 300, 400], "minuto": [0, 0, 0, 13],
                      "split": ["test", "test", "train", "val"]})  # fmt: skip
    t = co.cruzar([100, 202, 305, 500], m, radio=2)
    assert list(t.frame) == [100, 200, 400]  # el train no se cruza
    assert list(t.repetido) == [True, True, False]
    assert list(t.dist_frames) == [0, 2, 95]  # 400 está a 95 de 305


def test_augmentacion_clasifica_el_destino_de_cada_caja():
    assert cr.clasificar_caja(10, 10, 9, 9, True) == "conservado"
    assert cr.clasificar_caja(10, 10, 0, 9, False) == "fuera"  # negativo correcto
    assert cr.clasificar_caja(10, 10, 3, 3, False) == "recortado"  # 9 % del área
    assert cr.clasificar_caja(2, 2, 1.5, 1.5, False) == "pequeno"  # visible pero ≤ 2 px
    assert cr.lado_px([(0.5, 0.5, 0.01, 0.02)], alto=720, ancho=1280) == pytest.approx(
        [13.6]
    )


def test_augmentacion_elige_el_ajuste_mas_suave_que_llega():
    b = [{"scale": 0.5, "translate": 0.1, "conserva": 0.92},
         {"scale": 0.3, "translate": 0.1, "conserva": 0.96},
         {"scale": 0.3, "translate": 0.05, "conserva": 0.97},
         {"scale": 0.2, "translate": 0.1, "conserva": 0.99}]  # fmt: skip
    assert cr.elegir_mas_suave(b) == b[1]
    assert cr.elegir_mas_suave(b[:1]) is None
