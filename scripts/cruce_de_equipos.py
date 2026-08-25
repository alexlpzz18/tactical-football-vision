#!/usr/bin/env python
"""CERO cruces de equipo: la métrica nueva y el techo del veto de color.

Cambio de objetivo pedido por Alex (25-ago-2026): para el replay
COLECTIVO, una quimera entre compañeros del mismo equipo es **invisible**
—el bloque sigue teniendo a los mismos niños en los mismos sitios—. Lo
único que rompe el centroide, la anchura y la ocupación es que un jugador
aparezca en el equipo contrario. Así que la métrica deja de ser "quimeras"
y pasa a ser:

  1. **observaciones con el equipo equivocado**
  2. **identidades que contienen personas de los DOS equipos**

Las quimeras del mismo equipo se anotan APARTE y no cuentan como fallo.

Y la pregunta de fondo: si el color acierta el 96 % en un recorte suelto,
¿por qué acaba el sistema llamando naranja a un blanco? La propuesta es
usar el equipo como RESTRICCIÓN de la asociación. Antes de construir nada
hay que medir su TECHO, y este script lo mide:

**Bloque 1** — la métrica sobre el sistema de hoy, con la descomposición
que decide si la vía tiene sentido: ¿las observaciones mal etiquetadas
vienen de identidades que MEZCLAN equipos (y entonces el veto es la
palanca) o de identidades PURAS mal etiquetadas (y entonces el problema
no es la asociación, es la etiqueta)?

**Bloque 2** — el techo: de los saltos de persona dentro de una
identidad, cuántos son entre equipos distintos, y en cuántos de esos el
color POR OBSERVACIÓN ya dice cosas distintas a los dos lados. Solo esos
puede cazarlos un veto de color: si el color dice lo mismo a ambos lados,
es ciego ahí.

**Bloque 3** — simulación barata de la opción "doble pase": partir el
caché por el color de cada observación y correr el pipeline ENTERO una
vez por equipo. No toca ByteTrack ni una línea. **Es una medición, no una
adopción.**

⚠️ El GT solo cubre 60 de los 600 frames del caché (1 de cada 15), así
que todo lo que dependa de identidad GT se mide sobre esos 60 y los
"saltos" tienen medio segundo de resolución.

Uso:
    python scripts/cruce_de_equipos.py
"""

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402

