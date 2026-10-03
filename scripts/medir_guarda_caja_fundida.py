#!/usr/bin/env python
"""Mide la guarda de CAJA FUNDIDA en las dos patas, contra el azar. SOLO MEDICIÓN.

Plan y razones: docs/plan_guarda_caja_fundida.md. El CRITERIO de abajo se fijó y se
commiteó ANTES de correr ninguna variante.

Cada rama corre la cadena de producción COMPLETA (`procesar_desde_cache`). El corte se
inyecta envolviendo, solo durante la corrida, dos nombres de `src/tracking/perfiles.py`:
`asociar_con_bytetrack` (para quedarse con el caché filtrado, de donde salen las cajas) y
`coser_por_pureza` (para partir las identidades justo antes del cosido). Ningún fichero
de producción cambia. Guarda: la rama `base` tiene que dar EXACTAMENTE el CSV de una
corrida sin parches, o el script se para.

Uso:
    python scripts/medir_guarda_caja_fundida.py                # todo (~75 min)
    python scripts/medir_guarda_caja_fundida.py --patas villa  # solo Villaviciosa
"""

import argparse
import json
import logging
import random
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))
warnings.filterwarnings("ignore")

import guarda_caja_fundida as gcf  # noqa: E402
from comparar_escalas import casar as casar_banco  # noqa: E402
from comparar_escalas import equipo_gt  # noqa: E402
from desglose_del_error import construir_frames  # noqa: E402
from src.evaluation.desglose_error import (  # noqa: E402
    EQUIPOS,
    conjunto_del_equipo,
    conjunto_gt,
    error_de_conjunto,
)
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
import src.tracking.perfiles as perfiles  # noqa: E402
from src.tracking_data.processor import procesar_desde_cache  # noqa: E402

logger = logging.getLogger("guarda_caja_fundida")

# ══════════════════════════ CRITERIO (fijado ANTES de medir) ══════════════════════════
CANDIDATA = "candidata"
RAMAS = {
    "salto": dict(usar_fundida=False, usar_entera=False),
    "salto_entera": dict(usar_fundida=False, usar_entera=True),
    "salto_fundida": dict(usar_fundida=True, usar_entera=False),
    "candidata": dict(usar_fundida=True, usar_entera=True),
}
SEMILLAS = 10
CRITERIO = {
    # una pata con menos cortes que esto DENTRO de la ventana del GT: NO CONCLUYENTE
    "min_cortes_ventana": 5,
    # 1. equipo equivocado (%): variante ≤ base + esto
    "equipo_equivocado_tol_pp": 0.0,
    # 2. quimeras: ≤ base en cada pata y < base en la suma de las dos
    # 3. fragmentación: identidades por persona del GT, Δ ≤ esto
    "fragmentacion_delta_max": 0.25,
    # 4. centroide y anchura (m): variante ≤ base + esto (resolución de lectura)
    "centroide_tol_m": 0.01,
    "anchura_tol_m": 0.01,
    # 5. contra el azar: semillas (de SEMILLAS) en que la regla es estrictamente mejor
    "semillas_ganadas_min": 9,
    # 5b. en 20 min: tasa de cambio de etiqueta a través del corte > este percentil del azar
    "percentil_azar_etiqueta": 90,
}
RADIO_M = 2.0  # casado 1-a-1, el del banco
MIN_CASADOS_QUIMERA, PUREZA_QUIMERA = 10, 0.60  # la definición del banco
VENTANA_ETIQUETA_S = 2.0
# ═══════════════════════════════════════════════════════════════════════════════════════

PATAS = {
    "benja": dict(
        config="configs/processor_benja_parte_entera.yaml",
        gt="data/annotations/gt_benja/annotations.xml",
        offset=9750,
    ),
    "villa": dict(
        config="configs/processor.yaml",
        gt="data/annotations/ground_truth_tracking/annotations.xml",
        offset=7500,
    ),
}
PASO_GT = 15


# ───────────────────────────── el veredicto (puro, testeado) ─────────────────────────────
def mejor_que_azar(regla: dict, azar: dict) -> bool:
    """Estrictamente mejor: primero menos quimeras; si empatan, menos fragmentación."""
    if regla["quimeras"] != azar["quimeras"]:
        return regla["quimeras"] < azar["quimeras"]
    return regla["fragmentacion"] < azar["fragmentacion"]


