"""Todo interruptor `activa:` de un config tiene que APAGAR algo de verdad.

El 27-ago-2026 una auditoría de guardas encontró que `cota_plantilla.activa`
y `exclusion_espacial.activa` estaban a `false` en los cuatro configs de
tracking y `src/tracking/perfiles.py` **nunca leía la clave**: las dos
fusiones corrían igual. La misma función sí la leía para consolidación e
interpolación, así que era puro despiste. Medido: el perfil `candidato`
pasaba de 106 identidades a 58 por dos fusiones que se creían apagadas —
una de ellas la cota de plantilla, que es el fracaso canónico del proyecto.

Estaba DORMIDO (los dos configs de producción usan `perfil: bytetrack`,
que no pasa por esa rama) pero habría mordido al primero que probara
`candidato` creyendo que la cota estaba fuera.

⚠️ POR QUÉ ESTE TEST Y NO OTRO. Se probó antes la vía obvia —comprobar que
ninguna clave de config quede sin mencionar en el código— y **NO habría
cazado el bug**: `activa` sí aparece en `perfiles.py`, solo que en otras
dos ramas. Es una omisión de CAMINO, no una clave huérfana. Por eso este
test es de COMPORTAMIENTO: no mira si la palabra está escrita, mira si
cambiar el interruptor cambia el resultado.

Es el criterio de Alex: *"si una guarda se puede esquivar renombrando
algo, no es una guarda"*.
"""

import glob
import re

import pytest
import yaml

# Cada interruptor con la prueba de que apaga algo. Un interruptor nuevo
# que no esté aquí hace fallar el test: se entera por omisión, no por
# tener la ortografía correcta.
INTERRUPTORES = {
    # Se leen en perfiles.py y tienen prueba de comportamiento abajo.
    "exclusion_espacial": "candidato",
    "cota_plantilla": "candidato",
    "consolidacion": "postproceso",
    "interpolacion": "postproceso",
    # Se leen en OTRO sitio, comprobado: `activa` vive dentro de los propios
    # parámetros (puerta_reentrada.py:164, `if not params.activa`) y en el
    # banco (scripts/evaluar_tracking.py:237). Aparecieron gracias a este
    # test, que es exactamente para lo que está.
    "puerta_reentrada": "dentro de sus parametros",
    "segunda_pasada": "banco de evaluacion",
}


def _secciones_con_interruptor():
    """{sección: [configs donde aparece]} de todo `activa:` de configs/."""
    encontradas = {}
    for ruta in sorted(glob.glob("configs/*.yaml")):
        try:
            datos = yaml.safe_load(open(ruta))
        except yaml.YAMLError:  # pragma: no cover - config roto ya lo caza otro test
            continue
        if not isinstance(datos, dict):
            continue
        for seccion, valor in datos.items():
            if isinstance(valor, dict) and "activa" in valor:
                encontradas.setdefault(seccion, []).append(ruta)
    return encontradas


def test_todo_interruptor_activa_esta_registrado():
    """Un interruptor nuevo sin prueba de comportamiento falla POR OMISIÓN."""
    encontradas = set(_secciones_con_interruptor())
    nuevos = encontradas - set(INTERRUPTORES)
    assert not nuevos, (
        f"secciones con `activa:` que nadie ha comprobado que apaguen algo: "
        f"{sorted(nuevos)}. Añádelas a INTERRUPTORES y escribe la prueba de "
        "que poner activa: false cambia el resultado. Un interruptor que no "
        "apaga nada es peor que no tenerlo: da una falsa sensación de control."
    )
    fantasmas = set(INTERRUPTORES) - encontradas
    assert (
        not fantasmas
    ), f"registrados pero ya no existen en ningún config: {sorted(fantasmas)}"


def test_la_rama_candidato_LEE_el_interruptor():
    """El bug exacto del 27-ago: leer `cota` y `coste_max` pero no `activa`."""
    import inspect

    from src.tracking import perfiles

    codigo = inspect.getsource(perfiles)
    # Cada sección con interruptor que se consume en perfiles.py tiene que
    # aparecer junto a una lectura de `activa`, no solo de sus parámetros.
    for seccion in ("exclusion_espacial", "cota_plantilla"):
        assert re.search(
            r'cfg_\w+\s*=\s*cfg_tracking\.get\(\s*"%s"' % seccion, codigo
        ), f"{seccion} ya no se lee de cfg_tracking; revisa este test"
    lecturas = codigo.count('get("activa"')
    assert lecturas >= 4, (
        f"solo {lecturas} lecturas de `activa` en perfiles.py: hay cuatro "
        "secciones con interruptor (exclusion_espacial, cota_plantilla, "
        "consolidacion, interpolacion) y todas tienen que respetarlo"
    )


@pytest.mark.parametrize("seccion", ["exclusion_espacial", "cota_plantilla"])
def test_apagar_el_interruptor_CAMBIA_el_resultado(seccion):
    """La prueba de comportamiento: con `activa: false` no debe fusionar.

    Se construyen identidades duplicadas a propósito —dos que son la misma
    persona— y se comprueba que el perfil `candidato` las funde con el
    interruptor puesto y NO las funde con el interruptor quitado. Si el
    código dejara de leer `activa`, los dos casos darían lo mismo y esto
    falla.
    """
    import numpy as np

    from src.tracking.perfiles import correr_perfil

    # Cada interruptor fusiona un caso DISTINTO, así que el caché también:
    #  - exclusión espacial: dos identidades CO-UBICADAS en frames comunes
    #    (la misma persona detectada dos veces).
    #  - cota de plantilla: dos identidades ENTRELAZADAS (observaciones
    #    alternadas, nunca a la vez).
    cache = []
    for f in range(0, 120, 3):
        if seccion == "exclusion_espacial":
            dets = [
                (10.0, 20.0, 0, 0, 10, 30, 0.9),
                (10.3, 20.1, 0, 0, 10, 30, 0.9),
            ]
        else:
            dets = [
                (
                    (10.0, 20.0, 0, 0, 10, 30, 0.9)
                    if (f // 3) % 2 == 0
                    else (10.4, 20.2, 0, 0, 10, 30, 0.9)
                )
            ]
        dets.append((40.0, 20.0, 0, 0, 10, 30, 0.9))
        cache.append({"frame_idx": f, "t": f / 30.0, "dets": dets})

    base = yaml.safe_load(open("configs/tracking.yaml"))

    def correr(activa):
        cfg = {**base}
        cfg[seccion] = {**base.get(seccion, {}), "activa": activa}
        # El otro interruptor, siempre apagado, para aislar el que se prueba.
        otro = (
            "cota_plantilla"
            if seccion == "exclusion_espacial"
            else "exclusion_espacial"
        )
        cfg[otro] = {**base.get(otro, {}), "activa": False}
        if seccion == "cota_plantilla":
            cfg[seccion] = {**cfg[seccion], "cota": 1, "coste_max": 40.0}
        return len(correr_perfil(cache, 30.0, 3, cfg, perfil="candidato"))

    encendido, apagado = correr(True), correr(False)
    assert apagado >= encendido, (
        f"{seccion}: apagarlo no puede dar MENOS identidades "
        f"(apagado={apagado}, encendido={encendido})"
    )
    assert apagado != encendido, (
        f"{seccion}.activa NO HACE NADA: con true da {encendido} identidades "
        f"y con false da {apagado}. O el código no lee la clave (el bug del "
        "27-ago-2026) o el caso de prueba ya no la ejercita."
    )
    assert np is not None
