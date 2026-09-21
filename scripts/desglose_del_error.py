#!/usr/bin/env python
"""¿De qué está hecho el error del centroide y del recuento? (desglose del error total)

Alex (21-sep-2026): *«si ni el portero ni el árbitro explican el ruido grande
del recuento y el centroide, ¿QUÉ lo explica? Quiero un desglose del error total
en el partido entero: cuánto es identidad, cuánto encuadre, cuánto localización,
cuánto lo que queda sin nombre. Como hiciste con el benja al principio.»*

Es una escalera de oráculos (`docs/oraculos.md`) sobre la salida FINAL del sistema
(el CSV de posiciones) con cuatro palancas —LOC localización, LAB identidad de
equipo, EXT sobrantes, MIS faltantes— repartidas con valores de Shapley
(`src/evaluation/desglose_error.py`).

⚠️ El GT del benjamín son 30 s (2,5 % de la pasada). Por eso el script separa
SIEMPRE lo MEDIDO (contra el GT), lo ESTIMADO con proxies en los 20 minutos y lo
que NO SE PUEDE MEDIR sin más GT.

Uso:
    python scripts/desglose_del_error.py
    python scripts/desglose_del_error.py --radio 3 --csv RUTA_AL_CSV
"""

import argparse
import logging
import pickle
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from arbitro_medicion import (  # noqa: E402
    UMBRAL_MASA,
    ZONA_PORTERO_B_DY,
    ZONA_PORTERO_B_X,
    masa_de_ventana,
)
from src.evaluation.desglose_error import (  # noqa: E402
    EQUIPOS,
    FACTORES,
    JUGADORES_POR_EQUIPO,
    casar_frame,
    conjunto_gt,
    cuenta_de_recuento,
    equipo_de_etiqueta,
    error_de_conjunto,
    escalera_por_frame_equipo,
    shapley,
)
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402

logger = logging.getLogger("desglose")
RADIOS = (1.5, 2.0, 3.0, 4.0, 5.0)
RADIO_BANCO = 2.0  # el del banco (`comparar_escalas.py`): con él se compara el control


# ─────────────────────────────── carga y casado ───────────────────────────────
def construir_frames(gt_m: dict, filas: pd.DataFrame, radio: float):
    """Un `FrameCasado` por frame del GT (solo personas A/B; el GT no anota árbitro)."""
    por_frame = {f: g for f, g in filas.groupby("frame")}
    frames = []
    for f in sorted(gt_m):
        gt = [
            (equipo_de_etiqueta(o.team), o.pos[0], o.pos[1])
            for o in gt_m[f]
            if equipo_de_etiqueta(o.team) in EQUIPOS
        ]
        s = por_frame.get(f)
        if s is None:
            x = y = np.array([])
            etq = np.array([], dtype=object)
        else:
            x, y, etq = s.x_m.to_numpy(), s.y_m.to_numpy(), s.etiqueta.to_numpy()
        frames.append(casar_frame(f, gt, x, y, etq, radio))
    return frames


def _valor_por_subconjunto(R: pd.DataFrame, metrica: str, agregado: str) -> dict:
    f = {"media": "mean", "mediana": "median", "p90": lambda s: s.quantile(0.9)}[
        agregado
    ]
    return {S: float(g[metrica].agg(f)) for S, g in R.groupby("arreglos")}


# ───────────────────────────── 1. control y escalera ─────────────────────────────
def control_base(frames) -> None:
    """El control «¿lo que mido es lo que creo?»: reproduce las cifras del banco."""
    c = Counter()
    for fc in frames:
        for p in fc.personas:
            if p.fila is not None:
                c[(p.equipo, fc.etiqueta[p.fila])] += 1
    n_gt = sum(len(fc.personas) for fc in frames)
    casadas = sum(c.values())
    mal = c[("A", "B")] + c[("B", "A")]
    print(f"\n0. CONTROL (radio {RADIO_BANCO:.0f} m, protocolo de comparar_escalas.py)")
    print(f"   personas del GT {n_gt} · casadas {casadas} ({casadas / n_gt:.1%}) · ")
    print(
        f"   equipo equivocado {mal} de {casadas} = {mal / casadas:.1%}   [documentado: 1,2 %]"
    )