def veredicto(base: dict, rama: dict, azares: dict, crit: dict = CRITERIO) -> dict:
    """Aplica el criterio. base/rama/azares: {pata: métricas}; azares[pata] es una lista.

    Dos tipos de punto, y la falta de casos no les afecta igual:
    - "NO EMPEORAR" (1-4) y el 5b de 20 min: se evalúan siempre. Un empeoramiento con
      pocos cortes sigue siendo un empeoramiento.
    - "MEJORAR" (gana al azar contra el GT, la suma de quimeras baja): necesitan casos.
      Con menos de `min_cortes_ventana` cortes en la ventana valen None (NO CONCLUYENTE).

    `pasa`: False si algún punto es False; None si no hay ninguno False pero alguno es
    None; True solo si todos son True.
    """
    salida, concluyentes = {}, {}
    for pata in base:
        b, v, az = base[pata], rama[pata], azares[pata]
        concluyente = v["cortes_ventana"] >= crit["min_cortes_ventana"]
        concluyentes[pata] = concluyente
        tasas = [a["cambio_etiqueta"] for a in az if a["cambio_etiqueta"] is not None]
        salida[pata] = {
            "1_equipo_equivocado": v["equipo_mal_pct"]
            <= b["equipo_mal_pct"] + crit["equipo_equivocado_tol_pp"],
            "2_quimeras_no_suben": v["quimeras"] <= b["quimeras"],
            "3_fragmentacion": v["fragmentacion"] - b["fragmentacion"]
            <= crit["fragmentacion_delta_max"],
            "4_centroide": v["centroide_m"]
            <= b["centroide_m"] + crit["centroide_tol_m"],
            "4_anchura": v["anchura_m"] <= b["anchura_m"] + crit["anchura_tol_m"],
            "5_gana_al_azar": (
                sum(mejor_que_azar(v, a) for a in az) >= crit["semillas_ganadas_min"]
                if concluyente
                else None
            ),
            "5b_etiqueta_vs_azar_20min": bool(
                v["cambio_etiqueta"] is not None
                and tasas
                and v["cambio_etiqueta"]
                > np.percentile(tasas, crit["percentil_azar_etiqueta"])
            ),
            "concluyente": concluyente,
        }
    salida["suma_quimeras_baja"] = (
        sum(rama[p]["quimeras"] for p in base) < sum(base[p]["quimeras"] for p in base)
        if all(concluyentes.values())
        else None
    )
    valores = [
        ok for p in base for k, ok in salida[p].items() if k != "concluyente"
    ] + [salida["suma_quimeras_baja"]]
    if any(ok is False for ok in valores):
        salida["pasa"] = False
    elif any(ok is None for ok in valores):
        salida["pasa"] = None
    else:
        salida["pasa"] = True
    return salida


# ───────────────────────────────── la corrida ─────────────────────────────────
def _cajas(cache) -> dict:
    return {
        (e["frame_idx"], i): tuple(d[2:6])
        for e in cache
        for i, d in enumerate(e["dets"])
    }


def _parametros(rama: str | None, cfg: dict) -> gcf.ParametrosGuarda:
    extra = RAMAS[rama] if rama else {}
    return gcf.ParametrosGuarda(
        largo=float(cfg["campo_m"]["largo"]),
        ancho=float(cfg["campo_m"]["ancho"]),
        **extra,
    )


