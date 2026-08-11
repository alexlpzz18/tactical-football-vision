"""Cosido de fragmentos con criterio de PUREZA, sin cupo de plantilla.

ByteTrack fragmenta mucho (237 identidades para 23 personas en el tramo
de validación) pero casi nunca mezcla (5 quimeras frente a nuestras 24).
Este módulo aprovecha esa propiedad: recupera cobertura uniendo trozos
del mismo jugador, con el compromiso explícito de NO estropear la pureza
que hace valioso el punto de partida.

Por qué no se reutiliza `stitcher.py`: aquel cose para llegar a un número
de identidades, y su selección golosa une siempre que encuentra un
candidato tolerable. Aquí el objetivo es el contrario, y eso cambia tres
cosas de fondo:

1. **Veto de ambigüedad.** Si el segundo mejor candidato compite con el
   mejor, NO se cose. En un campo con 22 personas parecidas, un empate
   significa que no sabemos cuál de los dos es, y unir a ciegas es
   exactamente como se fabrica una quimera. Ante la duda, fragmentar:
   fragmentar es recuperable, mezclar no.
2. **Mejor mutuo.** A se une a B solo si B es el mejor candidato de A y A
   es el mejor candidato de B. Evita las cadenas oportunistas.
3. **Prohibido el solape temporal.** Dos fragmentos que coexisten en
   algún frame son, por definición, dos personas distintas: nadie está en
   dos sitios a la vez. `stitcher.py` no lo comprueba porque sus
   tracklets vienen de una etapa que ya lo garantizaba.

No hay cota de plantilla y no la habrá: el número de identidades es un
proxy, la pureza es la métrica (ver docs/experimentos_tracking.md,
"¿Aporta nuestro tracking sobre un tracker estándar?").
"""

import bisect
import logging
from dataclasses import dataclass

import numpy as np

from src.tracking.field_tracker import Tracklet

logger = logging.getLogger(__name__)


@dataclass
class ParametrosCosidoPureza:
    """Parámetros del cosido por pureza.

    Los defaults son deliberadamente conservadores: se prefiere dejar
    cobertura sobre la mesa a contaminar una identidad.
    """

    activo: bool = True
    # Hueco temporal máximo entre el final de A y el inicio de B.
    max_hueco: float = 4.0
    # Tolerancia espacial: crece con el hueco (más tiempo, más incertidumbre).
    tol_base: float = 1.5
    tol_por_seg: float = 2.5
    # Veto físico: velocidad que exigiría el salto. Un jugador no corre
    # más de esto, así que por encima no es el mismo jugador.
    v_max_salto: float = 8.0
    # Veto de color: distancia entre firmas por encima de la cual son
    # personas distintas (equipaciones diferentes).
    # Medido: sin veto de color (99) las quimeras suben de 5 a 9.
    color_max_dist: float = 1.2
    peso_color: float = 0.5
    peso_hueco: float = 0.3
    # ── El corazón del criterio de pureza ──
    # Si el segundo mejor candidato tiene un coste menor que
    # mejor · (1 + margen_ambiguedad), la unión se descarta por dudosa.
    # Medido: sin veto (0,0) las quimeras suben de 5 a 11 con la misma
    # cobertura; 0,15 es el punto donde se recupera cobertura sin pagarlo.
    margen_ambiguedad: float = 0.15
    # Solape temporal tolerado (en frames comunes). 0 = ninguno.
    solape_max_frames: int = 0
    # Hueco ampliado SOLO para uniones con firma de color exigente: una
    # oclusión larga tras un cruce deja un hueco que el hueco normal no
    # alcanza, pero alargarlo para todo el mundo mete quimeras (medido).
    # Con las dos firmas presentes y muy parecidas, el riesgo baja.
    max_hueco_con_firma: float = 0.0  # 0 = desactivado
    color_estricto: float = 0.6
    # Pasadas: tras coser, los extremos cambian y aparecen uniones nuevas.
    max_pasadas: int = 3

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosCosidoPureza":
        if not d:
            return cls()
        conocidos = {c: d[c] for c in cls.__dataclass_fields__ if c in d}
        return cls(**conocidos)


def _extremos(identidad: list[Tracklet]) -> tuple[float, float, np.ndarray, np.ndarray]:
    """(t_inicio, t_fin, pos_inicio, pos_fin) de una identidad completa."""
    tracklets = sorted(identidad, key=lambda tr: tr.ts[0])
    return (
        tracklets[0].ts[0],
        tracklets[-1].ts[-1],
        tracklets[0].pos[0],
        tracklets[-1].pos[-1],
    )