def escalera(frames, radio_tag: str = "") -> pd.DataFrame:
    filas, descartados = escalera_por_frame_equipo(frames)
    R = pd.DataFrame(filas)
    n = len(R) // 2 ** len(FACTORES)
    print(f"\n   {n} pares (frame, equipo) con ≥3 personas; descartados {descartados}")
    return R


def imprimir_escalera(R: pd.DataFrame) -> None:
    print("\n1. ESCALERA DE ORÁCULOS (error que QUEDA al arreglar cada conjunto)")
    print(f"   {'':22s} {'centroide':>22s} {'anchura':>9s} {'profundidad':>12s}")
    print(f"   {'':22s} {'media  mediana  p90':>22s} {'media':>9s} {'media':>12s}")
    for arr in (
        [],
        ["LAB"],
        ["LOC"],
        ["EXT"],
        ["MIS"],
        ["DES"],
        ["LAB", "EXT"],
        ["LAB", "EXT", "MIS", "DES"],
        ["LAB", "EXT", "LOC"],
        list(FACTORES),
    ):
        g = R[R.arreglos == frozenset(arr)]
        nombre = "+".join(arr) if arr else "sistema"
        if len(arr) == len(FACTORES):
            nombre = "todo (=GT)"
        print(
            f"   {nombre:22s} {g.centroide.mean():6.2f} {g.centroide.median():8.2f}"
            f" {g.centroide.quantile(0.9):5.2f} {g.ancho.mean():9.2f} {g.prof.mean():12.2f}"
        )
    print(
        "   ⚠️ Las palancas se estorban (quitar un fantasma sin devolver al que falta desplaza"
        "\n      el bloque): el efecto de UNA sola no es el suyo, por eso se reparte con Shapley."
    )


def imprimir_shapley(R: pd.DataFrame, radio: float) -> dict:
    print(f"\n2. REPARTO DE SHAPLEY (radio {radio:.1f} m; la suma = error del sistema)")
    print(
        f"   {'métrica':12s} {'agregado':9s} {'sistema':>8s} "
        + " ".join(f"{f:>6s}" for f in FACTORES)
    )
    salida = {}
    for metrica, agregados in (
        ("centroide", ("media", "mediana", "p90")),
        ("ancho", ("media", "p90")),
        ("prof", ("media", "p90")),
    ):
        for agg in agregados:
            v = _valor_por_subconjunto(R, metrica, agg)
            sh = shapley(v)
            base = v[frozenset()]
            salida[(metrica, agg)] = sh
            print(
                f"   {metrica:12s} {agg:9s} {base:8.2f} "
                + " ".join(f"{sh[f]:6.2f}" for f in FACTORES)
                + f"   ({' / '.join(f'{sh[f] / base:.0%}' for f in FACTORES)})"
            )
    return salida


def barrido_de_radios(gt_m, filas) -> None:
    print(
        "\n3. BARRIDO DEL RADIO DE CASADO (el criterio es un parámetro, no una verdad)"
    )
    print(
        f"   {'radio':>6s} {'sistema':>8s} "
        + " ".join(f"{f:>6s}" for f in FACTORES)
        + f" {'% sin fila':>11s} {'filas libres A/B':>17s}"
    )
    for radio in RADIOS:
        frames = construir_frames(gt_m, filas, radio)
        R = pd.DataFrame(escalera_por_frame_equipo(frames)[0])
        v = _valor_por_subconjunto(R, "centroide", "media")
        sh = shapley(v)
        n_gt = sum(len(fc.personas) for fc in frames)
        sin_fila = sum(1 for fc in frames for p in fc.personas if p.fila is None)
        libres = sum(
            1
            for fc in frames
            for i in range(len(fc.x))
            if i not in fc.persona_de_fila and fc.etiqueta[i] in EQUIPOS
        )
        print(
            f"   {radio:6.1f} {v[frozenset()]:8.2f} "
            + " ".join(f"{sh[f]:6.2f}" for f in FACTORES)
            + f" {sin_fila / n_gt:11.1%} {libres:17d}"
        )