def correr(cfg: dict, salida_csv: Path, transformar) -> dict:
    """Corre producción con `transformar(identidades, cajas)` antes del cosido.

    `transformar` devuelve (identidades, eventos). Devuelve el CSV, los eventos y las
    identidades finales (cuyo orden es el `id_jugador` del CSV, empezando en 1).
    """
    cfg = yaml.safe_load(yaml.safe_dump(cfg))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(salida_csv)
    cfg["rutas"]["salida_meta"] = str(salida_csv.with_suffix(".json"))
    capt = {}
    asociar0, coser0 = perfiles.asociar_con_bytetrack, perfiles.coser_por_pureza

    def asociar(cache, *a, **k):
        capt["cache"] = cache
        return asociar0(cache, *a, **k)

    def coser(identidades, *a, **k):
        nuevas, eventos = transformar(identidades, _cajas(capt["cache"]))
        capt["eventos"] = eventos
        capt["finales"] = coser0(nuevas, *a, **k)
        return capt["finales"]

    perfiles.asociar_con_bytetrack, perfiles.coser_por_pureza = asociar, coser
    try:
        procesar_desde_cache(cfg)
    finally:
        perfiles.asociar_con_bytetrack, perfiles.coser_por_pureza = asociar0, coser0
    return {
        "df": pd.read_csv(salida_csv),
        "eventos": capt["eventos"],
        "finales": capt["finales"],
    }


def sin_cambios(identidades, cajas):
    return identidades, []


def con_regla(p: gcf.ParametrosGuarda, quitar_fundidas: bool = False):
    """La regla. Con `quitar_fundidas` (segundo intento), además se sacan de la identidad
    las observaciones fundidas en torno a cada corte, antes del cosido."""

    def transformar(identidades, cajas):
        nuevas, eventos = [], []
        for k, ident in enumerate(identidades):
            obs = gcf.observaciones(ident)
            cortes = gcf.detectar_cortes(obs, cajas, p)
            por_corte = {
                c["i"]: (
                    gcf.observaciones_fundidas(obs, cajas, c["i"], p)
                    if quitar_fundidas
                    else []
                )
                for c in cortes
            }
            quitar = {j for js in por_corte.values() for j in js}
            for c in cortes:
                info = {**c, "quitadas": len(por_corte[c["i"]])}
                eventos.append(_evento(k, obs, c["i"], info, quitar))
            nuevas.extend(gcf.partir(ident, [c["i"] for c in cortes], sorted(quitar)))
        return nuevas, eventos

    return transformar


def al_azar(
    p: gcf.ParametrosGuarda, n_dentro: int, n_fuera: int, ventana, semilla: int
):
    """El MISMO número de cortes que la regla, dentro y fuera de la ventana del GT."""

    def transformar(identidades, cajas):
        dentro, fuera, obs_de = [], [], {}
        for k, ident in enumerate(identidades):
            obs_de[k] = gcf.observaciones(ident)
            for i in gcf.posiciones_validas(obs_de[k], p):
                f = obs_de[k][i][2][0]
                (dentro if ventana[0] <= f <= ventana[1] else fuera).append((k, i))
        rng = random.Random(semilla)
        elegidos = rng.sample(dentro, min(n_dentro, len(dentro))) + rng.sample(
            fuera, min(n_fuera, len(fuera))
        )
        por_ident = defaultdict(list)
        for k, i in elegidos:
            por_ident[k].append(i)
        nuevas, eventos = [], []
        for k, ident in enumerate(identidades):
            for i in por_ident.get(k, []):
                eventos.append(_evento(k, obs_de[k], i, {}))
            nuevas.extend(gcf.partir(ident, sorted(por_ident.get(k, []))))
        return nuevas, eventos

    return transformar


def _evento(k, obs, i, info, quitar=frozenset()) -> dict:
    # las claves de cada lado son las observaciones que SIGUEN en la identidad: si la
    # fundida se quitó, la de antes/después más cercana que no se quitó
    antes = next((j for j in range(i - 1, -1, -1) if j not in quitar), i - 1)
    despues = next((j for j in range(i, len(obs)) if j not in quitar), i)
    return {
        "ident_original": k,
        "t": float(obs[i][0]),
        "frame": int(obs[i][2][0]),
        "clave_antes": obs[antes][2],
        "clave_despues": obs[despues][2],
        "x": float(obs[i - 1][1][0]),
        "y": float(obs[i - 1][1][1]),
        **{kk: vv for kk, vv in info.items() if kk not in ("i",)},
    }


