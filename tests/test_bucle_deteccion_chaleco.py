"""El bucle de detección REAL guarda la puntuación de chaleco en la caché (25-oct).

docs/diagnostico_25oct_chaleco_colab.md. El test de Colab del 23-oct (f) falló donde el de local no
podía ver: el local reproducía la parte posterior a SAHI con una función aparte, y nunca pasaba
por `detectar_y_cachear` ni por el volcado a disco. Aquí se ejerce el bucle entero: lectura del
vídeo, detección, filtro, feature de color, chaleco y `_guardar_caches`, con 3 frames.

El detector es un doble mínimo de SAHI (`sahi.AutoDetectionModel` y
`sahi.predict.get_sliced_prediction`): devuelve dos cajas fijas por frame, una con chaleco verde
flúor y otra naranja. Se inyecta en `sys.modules` para no depender de que torch funcione en el
entorno (en el Mac, torch 2.2.2 no arranca con numpy 2.4.6).
"""

import copy
import pickle
import sys
import types
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from src.tracking_data.processor import (
    comprobar_chaleco_antes_de_detectar,
    detectar_y_cachear,
)

R = Path(__file__).resolve().parent.parent
CAJAS = [(40, 60, 80, 140), (200, 60, 240, 140)]  # chaleco, naranja (x1, y1, x2, y2)


def _bgr(h, s, v):
    return cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()


def _video(ruta: Path, n: int = 9) -> None:
    """Vídeo sintético de n frames 320×240: césped, una persona de chaleco y otra naranja."""
    w = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (320, 240))
    for _ in range(n):
        img = np.full((240, 320, 3), _bgr(55, 120, 120), np.uint8)
        x1, y1, x2, y2 = CAJAS[0]
        img[y1:y2, x1:x2] = _bgr(44, 175, 247)
        x1, y1, x2, y2 = CAJAS[1]
        img[y1:y2, x1:x2] = _bgr(10, 220, 230)
        w.write(img)
    w.release()


class _Pred:
    def __init__(self, caja):
        self.bbox = types.SimpleNamespace(
            minx=caja[0], miny=caja[1], maxx=caja[2], maxy=caja[3]
        )
        self.score = types.SimpleNamespace(value=0.9)


@pytest.fixture
def sahi_doble(monkeypatch):
    llamadas = {"modelo": 0, "frames": 0}
    raiz = types.ModuleType("sahi")
    predict = types.ModuleType("sahi.predict")

    class _Modelo:
        @staticmethod
        def from_pretrained(**_kw):
            llamadas["modelo"] += 1
            return object()

    def _predecir(frame, modelo, **_kw):
        llamadas["frames"] += 1
        return types.SimpleNamespace(object_prediction_list=[_Pred(c) for c in CAJAS])

    raiz.AutoDetectionModel = _Modelo
    predict.get_sliced_prediction = _predecir
    raiz.predict = predict
    monkeypatch.setitem(sys.modules, "sahi", raiz)
    monkeypatch.setitem(sys.modules, "sahi.predict", predict)
    return llamadas


def _cfg(tmp_path: Path, banda) -> dict:
    _video(tmp_path / "v.avi")
    np.save(tmp_path / "h.npy", np.eye(3))
    cfg = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
    cfg["modo"] = "full"
    cfg["config_equipos"] = str(
        R / cfg["config_equipos"]
    )  # F7: la pista está encendida
    cfg["deteccion"].update(device="cpu", chaleco_banda=banda)
    cfg["muestreo"] = {"sample_every": 3, "tramo": None, "max_frames": 9}
    cfg["checkpoint"] = {"cada_frames": 0, "reanudar": False}
    cfg["rutas"] = {
        "video": str(tmp_path / "v.avi"),
        "homografia": str(tmp_path / "h.npy"),
        "cache": str(tmp_path / "cache.pkl"),
        "cache_colores": str(tmp_path / "colores.pkl"),
        "salida_csv": str(tmp_path / "pos.csv"),
        "salida_meta": str(tmp_path / "pos_meta.json"),
    }
    return cfg


def test_el_bucle_real_deja_el_chaleco_en_la_cache_de_disco(tmp_path, sahi_doble):
    detectar_y_cachear(_cfg(tmp_path, [38, 48, 112, 173]))
    assert sahi_doble["frames"] == 3
    datos = pickle.load(open(tmp_path / "cache.pkl", "rb"))  # lo que leerá desde_cache
    assert "chaleco" in datos, "la caché de detección no tiene la clave `chaleco`"
    dets = {(e["frame_idx"], j) for e in datos["cache"] for j in range(len(e["dets"]))}
    assert len(dets) == 6
    assert set(datos["chaleco"]) == dets  # una puntuación por detección, mismas claves
    for (f, j), v in datos["chaleco"].items():
        assert (v > 0.9) if j == 0 else (v == 0.0), (f, j, v)
    assert datos["firma"]["chaleco_banda"] == [38, 48, 112, 173]


def test_f7_sin_banda_falla_antes_de_cargar_el_detector(tmp_path, sahi_doble):
    with pytest.raises(ValueError, match="INCOHERENTE"):
        detectar_y_cachear(_cfg(tmp_path, None))
    assert sahi_doble["modelo"] == 0 and sahi_doble["frames"] == 0
    assert not (tmp_path / "cache.pkl").exists()


def test_coherencia_con_la_pista_apagada_o_con_cache_aparte(tmp_path):
    cfg = _cfg(tmp_path, None)
    con_cache = copy.deepcopy(cfg)
    con_cache["rutas"]["cache_chaleco"] = str(tmp_path / "ch.pkl")
    comprobar_chaleco_antes_de_detectar(con_cache)  # no lanza
    eq = yaml.safe_load(open(cfg["config_equipos"]))
    eq["arbitro"]["viterbi"]["activo"] = False
    (tmp_path / "eq.yaml").write_text(yaml.safe_dump(eq, allow_unicode=True))
    apagada = copy.deepcopy(cfg)
    apagada["config_equipos"] = str(tmp_path / "eq.yaml")
    comprobar_chaleco_antes_de_detectar(apagada)  # no lanza
    f11 = copy.deepcopy(cfg)
    f11["config_equipos"] = str(R / "configs/team_classification.yaml")
    comprobar_chaleco_antes_de_detectar(f11)  # F11: la pista está apagada, no lanza