def _velocidad_final(identidad: list[Tracklet], ventana: int = 3) -> np.ndarray:
    """Velocidad al final de la identidad, promediando las últimas obs.

    No se usa `Tracklet.vel` porque la identidad puede ser una cadena de
    varios tracklets y lo que interesa es cómo se movía al final de todo.
    """
    ultimo = max(identidad, key=lambda tr: tr.ts[-1])
    if len(ultimo.ts) < 2:
        return np.zeros(2)
    n = min(ventana, len(ultimo.ts) - 1)
    dt = ultimo.ts[-1] - ultimo.ts[-1 - n]
    if dt <= 0:
        return np.zeros(2)
    return (ultimo.pos[-1] - ultimo.pos[-1 - n]) / dt


def _frames_de(identidad: list[Tracklet]) -> set[int]:
    return {f for tr in identidad for f, _ in tr.det_idxs}


def _firma_color(identidad: list[Tracklet], colores: dict | None) -> np.ndarray | None:
    """Color medio de la identidad, o None si no hay recortes."""
    if colores is None:
        return None
    muestras = [
        colores[par] for tr in identidad for par in tr.det_idxs if par in colores
    ]
    return np.mean(muestras, axis=0) if muestras else None


def coser_por_pureza(
    identidades: list[list[Tracklet]],
    colores: dict | None = None,
    params: ParametrosCosidoPureza | None = None,
    resolucion=None,
    jitter_px: float = 3.5,
    dt: float = 0.12,
) -> list[list[Tracklet]]:
    """Une fragmentos del mismo jugador sin fabricar quimeras.

    Args:
        identidades: fragmentos (cada uno, lista de Tracklet).
        colores: caché {(frame_idx, det_idx): feature} para las firmas.
        params: ver ParametrosCosidoPureza.
        resolucion: ResolucionCampo opcional. Con ella, la tolerancia
            espacial y el veto de velocidad se relajan en las zonas donde
            un píxel vale más metros — si no, en el fondo del campo el
            ruido de proyección impide coser nada.
        jitter_px, dt: para traducir ese ruido a metros y m/s.

    Returns:
        Identidades cosidas (cada una, lista de Tracklet ordenada).
    """
    params = params or ParametrosCosidoPureza()
    if not params.activo or len(identidades) < 2:
        return identidades

    actuales = [list(ident) for ident in identidades]
    firmas = [_firma_color(ident, colores) for ident in actuales]
    n_inicial = len(actuales)

    for pasada in range(params.max_pasadas):
        uniones = _uniones_de_una_pasada(
            actuales, firmas, params, resolucion, jitter_px, dt
        )
        if not uniones:
            break
        actuales, firmas = _aplicar(actuales, firmas, uniones)
        logger.debug(
            "Cosido por pureza, pasada %d: %d uniones → %d identidades",
            pasada + 1,
            len(uniones),
            len(actuales),
        )

    logger.info(
        "Cosido por pureza: %d → %d identidades (sin cota de plantilla)",
        n_inicial,
        len(actuales),
    )
    return actuales


def _uniones_de_una_pasada(
    identidades, firmas, params, resolucion, jitter_px, dt
) -> dict[int, int]:
    """{i: j} uniones aceptadas: j continúa a i. Solo las inequívocas."""
    extremos = [_extremos(ident) for ident in identidades]
    velocidades = [_velocidad_final(ident) for ident in identidades]
    frames = [_frames_de(ident) for ident in identidades]

    orden = sorted(range(len(identidades)), key=lambda i: extremos[i][0])
    inicios = [extremos[i][0] for i in orden]

    # Para cada i, los dos mejores candidatos; y lo mismo visto desde j.
    mejores: dict[int, list[tuple[float, int]]] = {}
    for i in range(len(identidades)):
        _t_ini_a, t_fin_a, _p_ini_a, p_fin_a = extremos[i]
        desde = bisect.bisect_right(inicios, t_fin_a)
        hasta = bisect.bisect_right(inicios, t_fin_a + params.max_hueco)
        candidatos = []
        for k in range(desde, hasta):
            j = orden[k]
            if i == j:
                continue
            coste = _coste(
                i,
                j,
                extremos,
                velocidades,
                frames,
                firmas,
                params,
                resolucion,
                jitter_px,
                dt,
            )
            if coste is not None:
                candidatos.append((coste, j))
        if candidatos:
            mejores[i] = sorted(candidatos)[:2]

    # Mejor candidato de cada j mirando hacia atrás (para el mejor mutuo)
    mejor_hacia_atras: dict[int, list[tuple[float, int]]] = {}
    for i, lista in mejores.items():
        for coste, j in lista:
            mejor_hacia_atras.setdefault(j, []).append((coste, i))

    uniones: dict[int, int] = {}
    usados_como_continuacion: set[int] = set()
    for i, lista in sorted(mejores.items(), key=lambda kv: kv[1][0][0]):
        mejor_coste, j = lista[0]
        # (1) veto de ambigüedad hacia delante
        if len(lista) > 1 and lista[1][0] < mejor_coste * (
            1 + params.margen_ambiguedad
        ):
            continue
        # (2) veto de ambigüedad hacia atrás: ¿hay otro que también
        #     querría continuar en j, con un coste comparable?
        atras = sorted(mejor_hacia_atras.get(j, []))
        if not atras or atras[0][1] != i:
            continue  # no es mejor mutuo
        if len(atras) > 1 and atras[1][0] < atras[0][0] * (
            1 + params.margen_ambiguedad
        ):
            continue
        if j in usados_como_continuacion or j in uniones.get(i, ()):
            continue
        if i in usados_como_continuacion:
            continue
        uniones[i] = j
        usados_como_continuacion.add(j)
    return uniones