# ─────────────────────────────── las métricas ───────────────────────────────
def casado_con_ids(df: pd.DataFrame, gt_m: dict) -> list[tuple]:
    """(frame, obj_id, equipo_gt, id_jugador|None, etiqueta|None), 1-a-1, radio 2 m."""
    from scipy.optimize import linear_sum_assignment

    filas = []
    por_frame = {f: g for f, g in df.groupby("frame")}
    for frame, obs_gt in sorted(gt_m.items()):
        gente = [o for o in obs_gt if equipo_gt(o) in EQUIPOS]
        sub = por_frame.get(frame)
        if not gente:
            continue
        if sub is None:
            filas.extend((frame, o.obj_id, equipo_gt(o), None, None) for o in gente)
            continue
        xy = sub[["x_m", "y_m"]].to_numpy()
        coste = np.hypot(
            xy[None, :, 0] - np.array([o.pos[0] for o in gente])[:, None],
            xy[None, :, 1] - np.array([o.pos[1] for o in gente])[:, None],
        )
        coste = np.where(coste > RADIO_M, 1e6, coste)
        asig = {
            int(i): int(j)
            for i, j in zip(*linear_sum_assignment(coste))
            if coste[i, j] < 1e6
        }
        ids, etq = sub.id_jugador.to_numpy(), sub.etiqueta.to_numpy()
        for i, o in enumerate(gente):
            j = asig.get(i)
            filas.append(
                (
                    frame,
                    o.obj_id,
                    equipo_gt(o),
                    None if j is None else int(ids[j]),
                    None if j is None else str(etq[j]).replace("portero_", ""),
                )
            )
    return filas


def metricas_gt(df: pd.DataFrame, gt_m: dict) -> dict:
    reales = df[(df.es_real == 1) & df.frame.isin(gt_m)]
    casado = casado_con_ids(reales, gt_m)
    con_fila = [c for c in casado if c[3] is not None]
    conf = Counter((c[2], c[4]) for c in con_fila)
    directo = conf[("A", "A")] + conf[("B", "B")]
    cruzado = conf[("A", "B")] + conf[("B", "A")]
    en_equipo = sum(v for (g, s), v in conf.items() if s in EQUIPOS)
    mal = en_equipo - max(directo, cruzado)
    votos = defaultdict(Counter)
    personas = defaultdict(set)
    for _f, obj, _eq, idj, _e in con_fila:
        votos[idj][obj] += 1
        personas[obj].add(idj)
    quimeras = sum(
        1
        for c in votos.values()
        if sum(c.values()) >= MIN_CASADOS_QUIMERA
        and c.most_common(1)[0][1] / sum(c.values()) < PUREZA_QUIMERA
    )
    errores = []
    for fc in construir_frames(gt_m, reales, RADIO_M):
        for eq in EQUIPOS:
            verdad, sis = conjunto_gt(fc, eq), conjunto_del_equipo(fc, eq)
            if len(verdad) >= 3 and len(sis) >= 3:
                errores.append(error_de_conjunto(sis, verdad))
    return {
        "personas_gt": len(casado),
        "casadas": len(con_fila),
        "equipo_mal": mal,
        "equipo_mal_pct": 100 * mal / en_equipo if en_equipo else 0.0,
        "quimeras": quimeras,
        "con10": sum(
            1 for c in votos.values() if sum(c.values()) >= MIN_CASADOS_QUIMERA
        ),
        "fragmentacion": float(np.mean([len(s) for s in personas.values()])),
        "centroide_m": float(np.mean([e["centroide"] for e in errores])),
        "anchura_m": float(np.mean([e["ancho"] for e in errores])),
        "_casado": casado,
    }


def id_final_de(finales) -> dict:
    """{(frame, det_idx): id_jugador} — el id del CSV es el índice + 1."""
    return {
        par: n
        for n, ident in enumerate(finales, start=1)
        for tr in ident
        for par in tr.det_idxs
    }


