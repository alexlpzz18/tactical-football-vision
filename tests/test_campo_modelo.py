"""Tests del modelo de campo parametrizable (F11 / F7) y su calibración.

Lo crítico aquí es doble: que el F7 salga con las medidas del reglamento
de Madrid, y que el F11 de Villaviciosa NO cambie ni un decimal — su
homografía está calibrada contra esos puntos exactos.
"""

import json

import numpy as np
import pytest

from src.campo_modelo import (
    MARCAS_F7,
    MARCAS_F11,
    MODELO_F7,
    MODELO_F11,
    cargar_modelo,
)
from src.homography.calcular_homografia import (
    calcular_homografia,
    error_reproyeccion,
)

# Los 15 puntos que la herramienta pedía cuando estaban hardcodeados para
# el F11. La homografía de Villaviciosa se calibró con estas coordenadas.
PUNTOS_F11_LEGADO = {
    "center": (50.0, 32.0),
    "circulo_top": (50.0, 41.15),
    "circulo_bottom": (50.0, 22.85),
    "halfway_top": (50.0, 64.0),
    "halfway_bottom": (50.0, 0.0),
    "box_left_top": (16.5, 52.16),
    "box_left_bottom": (16.5, 11.84),
    "box_right_top": (83.5, 52.16),
    "box_right_bottom": (83.5, 11.84),
    "penalty_left": (11.0, 32.0),
    "penalty_right": (89.0, 32.0),
    "corner_top_left": (0.0, 64.0),
    "corner_bottom_left": (0.0, 0.0),
    "corner_top_right": (100.0, 64.0),
    "corner_bottom_right": (100.0, 0.0),
}


# ── el F11 no se toca ─────────────────────────────────────────────────


def test_f11_reproduce_exactamente_los_puntos_historicos():
    """Cada punto del F11 sale con la MISMA coordenada de siempre."""
    generados = dict(MODELO_F11.puntos_clicables())
    for nombre, (x, y) in PUNTOS_F11_LEGADO.items():
        assert nombre in generados, f"falta el punto histórico {nombre}"
        assert generados[nombre] == pytest.approx((x, y), abs=1e-9), nombre


def test_f11_conserva_dimensiones_y_marcas():
    assert (MODELO_F11.largo, MODELO_F11.ancho) == (100.0, 64.0)
    assert MODELO_F11.marcas is MARCAS_F11
    assert MARCAS_F11.penalti == 11.0
    assert MARCAS_F11.circulo_radio == 9.15
    assert MARCAS_F11.area_ancho == 40.32


def test_el_json_de_villaviciosa_sigue_encajando_en_el_modelo():
    """Los clics guardados coinciden con lo que el modelo pide hoy."""
    with open("data/calibracion/puntos_marcados.json") as f:
        guardados = json.load(f)
    generados = dict(MODELO_F11.puntos_clicables())
    for punto in guardados:
        assert punto["nombre"] in generados
        assert generados[punto["nombre"]] == pytest.approx(
            tuple(punto["metros"]), abs=1e-6
        ), punto["nombre"]


# ── modelo F7 ─────────────────────────────────────────────────────────


def test_f7_usa_el_reglamento_de_madrid():
    assert MARCAS_F7.area_ancho == 26.0
    assert MARCAS_F7.area_profundidad == 12.0
    assert MARCAS_F7.penalti == 9.0
    assert MARCAS_F7.circulo_radio == 6.0
    assert MARCAS_F7.porteria_ancho == 6.0
    assert (MODELO_F7.largo, MODELO_F7.ancho) == (62.0, 40.0)