def estabilidad_por_tercios(frames) -> None:
    """¿Aguanta el reparto si se parte la ventana? Son 120 pares muy autocorrelados."""
    print(
        "\n3b. ESTABILIDAD: el mismo reparto (centroide, media) en cada tercio de la ventana"
    )
    print(
        f"   {'tercio':>8s} {'sistema':>8s} " + " ".join(f"{f:>6s}" for f in FACTORES)
    )
    corte = np.array_split(np.arange(len(frames)), 3)
    for k, idx in enumerate(corte, start=1):
        R = pd.DataFrame(escalera_por_frame_equipo([frames[i] for i in idx])[0])
        v = _valor_por_subconjunto(R, "centroide", "media")
        sh = shapley(v)
        print(
            f"   {k:>8d} {v[frozenset()]:8.2f} "
            + " ".join(f"{sh[f]:6.2f}" for f in FACTORES)
        )


# ───────────────────────────── 2. contabilidad del recuento ─────────────────────────────
def recuento(frames) -> pd.DataFrame:
    filas = []
    for fc in frames:
        for eq in EQUIPOS:
            filas.append(
                {"frame": fc.frame, "equipo": eq, **cuenta_de_recuento(fc, eq)}
            )
    C = pd.DataFrame(filas)
    m = C[["encuadre", "faltan", "a_otro", "equivocado", "entran", "sobran"]].mean()
    print("\n4. CONTABILIDAD DEL RECUENTO (por equipo y frame, media)")
    print(
        f"   7 − n_sistema = ENCUADRE {m.encuadre:+.2f} + FALTAN {m.faltan:+.2f}"
        f" + A_OTRO {m.a_otro:+.2f} + EQUIVOCADO {m.equivocado:+.2f}"
        f" − ENTRAN {m.entran:.2f} − SOBRAN {m.sobran:.2f}  = {(7 - C.n_sis).mean():+.2f}"
    )
    print(
        f"   ⇒ el error NETO ({(7 - C.n_sis).mean():+.2f}) esconde dos flujos casi iguales que"
        f" se COMPENSAN: faltan {m.faltan:.2f} y sobran {m.sobran:.2f}."
    )
    print(
        f"   |7 − n_sistema| medio {(7 - C.n_sis).abs().mean():.2f} · |n_gt − n_sistema| "
        f"{(C.n_gt - C.n_sis).abs().mean():.2f} · recuento exacto 7: {(C.n_sis == 7).mean():.0%}"
    )
    print(f"   n del GT: {C.n_gt.value_counts().sort_index().to_dict()}")
    return C


