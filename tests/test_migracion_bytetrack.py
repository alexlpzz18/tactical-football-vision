"""Tests de la base nueva: ByteTrack + cosido por pureza.

El criterio que ordena estos tests es el hallazgo del banco (10-ago-2026):
fragmentar es un error recuperable, mezclar dos jugadores no lo es. Por
eso casi todos comprueban que el cosido PREFIERE NO UNIR cuando hay duda,
no que una lo máximo posible.
"""

import numpy as np
import pytest

from src.tracking.asociacion_bytetrack import (
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cosido_pureza import (
    ParametrosCosidoPureza,
    coser_por_pureza,
)
from src.tracking.field_tracker import Tracklet

DT = 0.12


def _identidad(tid, k_ini, n, x0, y0, vx=0.0, vy=0.0, det_base=0):
    """Fragmento recto que empieza en el frame k_ini (paso de 3 frames)."""
    t0 = k_ini * DT
    tracklet = Tracklet(tid, t0, np.array([x0, y0]), det_base, 100 + 3 * k_ini)
    for j in range(1, n):
        t = (k_ini + j) * DT
        tracklet.anadir(
            t,
            np.array([x0 + vx * j * DT, y0 + vy * j * DT]),
            det_base,
            100 + 3 * (k_ini + j),
        )
    return [tracklet]


# ── la asociación ─────────────────────────────────────────────────────


def _cache_sintetico(n_frames=20, n_personas=3):
    """Personas que se cruzan el campo en línea recta, sin ambigüedad."""
    cache = []
    for k in range(n_frames):
        dets = []
        for p in range(n_personas):
            x = 200 + p * 300 + k * 8
            y = 400 + p * 120
            dets.append((x / 20.0, y / 20.0, x, y, x + 30, y + 70, 0.9))
        cache.append({"frame_idx": 100 + 3 * k, "t": k * DT, "dets": dets})
    return cache


def test_bytetrack_sigue_a_cada_persona_con_una_identidad():
    cache = _cache_sintetico()
    identidades = asociar_con_bytetrack(cache, fps=25.0, sample=3)
    assert len(identidades) == 3
    for identidad in identidades:
        assert sum(len(tr.ts) for tr in identidad) >= 15


def test_las_posiciones_salen_del_cache_en_metros():
    """ByteTrack empareja en píxeles, pero lo que guarda son NUESTROS metros."""
    cache = _cache_sintetico()
    del_cache = {
        (e["frame_idx"], round(d[0], 6), round(d[1], 6))
        for e in cache
        for d in e["dets"]
    }
    for identidad in asociar_con_bytetrack(cache, fps=25.0, sample=3):
        for tracklet in identidad:
            for pos, (frame, _det) in zip(tracklet.pos, tracklet.det_idxs):
                assert (frame, round(pos[0], 6), round(pos[1], 6)) in del_cache


def test_el_det_idx_es_exacto_y_no_se_repite_en_un_frame():
    """Va pegado a la detección, no reconstruido por la geometría de la caja."""
    cache = _cache_sintetico()
    vistos = {}
    for identidad in asociar_con_bytetrack(cache, fps=25.0, sample=3):
        for tracklet in identidad:
            for frame, det_idx in tracklet.det_idxs:
                assert det_idx not in vistos.setdefault(frame, set())
                vistos[frame].add(det_idx)


def test_los_parametros_se_declaran_en_segundos():
    p = ParametrosByteTrack.desde_dict({"buffer_perdido_s": 3.0, "inventado": 1})
    assert p.buffer_perdido_s == 3.0  # y la clave desconocida no revienta


# ── el cosido por pureza ──────────────────────────────────────────────


def test_cose_dos_trozos_del_mismo_jugador():
    """Caso limpio: uno acaba, el otro sigue justo donde tocaba."""
    a = _identidad(1, 0, 10, 20.0, 30.0, vx=2.0)
    b = _identidad(2, 14, 10, 20.0 + 2.0 * 14 * DT, 30.0, vx=2.0)
    unidas = coser_por_pureza([a, b], colores=None, dt=DT)
    assert len(unidas) == 1


def test_no_cose_si_hay_DOS_candidatos_igual_de_buenos():
    """El corazón del criterio: ante el empate, fragmentar.

    Dos jugadores simétricos a la misma distancia del final de A. Unir a
    cualquiera de ellos es tirar una moneda, y acertar la mitad de las
    veces es exactamente cómo se fabrica una quimera.
    """
    a = _identidad(1, 0, 10, 20.0, 30.0)
    b = _identidad(2, 14, 10, 21.0, 31.0)
    c = _identidad(3, 14, 10, 21.0, 29.0)
    unidas = coser_por_pureza([a, b, c], colores=None, dt=DT)
    assert len(unidas) == 3, "con dos candidatos empatados no debe coser ninguno"


def test_sin_veto_de_ambiguedad_ese_mismo_caso_si_se_cose():
    """Contraprueba: el veto es lo que decide, no otra cosa del camino."""
    a = _identidad(1, 0, 10, 20.0, 30.0)
    b = _identidad(2, 14, 10, 21.0, 31.0)
    c = _identidad(3, 14, 10, 21.0, 29.0)
    unidas = coser_por_pureza(
        [a, b, c],
        colores=None,
        params=ParametrosCosidoPureza(margen_ambiguedad=0.0),
        dt=DT,
    )
    assert len(unidas) == 2


def test_no_cose_dos_fragmentos_que_coexisten():
    """Nadie está en dos sitios a la vez: son dos personas."""
    a = _identidad(1, 0, 20, 20.0, 30.0)
    b = _identidad(2, 10, 20, 21.0, 30.5)  # solapa en el tiempo con a
    unidas = coser_por_pureza([a, b], colores=None, dt=DT)
    assert len(unidas) == 2


def test_no_cose_saltos_fisicamente_imposibles():
    """40 m en medio segundo no los hace nadie."""
    a = _identidad(1, 0, 10, 20.0, 30.0)
    b = _identidad(2, 14, 10, 60.0, 30.0)
    unidas = coser_por_pureza([a, b], colores=None, dt=DT)
    assert len(unidas) == 2


def test_el_color_veta_una_union_geometricamente_perfecta():
    """Equipaciones distintas: aunque encaje el movimiento, no es la misma."""
    a = _identidad(1, 0, 10, 20.0, 30.0, vx=2.0, det_base=0)
    b = _identidad(2, 14, 10, 20.0 + 2.0 * 14 * DT, 30.0, vx=2.0, det_base=1)
    naranja = np.zeros(256)
    naranja[13] = 1.0
    blanco = np.zeros(256)
    blanco[200] = 1.0
    colores = {}
    for tr in a[0].det_idxs:
        colores[tr] = naranja
    for tr in b[0].det_idxs:
        colores[tr] = blanco

    assert len(coser_por_pureza([a, b], colores=None, dt=DT)) == 1  # sin color, cose
    assert len(coser_por_pureza([a, b], colores=colores, dt=DT)) == 2  # con color, no


def test_no_hay_cota_de_plantilla():
    """Con 40 jugadores separados no se fuerza ninguna fusión hacia 23.

    Es la lección explícita de la migración: el número de identidades es
    un proxy, no un objetivo.
    """
    identidades = [
        _identidad(i, 0, 20, 5.0 + 2.0 * i, 10.0 + (i % 5)) for i in range(40)
    ]
    assert len(coser_por_pureza(identidades, colores=None, dt=DT)) == 40


def test_una_sola_identidad_no_rompe():
    a = _identidad(1, 0, 10, 20.0, 30.0)
    assert coser_por_pureza([a], colores=None, dt=DT) == [a]


def test_desactivado_devuelve_lo_mismo():
    a = _identidad(1, 0, 10, 20.0, 30.0, vx=2.0)
    b = _identidad(2, 14, 10, 20.0 + 2.0 * 14 * DT, 30.0, vx=2.0)
    params = ParametrosCosidoPureza(activo=False)
    assert len(coser_por_pureza([a, b], colores=None, params=params, dt=DT)) == 2


@pytest.mark.parametrize("clave,valor", [("max_hueco", 9.0), ("v_max_salto", 3.0)])
def test_los_parametros_se_leen_del_dict(clave, valor):
    p = ParametrosCosidoPureza.desde_dict({clave: valor, "no_existe": 0})
    assert getattr(p, clave) == valor


# ── porteros cruzados (bug del benjamín, 11-ago-2026) ─────────────────


def _en(x, y, n=30, tid=1):
    tr = Tracklet(tid, 0.0, np.array([x, y]), 0, 100)
    for k in range(1, n):
        tr.anadir(k * DT, np.array([x, y]), 0, 100 + 3 * k)
    return [tr]


def _escena_f7():
    """Equipo A defiende x=0 (sus jugadores empujan hacia x=62)."""
    from src.campo_modelo import MODELO_F7
    from src.team_classification.porteros import ReglaPorteros

    identidades, equipos = [], {}

    def anadir(x, y, etiqueta):
        identidades.append(_en(x, y, tid=len(identidades) + 1))
        equipos[len(identidades)] = etiqueta

    for x in (28.0, 32.0, 35.0, 38.0):
        anadir(x, 20.0, "A")  # A ataca hacia x=62 → media ~33
    for x in (34.0, 38.0, 42.0, 46.0):
        anadir(x, 20.0, "B")  # B ataca hacia x=0 → media ~40
    # Los porteros visten distinto, así que el clasificador de color les
    # pone un equipo casi al azar. Aquí, como en el benjamín, cada uno
    # cae del lado equivocado: el de la portería lejana como "A" y el de
    # la cercana como "B". Con sus posiciones extremas, esos dos votos
    # basura bastan para invertir el orden de las medias.
    anadir(58.0, 20.0, "A")
    anadir(4.0, 20.0, "B")
    return identidades, equipos, MODELO_F7, ReglaPorteros.desde_modelo(MODELO_F7)


def test_los_lados_se_deducen_de_las_posiciones():
    """El equipo que ataca hacia x=62 defiende la portería x=0."""
    from src.team_classification.porteros import deducir_lados

    identidades, equipos, modelo, regla = _escena_f7()
    assert deducir_lados(
        equipos, identidades, modelo.largo, regla=regla, ancho=modelo.ancho
    ) == ("A", "B")


def test_el_voto_del_portero_no_invierte_el_resultado():
    """Regresión directa del bug del benjamín.

    Un portero viste distinto, así que su etiqueta de color es azarosa; y
    como vive en un extremo, ese voto basura arrastra la media de quien
    le toque y da la vuelta al signo.
    """
    from src.team_classification.porteros import deducir_lados

    identidades, equipos, modelo, regla = _escena_f7()
    sin_excluir = deducir_lados(
        equipos, identidades, modelo.largo, regla=None, ancho=modelo.ancho
    )
    assert sin_excluir == ("B", "A")  # invertido: el fallo que se arregló
    con_regla = deducir_lados(
        equipos, identidades, modelo.largo, regla=regla, ancho=modelo.ancho
    )
    assert con_regla == ("A", "B")


def test_el_publico_del_fondo_no_invierte_el_resultado():
    """Segunda causa del bug: esto corre ANTES de la regla de staff, y en
    el benjamín había gente proyectada a x=71, 80 y 95 sobre 62 m."""
    from src.team_classification.porteros import deducir_lados

    identidades, equipos, modelo, regla = _escena_f7()
    for x in (71.0, 80.0, 95.0):
        identidades.append(_en(x, 50.0, tid=len(identidades) + 1))
        equipos[len(identidades)] = "A"  # público mal clasificado como A

    assert deducir_lados(
        equipos, identidades, modelo.largo, regla=regla, ancho=modelo.ancho
    ) == ("A", "B")


def test_sin_separacion_clara_no_se_decide():
    """Ante la duda, manda lo configurado (y se avisa)."""
    from src.campo_modelo import MODELO_F7
    from src.team_classification.porteros import deducir_lados

    identidades, equipos = [], {}
    for i, etiqueta in enumerate(["A", "B"] * 4):
        identidades.append(_en(31.0, 20.0, tid=i + 1))
        equipos[i + 1] = etiqueta
    assert (
        deducir_lados(equipos, identidades, MODELO_F7.largo, ancho=MODELO_F7.ancho)
        is None
    )


# ── el replay no pinta nada fuera del campo (11-ago-2026) ─────────────


def test_el_replay_no_pinta_fuera_del_campo(tmp_path):
    """Banquillos y público: la regla de staff ya los saca de las
    métricas, pero en el replay tampoco deben existir — un entrenador
    pintado junto a la banda se lee como un jugador mal colocado."""
    import json

    import pandas as pd

    from src.report.replay_tactico import generar_replay

    filas = []
    for k in range(40):
        for id_j, x, y, etq in (
            (1, 30.0, 20.0, "A"),  # dentro
            (2, 30.0, -1.5, "staff"),  # banquillo, 1,5 m fuera de la banda
            (3, 71.0, 50.0, "B"),  # público del fondo
        ):
            filas.append(
                dict(
                    frame=100 + 3 * k,
                    tiempo_s=round(0.12 * k, 2),
                    id_jugador=id_j,
                    equipo=0,
                    etiqueta=etq,
                    x_m=x,
                    y_m=y,
                    es_real=1,
                )
            )
    csv = tmp_path / "pos.csv"
    pd.DataFrame(filas).to_csv(csv, index=False)

    html = generar_replay(
        csv, tmp_path / "r.html", largo=62.0, ancho=40.0, min_vida_s=0.0
    ).read_text()
    datos = json.loads(html.split("const DATOS = ")[1].split(";\n")[0])
    assert len(datos) == 1, "solo la identidad de dentro del campo debe pintarse"


# ── fusión de cachés por tramos (11-ago-2026) ────────────────────────


def _cache_parcial(desde, hasta, sample=3, fps=30.0):
    return {
        "fps": fps,
        "sample": sample,
        "wh": (1920, 1080),
        "cache": [
            {"frame_idx": f, "t": f / fps, "dets": [(1.0, 2.0, 10, 20, 30, 40, 0.9)]}
            for f in range(desde, hasta, sample)
        ],
    }


def test_la_fusion_ordena_y_quita_los_frames_repetidos():
    """Los tramos se piden CON solape a propósito; el solape no debe
    duplicar jugadores ni falsear la concurrencia."""
    from src.tracking.fusion_caches import fusionar_caches_detecciones

    # A propósito en desorden, y con 30 frames de solape entre ellos
    fusionado = fusionar_caches_detecciones(
        [_cache_parcial(300, 600), _cache_parcial(0, 330)]
    )
    frames = [e["frame_idx"] for e in fusionado["cache"]]
    assert frames == sorted(frames), "el tracking asume orden temporal"
    assert len(frames) == len(set(frames)), "el solape no debe duplicar frames"
    assert frames[0] == 0 and frames[-1] == 597


def test_la_fusion_falla_si_los_metadatos_no_cuadran():
    """Mezclar dt distintos rompería TODOS los umbrales físicos en
    silencio (velocidad, huecos, suavizado), así que se falla fuerte."""
    from src.tracking.fusion_caches import fusionar_caches_detecciones

    with pytest.raises(ValueError, match="dt"):
        fusionar_caches_detecciones(
            [_cache_parcial(0, 300, sample=3), _cache_parcial(300, 600, sample=5)]
        )


def test_se_detecta_el_tramo_que_falta():
    """La comprobación que evita creer que el partido está entero cuando
    una sesión de Colab murió por el camino."""
    from src.tracking.fusion_caches import (
        fusionar_caches_detecciones,
        huecos_de_cobertura,
    )

    # Falta el tramo de en medio (300-600)
    fusionado = fusionar_caches_detecciones(
        [_cache_parcial(0, 300), _cache_parcial(600, 900)]
    )
    huecos = huecos_de_cobertura(fusionado["cache"], fusionado["sample"])
    assert len(huecos) == 1
    assert huecos[0] == (297, 600)

    completo = fusionar_caches_detecciones(
        [_cache_parcial(0, 300), _cache_parcial(300, 600)]
    )
    assert huecos_de_cobertura(completo["cache"], completo["sample"]) == []


def test_los_colores_se_fusionan_por_clave_global():
    from src.tracking.fusion_caches import fusionar_caches_colores

    a = {(100, 0): np.ones(4), (100, 1): np.zeros(4)}
    b = {(100, 1): np.ones(4), (200, 0): np.ones(4)}  # (100,1) repetido
    fusionado = fusionar_caches_colores([a, b])
    assert len(fusionado) == 3
    assert np.array_equal(fusionado[(100, 1)], np.zeros(4))  # gana el primero


# ── catálogo arbitral (11-ago-2026) ──────────────────────────────────


def _hist(h, s, bins=16):
    """Histograma HS con todo el peso en el bin (h, s) de OpenCV."""
    f = np.zeros(bins * bins)
    ih = min(bins - 1, int(h * bins / 180))
    is_ = min(bins - 1, int(s * bins / 256))
    f[ih * bins + is_] = 1.0
    return f


def test_encuentra_al_arbitro_de_fluor():
    from src.tracking.field_tracker import Tracklet
    from src.team_classification.arbitro import identificar_arbitros

    identidades, colores = [], {}
    for tid, (h, s) in enumerate([(6, 248), (118, 56), (62, 248)], start=1):
        tr = Tracklet(tid, 0.0, np.array([30.0, 20.0]), 0, 100)
        for k in range(1, 40):
            tr.anadir(k * DT, np.array([30.0, 20.0]), tid, 100 + 3 * k)
        for par in tr.det_idxs:
            colores[par] = _hist(h, s)
        identidades.append([tr])

    # Equipos: naranja (H=6) y azulado sin saturar (H=118, S=56)
    arbitros = identificar_arbitros(
        identidades, colores, [_hist(6, 248), _hist(118, 56)]
    )
    assert list(arbitros) == [3]  # solo el verde flúor
    assert arbitros[3] == "verde_fluor"


def test_un_equipo_de_fluor_desactiva_su_arquetipo():
    """Regla de conflicto: si una equipación del partido cae en un
    arquetipo, ese arquetipo no puede usarse — si no, media plantilla
    saldría de árbitro. Caso real: el equipo B del benjamín es naranja
    saturado, que es exactamente el arquetipo 'naranja_fluor'."""
    from src.team_classification.arbitro import ARQUETIPOS, arquetipos_activos

    nombres = {a.nombre for a in arquetipos_activos([_hist(6, 248), _hist(118, 56)])}
    assert "naranja_fluor" not in nombres
    assert "verde_fluor" in nombres
    # Y el negro nunca está activo: el caché no guarda V
    assert "negro" not in nombres
    assert any(a.nombre == "negro" and a.necesita_v for a in ARQUETIPOS)


# ── feature de color v2 (11-ago-2026) ────────────────────────────────


def _recorte(bgr, alto=60, ancho=30):
    crop = np.zeros((alto, ancho, 3), dtype=np.uint8)
    crop[:, :] = bgr
    return crop


def test_la_v2_empieza_por_la_v1_bit_a_bit():
    """Es lo que hace que NINGÚN umbral calibrado cambie de escala.

    Todos los umbrales del sistema (fusión del fit 0,5-1,3, veto de color
    1,2, firmas) viven en la escala de la v1. Si los 256 primeros valores
    no fueran idénticos, cambiar de feature los invalidaría en silencio.
    """
    from src.team_classification.color_classifier import extraer_color_torso
    from src.team_classification.feature_v2 import (
        LONGITUD_V2,
        extraer_color_torso_v2,
        parte_camiseta_hs,
    )

    crop = _recorte((30, 140, 240))  # naranja
    v2 = extraer_color_torso_v2(crop)
    assert len(v2) == LONGITUD_V2
    assert np.allclose(parte_camiseta_hs(v2), extraer_color_torso(crop))


def test_la_v2_distingue_negro_de_blanco_y_la_v1_no():
    """El motivo de existir de la v2: sin V, negro y blanco son lo mismo
    (ambos tienen saturación baja), y por eso el arquetipo NEGRO del
    catálogo arbitral estaba inactivo."""
    from src.team_classification.color_classifier import extraer_color_torso
    from src.team_classification.feature_v2 import (
        brillo_medio,
        extraer_color_torso_v2,
    )

    negro, blanco = _recorte((18, 18, 18)), _recorte((235, 235, 235))
    # v1: indistinguibles
    assert np.allclose(extraer_color_torso(negro), extraer_color_torso(blanco))
    # v2: el brillo los separa sin margen de duda
    assert brillo_medio(extraer_color_torso_v2(negro)) < 60
    assert brillo_medio(extraer_color_torso_v2(blanco)) > 180


def test_los_accesores_aceptan_las_dos_versiones():
    """La compatibilidad: el código calibrado no necesita saber con qué
    versión de caché está trabajando."""
    from src.team_classification.color_classifier import extraer_color_torso
    from src.team_classification.feature_v2 import (
        brillo_medio,
        es_v2,
        extraer_color_torso_v2,
        parte_camiseta_hs,
        parte_pantalon,
    )

    crop = _recorte((30, 140, 240))
    v1, v2 = extraer_color_torso(crop), extraer_color_torso_v2(crop)
    assert not es_v2(v1) and es_v2(v2)
    assert len(parte_camiseta_hs(v1)) == len(parte_camiseta_hs(v2)) == 256
    assert parte_pantalon(v1) is None and parte_pantalon(v2) is not None
    assert brillo_medio(v1) is None


def test_el_arquetipo_negro_se_activa_solo_con_features_v2():
    from src.team_classification.arbitro import arquetipos_activos
    from src.team_classification.color_classifier import extraer_color_torso
    from src.team_classification.feature_v2 import extraer_color_torso_v2

    protos_v1 = [
        extraer_color_torso(_recorte(c)) for c in ((30, 140, 240), (200, 190, 180))
    ]
    protos_v2 = [
        extraer_color_torso_v2(_recorte(c)) for c in ((30, 140, 240), (200, 190, 180))
    ]
    assert "negro" not in {a.nombre for a in arquetipos_activos(protos_v1)}
    assert "negro" in {a.nombre for a in arquetipos_activos(protos_v2)}


# ── exclusividad de porteros (bug del id 55 del benjamín) ────────────


def test_solo_hay_un_portero_por_area():
    """Regresión del id 55: un jugador de campo que pasa mucho tiempo en
    el área rival salía reetiquetado como portero. Ahora el área tiene
    dueño único, y lo decide la PERMANENCIA."""
    from src.campo_modelo import MODELO_F7
    from src.team_classification.porteros import (
        ReglaPorteros,
        aplicar_regla_porteros,
    )

    def vive_en(x, y, n, tid):
        tr = Tracklet(tid, 0.0, np.array([x, y]), 0, 100)
        for k in range(1, n):
            tr.anadir(k * DT, np.array([x, y]), 0, 100 + 3 * k)
        return [tr]

    regla = ReglaPorteros.desde_modelo(MODELO_F7)
    regla = type(regla)(
        area_mx_bajo=regla.area_mx_bajo,
        area_mx_alto=regla.area_mx_alto,
        area_my=regla.area_my,
        equipo_mx_bajo="A",
        equipo_mx_alto="B",
    )
    identidades = [
        vive_en(58.0, 20.0, 200, 1),  # el portero de verdad
        vive_en(57.0, 21.0, 40, 2),  # un delantero que presiona
        vive_en(4.0, 20.0, 200, 3),  # el otro portero
    ]
    equipos = {1: "A", 2: "A", 3: "B"}
    resultado = aplicar_regla_porteros(equipos, identidades, regla)

    porteros = [k for k, v in resultado.items() if str(v).startswith("portero")]
    assert sorted(porteros) == [1, 3], "un solo portero por área"
    assert resultado[2] == "A", "el delantero conserva su etiqueta de color"