def test_f7_genera_las_familias_de_puntos_del_encargo():
    """Esquinas, cortes de área con fondo, esquinas interiores, penaltis,
    círculo (4), centro y medios de banda."""
    p = dict(MODELO_F7.puntos_clicables())
    # Esquinas
    assert p["corner_bottom_left"] == (0.0, 0.0)
    assert p["corner_top_right"] == (62.0, 40.0)
    # Cortes del área con la línea de fondo (26 m de ancho → 20±13)
    assert p["box_left_top_line"] == (0.0, 33.0)
    assert p["box_left_bottom_line"] == (0.0, 7.0)
    # Esquinas interiores del área (12 m de profundidad)
    assert p["box_left_top"] == (12.0, 33.0)
    assert p["box_right_bottom"] == (50.0, 7.0)
    # Penaltis a 9 m de cada fondo
    assert p["penalty_left"] == (9.0, 20.0)
    assert p["penalty_right"] == (53.0, 20.0)
    # Círculo con 4 puntos, radio 6
    assert p["circulo_top"] == (31.0, 26.0)
    assert p["circulo_left"] == (25.0, 20.0)
    # Centro y medios de banda
    assert p["center"] == (31.0, 20.0)
    assert p["halfway_bottom"] == (31.0, 0.0)
    # Portería de 6 m
    assert p["goal_left_top"] == (0.0, 23.0)
    assert p["goal_left_bottom"] == (0.0, 17.0)


def test_las_marcas_no_dependen_del_tamano_del_campo():
    """Cambiar largo/ancho mueve el marco pero no las medidas de reglamento."""
    grande = MODELO_F7.con_dimensiones(70.0, 46.0)
    p = dict(grande.puntos_clicables())
    assert p["penalty_left"][0] == 9.0  # sigue a 9 m del fondo
    assert p["box_left_top"][0] == 12.0  # el área sigue entrando 12 m
    ancho_area = p["box_left_top"][1] - p["box_left_bottom"][1]
    assert ancho_area == pytest.approx(26.0)
    diametro = p["circulo_top"][1] - p["circulo_bottom"][1]
    assert diametro == pytest.approx(12.0)
    # pero el campo sí crece
    assert p["corner_top_right"] == (70.0, 46.0)


# ── carga desde config ────────────────────────────────────────────────


def test_cargar_modelo_por_nombre():
    assert cargar_modelo("f7") is MODELO_F7
    assert cargar_modelo("f11") is MODELO_F11
    with pytest.raises(ValueError, match="desconocido"):
        cargar_modelo("f5")


def test_cargar_modelo_desde_config_del_benja():
    modelo = cargar_modelo(config="configs/campo_benja.yaml")
    assert modelo.nombre == "benjamines"
    assert (modelo.largo, modelo.ancho) == (62.0, 40.0)
    assert modelo.marcas == MARCAS_F7  # hereda el reglamento F7


def test_config_puede_ajustar_medidas_y_marcas(tmp_path):
    ruta = tmp_path / "campo.yaml"
    ruta.write_text(
        "campo:\n  nombre: raro\n  tipo: f7\n  largo: 55.0\n  ancho: 35.0\n"
        "  marcas:\n    area_ancho: 22.0\n"
    )
    modelo = cargar_modelo(config=ruta)
    assert (modelo.largo, modelo.ancho) == (55.0, 35.0)
    assert modelo.marcas.area_ancho == 22.0  # sobrescrito
    assert modelo.marcas.penalti == 9.0  # el resto sigue siendo F7


# ── geometría de dibujo ───────────────────────────────────────────────


def test_lineas_y_circulo_dentro_del_campo():
    for modelo in (MODELO_F11, MODELO_F7):
        for p1, p2 in modelo.lineas():
            for x, y in (p1, p2):
                assert -1e-9 <= x <= modelo.largo + 1e-9
                assert -1e-9 <= y <= modelo.ancho + 1e-9
        puntos = np.array(modelo.circulo(20))
        centro = np.array(modelo.centro)
        radios = np.linalg.norm(puntos - centro, axis=1)
        assert radios == pytest.approx(modelo.marcas.circulo_radio, abs=1e-6)


# ── homografía sobre el modelo ────────────────────────────────────────


def _camara_sintetica(modelo, altura=3.0, retroceso=12.0):
    """Cámara BAJA detrás de la portería izquierda mirando al campo.

    Devuelve una función metros→píxel con un modelo pinhole simple: es la
    geometría del caso benjamín (cámara normal tras portería), con el eje
    largo alejándose del objetivo.
    """

    def proyectar(x_m, y_m):
        # Cámara en (-retroceso, ancho/2, altura) mirando a +x
        dx = x_m + retroceso  # profundidad desde la cámara
        dy = y_m - modelo.ancho / 2  # lateral
        f = 1200.0
        u = 1280 + f * dy / dx
        v = 540 + f * altura / dx
        return u, v

    return proyectar


