#!/usr/bin/env python
"""Banco de la misión (docs/registro_mision.md): una variante = cambios de config; se mide TODO.

Corre el `desde_cache` de producción de una pata con cambios sobre su config de tracking y/o de
equipos (JSON, se mezclan en profundidad) y mide:
- lo que ve la pizarra (`linea_base_mision`): cambios de color, saltos, eventos, simultáneas;
- contra el GT donde lo hay (benjamín y alevín A): equipo equivocado, centroide, anchura
  (`banco_equipos_v2.medir_con_gt`) y error de posición casado 1-a-1 a 2 m;
- el mini-GT de equipo a ojo en el alevín B (`medir_gt_equipos_alevinb`).

Uso:
    python scripts/banco_mision.py --nombre rts3 --patas alevinb villa benja \\
        --tracking '{"suavizado": {"metodo": "rts", "rts": {"aceleracion_ms2": 3.0}}}'
"""

import argparse
import copy
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

SALIDA = R / "outputs/banco_mision"
PATAS = {
    "benja": {
        "config": "configs/processor_benja_v2color.yaml",
        "cache_chaleco": "data/tracking_benja/cache_chaleco_benja.pkl",
        "gt": "data/annotations/gt_benja/annotations.xml",
        "homografia": "data/calibracion_benja/homografia_benja.npy",
        "offset": 9750,
        "campo": (62.0, 40.0),
        "por_equipo": 7,
    },
    "benja_p1": {
        "config": "configs/processor_benja_parte_entera.yaml",
        "cache_colores": "data/tracking_benja/colores_v2_benja_p1.pkl",
        "gt": "data/annotations/gt_benja/annotations.xml",
        "homografia": "data/calibracion_benja/homografia_benja.npy",
        "offset": 9750,
        "campo": (62.0, 40.0),
        "por_equipo": 7,
        "tramo": (300.0, 1200.0),
    },
    # El benjamín ENTERO con su caché de color de producción (v1); la pizarra se mide en el tramo
    # 14:00-15:30 del archivo, el de los informes de la pizarra, y el GT cae en su minuto 5.
    "benja20": {
        "config": "configs/processor_benja_parte_entera.yaml",
        "gt": "data/annotations/gt_benja/annotations.xml",
        "homografia": "data/calibracion_benja/homografia_benja.npy",
        "offset": 9750,
        "campo": (62.0, 40.0),
        "por_equipo": 7,
        "tramo": (840.0, 930.0),
    },
    "villa": {
        "config": "configs/processor.yaml",
        "gt": "data/annotations/ground_truth_tracking/annotations.xml",
        "homografia": "data/calibracion/homografia.npy",
        "offset": 7500,
        "campo": (105.0, 68.0),
        "por_equipo": 11,
    },
    "alevinb": {
        "config": "data/tracking_alevinb/config_alevinb_p1.yaml",
        "campo": (100.0, 64.0),
        "por_equipo": 11,
    },
}


def mezclar(base: dict, cambios: dict) -> dict:
    """Mezcla en profundidad `cambios` sobre una copia de `base`."""
    salida = copy.deepcopy(base)
    for k, v in cambios.items():
        if isinstance(v, dict) and isinstance(salida.get(k), dict):
            salida[k] = mezclar(salida[k], v)
        else:
            salida[k] = v
    return salida


def correr(pata: str, nombre: str, tracking: dict, equipos: dict) -> Path:
    from src.tracking_data.processor import procesar_desde_cache

    d = PATAS[pata]
    cfg = yaml.safe_load(open(R / d["config"]))
    cfg["modo"] = "desde_cache"
    for clave in ("cache", "cache_colores", "cache_chaleco"):
        if clave in d:
            cfg["rutas"][clave] = str(R / d[clave])
    carpeta = SALIDA / pata
    carpeta.mkdir(parents=True, exist_ok=True)
    for clave, cambios, defecto in (
        ("config_tracking", tracking, "configs/tracking.yaml"),
        ("config_equipos", equipos, "configs/team_classification.yaml"),
    ):
        base = yaml.safe_load(open(R / cfg.get(clave, defecto)))
        ruta = carpeta / f"{clave}_{nombre}.yaml"
        ruta.write_text(yaml.safe_dump(mezclar(base, cambios), allow_unicode=True))
        cfg[clave] = str(ruta)
    csv = carpeta / f"posiciones_{nombre}.csv"
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(carpeta / f"meta_{nombre}.json")
    procesar_desde_cache(cfg)
    return csv


