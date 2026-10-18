"""Desglose del error de los números de producto (centroide, anchura, recuento).

21-sep-2026 (docs/desglose_del_error.md). Pregunta de Alex: *«si ni el portero
ni el árbitro explican el ruido del recuento y el centroide, ¿QUÉ lo explica?»*

El método es una escalera de ORÁCULOS, como en `docs/oraculos.md`, pero sobre la
salida FINAL del sistema (el CSV de posiciones) y con cinco palancas que se
pueden arreglar por separado:

  LOC  localización : las filas casadas con una persona del GT se mueven a su
                      posición real (error de proyección/caja).
  LAB  identidad    : las filas casadas con una persona del GT pasan a llevar
                      su equipo verdadero (equipo equivocado, o mandada a
                      `otro`/`staff` siendo un jugador).
  EXT  sobrantes    : se quitan las filas etiquetadas A/B que NO corresponden a
                      ninguna persona del GT (árbitro, duplicados, fantasmas).
  MIS  faltantes    : se añaden las personas del GT que ninguna fila cubre.
  DES  desplazadas  : una persona sin fila Y una fila A/B sin persona, a ≤ 5 m una
                      de otra, son UNA fila mal colocada (no un faltante más un
                      sobrante): se quita la fila y se pone la persona en su sitio.
                      Es lo que EXT y MIS contarían de más si no se separase.

Con todas aplicadas el conjunto del equipo ES el del GT, así que el error
vale 0 por construcción (esa es la comprobación de que la escalera cierra).
Como los arreglos interactúan (quitar un sobrante mueve el centroide de otra
forma si además falta alguien), el reparto se hace con valores de SHAPLEY: el
promedio de la mejora de cada palanca sobre todos los órdenes posibles, de modo que
la suma de todas es EXACTAMENTE el error del sistema.

Esto mide contra el GT, que solo existe en una ventana corta. La extensión al
partido entero está en el script, con las suposiciones a la vista.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from math import factorial

import numpy as np

FACTORES = ("LOC", "LAB", "EXT", "MIS", "DES")
RADIO_PAREJA_M = 5.0  # a más de esto, una fila y una persona sin casar no son la misma
EQUIPOS = ("A", "B")
JUGADORES_POR_EQUIPO = 7  # fútbol 7, portero incluido


@dataclass
class Persona:
    """Una persona del GT con la fila del sistema que la cubre (si hay)."""

    equipo: str
    x: float
    y: float
    fila: int | None = None  # índice en las filas del frame; None = faltante


@dataclass
class FrameCasado:
    """Un frame con el GT, las filas del sistema y el casado 1-a-1 entre ellos."""

    frame: int
    personas: list[Persona]
    x: np.ndarray  # filas del sistema (todas, cualquier etiqueta)
    y: np.ndarray
    etiqueta: np.ndarray  # 'A' / 'B' / 'otro' / 'staff' (portero_X → X)
    persona_de_fila: dict[int, int]  # índice de fila → índice de persona
    # fila libre A/B ↔ persona sin fila que son «la misma» (desplazada ≤ RADIO_PAREJA_M)
    pareja_de_fila: dict[int, int] = field(default_factory=dict)


def equipo_de_etiqueta(etiqueta: str) -> str:
    """Los porteros cuentan con su equipo (definición de producto)."""
    e = str(etiqueta)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def casar_frame(
    frame: int,
    gt: list[tuple[str, float, float]],
    x: np.ndarray,
    y: np.ndarray,
    etiqueta: np.ndarray,
    radio: float,
    radio_pareja: float = RADIO_PAREJA_M,
) -> FrameCasado:
    """Casado 1-a-1 óptimo (húngaro) entre las personas del GT y TODAS las filas.

    Es el mismo protocolo que `scripts/comparar_escalas.py`: una fila no puede
    servir a dos personas, y fuera del radio no hay casado.
    """
    from scipy.optimize import linear_sum_assignment

    personas = [Persona(e, float(px), float(py)) for e, px, py in gt]
    persona_de_fila: dict[int, int] = {}
    if personas and len(x):
        coste = np.hypot(
            x[None, :] - np.array([p.x for p in personas])[:, None],
            y[None, :] - np.array([p.y for p in personas])[:, None],
        )
        coste = np.where(coste > radio, 1e6, coste)
        for i, j in zip(*linear_sum_assignment(coste)):
            if coste[i, j] < 1e6:
                personas[i].fila = int(j)
                persona_de_fila[int(j)] = int(i)
    etiquetas = np.array([equipo_de_etiqueta(e) for e in etiqueta], dtype=object)
    pareja = _emparejar_desplazadas(
        personas, x, y, etiquetas, persona_de_fila, radio_pareja
    )
    return FrameCasado(frame, personas, x, y, etiquetas, persona_de_fila, pareja)


def _emparejar_desplazadas(personas, x, y, etiquetas, persona_de_fila, radio_pareja):
    """Segunda pasada: personas sin fila con filas A/B sin persona, a ≤ `radio_pareja`."""
    from scipy.optimize import linear_sum_assignment

    sin_fila = [k for k, p in enumerate(personas) if p.fila is None]
    libres = [
        i for i in range(len(x)) if i not in persona_de_fila and etiquetas[i] in EQUIPOS
    ]
    if not sin_fila or not libres:
        return {}
    coste = np.array(
        [
            [np.hypot(x[i] - personas[k].x, y[i] - personas[k].y) for i in libres]
            for k in sin_fila
        ]
    )
    pareja = {}
    for a, b in zip(*linear_sum_assignment(coste)):
        if coste[a, b] <= radio_pareja:
            pareja[libres[b]] = sin_fila[a]
    return pareja


def conjunto_del_equipo(fc: FrameCasado, equipo: str, arreglos=frozenset()):
    """Puntos (N×2) que el sistema atribuye a `equipo` tras aplicar los `arreglos`."""
    puntos = []
    for i in range(len(fc.x)):
        p = fc.personas[fc.persona_de_fila[i]] if i in fc.persona_de_fila else None
        etq = fc.etiqueta[i]
        if p is None:
            if i in fc.pareja_de_fila:
                if "DES" in arreglos:
                    continue  # fila mal colocada: se quita y su persona se pone en su sitio
            elif "EXT" in arreglos:
                continue  # sobrante: sin nadie en el GT (si no era de equipo, tampoco contaba)
        elif "LAB" in arreglos:
            etq = p.equipo
        if etq != equipo:
            continue
        if p is not None and "LOC" in arreglos:
            puntos.append((p.x, p.y))
        else:
            puntos.append((float(fc.x[i]), float(fc.y[i])))
    emparejadas = set(fc.pareja_de_fila.values())
    for k, p in enumerate(fc.personas):
        if p.fila is not None or p.equipo != equipo:
            continue
        if ("DES" if k in emparejadas else "MIS") in arreglos:
            puntos.append((p.x, p.y))
    return np.array(puntos, dtype=float).reshape(-1, 2)


def conjunto_gt(fc: FrameCasado, equipo: str) -> np.ndarray:
    return np.array(
        [(p.x, p.y) for p in fc.personas if p.equipo == equipo], dtype=float
    ).reshape(-1, 2)


def metricas_de_puntos(P: np.ndarray) -> dict[str, float]:
    """Centroide (x, y), anchura (extensión en y) y profundidad (extensión en x)."""
    if len(P) == 0:
        return {k: np.nan for k in ("cx", "cy", "ancho", "prof")}
    return {
        "cx": float(P[:, 0].mean()),
        "cy": float(P[:, 1].mean()),
        "ancho": float(P[:, 1].max() - P[:, 1].min()),
        "prof": float(P[:, 0].max() - P[:, 0].min()),
    }


def error_de_conjunto(P: np.ndarray, verdad: np.ndarray) -> dict[str, float]:
    """Error de centroide (distancia euclídea), de anchura y de profundidad (abs)."""
    a, b = metricas_de_puntos(P), metricas_de_puntos(verdad)
    return {
        "centroide": float(np.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"])),
        "centroide_x": abs(a["cx"] - b["cx"]),
        "ancho": abs(a["ancho"] - b["ancho"]),
        "prof": abs(a["prof"] - b["prof"]),
    }


def subconjuntos():
    """Todos los subconjuntos de palancas (2**len(FACTORES)), como frozensets."""
    return [
        frozenset(c)
        for k in range(len(FACTORES) + 1)
        for c in combinations(FACTORES, k)
    ]


def escalera_por_frame_equipo(frames: list[FrameCasado], min_puntos: int = 3):
    """Error de cada métrica para cada subconjunto de arreglos, por (frame, equipo).

    Solo entran los (frame, equipo) con al menos `min_puntos` personas en el GT y
    en el sistema (la regla de producto: por debajo de 3 no hay bloque). Los
    descartados se cuentan aparte para que no se pierdan en silencio.

    Con 5 palancas son 32 subconjuntos por par.

    Devuelve (filas, descartados): `filas` es una lista de dicts
    {frame, equipo, n_gt, n_sis, arreglos, centroide, centroide_x, ancho, prof}.
    """
    filas, descartados = [], 0
    for fc in frames:
        for eq in EQUIPOS:
            verdad = conjunto_gt(fc, eq)
            base = conjunto_del_equipo(fc, eq)
            if len(verdad) < min_puntos or len(base) < min_puntos:
                descartados += 1
                continue
            for arr in subconjuntos():
                P = conjunto_del_equipo(fc, eq, arr)
                if len(P) == 0:
                    descartados += 1
                    break
                e = error_de_conjunto(P, verdad)
                filas.append(
                    {
                        "frame": fc.frame,
                        "equipo": eq,
                        "n_gt": len(verdad),
                        "n_sis": len(base),
                        "arreglos": arr,
                        **e,
                    }
                )
    return filas, descartados


def shapley(valor: dict[frozenset, float]) -> dict[str, float]:
    """Reparto de Shapley de la MEJORA v(∅) − v(todos) entre las palancas.

    `valor[S]` = error que queda tras aplicar el subconjunto S de arreglos. La
    contribución de una palanca es su mejora media sobre todos los órdenes en
    que se pueden ir aplicando; la suma de todas es v(∅) − v(todos).
    """
    n = len(FACTORES)
    reparto = {f: 0.0 for f in FACTORES}
    for f in FACTORES:
        otros = [g for g in FACTORES if g != f]
        for k in range(n):
            for S in combinations(otros, k):
                S = frozenset(S)
                peso = factorial(k) * factorial(n - k - 1) / factorial(n)
                reparto[f] += peso * (valor[S] - valor[S | {f}])
    return reparto


def cuenta_de_recuento(fc: FrameCasado, equipo: str) -> dict[str, int]:
    """Identidad contable del recuento de un equipo en un frame.

        n_sistema = n_gt − faltan − a_otro − equipo_equivocado + entran + sobran

    donde `faltan` = personas del equipo sin fila que las cubra; `a_otro` = las
    cubiertas por una fila `otro`/`staff`; `equipo_equivocado` = las cubiertas por
    una fila del otro equipo; `entran` = personas del otro equipo cubiertas por
    una fila de ESTE equipo; `sobran` = filas de este equipo sin persona en el GT.
    El error contra 7 añade el ENCUADRE: 7 − n_gt (gente que el GT no ve).
    """
    otro_eq = "B" if equipo == "A" else "A"
    faltan = a_otro = equivocado = entran = 0
    for p in fc.personas:
        if p.equipo == equipo:
            if p.fila is None:
                faltan += 1
            else:
                etq = fc.etiqueta[p.fila]
                if etq == otro_eq:
                    equivocado += 1
                elif etq != equipo:
                    a_otro += 1
        elif p.fila is not None and fc.etiqueta[p.fila] == equipo:
            entran += 1
    sobran = sum(
        1
        for i in range(len(fc.x))
        if i not in fc.persona_de_fila and fc.etiqueta[i] == equipo
    )
    desplazadas = sum(
        1 for k in fc.pareja_de_fila.values() if fc.personas[k].equipo == equipo
    )  # de los `faltan`, los que en realidad tienen una fila mal colocada a ≤ 5 m
    n_gt = sum(1 for p in fc.personas if p.equipo == equipo)
    n_sis = int((fc.etiqueta == equipo).sum())
    assert n_sis == n_gt - faltan - a_otro - equivocado + entran + sobran, "no cuadra"
    return {
        "n_gt": n_gt,
        "n_sis": n_sis,
        "encuadre": JUGADORES_POR_EQUIPO - n_gt,
        "faltan": faltan,
        "a_otro": a_otro,
        "equivocado": equivocado,
        "entran": entran,
        "sobran": sobran,
        "desplazadas": desplazadas,
    }