def test_homografia_recupera_el_modelo_con_camara_tras_porteria():
    """Chain completo con datos sintéticos: puntos → H → error < 1 cm."""
    modelo = MODELO_F7
    proyectar = _camara_sintetica(modelo)
    puntos = [
        {"nombre": n, "pixel": list(proyectar(x, y)), "metros": [x, y]}
        for n, (x, y) in modelo.puntos_clicables()
    ]
    H, mask = calcular_homografia(puntos)
    assert int(mask.sum()) == len(puntos)  # sin clics ruidosos, todos valen
    errores = error_reproyeccion(puntos, H)
    assert errores.max() < 0.01


def test_homografia_falla_claro_con_pocos_puntos():
    with pytest.raises(ValueError, match="al menos 4 puntos"):
        calcular_homografia([{"pixel": [0, 0], "metros": [0.0, 0.0]}])


def test_el_error_metrico_crece_con_la_profundidad():
    """Física del caso: cámara baja tras portería → el fondo se comprime.

    Con 1 píxel de error de caja, los metros de error en la mitad lejana
    son MUCHO mayores que cerca de la cámara. No es un fallo: es la
    proyección, y por eso los umbrales por profundidad hay que
    recalibrarlos para este campo.
    """
    modelo = MODELO_F7
    proyectar = _camara_sintetica(modelo)
    puntos = [
        {"nombre": n, "pixel": list(proyectar(x, y)), "metros": [x, y]}
        for n, (x, y) in modelo.puntos_clicables()
    ]
    H, _ = calcular_homografia(puntos)

    import cv2

    def metros_por_pixel(x_m):
        u, v = proyectar(x_m, modelo.ancho / 2)
        par = np.array([[[u, v]], [[u, v + 1.0]]], dtype=np.float64)
        met = cv2.perspectiveTransform(par, H).reshape(2, 2)
        return float(np.linalg.norm(met[1] - met[0]))

    cerca = metros_por_pixel(modelo.largo * 0.1)
    lejos = metros_por_pixel(modelo.largo * 0.9)
    assert lejos > cerca * 5, (cerca, lejos)


# ── áreas de portería y eje de profundidad ────────────────────────────


def test_areas_porteria_derivadas_del_modelo_f7():
    """En F7 el área va de x=0 a 12 y de x=50 a 62, con y de 7 a 33."""
    areas = MODELO_F7.areas_porteria()
    assert areas["bajo"][0] == pytest.approx((0.0, 12.0))
    assert areas["alto"][0] == pytest.approx((50.0, 62.0))
    assert areas["bajo"][1] == pytest.approx((7.0, 33.0))
    assert areas["alto"][1] == areas["bajo"][1]


def test_areas_porteria_con_margen():
    areas = MODELO_F7.areas_porteria(margen=2.0)
    assert areas["bajo"][0] == pytest.approx((-2.0, 14.0))
    assert areas["alto"][0] == pytest.approx((48.0, 64.0))
    assert areas["bajo"][1] == pytest.approx((5.0, 35.0))


def test_regla_porteros_desde_modelo_no_usa_cortes_del_f11():
    """El corte mx=88.5 del F11 no existe en un campo de 62 m."""
    from src.team_classification.porteros import ReglaPorteros

    regla = ReglaPorteros.desde_modelo(MODELO_F7, margen=2.0)
    assert regla.area_mx_alto[0] == pytest.approx(48.0)
    assert regla.area_mx_alto[1] == pytest.approx(64.0)
    assert regla.area_mx_bajo[0] == pytest.approx(-2.0)
    assert 88.5 not in regla.area_mx_alto  # el hardcode del F11 no aparece
    # y el rango de ancho es el del área F7, no el 20-55 del F11
    assert regla.area_my == pytest.approx((5.0, 35.0))


