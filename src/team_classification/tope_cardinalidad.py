"""Etiqueta de equipo con TOPE DE CARDINALIDAD: el reglamento como restricción.

docs/diagnostico_22oct_e.md, bloque 1. Ruta nueva, tras el flag `equipos.tope_cardinalidad` del
config del processor (apagado por defecto: entonces nada de esto corre).

La idea: en un frame no puede haber más de 7 jugadores de un equipo (F7; 11 en F11) ni más de un
árbitro. Hoy cada identidad se etiqueta POR SU CUENTA, mirando solo su color, y el resultado lo
viola mucho: B pasa de 7 en el 28,5 % de los frames del benjamín, A pasa de 11 en el 54,6 % de los
de Villaviciosa (bloque 0). Aquí las identidades se etiquetan JUNTAS: se busca la asignación
{A, B, otro} de menor coste de color que respete los topes en cada instante.

Lo que NO cambia:
- la feature y el clasificador (el coste es la distancia a los prototipos de hoy);
- los porteros y el staff: los deciden sus reglas de posición, antes, y aquí se FIJAN (los
  porteros cuentan en el tope de su equipo; el staff no cuenta).

El coste de la identidad i, con n_i observaciones con color y color medio m_i:
- c(A) = n_i · ‖m_i − A‖ y c(B) = n_i · ‖m_i − B‖;
- c(otro) = n_i · (1 − f_i) · d_otro, con d_otro = ‖m_i − otro‖ si el clasificador tiene ese
  prototipo y la separación ‖A − B‖ si no (la escala de «lejos de los dos» de `dist_max`); f_i es
  la fracción de sus ventanas de 1,5 s que dispara el catálogo arbitral.

Las restricciones son BLANDAS (holgura con penalización λ por frame y persona de exceso): una caja
fantasma de unos frames no debe obligar a reetiquetar a nadie.
"""

from __future__ import annotations

import logging
import time

import numpy as np

logger = logging.getLogger(__name__)
EQUIPOS = ("A", "B", "otro")
FIJAS = ("portero_A", "portero_B", "staff")


def fraccion_catalogo(identidad, colores, clasificador, ventana_s: float) -> float:
    """Fracción de las observaciones cuya ventana dispara el catálogo arbitral (0 si no hay)."""
    from src.team_classification.arbitro import (
        ARQUETIPOS,
        arquetipos_activos,
        brillo_medio,
        tono_dominante,
    )
    from src.team_classification.pipeline_equipos import color_medio_limpio

    pr = getattr(clasificador, "_prototipos", None)
    activos = arquetipos_activos([pr.a, pr.b], ARQUETIPOS) if pr is not None else ()
    if not activos:
        return 0.0
    obs = sorted(
        (t, tuple(par))
        for tr in identidad
        for t, par in zip(tr.ts, tr.det_idxs)
        if tuple(par) in colores
    )
    if not obs:
        return 0.0
    ts = np.array([t for t, _p in obs])
    disparan = 0
    for t_actual, _par in obs:
        cerca = [
            (p, colores[p])
            for (t2, p) in obs[
                np.searchsorted(
                    ts, t_actual - ventana_s / 2
                ) : np.searchsorted(  # noqa: E203
                    ts, t_actual + ventana_s / 2, side="right"
                )
            ]
        ]
        media = color_medio_limpio(cerca, None)
        if media is None:
            continue
        tono = tono_dominante(media)
        if tono is not None and any(
            a.contiene(tono[0], tono[1], brillo_medio(media)) for a in activos
        ):
            disparan += 1
    return disparan / len(obs)