def clasificar_faltantes(frames, dets: dict, filas_todas: pd.DataFrame) -> pd.DataFrame:
    """¿Por qué no hay fila? Mira la detección CRUDA más cercana a cada persona sin fila."""
    reales_con_relleno = {
        f: g for f, g in filas_todas.groupby("frame")
    }  # incluye es_real=0 (rellenos)
    filas = []
    for fc in frames:
        D = dets.get(fc.frame, np.zeros((0, 7)))
        emparejadas = set(fc.pareja_de_fila.values())
        for k, p in enumerate(fc.personas):
            if p.fila is not None:
                continue
            if k in emparejadas:
                causa, dist = "DES: su fila está a ≤5 m, mal colocada", 0.0
            elif len(D) == 0:
                causa, dist = "no detectada (a <5 m)", np.inf
            else:
                d = np.hypot(D[:, 0] - p.x, D[:, 1] - p.y)
                j = int(d.argmin())
                dist = float(d[j])
                # ¿esa detección la reclama una persona del GT más cercana?
                reclamada = any(
                    q is not p and np.hypot(D[j, 0] - q.x, D[j, 1] - q.y) < dist
                    for q in fc.personas
                )
                otra = any(
                    q is not p and np.hypot(D[j, 0] - q.x, D[j, 1] - q.y) <= 2.0
                    for q in fc.personas
                )
                if dist <= 2.0 and reclamada:
                    causa = "detección fundida con un vecino (cruce)"
                elif dist <= 2.0:
                    rell = reales_con_relleno.get(fc.frame)
                    hay_relleno = (
                        rell is not None
                        and (np.hypot(rell.x_m - p.x, rell.y_m - p.y) <= 2.0).any()
                    )
                    causa = (
                        "detección propia; solo hay fila RELLENADA (es_real=0)"
                        if hay_relleno
                        else "detección propia; el tracking/filtros no la sacan"
                    )
                elif dist <= 5.0 and not otra:
                    causa = "detección libre a 2–5 m (posición desplazada)"
                else:
                    causa = "no detectada (a <5 m)"
            filas.append(
                {
                    "frame": fc.frame,
                    "equipo": p.equipo,
                    "x": p.x,
                    "y": p.y,
                    "causa": causa,
                }
            )
    F = pd.DataFrame(filas)
    n_personas = sum(len(fc.personas) for fc in frames)
    print(
        f"\n5. FALTANTES: {len(F)} personas sin fila a ≤ radio ({len(F) / n_personas:.1%})"
    )
    for causa, n in F.causa.value_counts().items():
        print(f"   {n:4d}  {causa}")
    tot = pd.cut(
        pd.Series([p.x for fc in frames for p in fc.personas]), [0, 20, 40, 62]
    ).value_counts()
    fal = pd.cut(F.x, [0, 20, 40, 62]).value_counts()
    print(
        "   tasa de faltantes por zona x (0-20 / 20-40 / 40-62 m): "
        + " / ".join(f"{fal.get(z, 0) / tot[z]:.0%}" for z in sorted(tot.index))
        + f"  (población {' / '.join(str(int(tot[z])) for z in sorted(tot.index))})"
    )
    return F


def clasificar_sobrantes(
    frames, filas: pd.DataFrame, masa: pd.DataFrame
) -> pd.DataFrame:
    """¿Qué son las filas A/B que no corresponden a nadie del GT?"""
    m = filas.merge(masa, on=["frame", "id_jugador"], how="left")
    zona_b = (m.x_m >= ZONA_PORTERO_B_X) & ((m.y_m - 20).abs() <= ZONA_PORTERO_B_DY)
    m["arbitro"] = (
        (m.masa >= UMBRAL_MASA) & ~zona_b & (m.etiqueta != "portero_B")
    ).fillna(False)
    m = m.set_index(["frame", "id_jugador"])
    por_frame = {f: g for f, g in filas.groupby("frame")}
    registros = []
    for fc in frames:
        s = por_frame.get(fc.frame)
        if s is None:
            continue
        for i, (_, r) in enumerate(s.iterrows()):
            if i in fc.persona_de_fila or fc.etiqueta[i] not in EQUIPOS:
                continue
            dmin = min(
                [np.hypot(r.x_m - p.x, r.y_m - p.y) for p in fc.personas] or [np.inf]
            )
            registros.append(
                {
                    "frame": fc.frame,
                    "id": r.id_jugador,
                    "dmin": dmin,
                    "pareada": i in fc.pareja_de_fila,
                    "arbitro": bool(m.loc[(r.frame, r.id_jugador), "arbitro"]),
                }
            )
    S = pd.DataFrame(registros)
    casadas_por_id = Counter(
        s.iloc[i].id_jugador
        for fc in frames
        for s in [por_frame.get(fc.frame)]
        if s is not None
        for i in fc.persona_de_fila
    )
    S["id_de_jugador_real"] = S.id.map(lambda k: casadas_por_id.get(k, 0) > 0)
    print(f"\n6. SOBRANTES: {len(S)} filas A/B sin persona del GT")
    libres = S[~S.pareada]
    fantasma = ~libres.id_de_jugador_real
    con_firma = fantasma & libres.arbitro
    print(
        f"   {int(S.pareada.sum()):4d}  DES: tienen una persona sin fila a ≤5 m (fila mal colocada)"
    )
    print(
        f"   {int(con_firma.sum()):4d}  identidad que nunca casa con nadie, CON firma de árbitro"
    )
    sin_firma = int((fantasma & ~libres.arbitro).sum())
    print(
        f"   {sin_firma:4d}  identidad que nunca casa con nadie, sin firma (banda, otros)"
    )
    n_real = int((~fantasma).sum())
    print(
        f"   {n_real:4d}  identidad de un jugador real (casa otros frames), sin pareja"
    )
    return S