def test_eje_profundidad_villaviciosa_es_el_ancho():
    """Cámara en banda: la profundidad es y, y no cambia el default."""
    from src.campo_modelo import EjeProfundidad

    eje = EjeProfundidad.desde_dict(None)  # sin config = comportamiento viejo
    assert (eje.eje, eje.creciente) == ("y", True)
    assert eje.de((50.0, 40.0), MODELO_F11) == 40.0


def test_eje_profundidad_benja_es_el_largo():
    """Cámara tras la portería x=0: la profundidad es x."""
    from src.campo_modelo import EjeProfundidad

    eje = EjeProfundidad.desde_dict({"eje": "x", "creciente": True})
    assert eje.de((50.0, 20.0), MODELO_F7) == 50.0  # lejos
    assert eje.de((5.0, 20.0), MODELO_F7) == 5.0  # cerca


def test_eje_profundidad_decreciente_mide_desde_la_camara():
    """Cámara tras la portería contraria: la profundidad se invierte."""
    from src.campo_modelo import EjeProfundidad

    eje = EjeProfundidad.desde_dict({"eje": "x", "creciente": False})
    assert eje.de((62.0, 20.0), MODELO_F7) == pytest.approx(0.0)  # pegado a cámara
    assert eje.de((2.0, 20.0), MODELO_F7) == pytest.approx(60.0)  # al fondo


def test_eje_profundidad_rechaza_ejes_invalidos():
    from src.campo_modelo import EjeProfundidad

    with pytest.raises(ValueError, match="eje de profundidad"):
        EjeProfundidad.desde_dict({"eje": "z"})


# ── los configs del benja son coherentes ──────────────────────────────


def test_config_equipos_del_benja_es_coherente():
    """El config del benja usa el eje y las áreas correctos para F7."""
    import yaml

    from src.team_classification.pipeline_equipos import _profundidad_configurada

    with open("configs/team_classification_benja.yaml") as f:
        cfg = yaml.safe_load(f)
    modelo, profundidad = _profundidad_configurada(cfg)
    assert (modelo.largo, modelo.ancho) == (62.0, 40.0)
    assert profundidad.eje == "x"  # cámara tras portería
    assert cfg["porteros"]["desde_modelo"] is True
    # Los umbrales están dentro del campo (no heredados del F11)
    assert cfg["entrenamiento"]["umbral_profundidad_m"] < modelo.largo
    assert cfg["agregacion"]["umbral_profundidad_m"] < modelo.largo


def test_config_equipos_del_f11_no_cambia_de_comportamiento():
    """Sin secciones nuevas, el config viejo da el comportamiento viejo."""
    import yaml

    from src.team_classification.pipeline_equipos import _profundidad_configurada

    with open("configs/team_classification.yaml") as f:
        cfg = yaml.safe_load(f)
    modelo, profundidad = _profundidad_configurada(cfg)
    assert (modelo.largo, modelo.ancho) == (100.0, 64.0)
    assert (profundidad.eje, profundidad.creciente) == ("y", True)
    assert cfg["porteros"].get("desde_modelo", False) is False  # áreas a mano


def test_processor_benja_tiene_las_claves_del_modo_full():
    """El config del benja arranca en Colab sin KeyError."""
    import yaml

    from src.tracking_data.processor import _CLAVES_FULL, validar_config

    with open("configs/processor_benja.yaml") as f:
        cfg = yaml.safe_load(f)
    validar_config(cfg, _CLAVES_FULL)  # lanza si falta alguna
    assert cfg["modo"] == "full"
    assert cfg["distorsion"] == {"k1": 0.0, "k2": 0.0}  # cámara sin distorsión
    assert cfg["campo_m"] == {"largo": 62.0, "ancho": 40.0, "margen": 5.0}
    assert "benja" in cfg["rutas"]["homografia"]
    assert cfg["config_equipos"] == "configs/team_classification_benja.yaml"
    # Ninguna ruta pisa a Villaviciosa
    for ruta in cfg["rutas"].values():
        assert "data/tracking/" not in ruta
        assert ruta != "data/calibracion/homografia.npy"


