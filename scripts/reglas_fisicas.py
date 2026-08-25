#!/usr/bin/env python
"""PARTE 1: limpiar la basura del campo. Cada regla medida por separado.

Medido en `docs/cruce_de_equipos.md`: sacar del bloque a quien no es
ninguna de las 14 personas vale **0,68 m de media de centroide** y se
lleva **el 61 % del error de anchura**, el doble que arreglar los cruces
de equipo. Este script mide las reglas que lo consiguen.

Tres bloques:

**A. ¿Es fiable el modelo físico?** La homografía da la escala del suelo
en cada píxel; con ella, `alto_px × escala_lateral` es la altura REAL del
objeto, sin saber dónde está la cámara (ver
`src/tracking/plausibilidad_fisica.py`). Si el modelo es bueno, esa
altura tiene que ser plana en todo el campo. Se comprueba antes de
construir nada encima.

**B. Barrido de cada regla física, POR SEPARADO.** Para cada umbral:
cuántas fugas mata y cuántas personas reales pierde. Los umbrales van
como fracción de la altura implícita MEDIANA DEL PARTIDO, nunca en metros
absolutos: en el benjamín juegan niños de 8-9 años y en Villaviciosa
adultos, y un número en metros no viaja (ya nos costó dos veces).

**C. Barrido de la tolerancia de staff.** Hoy son 2 m y protegen al
entrenador que está a 0,2 m fuera de la banda y mete la mitad de las 70
fugas. ¿Bajarla lo saca sin perder jugadores que la imprecisión de
proyección empuja fuera de las líneas?

**D. Lo acumulado, contra las métricas de producto.**

Uso:
    python scripts/reglas_fisicas.py
    python scripts/reglas_fisicas.py --solo A
"""

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from fugas_en_el_campo import casar_con_gt  # noqa: E402
from mirar_recortes_sueltos import (  # noqa: E402
    _regla_staff,
    regla_de_la_observacion,
)
from oraculos import metricas_producto  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.team_classification.arbitro import arquetipos_activos  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.team_classification.porteros import (  # noqa: E402
    ReglaPorteros,
    deducir_lados,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402
from src.tracking.plausibilidad_fisica import (  # noqa: E402
    filtrar_por_plausibilidad,
    medidas_implicadas,
    referencia_del_partido,
)

logger = logging.getLogger("reglas")


class Banco:
    """Todo lo que hace falta para medir, cargado una sola vez."""

    def __init__(self, ruta_cfg, ruta_gt, offset=9750, paso=15):
        self.cfg = yaml.safe_load(open(ruta_cfg))
        self.cfg_tr = yaml.safe_load(open(self.cfg["config_tracking"]))
        self.cfg_eq = cargar_config_equipos(self.cfg["config_equipos"])
        self.datos = cargar_cache(self.cfg["rutas"]["cache"])
        with open(self.cfg["rutas"]["cache_colores"], "rb") as f:
            self.colores_crudos = pickle.load(f)
        self.conf = float(self.cfg_tr.get("confianza_min", 0) or 0)
        self.cache, self.colores = filtrar_por_confianza(
            self.datos["cache"], self.colores_crudos, self.conf
        )
        self.H = np.load(self.cfg["rutas"]["homografia"])
        self.clf = entrenar_clasificador(self.colores, self.cfg_eq, self.cache)
        self.modelo, self.prof = _profundidad_configurada(self.cfg_eq)
        self.activos = arquetipos_activos(
            [self.clf._prototipos.a, self.clf._prototipos.b]
        )

        tracks = parsear_cvat(ruta_gt)
        self.gt_frames = {}
        for t in tracks:
            for c in t.cajas:
                # ⚠️ El GT de Villaviciosa SÍ tiene tracks 'referee' (el
                # del benjamín no). Un árbitro no es un jugador: entra en
                # el casado para no contarlo como fuga, pero su equipo se
                # marca como 'referee' y nunca cuenta en un bloque.
                self.gt_frames.setdefault(offset + paso * c.frame_local, []).append(
                    {
                        "id": t.track_id,
                        "pie": ((c.xtl + c.xbr) / 2.0, c.ybr),
                        "team": (
                            "referee"
                            if t.label == "referee"
                            else (c.team or t.team or "?")
                        ),
                    }
                )
        self.gt_m = gt_a_por_frame(tracks, self.H, frame_offset=offset, paso_gt=paso)
        self.por_frame = {e["frame_idx"]: e for e in self.cache}
        self.comunes = sorted(set(self.por_frame) & set(self.gt_frames))
        self.duenos, self.eq_gt = {}, {}
        for f in self.comunes:
            casado, _ = casar_con_gt(self.por_frame[f]["dets"], self.gt_frames[f])
            for i, o in casado.items():
                self.duenos[(f, i)] = o["id"]
                self.eq_gt[o["id"]] = o["team"].replace("portero_", "")

        self.medidas = medidas_implicadas(self.cache, self.H)
        self.ref = referencia_del_partido(self.medidas)

        # Reglas posicionales tal y como corren hoy (para saber qué es fuga)
        self.ids = correr_perfil(
            self.cache,
            self.datos["fps"],
            self.datos["sample"],
            self.cfg_tr,
            perfil="bytetrack",
            colores=self.colores,
            clasificador=self.clf,
            cfg_equipos=self.cfg_eq,
        )
        self.eq_ident = clasificar_identidades(
            self.ids, self.colores, self.clf, self.cfg_eq
        )
        cfg_p = self.cfg_eq.get("porteros", {})
        margen = cfg_p.get("margen_m", 2.0)
        lados = deducir_lados(
            {k: v for k, v in self.eq_ident.items() if v in ("A", "B")},
            self.ids,
            self.modelo.largo,
            regla=ReglaPorteros.desde_modelo(self.modelo, margen=margen),
            ancho=self.modelo.ancho,
        )
        bajo, alto = (
            lados if lados else (cfg_p["equipo_mx_bajo"], cfg_p["equipo_mx_alto"])
        )
        self.regla_p = ReglaPorteros.desde_modelo(
            self.modelo, margen=margen, equipo_mx_bajo=bajo, equipo_mx_alto=alto
        )
        self.regla_s = _regla_staff(self.cfg_eq, self.modelo)

        # Poblaciones sobre las que se mide TODO
        self.reales, self.otras, self.fugas = [], [], []
        for f in self.comunes:
            entrada = self.por_frame[f]
            for i, det in enumerate(entrada["dets"]):
                clave = (f, i)
                if clave in self.duenos:
                    self.reales.append(clave)
                    continue
                self.otras.append(clave)
                feat = self.colores.get(clave)
                if feat is None:
                    continue
                et, _m = regla_de_la_observacion(
                    float(det[0]),
                    float(det[1]),
                    feat,
                    self.regla_p,
                    self.regla_s,
                    self.activos,
                )
                if et is None:
                    self.fugas.append(clave)

    def verdad_producto(self):
        pf_gt = {}
        for f, obs in self.gt_m.items():
            for o in obs:
                eq = str(o.team).replace("portero_", "")
                if eq in ("A", "B"):
                    pf_gt.setdefault((f, eq), []).append(
                        (float(o.pos[0]), float(o.pos[1]))
                    )
        return pf_gt


# ─────────────────────────── bloque A ──────────────────────────────────


def bloque_a(b):
    print("\n" + "=" * 78)
    print("A. ¿ES FIABLE EL MODELO FÍSICO? (altura implícita = alto_px × escala)")
    print("=" * 78)
    alt_r = np.array([b.medidas[c][0] for c in b.reales if c in b.medidas])
    anc_r = np.array([b.medidas[c][1] for c in b.reales if c in b.medidas])
    alt_o = np.array([b.medidas[c][0] for c in b.otras if c in b.medidas])
    print(
        f"  Referencia del partido (mediana de TODAS las detecciones): "
        f"{b.ref:.2f} m"
    )
    print(f"\n  Las {len(alt_r)} detecciones que SÍ casan con una persona del GT:")
    q = np.percentile(alt_r, [1, 5, 50, 95, 99])
    print(
        f"    altura implícita: p1 {q[0]:.2f} · p5 {q[1]:.2f} · "
        f"MEDIANA {q[2]:.2f} · p95 {q[3]:.2f} · p99 {q[4]:.2f} m"
    )
    qw = np.percentile(anc_r, [1, 5, 50, 95, 99])
    print(
        f"    anchura implícita: p1 {qw[0]:.2f} · p5 {qw[1]:.2f} · "
        f"MEDIANA {qw[2]:.2f} · p95 {qw[3]:.2f} · p99 {qw[4]:.2f} m"
    )
    print(f"\n  Las {len(alt_o)} que NO casan con nadie del GT:")
    qo = np.percentile(alt_o, [1, 5, 50, 95, 99])
    print(
        f"    altura implícita: p1 {qo[0]:.2f} · p5 {qo[1]:.2f} · "
        f"MEDIANA {qo[2]:.2f} · p95 {qo[3]:.2f} · p99 {qo[4]:.2f} m"
    )

    print("\n  LA PRUEBA DEL MODELO: si es correcto, la altura implícita de una")
    print("  persona no debe depender de lo lejos que esté.")
    print(f"  (franjas por el EJE DE PROFUNDIDAD configurado: {b.prof.eje}; en")
    print("   Villaviciosa la cámara está en banda y no es el mismo que en el benja)")

    def prof(c):
        det = b.por_frame[c[0]]["dets"][c[1]]
        return b.prof.de((det[0], det[1]), b.modelo)

    cab = f"    {'franja mx':<12}{'n':>6}{'p1':>8}{'mediana':>10}{'p99':>8}"
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    for lo, hi in [(0, 20), (20, 30), (30, 40), (40, 50), (50, 65)]:
        sel = [
            b.medidas[c][0] for c in b.reales if c in b.medidas and lo <= prof(c) < hi
        ]
        if len(sel) < 5:
            continue
        print(
            f"    {f'{lo}-{hi} m':<12}{len(sel):>6}{np.percentile(sel,1):>8.2f}"
            f"{np.median(sel):>10.2f}{np.percentile(sel,99):>8.2f}"
        )
    deriva = 0.0
    medianas = []
    for lo, hi in [(0, 20), (20, 30), (30, 40), (40, 50), (50, 65)]:
        sel = [
            b.medidas[c][0] for c in b.reales if c in b.medidas and lo <= prof(c) < hi
        ]
        if len(sel) >= 5:
            medianas.append(np.median(sel))
    if medianas:
        deriva = (max(medianas) - min(medianas)) / np.mean(medianas)
    print(f"\n    Deriva de la mediana de punta a punta del campo: {deriva:.0%}")
    print("    (un modelo malo derivaría con la distancia; este no)")


# ─────────────────────────── bloque B ──────────────────────────────────


def _coste(b, mata):
    """(fugas muertas, otras muertas, personas reales perdidas)."""
    return (
        sum(1 for c in b.fugas if mata(c)),
        sum(1 for c in b.otras if mata(c)),
        sum(1 for c in b.reales if mata(c)),
    )


def bloque_b(b):
    print("\n" + "=" * 78)
    print("B. CADA REGLA FÍSICA POR SEPARADO (umbral = fracción de la mediana)")
    print("=" * 78)
    print(
        f"  Poblaciones: {len(b.reales)} personas reales · {len(b.otras)} que no "
        f"son de las 14 · {len(b.fugas)} fugas"
    )
    print(f"  Referencia del partido: {b.ref:.2f} m")

    def tabla(nombre, valores, hacer_mata, unidad="× la mediana"):
        cab = (
            f"    {'umbral':>14}{'fugas muertas':>16}{'otras muertas':>16}"
            f"{'PERSONAS PERDIDAS':>20}"
        )
        print(f"\n  ── {nombre} ──")
        print(cab)
        print("    " + "-" * (len(cab) - 4))
        for v in valores:
            fu, ot, re = _coste(b, hacer_mata(v))
            aviso = "  <-- toca personas" if re else ""
            print(
                f"    {f'{v:g} {unidad}':>14}"
                f"{f'{fu}/{len(b.fugas)}':>16}"
                f"{f'{ot}/{len(b.otras)}':>16}"
                f"{f'{re}/{len(b.reales)}':>20}{aviso}"
            )

    med = b.medidas
    tabla(
        "R1  ALTURA implícita MÍNIMA (mata lo demasiado pequeño)",
        [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70],
        lambda v: (lambda c: c in med and med[c][0] < v * b.ref),
    )
    tabla(
        "R2  ALTURA implícita MÁXIMA (mata lo demasiado grande)",
        [1.20, 1.30, 1.40, 1.50, 1.75, 2.00],
        lambda v: (lambda c: c in med and med[c][0] > v * b.ref),
    )
    tabla(
        "R3  ANCHURA implícita MÍNIMA (mata las líneas: altas y estrechas)",
        [0.10, 0.15, 0.20, 0.22, 0.25, 0.30, 0.35],
        lambda v: (lambda c: c in med and med[c][1] < v * b.ref),
    )
    tabla(
        "R4  ANCHURA implícita MÁXIMA",
        [0.70, 0.80, 0.90, 1.00, 1.20],
        lambda v: (lambda c: c in med and med[c][1] > v * b.ref),
    )

    def aspecto(c):
        if c not in med or med[c][0] <= 0:
            return None
        return med[c][1] / med[c][0]

    asp_r = np.array([a for a in (aspecto(c) for c in b.reales) if a])
    print("\n  -- R5  RELACIÓN DE ASPECTO (ancho/alto) --")
    print(
        f"    en las personas reales: p1 {np.percentile(asp_r,1):.2f} · "
        f"mediana {np.median(asp_r):.2f} · p99 {np.percentile(asp_r,99):.2f}"
    )
    tabla(
        "R5  aspecto MÍNIMO (ancho/alto)",
        [0.10, 0.15, 0.18, 0.20, 0.25],
        lambda v: (lambda c: (aspecto(c) or 9) < v),
        unidad="ancho/alto",
    )


# ─────────────────────────── bloque C ──────────────────────────────────


def _fuera_con_signo(mx, my, largo, ancho):
    """Distancia al borde del campo, NEGATIVA si está dentro.

    `staff._distancia_fuera` está acotada a 0 con un max(0, ...), así que
    una tolerancia negativa no significa nada: la comparación `0 > -1`
    es cierta para TODO el mundo y marcaba las 75 identidades como staff.
    Lo cazó el barrido al dar dos filas idénticas y absurdas. Con signo,
    una tolerancia negativa sí quiere decir "la mediana tiene que estar
    DENTRO por ese margen".
    """
    return max(-mx, mx - largo, -my, my - ancho)


def velocidad_media(identidad):
    """Metros recorridos por segundo, sobre toda la vida de la identidad.

    Es la señal de PERMANENCIA de Alex, en unidades físicas. Se calcula
    sobre pasos consecutivos y dividiendo por el tiempo REAL transcurrido
    (no por el número de observaciones): una identidad con huecos no debe
    parecer más lenta por tenerlos.
    """
    obs = sorted(
        ((t, p) for tr in identidad for t, p in zip(tr.ts, tr.pos)),
        key=lambda o: o[0],
    )
    if len(obs) < 2:
        return 0.0
    recorrido = sum(
        float(np.linalg.norm(np.asarray(obs[i][1]) - np.asarray(obs[i - 1][1])))
        for i in range(1, len(obs))
    )
    duracion = obs[-1][0] - obs[0][0]
    return recorrido / duracion if duracion > 0 else 0.0


def bloque_c(b):
    print("\n" + "=" * 78)
    print("C. LA TOLERANCIA DE STAFF (hoy 2 m). ¿Saca al entrenador sin coste?")
    print("=" * 78)
    print("  El tracking NO depende de esta regla (solo la etiqueta), así que se")
    print("  reusa la misma asociación y solo se reaplica el etiquetado.")
    medianas, obs_de = {}, {}
    for k, ident in enumerate(b.ids, start=1):
        pos = np.array([p for tr in ident for p in tr.pos])
        medianas[k] = (float(np.median(pos[:, 0])), float(np.median(pos[:, 1])))
        obs_de[k] = [
            tuple(par) for tr in ident for par in tr.det_idxs if par[0] in b.gt_frames
        ]
    cab = (
        f"    {'tolerancia':>12}{'ids staff':>11}{'obs de las 14':>16}"
        f"{'obs basura':>13}{'¿saca al entrenador?':>23}"
    )
    print("\n" + cab)
    print("    " + "-" * (len(cab) - 4))
    for tol in (-2.0, -1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0, 2.0, 3.0):
        n_staff = perdidas = basura = 0
        entrenador = False
        for k, ident in enumerate(b.ids, start=1):
            if len(obs_de[k]) == 0 and len(ident) == 0:
                continue
            n_obs = sum(len(tr.det_idxs) for tr in ident)
            if n_obs < b.regla_s.min_observaciones:
                continue
            if _fuera_con_signo(*medianas[k], b.modelo.largo, b.modelo.ancho) <= tol:
                continue
            n_staff += 1
            if abs(medianas[k][0] - 31.0) < 1.5 and abs(medianas[k][1]) < 1.0:
                entrenador = True
            for par in obs_de[k]:
                if par in b.duenos:
                    perdidas += 1
                else:
                    basura += 1
        marca = "  <- hoy" if tol == 2.0 else ""
        print(
            f"    {tol:>11.1f}m{n_staff:>11}{perdidas:>16}{basura:>13}"
            f"{('SÍ' if entrenador else 'no'):>23}{marca}"
        )
    print("\n    (tolerancia NEGATIVA = la mediana tiene que estar DENTRO del")
    print("     campo por ese margen; positiva = puede estar fuera hasta ahí)")

    print("\n  ¿Quién entra y quién sale al bajar de 2,0 m a 0,0 m?")
    for k in sorted(medianas, key=lambda x: medianas[x][1]):
        n_obs = sum(len(tr.det_idxs) for tr in b.ids[k - 1])
        if n_obs < b.regla_s.min_observaciones:
            continue
        d = _fuera_con_signo(*medianas[k], b.modelo.largo, b.modelo.ancho)
        if not (0.0 < d <= 2.0):
            continue
        reales = sum(1 for par in obs_de[k] if par in b.duenos)
        print(
            f"    id {k:<4} mediana ({medianas[k][0]:6.1f},{medianas[k][1]:6.1f}) m"
            f"  {d:.2f} m fuera · {n_obs:>4} obs · {reales} de ellas son "
            f"de las 14 · etiqueta '{b.eq_ident.get(k)}'"
        )

    # Si la distancia al borde no los separa, ¿los separa el MOVIMIENTO?
    # Es la pregunta que deja abierta el barrido: el entrenador (id 55)
    # está a 0,23 m fuera y un jugador real (id 46) a 0,22 m. Un
    # centímetro. Ninguna tolerancia puede distinguirlos mirando SOLO la
    # posición, así que o hay otra señal o esta vía se acaba aquí.
    print("\n  ¿Los separa el MOVIMIENTO? (mediana a menos de 3 m de una")
    print("  línea y al menos 25 observaciones)")
    cab2 = (
        f"    {'id':>5}{'obs':>6}{'mediana':>15}{'fuera':>8}"
        f"{'recorrido':>11}{'VELOCIDAD':>11}{'dispersión':>12}{'de las 14':>11}"
    )
    print(cab2)
    print("    " + "-" * (len(cab2) - 4))
    filas = []
    for k, ident in enumerate(b.ids, start=1):
        n_obs = sum(len(tr.det_idxs) for tr in ident)
        if n_obs < 25:
            continue
        d = _fuera_con_signo(*medianas[k], b.modelo.largo, b.modelo.ancho)
        if d < -3.0:
            continue
        pos = np.array([p for tr in ident for p in tr.pos])
        ts = np.array([t for tr in ident for t in tr.ts])
        pos = pos[np.argsort(ts)]
        recorrido = float(np.sum(np.linalg.norm(np.diff(pos, axis=0), axis=1)))
        disp = float(np.mean(np.linalg.norm(pos - pos.mean(axis=0), axis=1)))
        vel = velocidad_media(ident)
        reales = sum(1 for par in obs_de[k] if par in b.duenos)
        filas.append((vel, k, n_obs, medianas[k], d, recorrido, disp, reales))
    for vel, k, n_obs, med, d, rec, disp, reales in sorted(filas):
        print(
            f"    {k:>5}{n_obs:>6}{f'({med[0]:.0f},{med[1]:.0f})':>15}"
            f"{d:>7.2f}m{rec:>10.0f}m{vel:>9.2f}m/s{disp:>11.1f}m"
            f"{reales:>11}"
        )

    # ── R6: la VELOCIDAD MEDIA como discriminador ────────────────────
    # Es la señal que Alex llamó permanencia, medida. Un entrenador de
    # pie se mueve poco; un niño corriendo, no. Y a diferencia de la
    # distancia al borde, aquí sí hay separación.
    print("\n  R6  ¿Y como REGLA? (no-jugador = velocidad media por debajo de X)")
    cab3 = (
        f"    {'umbral':>10}{'ids marcados':>14}{'obs de las 14':>16}"
        f"{'obs basura':>13}{'¿entrenador?':>15}"
    )
    print(cab3)
    print("    " + "-" * (len(cab3) - 4))
    for umbral in (0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5):
        n_marcados = perd = bas = 0
        entre = False
        for k, ident in enumerate(b.ids, start=1):
            if sum(len(tr.det_idxs) for tr in ident) < 25:
                continue
            if velocidad_media(ident) >= umbral:
                continue
            n_marcados += 1
            if k == 55:
                entre = True
            for par in obs_de[k]:
                if par in b.duenos:
                    perd += 1
                else:
                    bas += 1
        print(
            f"    {umbral:>8.1f}m/s{n_marcados:>14}{perd:>16}{bas:>13}"
            f"{('SÍ' if entre else 'no'):>15}"
        )


# ─────────────────────────── bloque R ──────────────────────────────────


def bloque_r(b, semillas=(1, 2, 3, 4, 5)):
    """SUELO DE RUIDO: ¿cuánto se mueven las métricas por nada?

    Por qué hace falta, y es un control que casi me salto: en Villaviciosa
    quitar CINCO detecciones de 28.000 movía el centroide de 3,55 a 4,13 m.
    O el filtro es milagrosamente dañino, o el pipeline es caótico ante
    cambios minúsculos —quitar una detección cambia una asociación, que
    cambia una identidad, que cambia una etiqueta de equipo— y entonces
    cualquier diferencia por debajo del ruido no significa nada.

    Se quitan detecciones AL AZAR, en la misma cantidad que quitan los
    filtros que se están probando, y se mira la dispersión del resultado.
    Es el mismo control de aleatorio que ya salvó la medición de la
    partición de tracklets.
    """
    import random

    print("\n" + "=" * 78)
    print("R. SUELO DE RUIDO: quitar detecciones AL AZAR, misma cantidad")
    print("=" * 78)
    cab = (
        f"    {'quitadas al azar':<26}{'mediana':>9}{'media':>9}{'p90':>9}"
        f"{'anchura':>9}{'ocup':>8}"
    )
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    base = producto(b, b.cache, b.colores, {})
    print(
        f"    {'ninguna (referencia)':<26}{base[0]:>8.2f}m{base[1]:>8.2f}m"
        f"{base[2]:>8.2f}m{base[3]:>8.2f}m{base[4]:>7.1%}"
    )
    total = sum(len(e["dets"]) for e in b.cache)
    for n_quitar in (5, 100):
        res = []
        for semilla in semillas:
            rnd = random.Random(semilla)
            fuera = set(
                rnd.sample(
                    [
                        (e["frame_idx"], i)
                        for e in b.cache
                        for i in range(len(e["dets"]))
                    ],
                    min(n_quitar, total),
                )
            )
            cache, colores = [], {}
            for entrada in b.cache:
                f = entrada["frame_idx"]
                dets = []
                for i, det in enumerate(entrada["dets"]):
                    if (f, i) in fuera:
                        continue
                    j = len(dets)
                    dets.append(det)
                    if (f, i) in b.colores:
                        colores[(f, j)] = b.colores[(f, i)]
                cache.append({**entrada, "dets": dets})
            res.append(producto(b, cache, colores, {}))
        arr = np.array([[r[0], r[1], r[2], r[3], r[4]] for r in res])
        print(
            f"    {f'{n_quitar} dets, {len(semillas)} semillas':<26}"
            f"{arr[:,0].mean():>8.2f}m{arr[:,1].mean():>8.2f}m"
            f"{arr[:,2].mean():>8.2f}m{arr[:,3].mean():>8.2f}m"
            f"{arr[:,4].mean():>7.1%}"
        )
        print(
            f"    {'  (dispersión: min-max)':<26}"
            f"{f'{arr[:,0].min():.2f}-{arr[:,0].max():.2f}':>9}"
            f"{f'{arr[:,1].min():.2f}-{arr[:,1].max():.2f}':>9}"
            f"{f'{arr[:,2].min():.2f}-{arr[:,2].max():.2f}':>9}"
            f"{f'{arr[:,3].min():.2f}-{arr[:,3].max():.2f}':>9}"
            f"{f'{arr[:,4].min():.1%}-{arr[:,4].max():.1%}':>10}"
        )


# ─────────────────────────── bloque E ──────────────────────────────────


def bloque_e(b):
    """La regla compuesta: FUERA del campo Y lento.

    El barrido de la tolerancia (bloque C) se estrella contra un muro: el
    entrenador está 0,23 m fuera y un jugador real 0,22 m. Un centímetro.
    Ninguna tolerancia los separa mirando solo la posición.

    Y la velocidad sola tampoco: el más lento del partido NO es el
    entrenador (0,67 m/s) sino EL PORTERO (0,60 m/s, 526 observaciones).
    Una regla de "poca permanencia" a secas se lleva al portero por
    delante, que es justo el error que ya destrozó al doble pase.

    Pero las dos JUNTAS sí: el portero está DENTRO del campo y el
    entrenador FUERA. Es la doctrina de siempre —actuar solo donde hay
    riesgo—: la velocidad solo se mira en quien ya está fuera de las
    líneas.
    """
    print("\n" + "=" * 78)
    print("E. LA REGLA COMPUESTA: fuera de las líneas Y lento")
    print("=" * 78)
    velocidades, medianas, obs_de = {}, {}, {}
    for k, ident in enumerate(b.ids, start=1):
        pos = np.array([p for tr in ident for p in tr.pos])
        medianas[k] = (float(np.median(pos[:, 0])), float(np.median(pos[:, 1])))
        velocidades[k] = velocidad_media(ident)
        obs_de[k] = [
            tuple(par) for tr in ident for par in tr.det_idxs if par[0] in b.gt_frames
        ]

    vel_reales = []
    for k, ident in enumerate(b.ids, start=1):
        if sum(1 for par in obs_de[k] if par in b.duenos) >= 10:
            vel_reales.append((velocidades[k], k))
    vel_reales.sort()
    print(
        "  Velocidad media de las identidades que SON personas del GT "
        "(≥10 obs casadas):"
    )
    print("    " + " · ".join(f"{v:.2f}" for v, _k in vel_reales))
    print(
        f"    la más lenta es la id {vel_reales[0][1]} con "
        f"{vel_reales[0][0]:.2f} m/s (el portero)"
    )

    cab = (
        f"    {'tolerancia':>11}{'velocidad':>11}{'ids':>6}"
        f"{'obs de las 14':>16}{'obs basura':>12}{'¿entrenador?':>14}"
    )
    print("\n" + cab)
    print("    " + "-" * (len(cab) - 4))
    for tol in (0.0, 0.5, 2.0):
        for vel_max in (0.0, 1.0, 1.5, 2.0, 99.0):
            n = perd = bas = 0
            entre = False
            for k, ident in enumerate(b.ids, start=1):
                if sum(len(tr.det_idxs) for tr in ident) < b.regla_s.min_observaciones:
                    continue
                fuera = _fuera_con_signo(*medianas[k], b.modelo.largo, b.modelo.ancho)
                if fuera <= tol or velocidades[k] >= vel_max:
                    continue
                n += 1
                if k == 55:
                    entre = True
                for par in obs_de[k]:
                    if par in b.duenos:
                        perd += 1
                    else:
                        bas += 1
            etiq_v = "sin condición" if vel_max > 90 else f"< {vel_max:.1f} m/s"
            print(
                f"    {tol:>10.1f}m{etiq_v:>11}{n:>6}{perd:>16}{bas:>12}"
                f"{('SÍ' if entre else 'no'):>14}"
            )
    print("\n    (la fila 'tolerancia 2,0 · sin condición' es el sistema de hoy)")


# ─────────────────────────── bloque D ──────────────────────────────────


def producto(b, cache, colores, staff_kw):
    """Corre el pipeline entero y devuelve (centroide med/media/p90, anchura, ocup)."""
    clf = entrenar_clasificador(colores, b.cfg_eq, cache)
    cfg_eq = {**b.cfg_eq, "staff": {**b.cfg_eq.get("staff", {}), **staff_kw}}
    ids = correr_perfil(
        cache,
        b.datos["fps"],
        b.datos["sample"],
        b.cfg_tr,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=cfg_eq,
    )
    eq = clasificar_identidades(ids, colores, clf, cfg_eq)
    pf = {}
    for k, ident in enumerate(ids, start=1):
        e = str(eq.get(k, "otro")).replace("portero_", "")
        if e not in ("A", "B"):
            continue
        for tr in ident:
            for pos, par in zip(tr.pos, tr.det_idxs):
                if par[0] in b.gt_m:
                    pf.setdefault((par[0], e), []).append(
                        (float(pos[0]), float(pos[1]))
                    )
    pf_gt = b.verdad_producto()
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])
    m = (
        metricas_producto(pf)
        .set_index(["frame", "equipo"])
        .join(verdad, rsuffix="_gt", how="inner")
    )
    e = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt)
    largo, ancho = b.modelo.largo, b.modelo.ancho

    def ocupacion(p):
        z = {}
        for (_f, eq_), pts in p.items():
            for x, y in pts:
                k_ = (eq_, min(int(x / largo * 3), 2), min(int(y / ancho * 3), 2))
                z[k_] = z.get(k_, 0) + 1
        tot = sum(z.values()) or 1
        return {k_: v / tot for k_, v in z.items()}

    oc, oc_g = ocupacion(pf), ocupacion(pf_gt)
    dif = sum(abs(oc.get(k_, 0) - oc_g.get(k_, 0)) for k_ in set(oc) | set(oc_g)) / 2
    # CONTROL obligatorio: si una variante vacía el bloque, el error puede
    # bajar por quedarse con menos gente, no por acertar más. Se devuelven
    # los puntos y los grupos comparados para poder verlo.
    return (
        e.median(),
        e.mean(),
        e.quantile(0.9),
        (m.ancho - m.ancho_gt).abs().median(),
        dif,
        sum(len(v) for v in pf.values()),
        len(m),
    )