def correr_con_mini_gt(nombre: str, tracking: dict, equipos: dict) -> tuple[Path, dict]:
    """Alevín B: corre capturando qué detección lleva cada identidad y mide el mini-GT a ojo."""
    import medir_gt_equipos_alevinb as mg

    import src.tracking.perfiles as perfiles

    cap = {}
    orig_correr, orig_post = perfiles.correr_perfil, perfiles.postprocesar

    def espia_correr(cache, *a, **k):
        cap["cache"] = {e["frame_idx"]: e["dets"] for e in cache}
        return orig_correr(cache, *a, **k)

    def espia_post(identidades, *a, **k):
        cap["identidades"] = [
            [(int(f), int(j)) for tr in ident for (f, j) in tr.det_idxs]
            for ident in identidades
        ]
        return orig_post(identidades, *a, **k)

    perfiles.correr_perfil, perfiles.postprocesar = espia_correr, espia_post
    try:
        csv = correr("alevinb", nombre, tracking, equipos)
    finally:
        perfiles.correr_perfil, perfiles.postprocesar = orig_correr, orig_post
    return csv, mg.medir(csv, cap["identidades"], cap["cache"])


def error_de_posicion(pata: str, csv: Path) -> dict:
    """Error de posición contra el GT, casado 1-a-1 a ≤ 2 m, por tercio de profundidad (eje y)."""
    from scipy.optimize import linear_sum_assignment

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    d = PATAS[pata]
    gt_m = gt_a_por_frame(
        parsear_cvat(R / d["gt"]), np.load(R / d["homografia"]), d["offset"], 15
    )
    df = pd.read_csv(csv)
    df = df[df.es_real == 1]
    errores, casadas, personas = [], 0, 0
    for f, obs in gt_m.items():
        gt = np.array([o.pos for o in obs], dtype=float).reshape(-1, 2)
        sis = df[df.frame == f][["x_m", "y_m"]].to_numpy()
        personas += len(gt)
        if not len(gt) or not len(sis):
            continue
        dist = np.linalg.norm(gt[:, None] - sis[None], axis=2)
        i, j = linear_sum_assignment(np.where(dist <= 2.0, dist, 1e6))
        bien = dist[i, j] <= 2.0
        casadas += int(bien.sum())
        errores += [(gt[a, 1], dist[a, b]) for a, b in zip(i[bien], j[bien])]
    e = np.array(errores)
    tercio = np.digitize(e[:, 0], [d["campo"][1] / 3, 2 * d["campo"][1] / 3])
    return {
        "casadas_pct": round(100 * casadas / max(personas, 1), 1),
        "error_mediana_m": round(float(np.median(e[:, 1])), 3),
        "error_p90_m": round(float(np.percentile(e[:, 1], 90)), 3),
        "error_mediana_por_tercio_y": [
            (
                round(float(np.median(e[tercio == k, 1])), 3)
                if (tercio == k).any()
                else None
            )
            for k in range(3)
        ],
    }