def test_tracking_del_benja_ajusta_lo_que_depende_del_campo():
    """La cota de plantilla y la consolidación no pueden heredarse del F11."""
    import yaml

    with open("configs/tracking_benja.yaml") as f:
        benja = yaml.safe_load(f)
    with open("configs/tracking.yaml") as f:
        f11 = yaml.safe_load(f)

    # F7 son 7+7 jugadores + árbitro; con la cota del F11 (23) nunca actúa
    assert benja["cota_plantilla"]["cota"] == 15
    assert f11["cota_plantilla"]["cota"] == 23  # el F11 no se toca
    # La distancia de consolidación escala con el largo del campo
    assert benja["consolidacion"]["dist_max"] < f11["consolidacion"]["dist_max"]
    # Lo que es FÍSICO sí se hereda: un límite de velocidad humana no
    # depende del campo
    assert benja["corte_velocidad"]["v_max"] == f11["corte_velocidad"]["v_max"]

    # El hueco de interpolación PARECÍA temporal y heredable, pero no lo
    # es: cuánta ficción introduce rellenar T segundos depende de cuántos
    # metros vale un píxel. Medido en el benjamín (10-ago-2026), 6,0 s
    # inventaban >1,6 m incluso en su mejor zona.
    assert benja["interpolacion"]["max_hueco"] < f11["interpolacion"]["max_hueco"]

    # Jitter MEDIDO sobre el caché, no estimado, y distinto para el corte
    # (ruido real del desplazamiento) que para la consolidación (decidir
    # identidad con todo el margen de ruido sobre-fusiona)
    esc = benja["escalado_resolucion"]
    assert esc["activo"] is True
    assert esc["jitter_px_consolidacion"] < esc["jitter_px"]


# ── dibujo del campo desde el modelo ──────────────────────────────────


def test_geometria_dibujo_f7_no_tiene_medidas_de_f11():
    """Un campo de F7 se pinta con SU círculo y SUS áreas."""
    geo = MODELO_F7.geometria_dibujo()
    assert geo["largo"] == 62.0 and geo["ancho"] == 40.0
    assert geo["circulos"][0]["r"] == 6.0  # no 9.15
    assert geo["circulos"][0]["cx"] == 31.0
    # Penaltis a 9 m de cada fondo (más el punto central)
    xs_puntos = sorted(x for x, _y in geo["puntos"])
    assert xs_puntos == pytest.approx([9.0, 31.0, 53.0])
    # Porterías de 6 m
    assert geo["porterias"][0]["alto"] == 6.0
    # F7 no tiene área pequeña: solo las líneas del área grande
    assert MODELO_F7.marcas.area_pequena_ancho is None
    ys_lineas = {round(y, 2) for seg in geo["lineas"] for _x, y in seg}
    assert 7.0 in ys_lineas and 33.0 in ys_lineas  # área 26 m de ancho
    assert 9.16 not in ys_lineas  # el área pequeña del F11 no aparece


def test_geometria_dibujo_f11_conserva_sus_marcas():
    geo = MODELO_F11.geometria_dibujo()
    assert geo["circulos"][0]["r"] == 9.15
    assert MODELO_F11.marcas.area_pequena_ancho == 18.32
    xs_puntos = sorted(x for x, _y in geo["puntos"])
    assert xs_puntos == pytest.approx([11.0, 50.0, 89.0])
    assert geo["porterias"][0]["alto"] == pytest.approx(7.32)


def test_geometria_es_serializable_para_el_replay():
    """El replay embebe la geometría como JSON en el HTML."""
    json.dumps(MODELO_F7.geometria_dibujo())
    json.dumps(MODELO_F11.geometria_dibujo())


def test_todo_lo_dibujado_cae_dentro_del_campo():
    for modelo in (MODELO_F11, MODELO_F7):
        geo = modelo.geometria_dibujo()
        for seg in geo["lineas"]:
            for x, y in seg:
                assert -1e-9 <= x <= modelo.largo + 1e-9
                assert -1e-9 <= y <= modelo.ancho + 1e-9
        for x, y in geo["puntos"]:
            assert 0 <= x <= modelo.largo and 0 <= y <= modelo.ancho


