"""Ningún renderizador puede COLAPSAR lo que el CSV trae por observación.

El CSV de posiciones lleva una etiqueta POR OBSERVACIÓN desde que se
adoptó `etiquetar_por_observacion` (15,5 % → 3,2 % de observaciones con
el equipo equivocado). El 27-ago-2026 se descubrió que el replay la
reducía a una sola por identidad con `grupo["etiqueta"].mode()` y pintaba
esa en todos los frames: el visor deshacía la mejora del pipeline, y se
estaba juzgando al clasificador por un fallo del renderizador
(`docs/pizarra_colapsaba.md`).

> **Una herramienta de diagnóstico que resume puede mentir sobre el
> sistema que diagnostica.**

Es el mismo fallo que el "✓ engañoso" del caché vacío y que la guarda que
CUENTA en vez de comprobar QUIÉN: el instrumento daba una respuesta
tranquilizadora sobre algo que no había mirado.

⚠️ **ESTE FICHERO ES LA GUARDA. Todo renderizador nuevo que consuma el
CSV de posiciones tiene que añadir aquí su caso.** El contrato es uno y
se enuncia en una frase: si dos observaciones de la MISMA identidad
tienen etiquetas distintas, la salida tiene que reflejar las dos.
"""

import json
import re

import pandas as pd
import pytest

# Identidad que empieza en A y acaba en B. La moda es B: un renderizador
# que colapse pintará B también en las primeras muestras, que es
# exactamente el fallo.
ETIQUETAS = ["A"] * 10 + ["B"] * 30


@pytest.fixture
def csv_identidad_que_cambia(tmp_path):
    filas = [
        {
            "frame": i * 3,
            "tiempo_s": round(i * 0.1, 2),
            "id_jugador": 1,
            "equipo": 0,
            "etiqueta": e,
            "x_m": 30.0,
            "y_m": 20.0,
            "es_real": 1,
        }
        for i, e in enumerate(ETIQUETAS)
    ]
    ruta = tmp_path / "posiciones.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    return ruta


def test_el_csv_de_prueba_tiene_una_moda_QUE_ENGANA(csv_identidad_que_cambia):
    """Control del propio test: si la moda no engañara, no probaría nada."""
    df = pd.read_csv(csv_identidad_que_cambia)
    assert df.etiqueta.mode().iloc[0] == "B"
    assert df.etiqueta.iloc[0] == "A", "la primera observación debe diferir de la moda"


def test_LA_PIZARRA_no_colapsa(csv_identidad_que_cambia, tmp_path):
    """El replay táctico tiene que llevar la etiqueta de cada muestra."""
    from src.report.replay_tactico import generar_replay

    salida = tmp_path / "r.html"
    generar_replay(
        csv_identidad_que_cambia, salida, largo=62.0, ancho=40.0, min_vida_s=0.0
    )
    html = salida.read_text()
    datos = json.loads(re.search(r"const DATOS = (\[.*?\]);", html, re.S).group(1))
    catalogo = json.loads(
        re.search(r"const CATALOGO = (\[.*?\]);", html, re.S).group(1)
    )
    ident = datos[0]
    assert "ets" in ident, (
        "el replay COLAPSÓ la etiqueta por observación: una identidad que "
        "cambia de equipo tiene que llevar el array por muestra"
    )
    pintadas = [catalogo[i] for i in ident["ets"]]
    assert set(pintadas) == {"A", "B"}
    assert pintadas[0] == "A", "al principio pinta la etiqueta del INSTANTE, no la moda"


def test_EL_VIDEO_no_colapsa(csv_identidad_que_cambia):
    """El vídeo con cajas indexa por frame; nunca tuvo el bug, y se blinda.

    No se renderiza un vídeo (necesitaría el vídeo real): se comprueba el
    índice que `dibujar_frame` consume, que es donde vivía el riesgo.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from generar_video_detecciones import cargar_tracking

    indice = cargar_tracking(csv_identidad_que_cambia, homografia=None)
    # La etiqueta del primer frame y la del último tienen que diferir.
    frames = sorted(indice)
    primera = indice[frames[0]][0][3]
    ultima = indice[frames[-1]][0][3]
    assert primera == "A", (
        "el vídeo COLAPSÓ la etiqueta por observación: en el primer frame "
        f"debería pintar A y pinta {primera}"
    )
    assert ultima == "B"


def test_los_dos_renderizadores_coinciden_entre_si(csv_identidad_que_cambia, tmp_path):
    """Vídeo y pizarra tienen que contar LA MISMA historia.

    Si divergen, uno de los dos miente y no se sabe cuál: el diagnóstico
    deja de servir para decidir nada.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from generar_video_detecciones import cargar_tracking

    from src.report.replay_tactico import generar_replay

    salida = tmp_path / "r.html"
    generar_replay(
        csv_identidad_que_cambia, salida, largo=62.0, ancho=40.0, min_vida_s=0.0
    )
    html = salida.read_text()
    datos = json.loads(re.search(r"const DATOS = (\[.*?\]);", html, re.S).group(1))
    catalogo = json.loads(
        re.search(r"const CATALOGO = (\[.*?\]);", html, re.S).group(1)
    )
    del_replay = [catalogo[i] for i in datos[0]["ets"]]

    indice = cargar_tracking(csv_identidad_que_cambia, homografia=None)
    del_video = [indice[f][0][3] for f in sorted(indice)]

    assert del_replay == del_video, (
        "la pizarra y el vídeo pintan etiquetas distintas para las mismas "
        "observaciones"
    )
    assert del_video == ETIQUETAS


