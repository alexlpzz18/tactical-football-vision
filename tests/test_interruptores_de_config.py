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
