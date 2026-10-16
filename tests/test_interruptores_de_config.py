"""Todo interruptor `activa:` de un config tiene que APAGAR algo de verdad.

El 27-ago-2026 se descubrió que `cota_plantilla.activa` y
`exclusion_espacial.activa` estaban a `false` en los cuatro configs de
tracking y `src/tracking/perfiles.py` **nunca leía la clave**: las dos
fusiones corrían igual. Medido: el perfil `candidato` daba 58 identidades
donde salen 114, y una de las fusiones es la cota de plantilla, el
fracaso canónico del proyecto.

⚠️ Y LA PRIMERA VERSIÓN DE ESTE FICHERO REINTRODUJO EL MISMO ERROR.
Comprobaba los interruptores con `assert codigo.count('get("activa"') >= 4`.
Una verificación adversarial lo esquivó en una línea: cambió
`if reparadoras and cfg_consol.get("activa", False):` por
`if reparadoras:` dejando la palabra en un comentario. El recuento seguía
dando 4, los 377 tests pasaban, y el bug era real. **Tercera generación
del mismo error: el fichero escrito para impedirlo lo reintroducía en la
sección de al lado.**

> Si una guarda se puede esquivar renombrando o moviendo algo, no es una
> guarda.

Por eso aquí no se cuenta nada. Se EJERCE el interruptor: se corre el
pipeline con `true` y con `false` sobre el mismo caché y se exige que el
resultado cambie. Es lo único que la verificación no pudo esquivar.
"""

import inspect
import sys

import pytest
import yaml

# Cada interruptor con por qué se sabe que apaga algo. Uno nuevo que no
# esté aquí hace fallar el test: se entera por OMISIÓN.
INTERRUPTORES = {
    "exclusion_espacial": "perfil candidato",
    "cota_plantilla": "perfil candidato",
    "consolidacion": "postproceso",
    "interpolacion": "postproceso",
    # Se leen en otro sitio, comprobado: `activa` vive dentro de los
    # propios parámetros (puerta_reentrada.py:164) y en el banco
    # (scripts/evaluar_tracking.py:237). Aparecieron gracias a este test.
    "puerta_reentrada": None,
    "segunda_pasada": None,
}

# Los que se pueden ejercer end-to-end aquí, con dónde viven.
EJERCITABLES = [s for s, donde in INTERRUPTORES.items() if donde]


def _secciones_con_interruptor():
    """{sección} de todo `activa:` que aparezca en configs/."""
    import glob

    encontradas = set()
    for ruta in sorted(glob.glob("configs/*.yaml")):
        try:
            datos = yaml.safe_load(open(ruta))
        except yaml.YAMLError:  # pragma: no cover
            continue
        if not isinstance(datos, dict):
            continue
        for seccion, valor in datos.items():
            if isinstance(valor, dict) and "activa" in valor:
                encontradas.add(seccion)
    return encontradas


def test_todo_interruptor_activa_esta_registrado():
    """Un interruptor nuevo sin prueba de comportamiento falla POR OMISIÓN."""
    encontradas = _secciones_con_interruptor()
    nuevos = encontradas - set(INTERRUPTORES)
    assert not nuevos, (
        f"secciones con `activa:` que nadie ha comprobado que apaguen algo: "
        f"{sorted(nuevos)}. Añádelas a INTERRUPTORES y, si se pueden ejercer, "
        "a EJERCITABLES. Un interruptor que no apaga nada es peor que no "
        "tenerlo: da una falsa sensación de control."
    )
    fantasmas = set(INTERRUPTORES) - encontradas
    assert not fantasmas, f"registrados pero ya no existen: {sorted(fantasmas)}"


def test_ningun_interruptor_se_comprueba_CONTANDO():
    """Impide volver a poner un recuento sobre el código fuente.

    Es lo que hacía la v1 de este fichero y lo que la verificación
    adversarial esquivó moviendo una palabra a un comentario.
    """
    codigo = inspect.getsource(sys.modules[__name__])
    prohibido = "." + "count("  # armado por partes: si no, se casa solo
    # Se descuentan las apariciones de esta propia comprobación.
    apariciones = len(codigo.split(prohibido)) - 1
    assert apariciones <= 2, (
        "alguien ha vuelto a comprobar un interruptor CONTANDO apariciones "
        "en el código fuente. Se esquiva moviendo la palabra a un "
        "comentario: EJERCE el interruptor en su lugar."
    )