def episodios_de_error(pata: str, csv: Path) -> dict:
    """Errores de equipo contra el GT como EPISODIOS por persona (no cambiar cortos por largos).

    Cada persona del GT (jugador de A o B), en cada frame del GT, se casa 1-a-1 a ≤ 2 m con una fila
    real del sistema. Un episodio es una racha de frames seguidos de la misma persona con el equipo
    equivocado. Se mide con los dos nombres A/B y vale el mejor.
    """
    from scipy.optimize import linear_sum_assignment

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    d = PATAS[pata]
    gt_m = gt_a_por_frame(
        parsear_cvat(R / d["gt"]), np.load(R / d["homografia"]), d["offset"], 15
    )
    df = pd.read_csv(csv)
    df = df[df.es_real == 1]
    base = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}
    frames = sorted(gt_m)
    paso_s = float(np.median(np.diff(frames))) / 30.0 if len(frames) > 1 else 0.5
    mejor = None
    for cruzado in (False, True):
        por_persona: dict = {}
        for f in frames:
            gente = [o for o in gt_m[f] if base.get(str(o.team)) in ("A", "B")]
            sub = df[df.frame == f]
            if not gente or not len(sub):
                continue
            gt = np.array([o.pos for o in gente], dtype=float)
            sis = sub[["x_m", "y_m"]].to_numpy()
            dist = np.linalg.norm(gt[:, None] - sis[None], axis=2)
            i, j = linear_sum_assignment(np.where(dist <= 2.0, dist, 1e6))
            for a_, b_ in zip(i, j):
                if dist[a_, b_] > 2.0:
                    continue
                eq_gt = base[str(gente[a_].team)]
                eq_sis = base.get(str(sub.etiqueta.iloc[b_]))
                if eq_sis is None:
                    continue
                if cruzado:
                    eq_sis = "B" if eq_sis == "A" else "A"
                por_persona.setdefault(gente[a_].obj_id, []).append(
                    (f, eq_sis != eq_gt)
                )
        duraciones, mal, total = [], 0, 0
        for obs in por_persona.values():
            racha = 0
            for k, (f, es_mal) in enumerate(obs):
                total += 1
                mal += es_mal
                seguido = k > 0 and f - obs[k - 1][0] <= 1.5 * paso_s * 30
                if es_mal and (racha == 0 or seguido):
                    racha += 1
                elif es_mal:
                    duraciones.append(racha * paso_s)
                    racha = 1
                if not es_mal and racha:
                    duraciones.append(racha * paso_s)
                    racha = 0
            if racha:
                duraciones.append(racha * paso_s)
        r = {
            "casadas": total,
            "mal_pct": round(100 * mal / max(total, 1), 2),
            "jugador_segundos_mal": round(mal * paso_s, 1),
            "episodios": len(duraciones),
            "episodios_de_mas_de_3s": int(sum(x > 3.0 for x in duraciones)),
            "episodio_mas_largo_s": round(max(duraciones), 1) if duraciones else 0.0,
        }
        if mejor is None or r["mal_pct"] < mejor["mal_pct"]:
            mejor = r
    return mejor


def idf1_por_equipo(pata: str, csv: Path) -> dict:
    """IDF1 DENTRO de cada equipo contra el GT: ¿una ficha sigue a la misma persona?

    Para cada equipo: W[persona, ficha] = frames del GT en que la ficha (de ese color) está a
    ≤ 2 m de la persona. La asignación global que maximiza los frames casados da IDTP, e
    IDF1 = 2·IDTP / (observaciones del GT + filas del sistema de ese color en frames del GT).
    Se mide con los dos nombres A/B y vale el mejor.
    """
    from scipy.optimize import linear_sum_assignment

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    d = PATAS[pata]
    gt_m = gt_a_por_frame(
        parsear_cvat(R / d["gt"]), np.load(R / d["homografia"]), d["offset"], 15
    )
    df = pd.read_csv(csv)
    df = df[df.frame.isin(set(gt_m))]
    base = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}
    df = df.assign(eqb=df.etiqueta.map(base))
    mejor = None
    for nombres in ({"A": "A", "B": "B"}, {"A": "B", "B": "A"}):
        res = {}
        for eq_gt, eq_sis in nombres.items():
            sub = df[df.eqb == eq_sis]
            personas = sorted(
                {
                    o.obj_id
                    for obs in gt_m.values()
                    for o in obs
                    if base.get(str(o.team)) == eq_gt
                }
            )
            fichas = sorted(sub.id_jugador.unique())
            if not personas or not fichas:
                res[eq_gt] = 0.0
                continue
            W = np.zeros((len(personas), len(fichas)))
            ip = {x: k for k, x in enumerate(personas)}
            jf = {x: k for k, x in enumerate(fichas)}
            n_gt = 0
            por_frame = {f: g for f, g in sub.groupby("frame")}
            for f, obs in gt_m.items():
                gente = [o for o in obs if base.get(str(o.team)) == eq_gt]
                n_gt += len(gente)
                g = por_frame.get(f)
                if g is None or not gente:
                    continue
                xy = g[["x_m", "y_m"]].to_numpy()
                ids = g.id_jugador.to_numpy()
                for o in gente:
                    cerca = np.flatnonzero(
                        np.linalg.norm(xy - np.asarray(o.pos), axis=1) <= 2.0
                    )
                    for c in cerca:
                        W[ip[o.obj_id], jf[ids[c]]] += 1
            i, j = linear_sum_assignment(-W)
            res[eq_gt] = round(float(2 * W[i, j].sum() / max(n_gt + len(sub), 1)), 3)
        if mejor is None or sum(res.values()) > sum(mejor.values()):
            mejor = res
    return mejor