def describir_cortes(corrida: dict, gt_m: dict, casado: list, ventana) -> dict:
    """Por corte: ¿lo deshizo el cosido?, etiqueta a cada lado, persona del GT a cada lado."""
    df, eventos = corrida["df"], corrida["eventos"]
    idf = id_final_de(corrida["finales"])
    reales = df[df.es_real == 1]
    por_id = {k: g for k, g in reales.groupby("id_jugador")}
    persona = {(f, idj): obj for f, obj, _e, idj, _s in casado if idj is not None}
    frames_gt = np.array(sorted(gt_m))
    filas = []
    for ev in eventos:
        a, d = idf.get(tuple(ev["clave_antes"])), idf.get(tuple(ev["clave_despues"]))
        t = ev["t"]

        def mayoritaria(idj, ini, fin):
            g = por_id.get(idj)
            if g is None:
                return None
            s = g[(g.tiempo_s >= ini) & (g.tiempo_s < fin)].etiqueta
            return s.value_counts().index[0] if len(s) else None

        e_a = mayoritaria(a, t - VENTANA_ETIQUETA_S, t)
        e_d = mayoritaria(d, t, t + VENTANA_ETIQUETA_S)
        # persona del GT: el último frame del GT antes del corte (pieza de antes) y el
        # primero después (pieza de después), a ≤ 2 s
        p_a = p_d = None
        if ventana[0] <= ev["frame"] <= ventana[1]:
            previos = frames_gt[frames_gt < ev["frame"]][::-1]
            for f in previos[:4]:
                if (f, a) in persona:
                    p_a = persona[(f, a)]
                    break
            for f in frames_gt[frames_gt >= ev["frame"]][:4]:
                if (f, d) in persona:
                    p_d = persona[(f, d)]
                    break
        filas.append(
            {
                **{k: v for k, v in ev.items() if not k.startswith("clave")},
                "id_antes": a,
                "id_despues": d,
                "recosido": a is not None and a == d,
                "etiqueta_antes": e_a,
                "etiqueta_despues": e_d,
                "persona_antes": p_a,
                "persona_despues": p_d,
            }
        )
    t = pd.DataFrame(filas)
    if t.empty:
        return {"cortes": 0, "cortes_ventana": 0, "cambio_etiqueta": None, "_tabla": t}
    dentro = t[(t.frame >= ventana[0]) & (t.frame <= ventana[1])]
    con_etq = t.dropna(subset=["etiqueta_antes", "etiqueta_despues"])
    verif = dentro.dropna(subset=["persona_antes", "persona_despues"])
    papel = t.etiqueta_antes.isin(
        ["portero_A", "portero_B", "otro"]
    ) | t.etiqueta_despues.isin(["portero_A", "portero_B", "otro"])
    return {
        "cortes": len(t),
        "cortes_ventana": len(dentro),
        "recosidos": int(t.recosido.sum()),
        "cambio_etiqueta": (
            float((con_etq.etiqueta_antes != con_etq.etiqueta_despues).mean())
            if len(con_etq)
            else None
        ),
        "con_portero_u_otro": int(papel.sum()),
        "pares_de_etiqueta": Counter(
            zip(t.etiqueta_antes.fillna("-"), t.etiqueta_despues.fillna("-"))
        ).most_common(8),
        "verificables": len(verif),
        "separan_personas": int((verif.persona_antes != verif.persona_despues).sum()),
        "_tabla": t,
    }


def caso_525(df: pd.DataFrame) -> dict:
    """El portero de B (x>55 m) que en producción se pasa a un jugador en t≈792,7 s.

    Sobre el CSV: la identidad con más filas en la portería en 780-792,5 s. ¿Se aleja
    > 3 m de la portería en los 3 s siguientes (se pasó al jugador)? ¿Cómo salen sus
    filas de 628-792 s? (En producción: se aleja ~12 m y salen como `B`.)

    ⚠️ La primera versión cogía la primera identidad "en x≥55 a los 792,5 s" y daba la
    448, un jugador que llega corriendo al área. Se corrigió tras la primera corrida.
    """
    r = df[df.es_real == 1]
    w = r[(r.tiempo_s >= 780) & (r.tiempo_s <= 792.5) & (r.x_m > 55)]
    idp = int(w.id_jugador.value_counts().index[0])
    g = r[r.id_jugador == idp].sort_values("tiempo_s")
    ref = g[g.tiempo_s <= 792.6].iloc[-1][["x_m", "y_m"]].to_numpy(float)
    post = g[(g.tiempo_s > 793) & (g.tiempo_s <= 796)]
    se_aleja = (
        float(np.hypot(post.x_m - ref[0], post.y_m - ref[1]).max()) if len(post) else 0
    )
    filas = df[(df.id_jugador == idp) & (df.tiempo_s >= 628) & (df.tiempo_s <= 792.6)]
    return {
        "id": idp,
        "se_aleja_m": round(se_aleja, 1),
        "cortada": se_aleja <= 3.0,
        "etiqueta_628_792": filas.etiqueta.value_counts().to_dict(),
    }