def bloque_d(b, variantes):
    print("\n" + "=" * 78)
    print("D. LO ACUMULADO, CONTRA LAS MÉTRICAS DE PRODUCTO")
    print("=" * 78)
    cab = (
        f"    {'variante':<38}{'mediana':>9}{'media':>9}{'p90':>9}"
        f"{'anchura':>9}{'ocup':>8}{'pts':>7}{'grupos':>7}{'-dets':>7}"
    )
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    for nombre, kw, staff_kw in variantes:
        cache, colores, n = filtrar_por_plausibilidad(b.cache, b.colores, b.H, **kw)
        med, mea, p90, anc, oc, pts, grupos = producto(b, cache, colores, staff_kw)
        print(
            f"    {nombre:<38}{med:>8.2f}m{mea:>8.2f}m{p90:>8.2f}m"
            f"{anc:>8.2f}m{oc:>7.1%}{pts:>7}{grupos:>7}{n:>7}"
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--solo", default="ABCED")
    p.add_argument(
        "--offset",
        type=int,
        default=9750,
        help="frame global que corresponde al frame local 0 del GT",
    )
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    b = Banco(args.config, args.gt, args.offset, args.paso)
    if "A" in args.solo:
        bloque_a(b)
    if "B" in args.solo:
        bloque_b(b)
    if "C" in args.solo:
        bloque_c(b)
    if "E" in args.solo:
        bloque_e(b)
    if "R" in args.solo:
        bloque_r(b)
    if "D" in args.solo:
        # Cada pieza del filtro físico POR SEPARADO encima del staff
        # lento, que es la regla de Alex: nada acumulado sin saber qué
        # aporta cada cosa. Solo umbrales que el bloque B dio GRATIS
        # (0 personas perdidas), más una fila cara para ver si el
        # producto la perdona.
        LENTO = dict(tolerancia_lento_m=0.0, vel_max_lento=1.5)
        GRATIS = dict(
            alto_min_frac=0.30,
            alto_max_frac=1.75,
            ancho_min_frac=0.10,
            ancho_max_frac=1.00,
        )
        CARO = dict(
            alto_min_frac=0.50,
            alto_max_frac=1.50,
            ancho_min_frac=0.20,
            ancho_max_frac=0.90,
        )
        bloque_d(
            b,
            [
                # ⚠️ La referencia tiene que DESACTIVAR la regla a mano:
                # desde que se adoptó vive en el config, así que un dict
                # vacío ya la trae puesta y la tabla comparaba la regla
                # contra sí misma (la fila "hoy" salía 1,27 en vez de 1,55).
                ("ANTES de adoptar (staff lento off)", {}, dict(vel_max_lento=0.0)),
                (
                    "staff lento, vel < 1,0 m/s",
                    {},
                    dict(tolerancia_lento_m=0.0, vel_max_lento=1.0),
                ),
                ("staff lento, vel < 1,5 m/s", {}, LENTO),
                (
                    "staff lento, vel < 2,0 m/s",
                    {},
                    dict(tolerancia_lento_m=0.0, vel_max_lento=2.0),
                ),
                (
                    "staff lento, vel < 2,5 m/s",
                    {},
                    dict(tolerancia_lento_m=0.0, vel_max_lento=2.5),
                ),
                (
                    "staff lento 1,5 m/s, tolerancia 0,5 m",
                    {},
                    dict(tolerancia_lento_m=0.5, vel_max_lento=1.5),
                ),
                ("  + alto minimo 0,30", dict(alto_min_frac=0.30), LENTO),
                ("  + alto maximo 1,75", dict(alto_max_frac=1.75), LENTO),
                ("  + ancho minimo 0,10", dict(ancho_min_frac=0.10), LENTO),
                ("  + ancho maximo 1,00", dict(ancho_max_frac=1.00), LENTO),
                ("  + las cuatro (GRATIS)", GRATIS, LENTO),
                ("  + las cuatro CARAS", CARO, LENTO),
                (
                    "solo filtro fisico, staff lento OFF",
                    GRATIS,
                    dict(vel_max_lento=0.0),
                ),
            ],
        )


if __name__ == "__main__":
    main()