# ───────────────────────────── 3b. filas desplazadas ─────────────────────────────
def desplazadas(frames, gt_m: dict, radio_par: float = 5.0) -> None:
    """Una persona sin fila y una fila A/B sin persona, a ≤ `radio_par` m: ¿son la MISMA?

    Si lo son, no falta nadie ni sobra nadie: hay UNA fila mal colocada por más del
    radio de casado. Se mira además si el desplazamiento tiene la forma de un retardo
    del suavizado (media móvil de 0,5 s): entonces iría contra la velocidad del jugador.
    """
    from scipy.optimize import linear_sum_assignment

    dt = 15 / 29.97  # el GT va cada 15 frames
    pos = {
        (o.obj_id, f): np.array(o.pos, float)
        for f in gt_m
        for o in gt_m[f]
        if equipo_de_etiqueta(o.team) in EQUIPOS
    }
    pares = []
    for fc in frames:
        ids = [
            o.obj_id for o in gt_m[fc.frame] if equipo_de_etiqueta(o.team) in EQUIPOS
        ]
        libres = [
            i
            for i in range(len(fc.x))
            if i not in fc.persona_de_fila and fc.etiqueta[i] in EQUIPOS
        ]
        faltan = [k for k, p in enumerate(fc.personas) if p.fila is None]
        if not faltan or not libres:
            continue
        c = np.array(
            [
                [
                    np.hypot(fc.x[i] - fc.personas[k].x, fc.y[i] - fc.personas[k].y)
                    for i in libres
                ]
                for k in faltan
            ]
        )
        for a, b in zip(*linear_sum_assignment(c)):
            if c[a, b] > radio_par:
                continue
            k, i = faltan[a], libres[b]
            antes, despues = pos.get((ids[k], fc.frame - 15)), pos.get(
                (ids[k], fc.frame + 15)
            )
            v = (
                (despues - antes) / (2 * dt)
                if antes is not None and despues is not None
                else None
            )
            pares.append(
                {
                    "d": c[a, b],
                    "dx": fc.x[i] - fc.personas[k].x,
                    "dy": fc.y[i] - fc.personas[k].y,
                    "vx": np.nan if v is None else v[0],
                    "mismo_equipo": fc.etiqueta[i] == fc.personas[k].equipo,
                }
            )
    P = pd.DataFrame(pares)
    print(
        f"\n6b. FILAS DESPLAZADAS: {len(P)} pares (persona sin fila + fila A/B sin persona)"
    )
    print(f"   a ≤ {radio_par:.0f} m uno del otro")
    print(
        f"   del mismo equipo {int(P.mismo_equipo.sum())} · distancia mediana {P.d.median():.1f} m"
    )
    print(
        f"   |dx| (profundidad) mediana {P.dx.abs().median():.1f} m"
        f" · |dy| (ancho) {P.dy.abs().median():.1f} m"
        f" · hacia la cámara (dx<0): {(P.dx < 0).mean():.0%}"
    )
    q = P.dropna(subset=["vx"])
    coincide = (np.sign(q.dx) == np.sign(q.vx)).mean()
    print(
        f"   ¿retardo del suavizado? signo(dx)=signo(vx) en {coincide:.0%} de {len(q)}"
        " (un retardo daría ≈ 0 %; el azar, 50 %)"
    )