def _coste(
    i, j, extremos, velocidades, frames, firmas, params, resolucion, jitter_px, dt
) -> float | None:
    """Coste de que j continúe a i, o None si algún veto lo prohíbe."""
    _t_ini_a, t_fin_a, _p_ini_a, p_fin_a = extremos[i]
    t_ini_b, _t_fin_b, p_ini_b, _p_fin_b = extremos[j]

    hueco = t_ini_b - t_fin_a
    if hueco <= 0:
        return None
    if hueco > params.max_hueco:
        # Puerta estrecha para huecos largos: solo si AMBOS tienen firma
        # de color y son casi el mismo color.
        if params.max_hueco_con_firma <= params.max_hueco:
            return None
        if hueco > params.max_hueco_con_firma:
            return None
        if firmas[i] is None or firmas[j] is None:
            return None
        if float(np.linalg.norm(firmas[i] - firmas[j])) > params.color_estricto:
            return None

    # Veto duro: dos fragmentos que coexisten son dos personas.
    if len(frames[i] & frames[j]) > params.solape_max_frames:
        return None

    # Márgenes locales: en el fondo del campo, el ruido de proyección
    # hace que dos observaciones del MISMO jugador se separen metros.
    margen_m, margen_v = 0.0, 0.0
    if resolucion is not None:
        margen_m = resolucion.metros_por_pixel(p_fin_a) * jitter_px
        margen_v = resolucion.velocidad_ruido(p_fin_a, jitter_px, dt)

    prediccion = p_fin_a + velocidades[i] * hueco
    dist = float(np.linalg.norm(prediccion - p_ini_b))
    tol = params.tol_base + params.tol_por_seg * hueco + margen_m
    if dist > tol:
        return None

    v_salto = float(np.linalg.norm(p_ini_b - p_fin_a) / hueco)
    if v_salto > params.v_max_salto + margen_v:
        return None

    coste_color = 0.0
    if firmas[i] is not None and firmas[j] is not None:
        dcol = float(np.linalg.norm(firmas[i] - firmas[j]))
        if dcol > params.color_max_dist:
            return None  # equipaciones incompatibles: no es la misma persona
        coste_color = dcol / params.color_max_dist

    return (
        dist / tol
        + params.peso_hueco * (hueco / params.max_hueco)
        + params.peso_color * coste_color
    )


def _aplicar(identidades, firmas, uniones):
    """Aplica las uniones {i: j} encadenando y devuelve la lista nueva."""
    destino = {}  # i → raíz de su cadena
    for i in uniones:
        destino[i] = i

    raiz = list(range(len(identidades)))

    def buscar(x):
        while raiz[x] != x:
            raiz[x] = raiz[raiz[x]]
            x = raiz[x]
        return x

    for i, j in uniones.items():
        ri, rj = buscar(i), buscar(j)
        if ri != rj:
            raiz[rj] = ri

    grupos: dict[int, list[int]] = {}
    for indice in range(len(identidades)):
        grupos.setdefault(buscar(indice), []).append(indice)

    nuevas, nuevas_firmas = [], []
    for miembros in grupos.values():
        fusionada = [tr for m in miembros for tr in identidades[m]]
        fusionada.sort(key=lambda tr: tr.ts[0])
        nuevas.append(fusionada)
        presentes = [firmas[m] for m in miembros if firmas[m] is not None]
        nuevas_firmas.append(np.mean(presentes, axis=0) if presentes else None)
    return nuevas, nuevas_firmas