from fugas_en_el_campo import casar_con_gt  # noqa: E402
from oraculos import metricas_producto  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.team_classification.arbitro import identificar_arbitros  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.team_classification.porteros import (  # noqa: E402
    ReglaPorteros,
    aplicar_regla_porteros,
    deducir_lados,
)
from src.team_classification.staff import (  # noqa: E402
    ReglaStaff,
    aplicar_regla_staff,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("cruces")


def etiquetas_por_observacion(identidades, equipos):
    """{(frame, det_idx): etiqueta} a partir de las etiquetas por identidad."""
    salida = {}
    for k, ident in enumerate(identidades, start=1):
        et = str(equipos.get(k, "otro"))
        for tr in ident:
            for par in tr.det_idxs:
                salida[tuple(par)] = et
    return salida


def medir(identidades, equipos, duenos, eq_gt):
    """La métrica nueva: cruces de equipo, no quimeras.

    Returns:
        dict con las observaciones mal etiquetadas (desglosadas por si
        vienen de una identidad que mezcla equipos o de una pura), y el
        recuento de identidades por tipo.
    """
    etiquetas = etiquetas_por_observacion(identidades, equipos)
    tipo_de_ident = {}
    n_cruce = n_mismo = n_pura = 0
    for k, ident in enumerate(identidades, start=1):
        personas = {
            duenos[tuple(par)]
            for tr in ident
            for par in tr.det_idxs
            if tuple(par) in duenos
        }
        if not personas:
            tipo_de_ident[k] = "sin_gt"
            continue
        equipos_dentro = {eq_gt.get(p) for p in personas}
        if len(equipos_dentro) > 1:
            tipo_de_ident[k] = "cruce"
            n_cruce += 1
        elif len(personas) > 1:
            tipo_de_ident[k] = "mismo"
            n_mismo += 1
        else:
            tipo_de_ident[k] = "pura"
            n_pura += 1

    mal = {"cruce": 0, "mismo": 0, "pura": 0, "sin_gt": 0}
    total = 0
    for k, ident in enumerate(identidades, start=1):
        for tr in ident:
            for par in tr.det_idxs:
                par = tuple(par)
                persona = duenos.get(par)
                if persona is None:
                    continue
                total += 1
                if etiquetas.get(par, "otro").replace("portero_", "") != eq_gt[persona]:
                    mal[tipo_de_ident[k]] += 1
    return {
        "obs_total": total,
        "obs_mal": sum(mal.values()),
        "mal_por_tipo": mal,
        "ids_cruce": n_cruce,
        "ids_mismo": n_mismo,
        "ids_pura": n_pura,
        "ids_total": len(identidades),
    }


def imprimir(nombre, m):
    print(f"\n  ── {nombre} ──")
    print(
        f"     observaciones con el EQUIPO EQUIVOCADO : "
        f"{m['obs_mal']} de {m['obs_total']} = {m['obs_mal']/max(m['obs_total'],1):.1%}"
    )
    print(f"     identidades que MEZCLAN LOS DOS EQUIPOS: {m['ids_cruce']}")
    print(
        f"     (aparte, no cuentan como fallo) identidades que mezclan "
        f"personas del MISMO equipo: {m['ids_mismo']}"
    )
    print(f"     identidades puras: {m['ids_pura']} · totales: {m['ids_total']}")
    t = m["mal_por_tipo"]
    print(
        f"     de dónde salen las mal etiquetadas: "
        f"identidad que cruza equipos {t['cruce']} · "
        f"identidad pura mal etiquetada {t['pura']} · "
        f"quimera del mismo equipo {t['mismo']}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--sin-doble-pase", dest="doble", action="store_false")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores_crudos = pickle.load(f)
    cache, colores = filtrar_por_confianza(
        datos["cache"], colores_crudos, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    modelo, _prof = _profundidad_configurada(cfg_eq)

    # ── GT: quién es cada detección y de qué equipo ───────────────────
    tracks = parsear_cvat(args.gt)
    gt_frames = {}
    for t in tracks:
        for c in t.cajas:
            gt_frames.setdefault(9750 + 15 * c.frame_local, []).append(
                {
                    "id": t.track_id,
                    "pie": ((c.xtl + c.xbr) / 2.0, c.ybr),
                    "team": (c.team or t.team or "?"),
                }
            )
    por_frame = {e["frame_idx"]: e for e in cache}
    comunes = sorted(set(por_frame) & set(gt_frames))
    duenos, eq_gt = {}, {}
    for f in comunes:
        casado, _ = casar_con_gt(por_frame[f]["dets"], gt_frames[f])
        for i, o in casado.items():
            duenos[(f, i)] = o["id"]
            eq_gt[o["id"]] = o["team"].replace("portero_", "")

    ids = correr_perfil(
        cache,
        datos["fps"],
        datos["sample"],
        cfg_tr,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=cfg_eq,
    )
    eq_ident = clasificar_identidades(ids, colores, clf, cfg_eq)

    print("\n" + "=" * 74)
    print("1. LA MÉTRICA NUEVA sobre el sistema de hoy")
    print("=" * 74)
    print(
        f"  {len(comunes)} frames con GT · {len(duenos)} observaciones "
        f"casadas con una de las 14 personas"
    )
    m_sistema = medir(ids, eq_ident, duenos, eq_gt)
    imprimir("SISTEMA DE HOY (voto por identidad + reglas)", m_sistema)

    # Control: etiquetar por observación, sin tocar la asociación
    # OJO: sobre TODAS las detecciones del caché, no solo las que hoy
    # acaban dentro de una identidad. Construirlo desde las identidades
    # dejaba fuera las detecciones que ByteTrack descarta, y el doble
    # pase del bloque 3 se quedaba sin ellas: comparaba 719 observaciones
    # contra 729 y el número salía favorecido sin motivo.
    et_obs = {
        (entrada["frame_idx"], i): clf.predict_color(colores[(entrada["frame_idx"], i)])
        for entrada in cache
        for i in range(len(entrada["dets"]))
        if (entrada["frame_idx"], i) in colores
    }
    mal_obs = sum(
        1
        for par, g in duenos.items()
        if et_obs.get(par, "otro").replace("portero_", "") != eq_gt[g]
    )
    print("\n  -- control: etiqueta POR OBSERVACIÓN, misma asociación --")
    print(
        f"     observaciones con el EQUIPO EQUIVOCADO : "
        f"{mal_obs} de {len(duenos)} = {mal_obs/max(len(duenos),1):.1%}"
    )
    print(
        "     identidades que mezclan equipos: las MISMAS "
        f"({m_sistema['ids_cruce']}): etiquetar por observación no cambia "
        "la asociación, solo deja de arrastrar la etiqueta."
    )

    # ── 2. El techo del veto de color ─────────────────────────────────
    print("\n" + "=" * 74)
    print("2. EL TECHO: ¿cuántos saltos de persona puede ver el color?")
    print("=" * 74)
    saltos = {"mismo": 0, "cruce": 0}
    visibles = {"mismo": 0, "cruce": 0}
    # EL CONTROL QUE DUELE. Que el color no se equivoque en los saltos
    # entre compañeros no es mérito: visten igual, no puede verlos. La
    # falsa alarma de verdad es otra: entre dos observaciones seguidas de
    # LA MISMA PERSONA, ¿cuántas veces el color dice cosas distintas? Ahí
    # un veto por frame cortaría una identidad buena. Sin este número, el
    # 77 % de arriba sería un beneficio sin coste, y eso no existe.
    misma_persona = falsa_alarma = 0
    detalle = []
    for k, ident in enumerate(ids, start=1):
        obs = sorted(
            ((par[0], tuple(par)) for tr in ident for par in tr.det_idxs),
            key=lambda o: o[0],
        )
        obs = [(f, par) for f, par in obs if par in duenos]
        for j in range(1, len(obs)):
            p_ant, p_act = duenos[obs[j - 1][1]], duenos[obs[j][1]]
            if p_ant == p_act:
                c_a, c_b = et_obs.get(obs[j - 1][1]), et_obs.get(obs[j][1])
                if c_a is not None and c_b is not None:
                    misma_persona += 1
                    falsa_alarma += c_a != c_b
                continue
            cruce = eq_gt[p_ant] != eq_gt[p_act]
            clave = "cruce" if cruce else "mismo"
            saltos[clave] += 1
            c_ant = et_obs.get(obs[j - 1][1])
            c_act = et_obs.get(obs[j][1])
            ve = c_ant is not None and c_act is not None and c_ant != c_act
            visibles[clave] += ve
            if cruce:
                detalle.append((k, obs[j][0], p_ant, p_act, c_ant, c_act, ve))
    tot = saltos["mismo"] + saltos["cruce"]
    print(f"  saltos de persona dentro de una identidad: {tot}")
    print(
        f"    entre equipos DISTINTOS (lo que rompe el replay): "
        f"{saltos['cruce']} = {saltos['cruce']/max(tot,1):.0%}"
    )
    print(
        f"    entre compañeros del MISMO equipo (invisibles): "
        f"{saltos['mismo']} = {saltos['mismo']/max(tot,1):.0%}"
    )
    print(
        f"\n  De los {saltos['cruce']} saltos ENTRE EQUIPOS, el color por "
        f"observación ya dice cosas distintas a los dos lados en "
        f"{visibles['cruce']} = {visibles['cruce']/max(saltos['cruce'],1):.0%}"
    )
    print(
        f"    (en los saltos del MISMO equipo lo ve en "
        f"{visibles['mismo']}/{saltos['mismo']}: no es mérito, visten igual "
        f"y el color no puede verlos)"
    )
    print(
        f"\n  CONTROL DEL COSTE — entre dos observaciones SEGUIDAS DE LA "
        f"MISMA PERSONA,\n  el color dice cosas distintas en {falsa_alarma} "
        f"de {misma_persona} = {falsa_alarma/max(misma_persona,1):.1%}."
    )
    print(
        f"  Un veto aplicado en TODOS los frames haria ~{falsa_alarma} cortes "
        f"BUENOS\n  para cazar {visibles['cruce']} malos. Fragmentar es "
        f"recuperable, pero ese ratio\n  es el que decide DÓNDE se pone la "
        f"puerta."
    )
    if detalle:
        print(f"\n  Los {len(detalle)} saltos entre equipos, uno a uno:")
        print(
            f"    {'id':>4}{'frame':>8}  {'persona':<14}{'color antes|después':<22}"
            f"{'¿lo ve?':<8}"
        )
        for k, f, pa, pb, ca, cb, ve in detalle:
            print(
                f"    {k:>4}{f:>8}  {f'{pa} -> {pb}':<14}"
                f"{f'{ca} | {cb}':<22}{'SÍ' if ve else 'no':<8}"
            )

    if not args.doble:
        return

    # ── 3. Simulación del doble pase ──────────────────────────────────
    print("\n" + "=" * 74)
    print("3. SIMULACIÓN: una pasada de ByteTrack POR EQUIPO (no adoptado)")
    print("=" * 74)
    ids_dp, eq_dp = doble_pase(
        cache, colores, datos, cfg_tr, cfg_eq, clf, modelo, et_obs
    )
    m_dp = medir(ids_dp, eq_dp, duenos, eq_gt)
    imprimir("DOBLE PASE (equipo por construcción) + reglas posicionales", m_dp)

    # ── Ablación: ¿el daño es de la asociación o de las reglas? ───────
    # El doble pase parte el caché y, con él, las identidades. Las reglas
    # posicionales son POR IDENTIDAD y dos de ellas necesitan identidades
    # largas: el catálogo arbitral pide 25 observaciones y la exclusividad
    # del área se la lleva "quien más observaciones acumula dentro". Al
    # fragmentar, el portero puede perder su propia área contra un trozo
    # ajeno. Aquí se le regalan al doble pase las exclusiones que hace el
    # sistema de HOY, para separar las dos cosas.
    excluir = {
        tuple(par)
        for k, ident in enumerate(ids, start=1)
        if str(eq_ident.get(k, "otro")).replace("portero_", "") not in ("A", "B")
        for tr in ident
        for par in tr.det_idxs
    }
    print(
        f"\n  Ablación: se le regalan al doble pase las {len(excluir)} "
        f"detecciones\n  que las reglas de HOY sacan del cómputo "
        f"(árbitro, staff, 'otro')."
    )
    ids_ab, eq_ab = doble_pase(
        cache, colores, datos, cfg_tr, cfg_eq, clf, modelo, et_obs, excluir=excluir
    )
    m_ab = medir(ids_ab, eq_ab, duenos, eq_gt)
    imprimir("DOBLE PASE con las exclusiones de hoy", m_ab)
    print("\n  Comparación directa:")
    cab = f"    {'variante':<34}{'obs mal':>10}{'ids que cruzan':>17}{'ids':>8}"
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    for nombre, m in (
        ("sistema de hoy", m_sistema),
        ("doble pase", m_dp),
        ("doble pase + exclusiones de hoy", m_ab),
    ):
        pct = m["obs_mal"] / max(m["obs_total"], 1)
        celda = f"{m['obs_mal']} ({pct:.1%})"
        print(f"    {nombre:<34}{celda:>10}{m['ids_cruce']:>17}{m['ids_total']:>8}")

    # ── 4. ¿Y en las métricas que van al replay COLECTIVO? ────────────
    print("\n" + "=" * 74)
    print("4. LO QUE IMPORTA: centroide, anchura y ocupación del bloque")
    print("=" * 74)
    H = np.load(cfg["rutas"]["homografia"])
    gt_m = gt_a_por_frame(parsear_cvat(args.gt), H, frame_offset=9750, paso_gt=15)
    pf_gt = {}
    for f, obs in gt_m.items():
        for o in obs:
            eq = str(o.team).replace("portero_", "")
            if eq in ("A", "B"):
                pf_gt.setdefault((f, eq), []).append((float(o.pos[0]), float(o.pos[1])))
    verdad = metricas_producto(pf_gt).set_index(["frame", "equipo"])
    largo, ancho = modelo.largo, modelo.ancho

    def bloques(identidades, equipos):
        pf = {}
        for k, ident in enumerate(identidades, start=1):
            eq = str(equipos.get(k, "otro")).replace("portero_", "")
            if eq not in ("A", "B"):
                continue
            for tr in ident:
                for pos, par in zip(tr.pos, tr.det_idxs):
                    if par[0] in gt_m:
                        pf.setdefault((par[0], eq), []).append(
                            (float(pos[0]), float(pos[1]))
                        )
        return pf

    def ocupacion(pf):
        z = {}
        for (_f, eq), puntos in pf.items():
            for x, y in puntos:
                zx = min(int(x / largo * 3), 2)
                zy = min(int(y / ancho * 3), 2)
                z[(eq, zx, zy)] = z.get((eq, zx, zy), 0) + 1
        total = sum(z.values()) or 1
        return {k: v / total for k, v in z.items()}

    oc_gt = ocupacion(pf_gt)
    cab = f"    {'variante':<24}{'centroide':>12}{'anchura':>10}{'ocupación':>12}"
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    for nombre, idents, eqs in (
        ("sistema de hoy", ids, eq_ident),
        ("doble pase", ids_dp, eq_dp),
        ("doble pase + exclus. hoy", ids_ab, eq_ab),
    ):
        pf = bloques(idents, eqs)
        m = (
            metricas_producto(pf)
            .set_index(["frame", "equipo"])
            .join(verdad, rsuffix="_gt", how="inner")
        )
        cen = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt).median() if len(m) else np.nan
        anc = (m.ancho - m.ancho_gt).abs().median() if len(m) else np.nan
        oc = ocupacion(pf)
        dif = sum(abs(oc.get(k, 0) - oc_gt.get(k, 0)) for k in set(oc) | set(oc_gt)) / 2
        n_pts = sum(len(v) for v in pf.values())
        reparto = {}
        for k in range(1, len(idents) + 1):
            e = str(eqs.get(k, "otro"))
            e = "portero" if e.startswith("portero") else e
            reparto[e] = reparto.get(e, 0) + 1
        print(f"    {nombre:<24}{cen:>11.2f}m{anc:>9.2f}m{dif:>11.1%}")
        print(
            f"      {n_pts} posiciones en el bloque · identidades por "
            f"etiqueta: {reparto}"
        )
    print(
        "\n    (ocupación = fracción de la masa mal repartida en zonas 3x3;"
        "\n     centroide y anchura son medianas del error contra el GT)"
    )

    # ── 5. EL ORÁCULO: ¿cuánto pagaría CERO cruces de equipo? ─────────
    # Antes de construir nada hay que saber el premio. Se deja la
    # asociación EXACTAMENTE como está y se le regala la etiqueta de
    # equipo perfecta a cada observación casada con el GT. Si con eso el
    # centroide no baja, es que los cruces de equipo no dominan el error
    # y esta vía no paga, por bien que funcione.
    print("\n" + "=" * 74)
    print("5. ORÁCULO: misma asociación, etiqueta de equipo PERFECTA")
    print("=" * 74)
    pf_or = {}
    for k, ident in enumerate(ids, start=1):
        eq_id = str(eq_ident.get(k, "otro")).replace("portero_", "")
        for tr in ident:
            for pos, par in zip(tr.pos, tr.det_idxs):
                par = tuple(par)
                if par[0] not in gt_m:
                    continue
                persona = duenos.get(par)
                eq = eq_gt[persona] if persona is not None else eq_id
                if eq in ("A", "B"):
                    pf_or.setdefault((par[0], eq), []).append(
                        (float(pos[0]), float(pos[1]))
                    )
    m_o = (
        metricas_producto(pf_or)
        .set_index(["frame", "equipo"])
        .join(verdad, rsuffix="_gt", how="inner")
    )
    cen_o = np.hypot(m_o.cx - m_o.cx_gt, m_o.cy - m_o.cy_gt).median()
    anc_o = (m_o.ancho - m_o.ancho_gt).abs().median()
    oc_o = ocupacion(pf_or)
    dif_o = (
        sum(abs(oc_o.get(k, 0) - oc_gt.get(k, 0)) for k in set(oc_o) | set(oc_gt)) / 2
    )
    pf_s = bloques(ids, eq_ident)
    m_s = (
        metricas_producto(pf_s)
        .set_index(["frame", "equipo"])
        .join(verdad, rsuffix="_gt", how="inner")
    )
    cen_s = np.hypot(m_s.cx - m_s.cx_gt, m_s.cy - m_s.cy_gt).median()
    anc_s = (m_s.ancho - m_s.ancho_gt).abs().median()
    print(f"    {'sistema de hoy':<36}{cen_s:>9.2f}m{anc_s:>9.2f}m")
    print(
        f"    {'+ CERO cruces de equipo (oráculo)':<36}{cen_o:>9.2f}m"
        f"{anc_o:>9.2f}m   ocupación {dif_o:.1%}"
    )
    print(
        f"\n    El premio MÁXIMO de toda esta vía: {cen_o - cen_s:+.2f} m "
        f"de centroide."
    )

    # ¿Y entonces de dónde sale el error? El oráculo de asociación
    # perfecta daba 0,42 m y este solo 1,47, así que la diferencia está
    # en algo que este oráculo NO arregla. Sospecha: la BASURA, o sea las
    # detecciones que están en el bloque sin ser ninguna de las 14.
    print("\n  Descomposición del error de centroide:")

    def bloque_filtrado(usar_gt_equipo, quitar_basura):
        pf = {}
        for k, ident in enumerate(ids, start=1):
            eq_id = str(eq_ident.get(k, "otro")).replace("portero_", "")
            for tr in ident:
                for pos, par in zip(tr.pos, tr.det_idxs):
                    par = tuple(par)
                    if par[0] not in gt_m:
                        continue
                    persona = duenos.get(par)
                    if quitar_basura and persona is None:
                        continue
                    eq = (
                        eq_gt[persona]
                        if (usar_gt_equipo and persona is not None)
                        else eq_id
                    )
                    if eq in ("A", "B"):
                        pf.setdefault((par[0], eq), []).append(
                            (float(pos[0]), float(pos[1]))
                        )
        m = (
            metricas_producto(pf)
            .set_index(["frame", "equipo"])
            .join(verdad, rsuffix="_gt", how="inner")
        )
        e = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt)
        return (
            e.median(),
            e.mean(),
            e.quantile(0.9),
            (m.ancho - m.ancho_gt).abs().median(),
        )

    # ⚠️ La MEDIANA es mala resumidora aquí: el daño está concentrado en
    # pocos frames, así que se imprimen también la media y el p90. Con la
    # mediana sola, "equipo perfecto" parece valer 0,08 m; en la media
    # vale 0,35 m y en el p90, 1,40 m. Y es el p90 lo que se ve en un
    # replay: los instantes en los que el bloque pega un salto.
    cab5 = (
        f"    {'variante':<38}{'mediana':>9}{'media':>9}{'p90':>9}" f"{'anchura':>10}"
    )
    print(cab5)
    print("    " + "-" * (len(cab5) - 4))
    for nombre, ug, qb in (
        ("sistema de hoy", False, False),
        ("+ equipo perfecto", True, False),
        ("+ sin basura (solo las 14 personas)", False, True),
        ("+ equipo perfecto Y sin basura", True, True),
    ):
        med, mea, p90, anc = bloque_filtrado(ug, qb)
        print(f"    {nombre:<38}{med:>8.2f}m{mea:>8.2f}m{p90:>8.2f}m" f"{anc:>9.2f}m")
    print(
        "\n    'basura' = detecciones que estan en el bloque sin ser ninguna"
        "\n    de las 14 personas: arbitro, entrenador, lineas del campo."
    )