def asociacion_gt(
    pata: str, csv: Path, radio: float = 2.0, cruce_m: float = 2.5
) -> dict:
    """Recall, IDF1 global, fragmentación e intercambios de persona contra el GT.

    Casado 1-a-1 a ≤ `radio` en cada frame del GT entre las personas del GT (jugadores de A o B) y
    las filas reales del sistema etiquetadas como jugador (A, B o porteros). Un INTERCAMBIO es una
    identidad del sistema que, entre dos casados seguidos, pasa de la persona P a la Q; es «en
    cruce» si P y Q están a ≤ `cruce_m` en alguno de los dos frames, y «entre rivales» si P y Q son
    de equipos distintos.
    """
    from scipy.optimize import linear_sum_assignment

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    d = PATAS[pata]
    gt_m = gt_a_por_frame(
        parsear_cvat(R / d["gt"]), np.load(R / d["homografia"]), d["offset"], 15
    )
    base = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}
    df = pd.read_csv(csv)
    df = df[(df.es_real == 1) & df.etiqueta.isin(list(base)) & df.frame.isin(set(gt_m))]
    por_frame = {f: g for f, g in df.groupby("frame")}
    equipo_de, pos_de = {}, {}
    casados = []  # (frame, persona, ficha)
    n_gt = 0
    for f in sorted(gt_m):
        gente = [o for o in gt_m[f] if base.get(str(o.team)) in ("A", "B")]
        n_gt += len(gente)
        for o in gente:
            equipo_de[o.obj_id] = base[str(o.team)]
            pos_de[(f, o.obj_id)] = np.asarray(o.pos, dtype=float)
        g = por_frame.get(f)
        if g is None or not gente:
            continue
        gt = np.array([o.pos for o in gente], dtype=float)
        sis = g[["x_m", "y_m"]].to_numpy()
        dist = np.linalg.norm(gt[:, None] - sis[None], axis=2)
        i, j = linear_sum_assignment(np.where(dist <= radio, dist, 1e6))
        for a_, b_ in zip(i, j):
            if dist[a_, b_] <= radio:
                casados.append((f, gente[a_].obj_id, int(g.id_jugador.iloc[b_])))
    personas = sorted(equipo_de)
    fichas = sorted({c[2] for c in casados})
    W = np.zeros((len(personas), max(len(fichas), 1)))
    ip = {x: k for k, x in enumerate(personas)}
    jf = {x: k for k, x in enumerate(fichas)}
    for _f, per, fi in casados:
        W[ip[per], jf[fi]] += 1
    a_, b_ = linear_sum_assignment(-W)
    idtp = W[a_, b_].sum()
    por_ficha: dict = {}
    for f, per, fi in casados:
        por_ficha.setdefault(fi, []).append((f, per))
    cambios = {
        "rivales_en_cruce": 0,
        "companeros_en_cruce": 0,
        "rivales": 0,
        "companeros": 0,
    }
    for obs in por_ficha.values():
        obs.sort()
        for (f0, p0), (f1, p1) in zip(obs[:-1], obs[1:]):
            if p0 == p1:
                continue
            tipo = "rivales" if equipo_de[p0] != equipo_de[p1] else "companeros"
            cambios[tipo] += 1
            cerca = [
                np.linalg.norm(pos_de[(f, p0)] - pos_de[(f, p1)])
                for f in (f0, f1)
                if (f, p0) in pos_de and (f, p1) in pos_de
            ]
            if cerca and min(cerca) <= cruce_m:
                cambios[f"{tipo}_en_cruce"] += 1
    fichas_por_persona = [
        len({fi for _f, pe, fi in casados if pe == per}) for per in personas
    ]
    return {
        "recall_pct": round(100 * len(casados) / max(n_gt, 1), 1),
        "idf1": round(float(2 * idtp / max(n_gt + len(df), 1)), 3),
        "fichas_por_persona": round(float(np.mean(fichas_por_persona)), 2),
        "intercambios": cambios,
    }