def _cache_sintetico(seccion):
    """Un caché que ejercita justo lo que fusiona cada interruptor."""
    cache = []
    for f in range(0, 120, 3):
        if seccion in ("exclusion_espacial", "consolidacion", "interpolacion"):
            # Dos identidades CO-UBICADAS: la misma persona detectada dos veces.
            dets = [
                (10.0, 20.0, 0, 0, 10, 30, 0.9),
                (10.3, 20.1, 0, 0, 10, 30, 0.9),
            ]
        else:
            # ENTRELAZADAS: observaciones alternadas, nunca a la vez.
            dets = [
                (
                    (10.0, 20.0, 0, 0, 10, 30, 0.9)
                    if (f // 3) % 2 == 0
                    else (10.4, 20.2, 0, 0, 10, 30, 0.9)
                )
            ]
        if seccion == "interpolacion":
            # Un hueco que interpolar: sin detecciones en el medio.
            if 30 <= f < 60:
                dets = dets[:1]
        dets.append((40.0, 20.0, 0, 0, 10, 30, 0.9))
        cache.append({"frame_idx": f, "t": f / 30.0, "dets": dets})
    return cache


def _medir(seccion, activa):
    """Corre el pipeline con el interruptor puesto o quitado."""
    from src.tracking.perfiles import correr_perfil, postprocesar

    base = yaml.safe_load(open("configs/tracking.yaml"))
    cache = _cache_sintetico(seccion)
    cfg = {**base, seccion: {**base.get(seccion, {}), "activa": activa}}
    if seccion == "cota_plantilla":
        cfg[seccion] = {**cfg[seccion], "cota": 1, "coste_max": 40.0}

    if INTERRUPTORES[seccion] == "perfil candidato":
        # El otro interruptor del perfil, siempre apagado, para aislar.
        otro = (
            "cota_plantilla"
            if seccion == "exclusion_espacial"
            else "exclusion_espacial"
        )
        cfg[otro] = {**base.get(otro, {}), "activa": False}
        return len(correr_perfil(cache, 30.0, 3, cfg, perfil="candidato"))

    identidades = correr_perfil(cache, 30.0, 3, cfg, perfil="bytetrack")
    equipos = {i: "A" for i in range(1, len(identidades) + 1)}
    frames_ts = [(e["frame_idx"], e["t"]) for e in cache]
    trayectorias, _ = postprocesar(identidades, equipos, frames_ts, cfg)
    if seccion == "consolidacion":
        return len(trayectorias)  # consolidar FUNDE trayectorias
    # interpolar AÑADE posiciones. Cada trayectoria es una lista de
    # (frame_idx, pos, es_real), así que se cuentan las observaciones.
    return sum(len(t) for t in trayectorias)


@pytest.mark.parametrize("seccion", EJERCITABLES)
def test_apagar_el_interruptor_CAMBIA_el_resultado(seccion):
    """La prueba que la verificación adversarial NO pudo esquivar.

    No mira el código: corre el pipeline dos veces sobre el mismo caché y
    exige que el resultado cambie. Si alguien deja de leer `activa`, los
    dos casos dan lo mismo y esto falla.
    """
    encendido, apagado = _medir(seccion, True), _medir(seccion, False)
    assert apagado != encendido, (
        f"{seccion}.activa NO HACE NADA: con true da {encendido} y con false "
        f"da {apagado}. O el código no lee la clave (el bug del 27-ago-2026) "
        "o el caso de prueba ya no la ejercita."
    )


# ══════════════════ escalado_resolucion.jitter_px en el perfil bytetrack ══════════════════
#
# El 16-oct-2026 (docs/plan_ablacion_1a1.md) se vio que cambiar `jitter_px` de 3,5 a 2,2
# daba el CSV de producción IDÉNTICO byte a byte. La causa: `perfiles._perfil_bytetrack`
# lee `cfg_tracking["_resolucion"]` («lo inyecta el processor») y NADIE escribe esa clave.
# El processor construye la resolución, pero solo se la pasa a `postprocesar`. Así que el
# cosido por pureza corre SIN márgenes locales y `jitter_px` no lo lee nadie en producción:
# es el patrón del interruptor que no apaga nada, con un número en vez de un `activa`.
#
# Dos tests, y hacen falta los dos:
# 1. el caso sintético SÍ ejerce el margen cuando la resolución llega al cosido (si no,
#    el test 2 podría «no cambiar nada» porque el caso está mal hecho, no por el cableado);
# 2. por el camino de PRODUCCIÓN (`procesar_desde_cache`), hoy NO cambia: xfail ESTRICTO.
#    El día que alguien cablee la resolución al cosido, este test pasará, el xfail estricto
#    lo convertirá en fallo y obligará a quitar el xfail y a leer
#    docs/plan_resolucion_en_cosido.md, que dice si ese cambio se midió y qué dio.

_HOMOGRAFIA_BENJA = "data/calibracion_benja/homografia_benja.npy"


def _caja_px(homografia_inv, x, y):
    """Caja de 10×30 px con el pie en la proyección de (x, y) metros."""
    import numpy as np

    v = homografia_inv @ np.array([x, y, 1.0])
    u, w = v[:2] / v[2]
    return (u - 5, w - 30, u + 5, w)


def _cache_jugador_del_fondo(salto_m=8.5):
    """Un jugador en el FONDO (x=55 m, ~0,42 m/píxel) que desaparece 2,5 s y vuelve
    `salto_m` más allá, más un testigo quieto cerca de la cámara.

    Las cuentas (tracking_benja.yaml, cosido_pureza): hueco 2,5 s → tolerancia
    1,5 + 2,5·2,5 = 7,75 m. A 8,5 m NO se cose sin márgenes; con jitter 3,5 px el
    margen local es 3,5 × 0,42 ≈ 1,46 m → tolerancia 9,2 m y SÍ se cose. El hueco
    (2,5 s) supera el buffer de ByteTrack (2,0 s), así que llegan como dos fragmentos.
    """
    import numpy as np

    h_inv = np.linalg.inv(np.load(_HOMOGRAFIA_BENJA))
    cache = []
    for k in range(46):  # t = 0 … 4,5 s, dt = 0,1 s (fps 30, 1 de cada 3)
        t = round(k * 0.1, 3)
        dets = []
        if t <= 1.5:
            dets.append((55.0, 20.0, *_caja_px(h_inv, 55.0, 20.0), 0.9))
        elif t >= 4.0:
            y = 20.0 + salto_m
            dets.append((55.0, y, *_caja_px(h_inv, 55.0, y), 0.9))
        dets.append((20.0, 10.0, *_caja_px(h_inv, 20.0, 10.0), 0.9))
        cache.append({"frame_idx": 3 * k, "t": t, "dets": dets})
    return cache


def _cfg_tracking_benja(jitter_px):
    cfg = yaml.safe_load(open("configs/tracking_benja.yaml"))
    # El filtro físico mira la anchura en metros de cada caja: el caso sintético no
    # intenta parecer una persona, así que se aparta para aislar el cosido.
    cfg["plausibilidad_fisica"] = {"activo": False}
    cfg["escalado_resolucion"] = {**cfg["escalado_resolucion"], "jitter_px": jitter_px}
    return cfg


def test_el_caso_sintetico_SI_ejerce_el_margen_si_la_resolucion_llega():
    """Control del caso: con la resolución pasada a mano, jitter_px cambia el cosido."""
    import numpy as np

    from src.tracking.asociacion_bytetrack import (
        ParametrosByteTrack,
        asociar_con_bytetrack,
    )
    from src.tracking.cosido_pureza import ParametrosCosidoPureza, coser_por_pureza
    from src.tracking.resolucion import ResolucionCampo

    cfg = _cfg_tracking_benja(3.5)
    cache = _cache_jugador_del_fondo()
    fragmentos = asociar_con_bytetrack(
        cache, 30.0, 3, ParametrosByteTrack.desde_dict(cfg["bytetrack"])
    )
    assert len(fragmentos) == 3, "el caso tiene que llegar al cosido en 3 trozos"
    resolucion = ResolucionCampo(np.load(_HOMOGRAFIA_BENJA), 62.0, 40.0, 2.0)
    params = ParametrosCosidoPureza.desde_dict(cfg["cosido_pureza"])
    sin_margen = coser_por_pureza(
        fragmentos, None, params, resolucion=resolucion, jitter_px=0.0, dt=0.1
    )
    con_margen = coser_por_pureza(
        fragmentos, None, params, resolucion=resolucion, jitter_px=3.5, dt=0.1
    )
    assert (len(sin_margen), len(con_margen)) == (3, 2)


def _identidades_por_produccion(tmp_path, jitter_px):
    """Corre `procesar_desde_cache` (el camino de producción) y cuenta identidades."""
    import pickle

    import pandas as pd

    from src.tracking_data.processor import procesar_desde_cache

    d = tmp_path / f"jitter_{jitter_px}"
    d.mkdir()
    pickle.dump(
        {
            "cache": _cache_jugador_del_fondo(),
            "fps": 30.0,
            "sample": 3,
            "wh": (1920, 1080),
        },
        open(d / "cache.pkl", "wb"),
    )
    yaml.safe_dump(_cfg_tracking_benja(jitter_px), open(d / "tracking.yaml", "w"))
    cfg = {
        "modo": "desde_cache",
        "tracking": {"perfil": "bytetrack"},
        "config_tracking": str(d / "tracking.yaml"),
        "equipos": {"activo": False},
        "campo_m": {"largo": 62.0, "ancho": 40.0, "margen": 5.0},
        "rutas": {
            "cache": str(d / "cache.pkl"),
            "cache_colores": str(d / "no_hay_colores.pkl"),
            "homografia": _HOMOGRAFIA_BENJA,
            "salida_csv": str(d / "posiciones.csv"),
            "salida_meta": str(d / "meta.json"),
        },
    }
    procesar_desde_cache(cfg)
    return pd.read_csv(d / "posiciones.csv").id_jugador.nunique()


@pytest.mark.xfail(
    strict=True,
    reason="HOY jitter_px no llega al cosido del perfil bytetrack: nadie inyecta "
    "`_resolucion` (docs/plan_resolucion_en_cosido.md). Si esto pasa, alguien lo ha "
    "cableado: quitar el xfail y comprobar que el cambio se midió en las dos patas.",
)
def test_jitter_px_CAMBIA_la_salida_de_produccion_con_bytetrack(tmp_path):
    con_margen = _identidades_por_produccion(tmp_path, 3.5)
    sin_margen = _identidades_por_produccion(tmp_path, 0.0)
    assert con_margen != sin_margen, (
        f"jitter_px no hace nada en producción: {con_margen} identidades con 3,5 px "
        f"y {sin_margen} con 0. El cosido no recibe la resolución."
    )
