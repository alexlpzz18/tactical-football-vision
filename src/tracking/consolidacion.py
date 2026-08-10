"""Consolidación final: fusiona fichas del MISMO equipo que van montadas.

Motivación (feedback visual del replay v4pre, 08-ago-2026): el replay
dibuja ~47 fichas simultáneas para ~23 personas reales, con racimos de
círculos del mismo color pegados. Las métricas clásicas no lo ven porque
puntúan por posición emparejada, no por exceso de identidades vivas.

Por qué aquí y no en la exclusión espacial: aquella corre ANTES del
cosido/interpolación y con un umbral duro de 1,5 m pensado para
duplicados de SAHI. Los racimos que se ven ahora están a 3-6 m — la
distancia que el ruido de proyección del fondo mete entre dos
observaciones del MISMO jugador (mediana 1,16 m y p90 2,45 m en my>51,
así que dos fragmentos pueden distar el doble). A esa distancia el
criterio de "misma persona" ya no se sostiene solo con geometría: por eso
esta pasada es la ÚLTIMA (después de clasificar equipos) y exige
condiciones más restrictivas que el dedup genérico:

  1. MISMO equipo (no puede juntar un A con un B: eso sería inventar).
  2. Proximidad SOSTENIDA: mediana de la distancia por debajo del umbral
     sobre un mínimo de frames compartidos (no un cruce puntual).
  3. Se fusiona el grupo entero por transitividad, deduplicando por frame.

Límite documentado y medido: a 4-6 m la geometría NO distingue un
duplicado de dos compañeros que corren juntos (validado contra el GT:
precisión ~0,4). La fusión es segura para la métrica de PRODUCTO
(cobertura y equipos no se degradan, porque ambas fichas eran del mismo
equipo y sus posiciones se conservan) pero NO recupera la identidad
individual: dos compañeros fusionados siguen siendo un error de tracking
individual. Por eso el umbral por defecto es conservador.
"""

import logging
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)

# Trayectoria = lista de (frame_idx, pos, es_real)
Trayectoria = list[tuple[int, np.ndarray, bool]]


def _grupo_equipo(etiqueta: str | None) -> str | None:
    """Grupo a efectos de fusión: el portero cuenta con su equipo."""
    if etiqueta in ("A", "portero_A"):
        return "A"
    if etiqueta in ("B", "portero_B"):
        return "B"
    return None  # 'otro', 'staff' o sin clasificar: nunca se fusionan


def consolidar_colocadas(
    trayectorias: list[Trayectoria],
    equipos: dict[int, str],
    dist_max: float = 4.0,
    min_frames_comunes: int = 100,
    resolucion=None,
    jitter_px: float = 2.0,
) -> tuple[list[Trayectoria], dict[int, str]]:
    """Fusiona identidades del mismo equipo co-locadas de forma sostenida.

    Args:
        trayectorias: una por identidad (ids 1..N por posición en la lista).
        equipos: {id_identidad: etiqueta} del clasificador (+ porteros/staff).
        dist_max: distancia MEDIANA máxima (m) en los frames comunes.
        min_frames_comunes: mínimo de frames compartidos para decidir. Alto
            a propósito: "sostenida", no un cruce.
        resolucion: ResolucionCampo opcional. Dos fichas del MISMO jugador
            se separan tanto más cuanto peor es la resolución de su zona,
            así que el umbral se amplía con ella (dist_max + jitter · m/px)
            en vez de ser el mismo en todo el campo.
        jitter_px: vibración típica de la caja del detector, en píxeles.

    Returns:
        (trayectorias nuevas, equipos nuevos) con los ids renumerados 1..M.
        En los frames donde varias fichas del grupo tienen posición se
        conserva la de la identidad con más observaciones REALES (la mejor
        soportada por detecciones, no por interpolación).
    """
    if not trayectorias:
        return [], {}

    posiciones = [{frame: pos for frame, pos, _real in tray} for tray in trayectorias]
    n_reales = [sum(1 for _f, _p, real in tray if real) for tray in trayectorias]

    padre = list(range(len(trayectorias)))

    def raiz(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    n_fusiones = 0
    for i in range(len(trayectorias)):
        grupo_i = _grupo_equipo(equipos.get(i + 1))
        if grupo_i is None:
            continue
        for j in range(i + 1, len(trayectorias)):
            if _grupo_equipo(equipos.get(j + 1)) != grupo_i:
                continue
            comunes = posiciones[i].keys() & posiciones[j].keys()
            if len(comunes) < min_frames_comunes:
                continue
            distancias = [
                np.linalg.norm(posiciones[i][f] - posiciones[j][f]) for f in comunes
            ]
            umbral = dist_max
            if resolucion is not None:
                # La zona la marca el punto medio del par
                medio = np.mean(
                    [(posiciones[i][f] + posiciones[j][f]) / 2 for f in comunes], axis=0
                )
                umbral += jitter_px * resolucion.metros_por_pixel(medio)
            if float(np.median(distancias)) <= umbral:
                if raiz(i) != raiz(j):
                    padre[raiz(i)] = raiz(j)
                    n_fusiones += 1

    grupos: dict[int, list[int]] = defaultdict(list)
    for i in range(len(trayectorias)):
        grupos[raiz(i)].append(i)

    nuevas: list[Trayectoria] = []
    nuevos_equipos: dict[int, str] = {}
    for miembros in grupos.values():
        # Prioridad: la identidad con más observaciones reales manda
        miembros = sorted(miembros, key=lambda m: -n_reales[m])
        por_frame: dict[int, tuple[np.ndarray, bool]] = {}
        for m in miembros:
            for frame, pos, real in trayectorias[m]:
                if frame not in por_frame:
                    por_frame[frame] = (pos, real)
        fusionada = [
            (frame, por_frame[frame][0], por_frame[frame][1])
            for frame in sorted(por_frame)
        ]
        nuevas.append(fusionada)
        etiqueta = equipos.get(miembros[0] + 1)
        if etiqueta is not None:
            nuevos_equipos[len(nuevas)] = etiqueta

    logger.info(
        "Consolidación final: %d fusiones (dist_max=%.1f m, ≥%d frames) "
        "→ %d → %d identidades",
        n_fusiones,
        dist_max,
        min_frames_comunes,
        len(trayectorias),
        len(nuevas),
    )
    return nuevas, nuevos_equipos