def medir(pata: str, csv: Path) -> dict:
    import linea_base_mision as lb

    d = PATAS[pata]
    largo, ancho = d["campo"]
    desde, hasta = d.get("tramo", (None, None))
    df = lb.lo_que_pinta(csv, largo, ancho, desde, hasta)
    desde = desde if desde is not None else float(df.tiempo_s.min())
    hasta = hasta if hasta is not None else float(df.tiempo_s.max())
    res = {
        "pizarra": lb.medir(
            lb.simular(df, desde, hasta), largo, ancho, d["por_equipo"], 2.0
        ),
        "datos": lb.conciliar(df, desde, hasta),
    }
    if "gt" in d:
        import banco_equipos_v2 as bq

        bq.PATAS[pata] = d
        res["gt"] = bq.medir_con_gt(pata, csv)
        res["posicion"] = error_de_posicion(pata, csv)
        res["episodios"] = episodios_de_error(pata, csv)
        res["idf1_equipo"] = idf1_por_equipo(pata, csv)
        res["asociacion"] = asociacion_gt(pata, csv)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--patas", nargs="+", default=["alevinb", "villa", "benja"])
    ap.add_argument(
        "--tracking", default="{}", help="cambios (JSON) sobre la config de tracking"
    )
    ap.add_argument(
        "--equipos", default="{}", help="cambios (JSON) sobre la config de equipos"
    )
    ap.add_argument("--rehacer", action="store_true")
    ap.add_argument(
        "--salida",
        type=Path,
        default=None,
        help="carpeta de salida (por defecto la de siempre)",
    )
    a = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    global SALIDA
    if a.salida is not None:
        SALIDA = a.salida
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / "resultados.json"
    res = json.loads(ruta.read_text()) if ruta.exists() else {}
    for pata in a.patas:
        if a.nombre in res.get(pata, {}) and not a.rehacer:
            continue
        if pata == "alevinb":
            csv, mini_gt = correr_con_mini_gt(
                a.nombre, json.loads(a.tracking), json.loads(a.equipos)
            )
        else:
            csv, mini_gt = (
                correr(pata, a.nombre, json.loads(a.tracking), json.loads(a.equipos)),
                None,
            )
        r = medir(pata, csv)
        if mini_gt:
            r["mini_gt"] = mini_gt
        res = json.loads(ruta.read_text()) if ruta.exists() else {}
        res.setdefault(pata, {})[a.nombre] = r
        ruta.write_text(json.dumps(res, indent=1, ensure_ascii=False))
        p = r["pizarra"]
        print(
            pata,
            a.nombre,
            json.dumps(
                {
                    "cambiosAB": p["cambios_AB_por_min"],
                    "saltos": p["saltos_3m_en_02s_por_min"],
                    "v_p99": p["velocidad_p50_p95_p99_ms"][2],
                    "eventos": p["eventos_por_min"],
                    "simult_pct_sobre_tope": [
                        v[k]
                        for v in p["simultaneas"].values()
                        for k in v
                        if k.startswith("pct")
                    ],
                    "ids_min": r["datos"]["identidades_por_min"],
                    "mini_gt": (r.get("mini_gt") or {}).get("acierto_pct"),
                    "gt": r.get("gt"),
                    "posicion": r.get("posicion"),
                    "episodios": r.get("episodios"),
                    "idf1_equipo": r.get("idf1_equipo"),
                    "asociacion": r.get("asociacion"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
