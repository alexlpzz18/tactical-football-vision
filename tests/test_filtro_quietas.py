"""El filtro de débiles quietas: quita solo débiles que no se mueven, nunca las de producción, y
renumera los colores para que cada caja siga con SU color."""

from src.tracking.filtro_quietas import detecciones_quietas, filtrar_quietas


def _det(x, conf):
    return (0.0, 0.0, x, 10.0, x + 10, 30.0, conf)


def _cache(conf_fija=0.2):
    cache = []
    for k in range(10):  # 10 fotogramas en 1,2 s
        dets = [_det(100, conf_fija), _det(200 + 15 * k, 0.2), _det(500, 0.9)]
        cache.append({"frame_idx": 3 * k, "t": 0.12 * k, "dets": dets})
    return cache


def test_la_debil_quieta_sale_y_la_que_se_mueve_no():
    fuera = detecciones_quietas(_cache())
    assert all((3 * k, 0) in fuera for k in range(10))
    assert not any((3 * k, 1) in fuera for k in range(10))


def test_una_deteccion_de_produccion_quieta_no_se_toca_nunca():
    # la caja de x=500 (conf 0,9) está quieta en los 10 fotogramas y no sale
    fuera = detecciones_quietas(_cache())
    assert not any((3 * k, 2) in fuera for k in range(10))
    # con la caja fija también de producción, el filtro no hace nada
    assert not any(j == 0 for _f, j in detecciones_quietas(_cache(conf_fija=0.5)))


def test_quitar_renumera_los_colores():
    cache = _cache()
    colores = {
        (e["frame_idx"], j): f"c{e['frame_idx']}_{j}" for e in cache for j in range(3)
    }
    nuevo, col, n = filtrar_quietas(cache, colores)
    assert n == 10
    assert [d[2] for d in nuevo[0]["dets"]] == [200, 500]
    assert col[(0, 0)] == "c0_1" and col[(0, 1)] == "c0_2"


def test_sin_debiles_quietas_devuelve_lo_mismo():
    cache = [{"frame_idx": 0, "t": 0.0, "dets": [_det(100, 0.9)]}]
    nuevo, col, n = filtrar_quietas(cache, {(0, 0): "c"})
    assert n == 0 and nuevo is cache and col == {(0, 0): "c"}