def test_una_identidad_PURA_no_paga_el_arreglo(tmp_path):
    """La mayoría de identidades son puras: el HTML no debe engordar."""
    from src.report.replay_tactico import generar_replay

    filas = [
        {
            "frame": i * 3,
            "tiempo_s": round(i * 0.1, 2),
            "id_jugador": 1,
            "etiqueta": "A",
            "x_m": 30.0,
            "y_m": 20.0,
            "es_real": 1,
        }
        for i in range(40)
    ]
    ruta = tmp_path / "puras.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False)
    salida = tmp_path / "r.html"
    generar_replay(ruta, salida, largo=62.0, ancho=40.0, min_vida_s=0.0)
    datos = json.loads(
        re.search(r"const DATOS = (\[.*?\]);", salida.read_text(), re.S).group(1)
    )
    assert datos[0]["et"] == "A" and "ets" not in datos[0]


# ── Y una guarda de la misma familia: el ✓ del vídeo (27-ago-2026) ────
#
# Al re-renderizar la parte entera, el escritor de OpenCV reventó cerca
# del final ("Failed to write AVI file: chunk size is out of bounds") y
# el proceso, corriendo con `| tail`, salió con estado 0. Contar los
# frames ENVIADOS al escritor no prueba que estén en el disco.


def test_el_video_se_RELEE_antes_de_dar_el_visto_bueno():
    """El script tiene que verificar el fichero, no fiarse del contador."""
    from pathlib import Path

    codigo = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "generar_video_detecciones.py"
    ).read_text()
    assert "cv2.VideoCapture(str(ruta_salida))" in codigo, (
        "generar_video_detecciones.py ya no relee el vídeo antes del ✓: un "
        "fichero truncado volvería a darse por bueno"
    )
    assert "salió TRUNCADO" in codigo


# ── LA GUARDA DE VERDAD: registro con DESCUBRIMIENTO (27-ago-2026) ────
#
# La primera versión de esta guarda buscaba el texto `etiqueta"].mode()`.
# Una revisión adversarial la esquivó de CUATRO formas sin esfuerzo —
# `.agg(lambda x: x.mode().iloc[0])`, `scipy.stats.mode(...)`,
# `.value_counts().index[0]`, y hasta un espacio antes del punto— y
# además el `glob` no entraba en subdirectorios: bastaba mover el fichero.
#
# > Comprobaba una ORTOGRAFÍA, no un COMPORTAMIENTO.
#
# Es el primo hermano de "una guarda que CUENTA no puede detectar un fallo
# de IDENTIDAD". Así que se invierte: en vez de buscar el patrón
# prohibido, se DESCUBREN los módulos que traducen una etiqueta a un
# color —que es lo que puede mentir— y se exige que cada uno esté
# clasificado. Un renderizador nuevo falla **por omisión**.

# Módulos que pintan y tienen adaptador: se les corre la prueba de
# comportamiento (una identidad que cambia de etiqueta tiene que salir
# con las dos).
RENDERIZADORES = (
    "src/report/replay_tactico.py",
    "scripts/generar_video_detecciones.py",
)

# Módulos que traducen etiqueta→color pero NO pintan una ficha por
# observación. Cada uno necesita su motivo: clasificar es una decisión
# humana, no una heurística.
NO_PINTAN_POR_OBSERVACION = {
    "src/report/informe_v2.py": "agrega en heatmaps y medias, no pinta una ficha por observación",
    "scripts/generar_replay.py": "es la CLI de replay_tactico, no pinta nada por su cuenta",
    "scripts/gt_a_replay.py": "pinta el GROUND TRUTH, que no lleva etiqueta del sistema",
    "scripts/comparar_instante.py": "pinta UN instante: no hay vida de identidad que colapsar",
    "scripts/deriva_parte_entera.py": "banco de medida; solo lee los colores del fit para informar",
    "scripts/etiquetar_equipos_gt.py": "herramienta de etiquetado manual, no pinta el sistema",
}


def _modulos_que_traducen_etiqueta_a_color():
    """Descubre, recursivamente, quién puede cometer este fallo."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    encontrados = []
    for carpeta in ("src/report", "scripts"):
        for ruta in sorted((raiz / carpeta).rglob("*.py")):
            texto = ruta.read_text()
            if "etiqueta" not in texto:
                continue
            if not any(
                marca in texto
                for marca in ("colores_equipo", "_hex_a_bgr", "COLORES[", "paleta")
            ):
                continue
            encontrados.append(str(ruta.relative_to(raiz)))
    return set(encontrados)


def test_todo_modulo_QUE_PINTA_esta_clasificado():
    """Un renderizador nuevo falla POR OMISIÓN, no por su ortografía."""
    descubiertos = _modulos_que_traducen_etiqueta_a_color()
    clasificados = set(RENDERIZADORES) | set(NO_PINTAN_POR_OBSERVACION)
    nuevos = descubiertos - clasificados
    assert not nuevos, (
        f"módulos que traducen etiqueta→color y NADIE ha clasificado: {sorted(nuevos)}. "
        "Si pintan una ficha por observación, añádelos a RENDERIZADORES y dales "
        "un adaptador para la prueba de comportamiento; si no, a "
        "NO_PINTAN_POR_OBSERVACION con el motivo. Ver docs/pizarra_colapsaba.md"
    )
    fantasmas = clasificados - descubiertos
    assert not fantasmas, (
        f"clasificados pero ya no existen (o dejaron de pintar): {sorted(fantasmas)}. "
        "Quítalos de la lista para que no dé una falsa sensación de cobertura."
    )