# ─────────────────────── segundo intento: la comprobación previa ───────────────────────
# Los 16 cortes de la hoja (candidata, benjamín), por FRAME del corte, con la lectura a ojo
# de docs/guarda_caja_fundida.md: "distinta" = cambio de persona claro, "misma" = corte malo.
HOJA_16 = {
    174: "misma", 489: "distinta", 2646: "dudoso", 3078: "distinta",
    3267: "misma", 4302: "misma", 10782: "distinta", 12648: "distinta",
    13824: "dudoso", 15234: "dudoso", 18648: "dudoso", 20709: "misma",
    23694: "dudoso", 23757: "distinta", 25113: "distinta", 34725: "dudoso",
}  # fmt: skip


def comprobacion_previa(sal: Path) -> pd.DataFrame:
    """¿Une el cosido los cortes malos de la hoja si se quita la observación fundida?"""
    cfg = yaml.safe_load(open(R / PATAS["benja"]["config"]))
    cr = correr(
        cfg, sal / "benja_previa.csv", con_regla(_parametros(CANDIDATA, cfg), True)
    )
    idf = id_final_de(cr["finales"])
    filas = []
    for n, (frame, lectura) in enumerate(HOJA_16.items(), start=1):
        ev = [e for e in cr["eventos"] if e["frame"] == frame]
        if not ev:
            filas.append({"n": n, "frame": frame, "lectura": lectura, "recosido": None})
            continue
        e = ev[0]
        a, d = idf.get(tuple(e["clave_antes"])), idf.get(tuple(e["clave_despues"]))
        filas.append(
            {
                "n": n,
                "frame": frame,
                "lectura": lectura,
                "quitadas": e["quitadas"],
                "recosido": a is not None and a == d,
            }
        )
    (sal / "benja_previa.csv").unlink(missing_ok=True)
    t = pd.DataFrame(filas)
    print(t.to_string(index=False))
    unidos = sum(
        idf.get(tuple(e["clave_antes"])) == idf.get(tuple(e["clave_despues"]))
        for e in cr["eventos"]
    )
    print(f"\ncortes totales {len(cr['eventos'])}, recosidos {unidos}")
    return t