def doble_pase(
    cache, colores, datos, cfg_tr, cfg_eq, clf, modelo, et_obs, excluir=None
):
    """Parte el caché por el color de cada observación y corre el pipeline
    una vez por equipo. Devuelve (identidades, etiquetas).

    ⚠️ El índice de detección es la POSICIÓN dentro de la lista del frame.
    Al partir el caché, todos los índices se desplazan; si no se remapean,
    cada caja acabaría emparejada con el color de otra persona **sin
    fallar**, que es la peor forma de romperse (el mismo bug que documenta
    src/tracking/filtro_confianza.py). Aquí se guarda el mapa de vuelta y
    se reescriben los det_idxs al terminar.
    """
    identidades_todas = []
    for equipo in ("A", "B"):
        sub_cache, sub_colores, mapa = [], {}, {}
        for entrada in cache:
            f = entrada["frame_idx"]
            dets = []
            for i, d in enumerate(entrada["dets"]):
                if et_obs.get((f, i)) != equipo:
                    continue
                if excluir is not None and (f, i) in excluir:
                    continue  # ablación: la sacan las reglas de HOY
                nuevo = len(dets)
                dets.append(d)
                mapa[(f, nuevo)] = i
                if (f, i) in colores:
                    sub_colores[(f, nuevo)] = colores[(f, i)]
            sub_cache.append({**entrada, "dets": dets})
        n = sum(len(e["dets"]) for e in sub_cache)
        idents = correr_perfil(
            sub_cache,
            datos["fps"],
            datos["sample"],
            cfg_tr,
            perfil="bytetrack",
            colores=sub_colores,
            clasificador=clf,
            cfg_equipos=cfg_eq,
        )
        # Remapeo de vuelta a los índices originales del caché completo
        for ident in idents:
            for tr in ident:
                tr.det_idxs = [(f, mapa[(f, i)]) for f, i in tr.det_idxs]
        print(f"  pase '{equipo}': {n} detecciones -> {len(idents)} identidades")
        identidades_todas.append((equipo, idents))

    # La etiqueta ya no la vota el color: la da EL PASE del que sale.
    # Encima van las mismas reglas posicionales que en producción.
    ids, equipos = [], {}
    for equipo, idents in identidades_todas:
        for ident in idents:
            ids.append(ident)
            equipos[len(ids)] = equipo
    cfg_p = cfg_eq.get("porteros", {})
    margen = cfg_p.get("margen_m", 2.0)
    if cfg_eq.get("arbitro", {}).get("activo", False):
        for indice in identificar_arbitros(
            ids,
            colores,
            [clf._prototipos.a, clf._prototipos.b],
            min_observaciones=cfg_eq["arbitro"].get("min_observaciones", 25),
        ):
            equipos[indice] = "otro"
    lados = deducir_lados(
        {k: v for k, v in equipos.items() if v in ("A", "B")},
        ids,
        modelo.largo,
        regla=ReglaPorteros.desde_modelo(modelo, margen=margen),
        ancho=modelo.ancho,
    )
    bajo, alto = lados if lados else (cfg_p["equipo_mx_bajo"], cfg_p["equipo_mx_alto"])
    equipos = aplicar_regla_porteros(
        equipos,
        ids,
        ReglaPorteros.desde_modelo(
            modelo, margen=margen, equipo_mx_bajo=bajo, equipo_mx_alto=alto
        ),
    )
    cfg_s = cfg_eq.get("staff", {})
    equipos = aplicar_regla_staff(
        equipos,
        ids,
        ReglaStaff(
            largo=modelo.largo,
            ancho=modelo.ancho,
            tolerancia_m=cfg_s.get("tolerancia_m", 2.0),
            min_observaciones=cfg_s.get("min_observaciones", 5),
        ),
    )
    return ids, equipos


if __name__ == "__main__":
    main()