# ───────────────────────────── 3. encuadre ─────────────────────────────
def encuadre(frames) -> None:
    """Cuánto MOVERÍA el centroide que el GT no viera k jugadores (leave-k-out).

    Los ocultos de verdad no son aleatorios (suelen ser los del borde), así que esto
    es una ESTIMACIÓN del orden de magnitud, no una medida.
    """
    desplazamientos = {1: [], 2: []}
    dist_n = Counter()
    for fc in frames:
        for eq in EQUIPOS:
            P = conjunto_gt(fc, eq)
            dist_n[len(P)] += 1
            if len(P) != JUGADORES_POR_EQUIPO:
                continue
            for k in (1, 2):
                for oculto in combinations(range(len(P)), k):
                    Q = np.delete(P, oculto, axis=0)
                    desplazamientos[k].append(error_de_conjunto(Q, P)["centroide"])
    total = sum(dist_n.values())
    print(
        "\n7. ENCUADRE (jugadores que el GT no ve; leave-k-out sobre los frames con 7)"
    )
    print(f"   personas visibles por equipo y frame: {dict(sorted(dist_n.items()))}")
    medias = {k: float(np.mean(v)) for k, v in desplazamientos.items()}
    print(
        f"   si se ocultan al azar: 1 jugador mueve el centroide {medias[1]:.2f} m"
        f" · 2 jugadores {medias[2]:.2f} m"
    )
    faltan_k = {7 - n: c for n, c in dist_n.items()}
    esp = sum(
        c / total * medias.get(k, medias[2] * k / 2)
        for k, c in faltan_k.items()
        if k > 0
    )
    print(
        f"   con la distribución observada (k ocultos): efecto esperado ≈ {esp:.2f} m"
        f" — ESTIMACIÓN (supone ocultos al azar; los de borde moverían más)."
    )


# ───────────────────────────── 4. partido entero ─────────────────────────────
def distancia_a_deteccion(filas: pd.DataFrame, dets: dict) -> np.ndarray:
    """Para cada fila, distancia (m) a la detección CRUDA más cercana de su frame."""
    dist = np.full(len(filas), np.inf)
    pos = {i: k for k, i in enumerate(filas.index)}
    for frame, g in filas.groupby("frame"):
        D = dets.get(frame)
        if D is None or len(D) == 0:
            continue
        d = np.hypot(
            g.x_m.to_numpy()[:, None] - D[None, :, 0],
            g.y_m.to_numpy()[:, None] - D[None, :, 1],
        )
        for k, i in enumerate(g.index):
            dist[pos[i]] = d[k].min()
    return dist


