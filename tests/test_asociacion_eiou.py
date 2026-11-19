"""Asociación por IoU ampliado (docs/plan_literatura.md, método 1). Tests de comportamiento."""

import numpy as np

from src.tracking.asociacion_eiou import ParametrosEIoU, ampliar, asociar_con_eiou, iou


def test_ampliar_sigue_la_definicion_del_articulo_y_la_del_codigo():
    caja = np.array([[10.0, 20.0, 20.0, 40.0]])  # 10 de ancho, 20 de alto
    a = ampliar(caja, 0.7, "articulo")[0]
    assert np.isclose(a[2] - a[0], 10 * (1 + 2 * 0.7))
    assert np.isclose(a[3] - a[1], 20 * (1 + 2 * 0.7))
    c = ampliar(caja, 0.7, "codigo")[0]
    assert np.isclose(c[2] - c[0], 10 * (2 + 2 * 0.7))
    # el centro no se mueve
    assert np.allclose([(a[0] + a[2]) / 2, (a[1] + a[3]) / 2], [15, 30])


def test_cajas_que_no_se_tocan_solapan_al_ampliarlas():
    a = np.array([[0.0, 0.0, 10.0, 20.0]])
    b = np.array([[14.0, 0.0, 24.0, 20.0]])  # separadas 4 px
    assert iou(a, b)[0, 0] == 0.0
    assert iou(ampliar(a, 0.7), ampliar(b, 0.7))[0, 0] > 0.2


def _cache(trayectorias, n, dt=0.12, conf=0.9):
    """Cajas de 10×24 px que siguen las trayectorias dadas (funciones de k → x en píxeles)."""
    cache = []
    for k in range(n):
        dets = []
        for j, x in enumerate(trayectorias):
            xk = x(k)
            dets.append(
                (xk / 10.0, 20.0 + j, xk, 100.0 + 40 * j, xk + 10, 124.0 + 40 * j, conf)
            )
        cache.append({"frame_idx": 3 * k, "t": k * dt, "dets": dets})
    return cache


def test_dos_jugadores_que_corren_en_paralelo_dan_dos_identidades_enteras():
    cache = _cache([lambda k: 100 + 3 * k, lambda k: 100 + 3 * k], 60)
    ids = asociar_con_eiou(cache, 25.0, 3)
    assert len(ids) == 2
    assert sorted(len(i[0].ts) for i in ids) == [60, 60]
    # cada identidad lleva SIEMPRE la misma fila (no se intercambian)
    for i in ids:
        assert len({d for _f, d in i[0].det_idxs}) == 1


def test_un_hueco_mas_corto_que_la_memoria_no_parte_la_identidad():
    cache = _cache(
        [lambda k: 100 + 0.2 * k], 60
    )  # casi parado: sin Kalman no se extrapola
    for e in cache[20:30]:  # 1,2 s sin verse
        e["dets"] = []
    ids = asociar_con_eiou(cache, 25.0, 3, ParametrosEIoU(buffer_perdido_s=2.0))
    assert len(ids) == 1 and len(ids[0][0].ts) == 50
    ids = asociar_con_eiou(cache, 25.0, 3, ParametrosEIoU(buffer_perdido_s=0.5))
    assert len(ids) == 2


def test_una_deteccion_suelta_de_poca_confianza_no_abre_identidad():
    cache = _cache([lambda k: 100 + 2 * k], 30)
    cache[10]["dets"].append((50.0, 50.0, 900.0, 500.0, 910.0, 524.0, 0.3))
    ids = asociar_con_eiou(cache, 25.0, 3)
    assert len(ids) == 1


def test_interruptor_real_en_el_perfil():
    """`bytetrack.asociacion: eiou` cambia quién decide; sin la clave, ByteTrack de siempre."""
    from src.tracking.perfiles import correr_perfil

    rng = np.random.default_rng(0)
    cache = _cache(
        [
            lambda k: 100 + 3 * k + rng.normal(0, 1),
            lambda k: 400 - 3 * k + rng.normal(0, 1),
        ],
        80,
    )
    base = correr_perfil(cache, 25.0, 3, {}, perfil="bytetrack")
    eiou = correr_perfil(
        cache, 25.0, 3, {"bytetrack": {"asociacion": "eiou"}}, perfil="bytetrack"
    )
    assert len(base) >= 1 and len(eiou) >= 1
    # el parámetro de EIoU llega de verdad: con un umbral de pista nueva por encima de todas las
    # confianzas (0,9) no nace ninguna identidad; ByteTrack no lee esa clave
    sin_nuevas = correr_perfil(
        cache,
        25.0,
        3,
        {"bytetrack": {"asociacion": "eiou"}, "eiou": {"umbral_nueva": 0.95}},
        perfil="bytetrack",
    )
    assert len(sin_nuevas) == 0
    try:
        correr_perfil(
            cache, 25.0, 3, {"bytetrack": {"asociacion": "otra"}}, perfil="bytetrack"
        )
        assert False, "una asociación desconocida tiene que dar error"
    except ValueError:
        pass