def costes(
    identidades, libres, colores, clasificador, cfg_equipos, modelo, profundidad
):
    """Matriz (len(libres) × 3) de costes A / B / otro, y n_i de cada identidad."""
    from src.team_classification.pipeline_equipos import color_de_identidad

    cfg_agg = cfg_equipos.get("agregacion", {})
    umbral = cfg_agg.get("umbral_profundidad_m", cfg_agg.get("umbral_my", 45.0))
    solo_cercanos = cfg_agg.get("solo_cercanos", True)
    ventana = float(cfg_agg.get("por_observacion", {}).get("ventana_s", 1.5))
    pr = clasificador._prototipos
    from src.team_classification.color_classifier import _solo_hs

    separacion = float(np.linalg.norm(pr.a - pr.b))
    D = np.zeros((len(libres), 3))
    n = np.zeros(len(libres))
    for fila, indice in enumerate(libres):
        identidad = identidades[indice - 1]
        media, _feats = color_de_identidad(
            identidad, colores, modelo, profundidad, umbral, solo_cercanos
        )
        n[fila] = sum(
            1 for tr in identidad for par in tr.det_idxs if tuple(par) in colores
        )
        if media is None:  # todos sus recortes descartados: no hay color que comparar
            D[fila] = [separacion, separacion, separacion]
            continue
        m = _solo_hs(media)
        d_otro = (
            float(np.linalg.norm(m - pr.otro)) if pr.otro is not None else separacion
        )
        f = fraccion_catalogo(identidad, colores, clasificador, ventana)
        D[fila] = [np.linalg.norm(m - pr.a), np.linalg.norm(m - pr.b), (1 - f) * d_otro]
    return D, n


def presencias(identidades, indices, modelo) -> dict[int, set[int]]:
    """{frame: {identidad}} con observación DENTRO del campo en ese frame."""
    out: dict[int, set[int]] = {}
    for indice in indices:
        for tr in identidades[indice - 1]:
            for pos, par in zip(tr.pos, tr.det_idxs):
                if 0.0 <= pos[0] <= modelo.largo and 0.0 <= pos[1] <= modelo.ancho:
                    out.setdefault(int(par[0]), set()).add(indice)
    return out


