"""Etiqueta con tope de cardinalidad (flag, apagado por defecto). docs/diagnostico_22oct_e.md."""

from pathlib import Path

import numpy as np
import yaml

from src.team_classification.tope_cardinalidad import resolver, trozos_de

R = Path(__file__).resolve().parent.parent


def test_apagado_en_los_dos_configs_de_produccion():
    for ruta, tope in (
        ("configs/processor_benja_parte_entera.yaml", 7),
        ("configs/processor.yaml", 11),
    ):
        cfg = yaml.safe_load(open(R / ruta))["equipos"]["tope_cardinalidad"]
        assert cfg["activo"] is False
        assert cfg["tope"] == tope


def test_respeta_el_tope_aunque_el_color_diga_otra_cosa():
    """9 personas a la vez que «parecen» A: solo 7 pueden serlo; el resto, al más barato."""
    C = np.array([[0.1, 0.5, 0.9]] * 9) * 100
    C[7] = [0.1, 0.2, 0.9]  # las dos con menos margen A→B son las que se mueven
    C[8] = [0.1, 0.25, 0.9]
    pres = {f: set(range(9)) for f in range(100)}
    etiquetas, exceso, _n = resolver(C, pres, {}, 7, 1, 1.0, 30)
    assert etiquetas.count("A") == 7
    assert etiquetas[7] == "B" and etiquetas[8] == "B"
    assert exceso == 0


def test_holgura_cuando_violar_es_mas_barato_que_reetiquetar():
    """Una caja fantasma de 1 frame no obliga a reetiquetar a una identidad larga."""
    C = np.array([[0.0, 50.0, 90.0]] * 8)
    pres = {0: set(range(8))}  # las 8 juntas un solo frame
    etiquetas, exceso, _n = resolver(C, pres, {}, 7, 1, 1.0, 30)
    assert etiquetas.count("A") == 8
    assert exceso == 1.0


def test_los_porteros_fijados_cuentan_en_su_tope():
    # reetiquetar una cuesta 5; violar el tope 10 frames, 10 (λ = 1): gana reetiquetar
    C = np.array([[0.0, 5.0, 90.0]] * 7)
    pres = {f: set(range(7)) for f in range(10)}
    fijas = {f: (1, 0, 0) for f in range(10)}  # el portero de A, fijado
    etiquetas, _e, _n = resolver(C, pres, fijas, 7, 1, 1.0, 30)
    assert etiquetas.count("A") == 6


def test_trozos_de_cortan_cada_1_5_s():
    from src.tracking.field_tracker import Tracklet

    tr = Tracklet(1, 0.0, np.array([10.0, 10.0]), 0, 0)
    for i in range(1, 40):
        tr.anadir(i * 0.1, np.array([10.0, 10.0]), 0, i)
    trozos = trozos_de([[tr]], [1], 1.5)
    assert [len(obs) for _i, obs in trozos] == [15, 15, 10]