def partido_entero(
    filas: pd.DataFrame, dets: dict, masa: pd.DataFrame, gt_frames: set
) -> pd.DataFrame:
    """Lo que SÍ se puede medir en los 20 minutos sin GT, minuto a minuto."""
    m = filas.merge(masa, on=["frame", "id_jugador"], how="left")
    m["equipo_s"] = m.etiqueta.map(equipo_de_etiqueta)
    zona_b = (m.x_m >= ZONA_PORTERO_B_X) & ((m.y_m - 20).abs() <= ZONA_PORTERO_B_DY)
    m["arbitro"] = (
        (m.masa >= UMBRAL_MASA) & ~zona_b & (m.etiqueta != "portero_B")
    ).fillna(False)
    m["lejos_de_deteccion"] = distancia_a_deteccion(m, dets) > 1.0
    m["minuto"] = (m.tiempo_s // 60).astype(int)
    ab = m[m.equipo_s.isin(EQUIPOS)]
    por = (
        ab.groupby(["frame", "equipo_s"])
        .agg(
            n=("x_m", "size"),
            arb=("arbitro", "sum"),
            lejos=("lejos_de_deteccion", "sum"),
            minuto=("minuto", "first"),
        )
        .reset_index()
    )
    tabla = por.groupby("minuto").agg(
        n_frames=("n", lambda s: s.size // 2),
        n_medio=("n", "mean"),
        exacto7=("n", lambda s: (s == 7).mean()),
        mas_de_7=("n", lambda s: (s > 7).mean()),
        menos_de_7=("n", lambda s: (s < 7).mean()),
        arbitro_en_equipo=("arb", "mean"),
        filas_lejos_de_deteccion=("lejos", "mean"),
    )
    tabla = tabla[
        tabla.n_frames >= 100
    ]  # el último minuto de la pasada es un fragmento
    # Embudo por minuto: detecciones crudas EN EL CAMPO → filas reales → filas A/B.
    frames_min = m.groupby("minuto").frame.nunique()
    ab_frame = ab.groupby("minuto").size() / frames_min
    reales_frame = m.groupby("minuto").size() / frames_min
    minuto_de_frame = m.groupby("frame").minuto.first()  # el minuto sale del propio CSV
    dets_frame, alto_frame = {}, {}
    for frame, D in dets.items():
        if frame not in minuto_de_frame.index:
            continue
        en_campo = (D[:, 0] >= 0) & (D[:, 0] <= 62) & (D[:, 1] >= 0) & (D[:, 1] <= 40)
        k = int(minuto_de_frame[frame])
        dets_frame.setdefault(k, []).append(int(en_campo.sum()))
        if en_campo.any():
            alto_frame.setdefault(k, []).append(
                float(np.median(D[en_campo, 5] - D[en_campo, 3]))
            )
    tabla["dets_en_campo"] = [np.mean(dets_frame[k]) for k in tabla.index]
    # Altura mediana de las cajas: indicador de lo CERCA de la cámara que está el juego.
    tabla["alto_caja_px"] = [np.mean(alto_frame[k]) for k in tabla.index]
    tabla["filas_reales"] = reales_frame.reindex(tabla.index)
    tabla["filas_AB"] = ab_frame.reindex(tabla.index)
    print("\n8. PARTIDO ENTERO — lo medible SIN GT, por minuto (por equipo y frame)")
    print(tabla.round(2).to_string())
    c = tabla.corr()
    print(
        f"   correlación entre minutos: n_medio~dets_en_campo {c.n_medio.dets_en_campo:+.2f}"
        f" · n_medio~filas_reales {c.n_medio.filas_reales:+.2f}"
        f" · dets_en_campo~alto_caja_px {c.dets_en_campo.alto_caja_px:+.2f}"
    )
    ventana = por[por.frame.isin(gt_frames)]
    print(
        f"\n   en la ventana del GT los proxies dan: árbitro {ventana.arb.mean():.2f} y filas"
        f" lejos de detección {ventana.lejos.mean():.2f} por equipo y frame"
        f" (el GT midió {28 / 120:.2f} árbitro y 0,84 sobrantes en total)"
    )
    return tabla


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v3.csv")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument(
        "--dets", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument(
        "--colores", default="data/tracking_benja/cache_colores_benja_p1.pkl"
    )
    p.add_argument("--radio", type=float, default=RADIO_BANCO)
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    p.add_argument("--salida", default="outputs/desglose_error_por_minuto.csv")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)

    H = np.load(args.homografia)
    gt_m = gt_a_por_frame(parsear_cvat(args.gt), H, args.offset, args.paso)
    todas = pd.read_csv(args.csv)
    reales = todas[todas.es_real == 1].reset_index(drop=True)
    with open(args.dets, "rb") as f:
        dets = {
            e["frame_idx"]: np.array(e["dets"]).reshape(-1, 7)
            for e in pickle.load(f)["cache"]
        }
    print(
        f"GT: {len(gt_m)} frames ({min(gt_m)}-{max(gt_m)}), "
        f"{sum(len(v) for v in gt_m.values())} observaciones · CSV {args.csv}"
    )

    frames = construir_frames(gt_m, reales, args.radio)
    control_base(construir_frames(gt_m, reales, RADIO_BANCO))
    R = escalera(frames)
    imprimir_escalera(R)
    imprimir_shapley(R, args.radio)
    barrido_de_radios(gt_m, reales)
    estabilidad_por_tercios(frames)
    recuento(frames)
    clasificar_faltantes(frames, dets, todas)

    with open(args.colores, "rb") as f:
        colores = pickle.load(f)
    masa = masa_de_ventana(reales, {k: v.tolist() for k, v in dets.items()}, colores)[
        ["frame", "id_jugador", "masa"]
    ]
    clasificar_sobrantes(frames, reales, masa)
    desplazadas(frames, gt_m)
    encuadre(frames)
    tabla = partido_entero(reales, dets, masa, set(gt_m))
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(args.salida)
    print(f"\n(tabla por minuto en {args.salida})")


if __name__ == "__main__":
    main()