def trozos_de(identidades, libres, trozo_s: float) -> list[tuple[int, list]]:
    """Parte cada identidad libre en trozos de `trozo_s` segundos (intento 2).

    Returns:
        [(identidad, [(t, (frame, det), pos), ...])] en orden.
    """
    out = []
    for indice in libres:
        obs = sorted(
            (t, tuple(par), pos)
            for tr in identidades[indice - 1]
            for t, par, pos in zip(tr.ts, tr.det_idxs, tr.pos)
        )
        if not obs:
            continue
        t0 = obs[0][0]
        actual, clave = [], None
        for o in obs:
            k = int((o[0] - t0) // trozo_s)
            if clave is not None and k != clave:
                out.append((indice, actual))
                actual = []
            clave = k
            actual.append(o)
        out.append((indice, actual))
    return out


def costes_de_trozos(trozos, colores, clasificador) -> tuple[np.ndarray, np.ndarray]:
    """Coste por trozo, como el de la identidad pero con el color medio DEL TROZO."""
    from src.team_classification.arbitro import (
        ARQUETIPOS,
        arquetipos_activos,
        brillo_medio,
        tono_dominante,
    )
    from src.team_classification.color_classifier import _solo_hs
    from src.team_classification.pipeline_equipos import color_medio_limpio

    pr = clasificador._prototipos
    separacion = float(np.linalg.norm(pr.a - pr.b))
    activos = arquetipos_activos([pr.a, pr.b], ARQUETIPOS)
    D = np.full((len(trozos), 3), separacion)
    n = np.zeros(len(trozos))
    for k, (_ind, obs) in enumerate(trozos):
        feats = [(par, colores[par]) for _t, par, _p in obs if par in colores]
        n[k] = len(feats)
        media = color_medio_limpio(feats, None) if feats else None
        if media is None:
            continue
        m = _solo_hs(media)
        tono = tono_dominante(media)
        dispara = bool(
            activos
            and tono is not None
            and any(a.contiene(tono[0], tono[1], brillo_medio(media)) for a in activos)
        )
        d_otro = (
            float(np.linalg.norm(m - pr.otro)) if pr.otro is not None else separacion
        )
        D[k] = [
            np.linalg.norm(m - pr.a),
            np.linalg.norm(m - pr.b),
            (0.0 if dispara else 1.0) * d_otro,
        ]
    return D, n


def resolver(C, pres_libres, pres_fijas, tope, tope_otro, lam, tiempo_max_s):
    """MILP: una etiqueta por unidad, topes por frame con holgura penalizada.

    Args:
        C: (n_unidades × 3) costes A / B / otro.
        pres_libres: {frame: {unidad}} presentes dentro del campo.
        pres_fijas: {frame: (nº A fijos, nº B fijos, nº otro fijos)}.

    Returns:
        (etiqueta de cada unidad o None si el solver falla, exceso persona-frame, nº restricciones)
    """
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    claves: dict[tuple, int] = {}
    for f in set(pres_libres) | set(pres_fijas):
        fa, fb, fo = pres_fijas.get(f, (0, 0, 0))
        clave = (tuple(sorted(pres_libres.get(f, ()))), fa, fb, fo)
        claves[clave] = claves.get(clave, 0) + 1
    restricciones = []
    for (S, fa, fb, fo), peso in claves.items():
        for j, (cap, fijos) in enumerate(((tope, fa), (tope, fb), (tope_otro, fo))):
            residuo = cap - fijos
            if len(S) <= residuo:
                continue  # no se puede violar: no hace falta escribirla
            restricciones.append((S, j, residuo, peso))

    nl, nr = len(C), len(restricciones)
    nv = 3 * nl + nr
    c = np.concatenate(
        [C.ravel(), lam * np.array([r[3] for r in restricciones], float)]
    )
    A = lil_matrix((nl + nr, nv))
    for k in range(nl):
        A[k, 3 * k : 3 * k + 3] = 1  # noqa: E203  una etiqueta por unidad
    ub = np.concatenate([np.ones(nl), np.zeros(nr)])
    lb = np.concatenate([np.ones(nl), np.full(nr, -np.inf)])
    for r, (S, j, residuo, _peso) in enumerate(restricciones):
        for k in S:
            A[nl + r, 3 * k + j] = 1
        A[nl + r, 3 * nl + r] = -1  # holgura
        ub[nl + r] = residuo
    res = milp(
        c,
        constraints=LinearConstraint(A.tocsr(), lb, ub),
        integrality=np.concatenate([np.ones(3 * nl), np.zeros(nr)]),
        bounds=Bounds(
            np.zeros(nv), np.concatenate([np.ones(3 * nl), np.full(nr, np.inf)])
        ),
        options={"time_limit": float(tiempo_max_s)},
    )
    if res.x is None:
        logger.warning(
            "Tope de cardinalidad: el solver no devolvió solución (%s)", res.message
        )
        return None, 0.0, nr
    x = res.x[: 3 * nl].reshape(nl, 3)
    holgura = res.x[3 * nl :]  # noqa: E203
    exceso = float(np.dot(holgura, [r[3] for r in restricciones])) if nr else 0.0
    return [EQUIPOS[int(np.argmax(fila))] for fila in x], exceso, nr


def etiquetar_con_tope(
    identidades,
    equipos_hoy: dict[int, str],
    colores: dict,
    clasificador,
    cfg_equipos: dict,
    cfg_tope: dict,
) -> tuple[dict[int, str], dict[tuple[int, int], str]]:
    """Etiquetas con los topes de cardinalidad (ver el docstring del módulo).

    Args:
        equipos_hoy: la salida de `clasificar_identidades`; de ella salen las FIJADAS (porteros y
            staff) y la etiqueta de las identidades sin color.
        cfg_tope: el bloque `equipos.tope_cardinalidad` del config del processor: `tope` (7 en F7,
            11 en F11), `tope_otro` (1), `lambda_holgura` (1,0), `unidad` («identidad», el intento
            1; «trozo», el intento 2, con `trozo_s` 1,5) y, SOLO para el control del diagnóstico,
            `control_permutar_semilla` (permuta los costes de color entre unidades).

    Returns:
        (etiqueta por identidad, etiqueta por observación {(identidad, frame): etiqueta}). La
        segunda solo se rellena con `unidad: trozo`; el exportador la prefiere a la primera.
    """
    from src.team_classification.pipeline_equipos import _profundidad_configurada

    t0 = time.time()
    modelo, profundidad = _profundidad_configurada(cfg_equipos)
    tope = int(cfg_tope.get("tope", 7))
    tope_otro = int(cfg_tope.get("tope_otro", 1))
    lam = float(cfg_tope.get("lambda_holgura", 1.0))
    unidad = str(cfg_tope.get("unidad", "identidad"))
    if unidad not in ("identidad", "trozo"):
        raise ValueError(f"equipos.tope_cardinalidad.unidad desconocida: {unidad!r}")

    fijadas = {i: e for i, e in equipos_hoy.items() if str(e) in FIJAS}
    todos = range(1, len(identidades) + 1)
    con_color = {
        i
        for i in todos
        if any(
            tuple(par) in colores for tr in identidades[i - 1] for par in tr.det_idxs
        )
    }
    libres = [i for i in todos if i not in fijadas and i in con_color]
    # Las que no tienen color conservan su etiqueta de hoy y cuentan como fijas.
    sin_color = {
        i: str(equipos_hoy.get(i, "otro")) for i in todos if i not in con_color
    }
    fijas_todas = {**sin_color, **fijadas}

    if unidad == "identidad":
        D, n = costes(
            identidades, libres, colores, clasificador, cfg_equipos, modelo, profundidad
        )
        por_identidad = presencias(identidades, libres, modelo)
        fila_de = {ind: k for k, ind in enumerate(libres)}
        pres_libres = {f: {fila_de[i] for i in s} for f, s in por_identidad.items()}
        trozos = None
    else:
        trozos = trozos_de(identidades, libres, float(cfg_tope.get("trozo_s", 1.5)))
        D, n = costes_de_trozos(trozos, colores, clasificador)
        pres_libres = {}
        for k, (_ind, obs) in enumerate(trozos):
            for _t, par, pos in obs:
                if 0.0 <= pos[0] <= modelo.largo and 0.0 <= pos[1] <= modelo.ancho:
                    pres_libres.setdefault(int(par[0]), set()).add(k)
    semilla = cfg_tope.get("control_permutar_semilla")
    if semilla is not None:
        D = D[np.random.default_rng(int(semilla)).permutation(len(D))]
        logger.warning(
            "CONTROL: costes de color PERMUTADOS entre unidades (semilla %s)", semilla
        )

    pres_fijas: dict[int, tuple[int, int, int]] = {}
    for f, s in presencias(identidades, list(fijas_todas), modelo).items():
        fij = [fijas_todas[i] for i in s]
        pres_fijas[f] = (
            sum(e in ("A", "portero_A") for e in fij),
            sum(e in ("B", "portero_B") for e in fij),
            sum(e == "otro" for e in fij),
        )

    etiquetas, exceso, nr = resolver(
        D * n[:, None],
        pres_libres,
        pres_fijas,
        tope,
        tope_otro,
        lam,
        cfg_tope.get("tiempo_max_s", 120.0),
    )
    if etiquetas is None:
        return dict(equipos_hoy), {}

    salida = dict(fijas_todas)
    por_obs: dict[tuple[int, int], str] = {}
    if trozos is None:
        for k, ind in enumerate(libres):
            salida[ind] = etiquetas[k]
    else:
        votos: dict[int, dict[str, int]] = {}
        for (ind, obs), etq in zip(trozos, etiquetas):
            for _t, par, _p in obs:
                por_obs[(ind, int(par[0]))] = etq
            votos.setdefault(ind, {}).setdefault(etq, 0)
            votos[ind][etq] += len(obs)
        # la etiqueta de la identidad (la de sus filas interpoladas): la de más observaciones
        for ind, v in votos.items():
            salida[ind] = max(v, key=v.get)
    cambian = sum(salida[i] != str(equipos_hoy.get(i, "otro")) for i in libres)
    logger.info(
        "Tope de cardinalidad (unidad %s, tope %d, otro ≤ %d, λ %.2f): %d unidades libres, "
        "%d fijadas, %d restricciones; exceso total %.0f persona-frame; %d identidades cambian; "
        "%.1f s",
        unidad,
        tope,
        tope_otro,
        lam,
        len(D),
        len(fijadas),
        nr,
        exceso,
        cambian,
        time.time() - t0,
    )
    return salida, por_obs