def test_replay_del_benja_pinta_el_campo_f7(tmp_path):
    """El HTML del replay lleva la geometría F7, no la del F11."""
    import pandas as pd

    from src.report.replay_tactico import generar_replay

    filas = [
        dict(
            frame=100 + 3 * k,
            tiempo_s=round(0.12 * k, 2),
            id_jugador=1,
            equipo=0,
            etiqueta="A",
            x_m=20.0,
            y_m=20.0,
            es_real=1,
        )
        for k in range(40)
    ]
    ruta = tmp_path / "benja.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)

    salida = generar_replay(ruta, tmp_path / "r.html", modelo=MODELO_F7)
    html = salida.read_text()
    campo = json.loads(html.split("const CAMPO = ")[1].split(";\n")[0])
    assert campo["largo"] == 62.0 and campo["ancho"] == 40.0
    assert campo["circulos"][0]["r"] == 6.0
    assert "const LARGO = 62.0" in html
    # El dibujo ya no lleva constantes del F11 en el JS
    assert "9.15*ESCALA" not in html
    assert "20.16" not in html


def test_informe_del_benja_usa_las_dimensiones_f7(tmp_path):
    """El informe calcula tercios/pasillos sobre el campo del modelo."""
    import pandas as pd

    from src.report.informe_v2 import generar_informe_v2

    filas = []
    for k in range(40):
        t = round(0.12 * k, 2)
        filas.append(
            dict(
                frame=100 + 3 * k,
                tiempo_s=t,
                id_jugador=1,
                equipo=0,
                etiqueta="A",
                x_m=15.0,
                y_m=20.0,
                es_real=1,
            )
        )
        filas.append(
            dict(
                frame=100 + 3 * k,
                tiempo_s=t,
                id_jugador=2,
                equipo=1,
                etiqueta="B",
                x_m=45.0,
                y_m=20.0,
                es_real=1,
            )
        )
    ruta = tmp_path / "benja.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)

    salida = generar_informe_v2(ruta, tmp_path / "i.html", modelo=MODELO_F7)
    assert salida.exists()  # el heatmap se dibuja sobre 62x40 sin reventar


def test_los_defaults_siguen_siendo_los_del_f11(tmp_path):
    """Sin --campo, replay e informe pintan Villaviciosa como siempre."""
    import inspect

    import pandas as pd

    from src.campo import ANCHO_M, LARGO_M
    from src.report.informe_v2 import generar_informe_v2
    from src.report.replay_tactico import generar_replay

    for funcion in (generar_replay, generar_informe_v2):
        assert inspect.signature(funcion).parameters["modelo"].default is None

    filas = [
        dict(
            frame=100 + 3 * k,
            tiempo_s=round(0.12 * k, 2),
            id_jugador=1,
            equipo=0,
            etiqueta="A",
            x_m=50.0,
            y_m=32.0,
            es_real=1,
        )
        for k in range(40)
    ]
    ruta = tmp_path / "v.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    html = generar_replay(ruta, tmp_path / "r.html").read_text()
    campo = json.loads(html.split("const CAMPO = ")[1].split(";\n")[0])
    assert (campo["largo"], campo["ancho"]) == (LARGO_M, ANCHO_M)
    assert campo["circulos"][0]["r"] == 9.15


# ── los configs de tracking deben ser cargables ───────────────────────


def test_todos_los_configs_de_tracking_son_validos():
    """Blindaje: un config con una clave inventada crashea en su 1er uso.

    Pasó de verdad (10-ago-2026): `hueco_min` acabó bajo la sección
    `cosido`, que no lo acepta, y configs/tracking_benja.yaml reventaba
    al correr el perfil. El escalado por resolución solo cubre corte,
    consolidación e interpolación; el cosido no.
    """
    import glob

    import yaml

    from src.tracking.field_tracker import ParametrosEtapaA
    from src.tracking.stitcher import ParametrosCosido

    rutas = glob.glob("configs/tracking*.yaml")
    assert rutas, "no se encontró ningún config de tracking"
    for ruta in rutas:
        cfg = yaml.safe_load(open(ruta))
        ParametrosCosido.desde_dict(dict(cfg["cosido"])), f"{ruta}: cosido"
        ParametrosEtapaA.desde_dict(dict(cfg["etapa_a"])), f"{ruta}: etapa_a"