# ──────────────────────────────────── main ────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patas", default="benja,villa")
    ap.add_argument("--semillas", type=int, default=SEMILLAS)
    ap.add_argument("--salida", default="outputs/guarda_caja_fundida")
    ap.add_argument("--comprobacion-previa", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    sal = R / args.salida
    sal.mkdir(parents=True, exist_ok=True)
    if args.comprobacion_previa:
        comprobacion_previa(sal)
        return
    res = {}
    for pata in args.patas.split(","):
        d = PATAS[pata]
        cfg = yaml.safe_load(open(R / d["config"]))
        H = np.load(R / cfg["rutas"]["homografia"])
        gt_m = gt_a_por_frame(parsear_cvat(str(R / d["gt"])), H, d["offset"], PASO_GT)
        ventana = (min(gt_m), max(gt_m))
        print(
            f"\n════ {pata}: GT frames {ventana}, {len(gt_m)} frames ════", flush=True
        )

        # guarda: base con el parche = producción sin parche, byte a byte
        limpio = sal / f"{pata}_sin_parche.csv"
        c2 = yaml.safe_load(open(R / d["config"]))
        c2["modo"] = "desde_cache"
        c2["rutas"]["salida_csv"], c2["rutas"]["salida_meta"] = str(limpio), str(
            limpio.with_suffix(".json")
        )
        procesar_desde_cache(c2)
        base = correr(cfg, sal / f"{pata}_base.csv", sin_cambios)
        if not pd.read_csv(limpio).equals(base["df"]):
            sys.exit(
                "✗ la rama base NO reproduce producción: el arnés cambia algo. PARA."
            )
        # control del casado: mi equipo equivocado = el de comparar_escalas
        mb = metricas_gt(base["df"], gt_m)
        pares = casar_banco(base["df"][base["df"].es_real == 1], gt_m, RADIO_M)
        mal_banco = sum(1 for g, s in pares if s in EQUIPOS and s != g)
        mal_banco = min(mal_banco, sum(1 for g, s in pares if s in EQUIPOS and s == g))
        assert mal_banco == mb["equipo_mal"], (mal_banco, mb["equipo_mal"])
        if pata == "benja":
            mb["caso_525"] = caso_525(base["df"])  # en producción NO debe salir cortada
        print(
            f"✓ base = producción; casado = el del banco · base: {_fmt(mb)}", flush=True
        )
        res[pata] = {"base": mb, "ramas": {}}

        for rama in RAMAS:
            p = _parametros(rama, cfg)
            cr = correr(cfg, sal / f"{pata}_{rama}.csv", con_regla(p))
            m = metricas_gt(cr["df"], gt_m)
            m.update(describir_cortes(cr, gt_m, m["_casado"], ventana))
            if pata == "benja":
                m["caso_525"] = caso_525(cr["df"])
            m["_tabla"].to_csv(sal / f"{pata}_{rama}_cortes.csv", index=False)
            n_dentro = m["cortes_ventana"]
            azares = []
            for s in range(args.semillas):
                ca = correr(
                    cfg,
                    sal / f"{pata}_{rama}_azar.csv",
                    al_azar(p, n_dentro, m["cortes"] - n_dentro, ventana, 1000 + s),
                )
                ma = metricas_gt(ca["df"], gt_m)
                ma.update(describir_cortes(ca, gt_m, ma["_casado"], ventana))
                azares.append(ma)
            print(f"  {rama:<14} {_fmt(m)}", flush=True)
            print(
                f"  {'  azar (med.)':<14} quim {np.median([a['quimeras'] for a in azares]):.1f}"
                f" frag {np.median([a['fragmentacion'] for a in azares]):.3f}"
                f" cambio_etq {np.median([a['cambio_etiqueta'] or 0 for a in azares]):.2f}"
                f" separan {sum(a.get('separan_personas', 0) for a in azares)}/"
                f"{sum(a.get('verificables', 0) for a in azares)}",
                flush=True,
            )
            res[pata]["ramas"][rama] = {"m": m, "azar": azares}

    patas = list(res)
    informe = {}
    for rama in RAMAS:
        v = veredicto(
            {p: res[p]["base"] for p in patas},
            {p: res[p]["ramas"][rama]["m"] for p in patas},
            {p: res[p]["ramas"][rama]["azar"] for p in patas},
        )
        informe[rama] = v
        print(f"\nVEREDICTO {rama}{' (CANDIDATA)' if rama == CANDIDATA else ''}: {v}")
    limpio = {
        p: {
            "base": _sin_privados(res[p]["base"]),
            "ramas": {
                r: {
                    "m": _sin_privados(x["m"]),
                    "azar": [_sin_privados(a) for a in x["azar"]],
                }
                for r, x in res[p]["ramas"].items()
            },
        }
        for p in res
    }
    json.dump(
        {"criterio": CRITERIO, "resultados": limpio, "veredictos": informe},
        open(sal / "resultados.json", "w"),
        indent=1,
        default=str,
    )
    print(f"\n(todo en {sal}/resultados.json)")


def _sin_privados(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _fmt(m: dict) -> str:
    s = (
        f"equipo_mal {m['equipo_mal_pct']:.2f}% ({m['equipo_mal']}) · quim {m['quimeras']}/"
        f"{m['con10']} · frag {m['fragmentacion']:.3f} · centroide {m['centroide_m']:.3f} · "
        f"anchura {m['anchura_m']:.3f}"
    )
    if "cortes" in m:
        s += (
            f" · cortes {m['cortes']} (ventana {m['cortes_ventana']}, recosidos "
            f"{m.get('recosidos', 0)}) · separan {m.get('separan_personas', 0)}/"
            f"{m.get('verificables', 0)} · cambio_etq {m['cambio_etiqueta']}"
            f" · portero/otro {m.get('con_portero_u_otro', 0)}"
        )
    if m.get("caso_525"):
        s += f" · 525 {m['caso_525']}"
    return s


if __name__ == "__main__":
    main()
