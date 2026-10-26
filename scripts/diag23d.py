#!/usr/bin/env python
"""Diagnóstico 23-oct (d): la pista del árbitro de la variante 2, vista por dentro.

Criterios en `docs/diagnostico_23oct_d.md`. Usa las cachés de chaleco del 23-oct (c)
(`outputs/diagnostico_23oct_c/cache_chaleco_*.pkl`).

Uso:
    python scripts/diag23d.py pista --salida outputs/diagnostico_23oct_d        # pasada base
    python scripts/diag23d.py velocidades --salida outputs/diagnostico_23oct_d  # bloque 1
    python scripts/diag23d.py cruzada --salida outputs/diagnostico_23oct_d      # bloque 2
    python scripts/diag23d.py porteros --salida outputs/diagnostico_23oct_d     # bloque 3
    python scripts/diag23d.py clip --salida outputs/diagnostico_23oct_d         # bloque 4
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
CHALECO = R / "outputs/diagnostico_23oct_c/cache_chaleco_benja_p1.pkl"
MODELO = R / "configs/arbitro_viterbi_benja.json"
HOY_22D = (
    R / "outputs/diagnostico_22oct_d/posiciones_hoy.csv"
)  # la verdad del 23-oct (a)
BINS = [0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 1.0001]
VENTANA_GT = (9750, 10635)
CORTE_MITADES = 10192  # H1 = 9750-10191, H2 = 10192-10635
FPS = 29.97002997002997


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def relojes(frame: int) -> str:
    """Los dos relojes: archivo y reproductor de Alex (+1:33)."""
    t = frame / FPS
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int(r // 60)}:{r % 60:04.1f} repr"


def dets_crudos() -> dict:
    from src.tracking.cache_io import cargar_cache

    cfg = yaml.safe_load(open(CONFIG))
    return {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }


# ── la pasada de la variante 2 (con el modelo de emisión que se le pase) ──────────────────────


def pasada(nombre: str, salida: Path, modelo: Path, vit: dict | None):
    """CSV + la pista capturada + el caché filtrado que ve el tracker."""
    import src.team_classification.arbitro_viterbi as av
    import src.team_classification.pipeline_equipos as pe
    from src.tracking_data.processor import procesar_desde_cache

    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    csv = salida / f"{nombre}.csv"
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(salida / f"{nombre}_meta.json")
    cfg["rutas"]["cache_chaleco"] = str(CHALECO)
    captura = {}
    original_cfg, original_pista = pe.cargar_config_equipos, av.pista_del_arbitro

    def con_flag(ruta):
        ce = original_cfg(ruta)
        if vit is not None:
            ce.setdefault("arbitro", {})["viterbi"] = {
                "activo": True,
                "modelo_emision": str(modelo),
                **vit,
            }
        return ce

    def espia(cache, chaleco, mod, params, dims):
        p = original_pista(cache, chaleco, mod, params, dims)
        captura.update(pista=p, cache=cache, chaleco=chaleco, modelo=mod)
        return p

    original_aplicar = av.aplicar_pista

    def espia_aplicar(identidades, equipos, etiquetas, pista, colores, clf, params):
        salida_obs = original_aplicar(
            identidades, equipos, etiquetas, pista, colores, clf, params
        )
        captura.update(
            identidades=[
                [(int(f), int(j)) for tr in ident for (f, j) in tr.det_idxs]
                for ident in identidades
            ],
            equipos=dict(equipos),
            etiquetas_por_obs=dict(salida_obs),
        )
        return salida_obs

    pe.cargar_config_equipos, av.pista_del_arbitro = con_flag, espia
    av.aplicar_pista = espia_aplicar
    try:
        procesar_desde_cache(cfg)
    finally:
        pe.cargar_config_equipos, av.pista_del_arbitro = original_cfg, original_pista
        av.aplicar_pista = original_aplicar
    return csv, captura


def pista_base(salida: Path) -> None:
    """Hoy y variante 2 con el modelo de ayer; guarda la captura para los demás bloques."""
    for nombre, vit in (("hoy", None), ("v2_anade", {"variante": "anade"})):
        csv, captura = pasada(nombre, salida, MODELO, vit)
        if vit is not None:
            pickle.dump(captura, open(salida / f"captura_{nombre}.pkl", "wb"))
        print(nombre, csv)


def cargar_captura(salida: Path, nombre: str = "v2_anade") -> dict:
    return pickle.load(open(salida / f"captura_{nombre}.pkl", "rb"))


# ── utilidades de geometría ───────────────────────────────────────────────────────────────────


def metros_por_pixel(caja, H) -> float:
    """Metros que vale 1 px vertical en el pie de la caja (homografía local)."""

    def proy(u, v):
        p = H @ np.array([u, v, 1.0])
        return p[:2] / p[2]

    cx, y2 = (caja[0] + caja[2]) / 2, caja[3]
    return float(np.linalg.norm(proy(cx, y2 + 1) - proy(cx, y2)))


def iou_max_con_otras(dets_frame, j) -> float:
    """IoU máximo de la caja j con cualquier otra caja del frame."""
    a = np.asarray(dets_frame[j][2:6], float)
    mejor = 0.0
    for i, d in enumerate(dets_frame):
        if i == j:
            continue
        b = np.asarray(d[2:6], float)
        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
        iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy
        union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
        if union > 0:
            mejor = max(mejor, inter / union)
    return mejor


def pasos(fs, t, pos) -> np.ndarray:
    """Velocidad de cada paso entre frames consecutivos de una pista (la definición de ayer)."""
    if len(fs) < 2:
        return np.zeros(0)
    return np.hypot(*np.diff(pos, axis=0).T) / np.maximum(np.diff(t), 1e-6)


# ── bloque 1: los pasos a más de 9 m/s ────────────────────────────────────────────────────────


def identidad_por_deteccion(csv: Path, filtrado: dict, crudo: dict) -> dict:
    """{(frame, índice filtrado): id_jugador} por la caja cruda más cercana a cada fila real."""
    import pandas as pd

    inv = _mod("diag22e_invariantes")
    fk = inv.con_caja(pd.read_csv(csv), crudo)
    id_crudo = {
        (int(f), int(k)): int(i) for f, k, i in zip(fk.frame, fk.k, fk.id_jugador)
    }
    out = {}
    for f, dets in filtrado.items():
        indice = {tuple(d[2:6]): i for i, d in enumerate(crudo.get(f, []))}
        for j, d in enumerate(dets):
            i = indice.get(tuple(d[2:6]))
            if i is not None and (f, i) in id_crudo:
                out[(f, j)] = id_crudo[(f, i)]
    return out


def control_jugadores(filtrado: dict, t_de: dict, gt, radio: float) -> dict:
    """Pistas de los jugadores del GT al mismo muestreo: detección casada 1-a-1 a ≤ radio."""
    from scipy.optimize import linear_sum_assignment

    claves = sorted(gt)
    por_persona: dict[int, dict[int, tuple]] = {}
    for f, obs in gt.items():
        for o in obs:
            por_persona.setdefault(o.obj_id, {})[f] = (o.pos, o.label)
    frames = [f for f in sorted(filtrado) if claves[0] <= f <= claves[-1]]
    pistas: dict[int, list] = {}
    for f in frames:
        ids, P = [], []
        for pid, serie in por_persona.items():
            fk = sorted(serie)
            if not fk[0] <= f <= fk[-1] or serie[fk[0]][1] == "referee":
                continue
            a = max(x for x in fk if x <= f)
            b = min(x for x in fk if x >= f)
            pa, pb = np.asarray(serie[a][0]), np.asarray(serie[b][0])
            w = 0.0 if b == a else (f - a) / (b - a)
            ids.append(pid)
            P.append(pa + w * (pb - pa))
        D = np.array([d[:2] for d in filtrado[f]], float).reshape(-1, 2)
        if not ids or not len(D):
            continue
        P = np.array(P)
        coste = np.hypot(D[None, :, 0] - P[:, None, 0], D[None, :, 1] - P[:, None, 1])
        for i, j in zip(*linear_sum_assignment(np.where(coste > radio, 1e6, coste))):
            if coste[i, j] <= radio:
                pistas.setdefault(ids[i], []).append((f, D[j]))
    v = []
    for serie in pistas.values():
        fs = [f for f, _ in serie]
        v.extend(
            pasos(fs, np.array([t_de[f] for f in fs]), np.array([p for _, p in serie]))
        )
    v = np.asarray(v)
    return {
        "radio_m": radio,
        "personas": len(pistas),
        "pasos": int(len(v)),
        "pct_mas_de_9": round(100 * float(np.mean(v > 9.0)), 2) if len(v) else None,
    }


def velocidades(salida: Path) -> dict:
    from src.team_classification.arbitro_viterbi import log_lr

    col = _mod("diag22g_color")
    cap = cargar_captura(salida)
    pista, modelo = cap["pista"], cap["modelo"]
    filtrado = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    t_de = {e["frame_idx"]: float(e["t"]) for e in cap["cache"]}
    crudo = dets_crudos()
    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    ident = identidad_por_deteccion(salida / "v2_anade.csv", filtrado, crudo)
    fs = sorted(pista)
    pos = np.array([filtrado[f][pista[f]][:2] for f in fs])
    t = np.array([t_de[f] for f in fs])
    v = pasos(fs, t, pos)
    paso_proc = float(np.median(np.diff(sorted(t_de.values()))))
    filas = []
    for n in np.flatnonzero(v > 9.0):
        f0, f1 = fs[n], fs[n + 1]
        j0, j1 = pista[f0], pista[f1]
        llr = log_lr(
            np.array(
                [cap["chaleco"].get((f0, j0), 0.0), cap["chaleco"].get((f1, j1), 0.0)]
            ),
            modelo,
        )
        mpp = max(
            metros_por_pixel(filtrado[f0][j0][2:6], H),
            metros_por_pixel(filtrado[f1][j1][2:6], H),
        )
        i0, i1 = ident.get((f0, j0)), ident.get((f1, j1))
        filas.append(
            {
                "f0": int(f0),
                "f1": int(f1),
                "relojes": relojes(int(f0)),
                "v_m_s": round(float(v[n]), 1),
                "salto_m": round(float(np.hypot(*(pos[n + 1] - pos[n]))), 2),
                "dt_s": round(float(t[n + 1] - t[n]), 2),
                "hueco": bool(t[n + 1] - t[n] > 1.5 * paso_proc),
                "m_por_px": round(mpp, 3),
                "id0": i0,
                "id1": i1,
                "cambia_de_identidad": bool(
                    i0 is not None and i1 is not None and i0 != i1
                ),
                "chaleco_cae": bool(np.any(llr <= 0)),
                "caja_fundida": bool(
                    max(
                        iou_max_con_otras(filtrado[f0], j0),
                        iou_max_con_otras(filtrado[f1], j1),
                    )
                    > 0.1
                ),
                "en_ventana_gt": bool(VENTANA_GT[0] <= f0 <= VENTANA_GT[1]),
            }
        )

    def zona(m):
        return "cerca" if m < 0.1 else ("medio" if m <= 0.2 else "fondo")

    def magnitud(x):
        return (
            "9-12"
            if x < 12
            else ("12-20" if x < 20 else ("20-40" if x < 40 else ">40"))
        )

    def reparto(clave):
        out: dict = {}
        for r in filas:
            out[clave(r)] = out.get(clave(r), 0) + 1
        return dict(sorted(out.items(), key=lambda kv: str(kv[0])))

    # la misma fracción en la pista del árbitro, en todos los pasos de cada zona (el denominador)
    zonas_todos: dict = {}
    for n in range(len(v)):
        z = zona(metros_por_pixel(filtrado[fs[n]][pista[fs[n]]][2:6], H))
        tot, alto = zonas_todos.get(z, (0, 0))
        zonas_todos[z] = (tot + 1, alto + int(v[n] > 9.0))
    en_v = [
        n
        for n in range(len(v))
        if VENTANA_GT[0] <= fs[n] and fs[n + 1] <= VENTANA_GT[1]
    ]
    gt = col.gt_de("benja")
    res = {
        "pasos_pista": int(len(v)),
        "pasos_mas_de_9": len(filas),
        "pct_mas_de_9": round(100 * len(filas) / max(len(v), 1), 2),
        "pct_mas_de_9_sin_huecos": round(
            100
            * sum(not r["hueco"] for r in filas)
            / max(int(np.sum(np.diff(t) <= 1.5 * paso_proc)), 1),
            2,
        ),
        "paso_procesado_s": round(paso_proc, 3),
        "arbitro_en_ventana_gt": {
            "pasos": len(en_v),
            "pct_mas_de_9": (
                round(100 * float(np.mean(v[en_v] > 9.0)), 2) if en_v else None
            ),
        },
        "por_zona_pct_de_sus_pasos": {
            z: {"pasos": a, "mas_de_9": b, "pct": round(100 * b / max(a, 1), 2)}
            for z, (a, b) in sorted(zonas_todos.items())
        },
        "por_magnitud": reparto(lambda r: magnitud(r["v_m_s"])),
        "con_hueco": reparto(lambda r: r["hueco"]),
        "cambia_de_identidad": reparto(lambda r: r["cambia_de_identidad"]),
        "chaleco_cae": reparto(lambda r: r["chaleco_cae"]),
        "caja_fundida": reparto(lambda r: r["caja_fundida"]),
        "control_jugadores_1m": control_jugadores(filtrado, t_de, gt, 1.0),
        "control_jugadores_2m": control_jugadores(filtrado, t_de, gt, 2.0),
    }
    (salida / "bloque1_pasos.json").write_text(
        json.dumps(filas, indent=1, ensure_ascii=False)
    )
    return res


# ── bloque 2: emisión con mitades cruzadas ────────────────────────────────────────────────────


def modelo_en_rango(rango: tuple[int, int], ruta: Path) -> dict:
    """El modelo de ayer (misma verdad del 23-oct a, mismos bins) con solo los frames del rango."""
    import pandas as pd
    from scipy.optimize import linear_sum_assignment

    from src.team_classification.arbitro_viterbi import estimar_modelo

    inv, col = _mod("diag22e_invariantes"), _mod("diag22g_color")
    dets = dets_crudos()
    chaleco = pickle.load(open(CHALECO, "rb"))
    fk = inv.con_caja(pd.read_csv(HOY_22D), dets)
    arb, jug = [], []
    for f, obs in col.gt_de("benja").items():
        if not rango[0] <= f <= rango[1]:
            continue
        g = fk[fk.frame == f]
        if not len(g):
            continue
        D = np.array([dets[f][k][:2] for k in g.k])
        P = np.array([o.pos for o in obs])
        coste = np.hypot(D[None, :, 0] - P[:, None, 0], D[None, :, 1] - P[:, None, 1])
        for i, j in zip(*linear_sum_assignment(np.where(coste > 1.0, 1e6, coste))):
            if coste[i, j] <= 1.0:
                jug.append(chaleco.get((f, int(g.k.iloc[j])), 0.0))
        for j, (x, y) in enumerate(D):
            if (
                np.min(np.hypot(P[:, 0] - x, P[:, 1] - y)) > 3.0
                and 2 <= x <= 60
                and 2 <= y <= 38
            ):
                arb.append(chaleco.get((f, int(g.k.iloc[j])), 0.0))
    m = estimar_modelo(np.array(arb), np.array(jug), BINS)
    ruta.write_text(json.dumps(m, indent=1))
    return m


def cruzada(salida: Path) -> dict:
    import pandas as pd

    inv, fe, col = (
        _mod(n) for n in ("diag22e_invariantes", "foto_de_estado", "diag22g_color")
    )
    gt = col.gt_de("benja")
    mitades = {
        "H1": (VENTANA_GT[0], CORTE_MITADES - 1),
        "H2": (CORTE_MITADES, VENTANA_GT[1]),
    }

    def gt_de_mitad(m):
        a, b = mitades[m]
        return {f: o for f, o in gt.items() if a <= f <= b}

    ref_csv = salida / "v2_anade.csv"
    ref = cargar_captura(salida)

    def medidas(csv, cap, gt_eval):
        filas = pd.read_csv(csv)
        return {
            "cobertura_pct": round(
                100 * len(cap["pista"]) / max(len(cap["cache"]), 1), 2
            ),
            "B_mas_de_7_pct": inv.invariantes(
                inv.recuento_por_frame(filas, 62.0, 40.0), 7
            )["pct_B_mas_del_tope"],
            "centroide_m_en_la_mitad_no_vista": round(
                float(fe.medir(str(csv), gt_eval, None, 62.0, 40.0)["centroide"]), 3
            ),
        }

    res = {"modelo_ventana_entera": json.loads(MODELO.read_text())}
    for estima, evalua in (("H1", "H2"), ("H2", "H1")):
        ruta = salida / f"modelo_emision_{estima}.json"
        res[f"modelo_{estima}"] = modelo_en_rango(mitades[estima], ruta)
        csv, cap = pasada(f"v2_modelo_{estima}", salida, ruta, {"variante": "anade"})
        nueva = medidas(csv, cap, gt_de_mitad(evalua))
        base = medidas(ref_csv, ref, gt_de_mitad(evalua))
        comunes = [f for f in cap["pista"] if f in ref["pista"]]
        misma = sum(cap["pista"][f] == ref["pista"][f] for f in comunes)
        d = {k: round(nueva[k] - base[k], 3) for k in nueva}
        res[f"estima_{estima}_evalua_{evalua}"] = {
            "con_modelo_de_la_mitad": nueva,
            "con_modelo_de_la_ventana_entera": base,
            "diferencia": d,
            "frames_de_la_pista_con_la_misma_deteccion_pct": round(
                100 * misma / max(len(set(cap["pista"]) | set(ref["pista"])), 1), 2
            ),
            "criterio": {
                "centroide_<=0,03": abs(d["centroide_m_en_la_mitad_no_vista"]) <= 0.03,
                "cobertura_<=1_punto": abs(d["cobertura_pct"]) <= 1.0,
                "B_mas_de_7_<=1_punto": abs(d["B_mas_de_7_pct"]) <= 1.0,
            },
        }
    return res


# ── bloque 3: la regla de portero ─────────────────────────────────────────────────────────────

AREA_Y = (7.0, 33.0)  # área F7 del modelo: 26 m de ancho centrados en un campo de 40
AREA_X = {
    "A": (0.0, 12.0),
    "B": (50.0, 62.0),
}  # A defiende x = 0 (la portería de la cámara)
COLOR_BGR = {
    "A": (235, 187, 183),
    "B": (6, 45, 235),
    "portero_A": (255, 255, 0),
    "portero_B": (0, 140, 255),
    "otro": (0, 255, 255),
    "staff": (150, 150, 150),
}


def proxy_portero(xy: np.ndarray, lado: str) -> int | None:
    """Índice de la detección más profunda dentro del área de `lado`, o None."""
    if not len(xy):
        return None
    x0, x1 = AREA_X[lado]
    dentro = (xy[:, 0] >= x0) & (xy[:, 0] <= x1) & (xy[:, 1] >= AREA_Y[0])
    dentro &= xy[:, 1] <= AREA_Y[1]
    if not dentro.any():
        return None
    idx = np.flatnonzero(dentro)
    return int(
        idx[np.argmax(xy[idx, 0])] if lado == "B" else idx[np.argmin(xy[idx, 0])]
    )


def filas_con_caja(csv: Path, crudo: dict):
    import pandas as pd

    inv = _mod("diag22e_invariantes")
    return inv.con_caja(pd.read_csv(csv), crudo)


def por_frame(fk) -> dict:
    """{frame: (k[], xy crudo[], etiqueta[], id[])} con UNA fila por detección cruda."""
    out = {}
    for f, g in fk.drop_duplicates(["frame", "k"]).groupby("frame"):
        out[int(f)] = (
            g.k.to_numpy(),
            g.etiqueta.astype(str).to_numpy(),
            g.id_jugador.to_numpy(),
        )
    return out


def control_proxy_gt(pf: dict, crudo: dict) -> dict:
    """¿El proxy cae a ≤ 1,5 m del portero del GT (la persona de mediana de x más extrema)?"""
    col = _mod("diag22g_color")
    gt = col.gt_de("benja")
    xs: dict[int, list] = {}
    for obs in gt.values():
        for o in obs:
            xs.setdefault(o.obj_id, []).append(o.pos[0])
    med = {i: float(np.median(v)) for i, v in xs.items()}
    portero_gt = {"A": min(med, key=med.get), "B": max(med, key=med.get)}
    res = {}
    for lado, pid in portero_gt.items():
        n = acierta = sin_proxy = 0
        for f, obs in gt.items():
            o = next((o for o in obs if o.obj_id == pid), None)
            if o is None or f not in pf:
                continue
            k = pf[f][0]
            xy = np.array([crudo[f][int(j)][:2] for j in k], float)
            p = proxy_portero(xy, lado)
            n += 1
            if p is None:
                sin_proxy += 1
                continue
            acierta += np.hypot(*(xy[p] - np.asarray(o.pos))) <= 1.5
        res[lado] = {
            "track_gt": int(pid),
            "mediana_x_gt": round(med[pid], 2),
            "frames": n,
            "proxy_a_menos_de_1_5m_pct": round(100 * acierta / max(n, 1), 1),
            "sin_proxy": sin_proxy,
        }
    return res


def clasificador_de_color():
    from src.team_classification.pipeline_equipos import (
        cargar_config_equipos,
        entrenar_clasificador,
    )
    from src.tracking.cache_io import cargar_cache

    cfg = yaml.safe_load(open(CONFIG))
    ce = cargar_config_equipos(cfg["config_equipos"])
    colores = pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    cache = cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    return entrenar_clasificador(colores, ce, cache), colores


def roles(salida: Path, fk, pf: dict, crudo: dict, alto_img: int) -> dict:
    """Fracción de frames con rol correcto por lado y fallos por tipo."""
    from src.team_classification.oclusion import color_medio_limpio

    clf, colores = clasificador_de_color()

    def equipo_de_color(f, k):
        c = colores.get((f, int(k)))
        if c is None:
            return None
        return clf.predict_color(
            color_medio_limpio([((f, int(k)), c)], None), solo_equipos=True
        )

    res = {}
    ambos = 0
    cuentas = {lado: {} for lado in ("A", "B")}
    for f, (k, et, _ids) in pf.items():
        xy = np.array([crudo[f][int(j)][:2] for j in k], float)
        p = {lado: proxy_portero(xy, lado) for lado in ("A", "B")}
        if p["A"] is None or p["B"] is None:
            continue
        ambos += 1
        for lado in ("A", "B"):
            c = cuentas[lado]
            rol = f"portero_{lado}"
            if et[p[lado]] == rol:
                c["correcto"] = c.get("correcto", 0) + 1
                continue
            portadores = np.flatnonzero(et == rol)
            caja = crudo[f][int(k[p[lado]])][2:6]
            if caja[3] >= alto_img - 3:
                tipo = "2_portero_cortado_por_el_borde"
            elif len(portadores) >= 2:
                tipo = "4_dos_a_la_vez"
            elif len(portadores) == 1:
                eq = equipo_de_color(f, k[portadores[0]])
                tipo = (
                    "1_se_la_lleva_jugador_del_otro_equipo"
                    if eq is not None and eq != lado
                    else "1b_se_la_lleva_otra_deteccion_de_su_color"
                )
            else:
                tipo = "3_sin_corona"
            c[tipo] = c.get(tipo, 0) + 1
            clave = f"etiqueta_del_portero_real_{et[p[lado]]}"
            c[clave] = c.get(clave, 0) + 1
    for lado, c in cuentas.items():
        res[lado] = {
            "frames_con_ambos_visibles": ambos,
            "rol_correcto_pct": round(100 * c.get("correcto", 0) / max(ambos, 1), 1),
            "fallos": {k: v for k, v in sorted(c.items()) if k != "correcto"},
        }
    return res


def tabla_identidades(fk) -> dict:
    out = {}
    for rol in ("portero_A", "portero_B"):
        g = fk[fk.etiqueta == rol]
        t = g.groupby("id_jugador").agg(
            filas=("frame", "size"), f0=("frame", "min"), f1=("frame", "max")
        )
        out[rol] = [
            {
                "id": int(i),
                "filas": int(r.filas),
                "desde": relojes(int(r.f0)),
                "hasta": relojes(int(r.f1)),
            }
            for i, r in t.sort_values("f0").iterrows()
        ]
    return out


def pizarra(filas_frame, ancho_px: int, alto_px: int):
    """La pizarra de UN frame: el campo 62 x 40 visto desde arriba, con la etiqueta del instante."""
    import cv2

    img = np.full((alto_px, ancho_px, 3), (40, 110, 40), np.uint8)
    m = 20
    esc = min((ancho_px - 2 * m) / 62.0, (alto_px - 2 * m) / 40.0)

    def px(x, y):
        return int(m + x * esc), int(m + (40.0 - y) * esc)

    cv2.rectangle(img, px(0, 0), px(62, 40), (255, 255, 255), 1)
    cv2.line(img, px(31, 0), px(31, 40), (255, 255, 255), 1)
    for lado in ("A", "B"):
        x0, x1 = AREA_X[lado]
        cv2.rectangle(img, px(x0, AREA_Y[0]), px(x1, AREA_Y[1]), (255, 255, 255), 1)
    for r in filas_frame.itertuples():
        col = COLOR_BGR.get(str(r.etiqueta), (255, 255, 255))
        cv2.circle(img, px(r.x_m, r.y_m), 6, col, -1)
        cv2.putText(
            img,
            f"{r.etiqueta[:6]}#{int(r.id_jugador)}",
            px(r.x_m + 0.8, r.y_m),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (255, 255, 255),
            1,
        )
    cv2.putText(
        img,
        "x=0 (camara, porteria A)",
        (m, alto_px - 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        (255, 255, 255),
        1,
    )
    return img


def paneles_30(salida: Path, fk, pf: dict, crudo: dict) -> list[dict]:
    """30 frames con B > 7 repartidos por el partido: vídeo con cajas + pizarra del frame."""
    import cv2
    import pandas as pd

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    inv = _mod("diag22e_invariantes")
    cfg = yaml.safe_load(open(CONFIG))
    filas = pd.read_csv(salida / "v2_anade.csv")
    c = inv.recuento_por_frame(filas, 62.0, 40.0)
    con_b = np.array(sorted(int(f) for f in c.index[c.B > 7]))
    bordes = np.linspace(filas.frame.min(), filas.frame.max() + 1, 31)
    rng = np.random.default_rng(1)
    elegidos = []
    for a, b in zip(bordes[:-1], bordes[1:]):
        en = con_b[(con_b >= a) & (con_b < b)]
        if len(en):
            elegidos.append(int(rng.choice(en)))
    carpeta = salida / "paneles_30"
    carpeta.mkdir(parents=True, exist_ok=True)
    lista = []
    for f, img in leer_frames_ffmpeg(R / cfg["rutas"]["video"], elegidos):
        k, et, ids = pf[f]
        xy = np.array([crudo[f][int(j)][:2] for j in k], float)
        prox = {lado: proxy_portero(xy, lado) for lado in ("A", "B")}
        for n, j in enumerate(k):
            x1, y1, x2, y2 = (int(round(v)) for v in crudo[f][int(j)][2:6])
            col = COLOR_BGR.get(str(et[n]), (255, 255, 255))
            grosor = 3 if str(et[n]) in ("B", "portero_B") else 1
            cv2.rectangle(img, (x1, y1), (x2, y2), col, grosor)
            cv2.putText(
                img,
                f"{et[n]} #{int(ids[n])}",
                (x1, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                col,
                1,
            )
        for lado, p in prox.items():
            if p is None:
                continue
            x1, y1, x2, y2 = (int(round(v)) for v in crudo[f][int(k[p])][2:6])
            cv2.circle(img, ((x1 + x2) // 2, y1 - 18), 9, (255, 0, 255), 2)
            cv2.putText(
                img,
                f"P{lado}",
                ((x1 + x2) // 2 - 9, y1 - 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 0, 255),
                2,
            )
        h = img.shape[0]
        piz = pizarra(fk[fk.frame == f], int(h * 62 / 40) // 2, h // 2)
        lienzo = np.zeros((h, img.shape[1] + piz.shape[1], 3), np.uint8)
        ancho_video = img.shape[1]
        lienzo[:, :ancho_video] = img
        lienzo[: piz.shape[0], ancho_video:] = piz
        cv2.rectangle(lienzo, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(
            lienzo,
            f"f{f}  {relojes(f)}  B en el campo: {int(c.loc[f, 'B'])}"
            "  (B en grueso; PA/PB = proxy del portero real)",
            (8, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
        )
        nombre = f"f{f}.jpg"
        cv2.imwrite(str(carpeta / nombre), lienzo, [cv2.IMWRITE_JPEG_QUALITY, 85])
        lista.append(
            {
                "frame": f,
                "relojes": relojes(f),
                "B": int(c.loc[f, "B"]),
                "panel": nombre,
            }
        )
    (carpeta / "paneles.json").write_text(
        json.dumps(lista, indent=1, ensure_ascii=False)
    )
    return lista


def tabla_filas_b(salida: Path) -> dict:
    """Apoyo a la lectura a ojo de los paneles: cada fila B / portero_B de los frames elegidos.

    Para cada fila: el voto de color de ESA observación, la altura de su caja relativa a las
    vecinas a la misma altura de imagen (< 0,6 = fragmento o fantasma), el IoU con otra caja
    (> 0,3 = fundida) y cuántas filas del CSV caen en la MISMA caja (≥ 2 = fila duplicada).
    """
    from src.team_classification.oclusion import color_medio_limpio

    inv = _mod("diag22e_invariantes")
    import pandas as pd

    lista = json.loads((salida / "paneles_30/paneles.json").read_text())
    frames = [x["frame"] for x in lista]
    crudo = dets_crudos()
    filas = pd.read_csv(salida / "v2_anade.csv")
    fk = inv.con_caja(filas[filas.frame.isin(frames)], crudo)
    clf, colores = clasificador_de_color()
    out = {}
    for f in frames:
        g = fk[fk.frame == f]
        D = crudo[f]
        filas_b = []
        for r in g.itertuples():
            if str(r.etiqueta) not in ("B", "portero_B"):
                continue
            caja = D[int(r.k)][2:6]
            vecinas = [
                D[int(o.k)][2:6]
                for o in g.itertuples()
                if o.k != r.k and abs(D[int(o.k)][5] - caja[3]) < 60
            ]
            alto_med = np.median([v[3] - v[1] for v in vecinas]) if vecinas else None
            c = colores.get((f, int(r.k)))
            voto = (
                clf.predict_color(
                    color_medio_limpio([((f, int(r.k)), c)], None), solo_equipos=True
                )
                if c is not None
                else None
            )
            filas_b.append(
                {
                    "id": int(r.id_jugador),
                    "etiqueta": str(r.etiqueta),
                    "voto_color": voto,
                    "alto_relativo": (
                        round(float((caja[3] - caja[1]) / alto_med), 2)
                        if alto_med
                        else None
                    ),
                    "iou_max": round(iou_max_con_otras(D, int(r.k)), 2),
                    "filas_en_la_misma_caja": int((g.k == r.k).sum()),
                }
            )
        out[str(f)] = {"relojes": relojes(f), "filas_B": filas_b}
    return out


# ── bloque 5: las filas duplicadas ────────────────────────────────────────────────────────────

CASOS_DUPLICADO = [4662, 4923, 6780, 10782, 13959, 17115, 18885, 19608]  # bloque 3


def equipo_base(etiqueta) -> str:
    e = str(etiqueta)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def iou_cajas(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0


def observaciones_por_frame(cap: dict) -> dict:
    """{frame: [(identidad 1-based, índice filtrado, equipo base de su etiqueta FINAL)]}."""
    out: dict[int, list] = {}
    for i, obs in enumerate(cap["identidades"], start=1):
        et_id = cap["equipos"].get(i, "otro")
        for f, j in obs:
            et = cap["etiquetas_por_obs"].get((i, f)) or et_id
            out.setdefault(f, []).append((i, j, equipo_base(et)))
    return out


def pareja(cap, filtrado, f, a, b) -> dict:
    """IoU de las cajas PROPIAS, distancia y solape temporal de dos observaciones del frame f."""
    (i1, j1, e1), (i2, j2, e2) = a, b
    d1, d2 = filtrado[f][j1], filtrado[f][j2]
    f1 = {x for x, _ in cap["identidades"][i1 - 1]}
    f2 = {x for x, _ in cap["identidades"][i2 - 1]}
    return {
        "frame": int(f),
        "ids": [int(i1), int(i2)],
        "equipos": [e1, e2],
        "iou_propio": round(iou_cajas(d1[2:6], d2[2:6]), 3),
        "distancia_m": round(float(np.hypot(d1[0] - d2[0], d1[1] - d2[1])), 2),
        "solape_temporal": round(len(f1 & f2) / max(min(len(f1), len(f2)), 1), 3),
        "obs": [len(f1), len(f2)],
    }


def casos_misma_caja(salida, cap, filtrado, crudo, frames) -> list[dict]:
    """Parejas de filas reales del CSV en la MISMA caja cruda (la medida del bloque 3)."""
    import pandas as pd

    inv = _mod("diag22e_invariantes")
    filas = pd.read_csv(salida / "v2_anade_ident.csv")
    fk = inv.con_caja(filas[filas.frame.isin(frames)], crudo)
    pf = observaciones_por_frame(cap)
    out = []
    for f in frames:
        g = fk[fk.frame == f]
        obs_de = {o[0]: o for o in pf.get(f, [])}
        for k, gg in g.groupby("k"):
            if len(gg) < 2 or not gg.etiqueta.map(equipo_base).eq("B").any():
                continue
            ids = [int(x) for x in gg.id_jugador]
            fila = {
                "frame": int(f),
                "relojes": relojes(int(f)),
                "ids": ids,
                "etiquetas": gg.etiqueta.astype(str).tolist(),
                "con_observacion_propia": [i in obs_de for i in ids],
            }
            if all(i in obs_de for i in ids[:2]):
                fila.update(pareja(cap, filtrado, f, obs_de[ids[0]], obs_de[ids[1]]))
            out.append(fila)
    return out


def parejas_gt(cap, filtrado, radio_gt: float = 2.0, casado: float = 1.0) -> list[dict]:
    """Compañeros del GT a ≤ radio_gt, casados 1-a-1 a ≤ casado con detecciones de identidades
    DISTINTAS: el control de personas distintas."""
    from scipy.optimize import linear_sum_assignment

    col = _mod("diag22g_color")
    gt = col.gt_de("benja")
    pf = observaciones_por_frame(cap)
    out = []
    for f, obs in gt.items():
        if f not in filtrado:
            continue
        D = np.array([d[:2] for d in filtrado[f]], float).reshape(-1, 2)
        P = np.array([o.pos for o in obs], float)
        if not len(D):
            continue
        coste = np.hypot(D[None, :, 0] - P[:, None, 0], D[None, :, 1] - P[:, None, 1])
        casa = {}
        for i, j in zip(*linear_sum_assignment(np.where(coste > casado, 1e6, coste))):
            if coste[i, j] <= casado:
                casa[i] = j
        dueno = {j: o for o in pf.get(f, []) for j in [o[1]]}
        for a in range(len(obs)):
            for b in range(a + 1, len(obs)):
                if equipo_base(obs[a].team) != equipo_base(obs[b].team):
                    continue
                if (
                    np.hypot(*(np.asarray(obs[a].pos) - np.asarray(obs[b].pos)))
                    > radio_gt
                ):
                    continue
                if a not in casa or b not in casa:
                    continue
                oa, ob = dueno.get(casa[a]), dueno.get(casa[b])
                if oa is None or ob is None or oa[0] == ob[0]:
                    continue
                out.append(pareja(cap, filtrado, f, oa, ob))
    return out


def reconciliar(salida, cap, filtrado, crudo) -> dict:
    """«Filas en la misma caja» en la ventana del GT: ¿una persona o dos, según el GT?"""
    import pandas as pd

    inv, col = _mod("diag22e_invariantes"), _mod("diag22g_color")
    gt = col.gt_de("benja")
    filas = pd.read_csv(salida / "v2_anade_ident.csv")
    r = filas[filas.es_real == 1]
    fk = inv.con_caja(r[r.frame.isin(list(gt))], crudo)
    una = dos = ninguna = 0
    for (f, k), gg in fk.groupby(["frame", "k"]):
        if len(gg) < 2:
            continue
        x, y = crudo[f][int(k)][:2]
        cerca = sum(np.hypot(o.pos[0] - x, o.pos[1] - y) <= 1.5 for o in gt[f])
        if cerca >= 2:
            dos += 1
        elif cerca == 1:
            una += 1
        else:
            ninguna += 1
    return {
        "cajas_con_2_o_mas_filas_en_los_frames_del_gt": una + dos + ninguna,
        "con_1_persona_del_gt_a_1_5m": una,
        "con_2_o_mas_personas_del_gt_a_1_5m": dos,
        "sin_persona_del_gt": ninguna,
        "frames_del_gt": len(gt),
    }


def control_gt_amplio(cap, filtrado, casado: float = 1.0) -> list[tuple]:
    """TODAS las parejas del mismo equipo en los frames del GT cuyas detecciones están casadas con
    personas DISTINTAS, a cualquier distancia: (IoU de las cajas, distancia en m, frame).

    El control de compañeros a ≤ 2 m no ve a dos personas que se solapan en la IMAGEN estando
    lejos en METROS (una detrás de otra en profundidad), que es justo lo que un IoU toca.
    """
    from scipy.optimize import linear_sum_assignment

    gt = _mod("diag22g_color").gt_de("benja")
    pf = observaciones_por_frame(cap)
    out = []
    for f, obs in gt.items():
        if f not in filtrado:
            continue
        D = np.array([x[:2] for x in filtrado[f]], float).reshape(-1, 2)
        P = np.array([o.pos for o in obs], float)
        C = np.hypot(D[None, :, 0] - P[:, None, 0], D[None, :, 1] - P[:, None, 1])
        persona = {}
        for i, j in zip(*linear_sum_assignment(np.where(C > casado, 1e6, C))):
            if C[i, j] <= casado:
                persona[j] = i
        lst = pf.get(f, [])
        for a in range(len(lst)):
            for b in range(a + 1, len(lst)):
                (_, j1, e1), (_, j2, e2) = lst[a], lst[b]
                if e1 != e2 or e1 not in ("A", "B"):
                    continue
                if j1 in persona and j2 in persona and persona[j1] != persona[j2]:
                    iou = iou_cajas(filtrado[f][j1][2:6], filtrado[f][j2][2:6])
                    out.append(
                        (round(iou, 3), round(float(np.hypot(*(D[j1] - D[j2]))), 2), f)
                    )
    return sorted(out, reverse=True)


def desplazamiento_de_filas(salida, cap, filtrado, casos) -> None:
    """Distancia de la fila del CSV a la detección PROPIA de su identidad (añade a cada caso)."""
    import pandas as pd

    filas = pd.read_csv(salida / "v2_anade_ident.csv")
    pf = observaciones_por_frame(cap)
    for c in casos:
        f = c["frame"]
        obs_de = {o[0]: o for o in pf.get(f, [])}
        c["desplazamiento_fila_m"] = []
        for i in c["ids"][:2]:
            fila = filas[(filas.frame == f) & (filas.id_jugador == i)].iloc[0]
            j = obs_de[i][1]
            c["desplazamiento_fila_m"].append(
                round(
                    float(
                        np.hypot(
                            fila.x_m - filtrado[f][j][0], fila.y_m - filtrado[f][j][1]
                        )
                    ),
                    2,
                )
            )


def capturar_identidades(salida: Path) -> dict:
    if not (salida / "captura_v2_anade_ident.pkl").exists():
        _csv, cap = pasada("v2_anade_ident", salida, MODELO, {"variante": "anade"})
        pickle.dump(cap, open(salida / "captura_v2_anade_ident.pkl", "wb"))
    return pickle.load(open(salida / "captura_v2_anade_ident.pkl", "rb"))


def duplicados(salida: Path) -> dict:
    cap = capturar_identidades(salida)
    filtrado = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    crudo = dets_crudos()
    casos = casos_misma_caja(salida, cap, filtrado, crudo, CASOS_DUPLICADO)
    desplazamiento_de_filas(salida, cap, filtrado, casos)
    negativos = parejas_gt(cap, filtrado)
    amplio = control_gt_amplio(cap, filtrado)
    iou_neg = sorted(p["iou_propio"] for p in negativos)
    iou_casos = sorted(
        (c["iou_propio"] for c in casos if "iou_propio" in c), reverse=True
    )
    techo_neg = iou_neg[-1] if iou_neg else 0.0
    sexto = iou_casos[5] if len(iou_casos) >= 6 else None
    if sexto is not None and sexto > techo_neg:
        x = round((techo_neg + sexto) / 2, 3)
        criterio = {"intervalo": [techo_neg, sexto], "x": x}
    else:
        criterio = {
            "intervalo": None,
            "x": None,
            "motivo": "ningún x deja 0 parejas del GT y cubre ≥ 6 de los 8",
        }

    def cuantiles(v):
        return (
            [round(float(q), 3) for q in np.quantile(v, [0, 0.5, 0.9, 1])]
            if v
            else None
        )

    res = {
        "casos": casos,
        "control_gt": {
            "parejas": len(negativos),
            "iou_propio_min_med_p90_max": cuantiles(iou_neg),
            "distancia_m_min_med_p90_max": cuantiles(
                [p["distancia_m"] for p in negativos]
            ),
            "solape_min_med_p90_max": cuantiles(
                [p["solape_temporal"] for p in negativos]
            ),
        },
        "criterio_con_el_control_de_companeros_a_2m": criterio,
        "control_gt_amplio": {
            "parejas_de_personas_distintas": len(amplio),
            "top_iou_distancia_frame": amplio[:8],
            "con_iou_>=_x": (
                sum(a[0] >= criterio["x"] for a in amplio) if criterio["x"] else None
            ),
            "casos_con_iou_por_encima_del_maximo_amplio": sum(
                c.get("iou_propio", 0) > (amplio[0][0] if amplio else 0) for c in casos
            ),
        },
        "reconciliacion_ventana_gt": reconciliar(salida, cap, filtrado, crudo),
    }
    (salida / "bloque5_parejas_gt.json").write_text(json.dumps(negativos, indent=1))
    return res


def porteros(salida: Path) -> dict:
    crudo = dets_crudos()
    fk = filas_con_caja(salida / "v2_anade.csv", crudo)
    pf = por_frame(fk)
    cfg = yaml.safe_load(open(CONFIG))
    from src.tracking.cache_io import cargar_cache

    alto_img = int(cargar_cache(R / cfg["rutas"]["cache"])["wh"][1])
    return {
        "control_proxy_contra_el_gt": control_proxy_gt(pf, crudo),
        "roles": roles(salida, fk, pf, crudo, alto_img),
        "identidades": tabla_identidades(fk),
        "paneles": paneles_30(salida, fk, pf, crudo),
    }


# ── bloque 4: el clip 10:00-10:45 y el frame f23553 ───────────────────────────────────────────

F_ARBITRO_EN_B = 23553  # 13:05,9 archivo / 14:38,9 reproductor


def traza_f23553(salida: Path, ancho_s: float = 3.0) -> dict:
    """Alrededor de f23553: dónde está la pista y qué dice el chaleco de la fila del árbitro."""
    import pandas as pd

    from src.team_classification.arbitro_viterbi import log_lr

    cap = cargar_captura(salida)
    filtrado = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    crudo = dets_crudos()
    ident = identidad_por_deteccion(salida / "v2_anade.csv", filtrado, crudo)
    filas = pd.read_csv(salida / "v2_anade.csv")
    g = filas[(filas.frame == F_ARBITRO_EN_B) & (filas.es_real == 1)]
    # la fila B del árbitro: la de mayor chaleco del frame, entre las B
    cand = []
    for j, d in enumerate(filtrado[F_ARBITRO_EN_B]):
        i = ident.get((F_ARBITRO_EN_B, j))
        et = g[g.id_jugador == i].etiqueta.astype(str)
        cand.append(
            (
                cap["chaleco"].get((F_ARBITRO_EN_B, j), 0.0),
                j,
                i,
                et.iloc[0] if len(et) else None,
            )
        )
    s_arb, j_arb, id_arb, et_arb = max(cand)
    salto = int(round(ancho_s * FPS))
    frames = [f for f in sorted(filtrado) if abs(f - F_ARBITRO_EN_B) <= salto]
    traza = []
    for f in frames:
        j_p = cap["pista"].get(f)
        j_id = next(
            (j for j in range(len(filtrado[f])) if ident.get((f, j)) == id_arb), None
        )
        fila = {
            "frame": f,
            "relojes": relojes(f),
            "pista": None,
            "identidad_del_arbitro": None,
        }
        if j_p is not None:
            s = cap["chaleco"].get((f, j_p), 0.0)
            fila["pista"] = {
                "det": int(j_p),
                "id": ident.get((f, j_p)),
                "xy": [round(float(v), 2) for v in filtrado[f][j_p][:2]],
                "chaleco": round(float(s), 4),
                "log_lr": float(log_lr(np.array([s]), cap["modelo"])[0]),
            }
        if j_id is not None:
            s = cap["chaleco"].get((f, j_id), 0.0)
            fila["identidad_del_arbitro"] = {
                "det": int(j_id),
                "xy": [round(float(v), 2) for v in filtrado[f][j_id][:2]],
                "chaleco": round(float(s), 4),
                "log_lr": float(log_lr(np.array([s]), cap["modelo"])[0]),
                "etiqueta": (
                    filas[(filas.frame == f) & (filas.id_jugador == id_arb)]
                    .etiqueta.astype(str)
                    .tolist()[:1]
                    or [None]
                )[0],
            }
        traza.append(fila)
    (salida / "traza_f23553.json").write_text(
        json.dumps(traza, indent=1, ensure_ascii=False)
    )
    en_pista = [t for t in traza if t["pista"]]
    return {
        "fila_del_arbitro_en_f23553": {
            "det": int(j_arb),
            "id": id_arb,
            "etiqueta": et_arb,
            "chaleco": round(s_arb, 4),
            "log_lr": float(log_lr(np.array([s_arb]), cap["modelo"])[0]),
        },
        "frames_en_la_ventana": len(traza),
        "frames_con_pista": len(en_pista),
        "frames_con_la_pista_en_la_identidad_del_arbitro": sum(
            t["pista"]["id"] == id_arb for t in en_pista
        ),
        "detalle": "traza_f23553.json",
    }


def clip(salida: Path) -> dict:
    import subprocess

    carpeta = salida / "clip_10m"
    subprocess.run(
        [
            sys.executable,
            str(R / "scripts/diag23b_auditoria.py"),
            "render",
            "--csv-hoy",
            str(salida / "hoy.csv"),
            "--csv-variante",
            str(salida / "v2_anade.csv"),
            "--salida",
            str(carpeta),
        ],
        check=True,
    )
    return {
        "clip": sorted(
            p.name for p in carpeta.iterdir() if p.suffix in (".mp4", ".html")
        ),
        "f23553": traza_f23553(salida),
    }


# ── bloque 6: relleno de los huecos de un frame (velocidad mediana de 3 pasos) ────────────────


def huecos_de_un_frame(
    salida: Path, cap: dict, filtrado: dict, crudo: dict
) -> list[dict]:
    """Los 56 casos del bloque 4: un frame fuera de la pista entre dos frames de la pista con la
    MISMA identidad del tracker, con la detección de esa identidad presente y su fila en un equipo.
    """
    import pandas as pd

    ident = identidad_por_deteccion(salida / "v2_anade.csv", filtrado, crudo)
    filas = pd.read_csv(salida / "v2_anade.csv")
    r = filas[filas.es_real == 1]
    et = {
        (int(a), int(b)): str(c) for a, b, c in zip(r.frame, r.id_jugador, r.etiqueta)
    }
    p = cap["pista"]
    frames = sorted(filtrado)
    casos = []
    for n in range(1, len(frames) - 1):
        f, a, b = frames[n], frames[n - 1], frames[n + 1]
        if f in p or a not in p or b not in p:
            continue
        ia, ib = ident.get((a, p[a])), ident.get((b, p[b]))
        if ia is None or ia != ib:
            continue
        j = next((j for j in range(len(filtrado[f])) if ident.get((f, j)) == ia), None)
        if j is None:
            continue
        if equipo_base(et.get((f, ia))) in ("A", "B"):
            casos.append({"frame": int(f), "id": int(ia), "det": int(j)})
    return casos


def relleno(salida: Path) -> dict:
    import pandas as pd

    inv = _mod("diag22e_invariantes")
    base = cargar_captura(salida)
    filtrado = {e["frame_idx"]: e["dets"] for e in base["cache"]}
    t_de = {e["frame_idx"]: float(e["t"]) for e in base["cache"]}
    crudo = dets_crudos()
    casos = huecos_de_un_frame(salida, base, filtrado, crudo)
    csv, cap = pasada(
        "v2_vel3", salida, MODELO, {"variante": "anade", "velocidad_pasos": 3}
    )

    def medidas(csv_ruta, c):
        fs = sorted(c["pista"])
        pos = np.array([filtrado[f][c["pista"][f]][:2] for f in fs])
        v = pasos(fs, np.array([t_de[f] for f in fs]), pos)
        filas = pd.read_csv(csv_ruta)
        return {
            "cobertura_pct": round(100 * len(fs) / max(len(filtrado), 1), 2),
            "B_mas_de_7_pct": inv.invariantes(
                inv.recuento_por_frame(filas, 62.0, 40.0), 7
            )["pct_B_mas_del_tope"],
            "pasos_mas_de_9_pct": round(100 * float(np.mean(v > 9.0)), 2),
        }

    antes = medidas(salida / "v2_anade.csv", base)
    despues = medidas(csv, cap)
    cubiertos = sum(cap["pista"].get(c["frame"]) == c["det"] for c in casos)
    comunes = set(cap["pista"]) & set(base["pista"])
    cambia = sum(cap["pista"][f] != base["pista"][f] for f in comunes)
    return {
        "casos": len(casos),
        "cubiertos": int(cubiertos),
        "v2_velocidad_1_paso": antes,
        "v2_velocidad_3_pasos": despues,
        "frames_que_entran_en_la_pista": len(set(cap["pista"]) - set(base["pista"])),
        "frames_que_salen_de_la_pista": len(set(base["pista"]) - set(cap["pista"])),
        "frames_con_otra_deteccion_elegida": int(cambia),
        "criterio": {
            "cubre_>=40": cubiertos >= 40,
            "cobertura_no_empeora": despues["cobertura_pct"] >= antes["cobertura_pct"],
            "B_mas_de_7_no_empeora": despues["B_mas_de_7_pct"]
            <= antes["B_mas_de_7_pct"],
            "pasos_>9_suben_<=0,2": despues["pasos_mas_de_9_pct"]
            <= antes["pasos_mas_de_9_pct"] + 0.2,
        },
    }


# ── bloque 7: los clips donde hoy y la variante 2 más se distinguen ───────────────────────────

TRAMOS_CLIP = {"1m00": (60.0, 105.0), "7m00": (420.0, 465.0)}  # segundos del ARCHIVO


def clips(salida: Path) -> dict:
    """Vídeo + pizarra de cada tramo, con hoy y con la variante 2 (ésta, con la pista dibujada)."""
    import subprocess

    import pandas as pd

    cap = cargar_captura(salida)
    filtrado = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    py = sys.executable
    res = {}
    for nombre, (t0, t1) in TRAMOS_CLIP.items():
        carpeta = salida / f"clip_{nombre}"
        carpeta.mkdir(parents=True, exist_ok=True)
        cfg = yaml.safe_load(open(CONFIG))
        cfg["muestreo"]["tramo"] = {"min_ini": t0 / 60, "dur_seg": t1 - t0}
        ruta_cfg = carpeta / "config_tramo.yaml"
        ruta_cfg.write_text(yaml.safe_dump(cfg, allow_unicode=True))
        frames = [f for f in sorted(filtrado) if t0 <= f / FPS < t1]
        cajas = {
            str(f): [float(v) for v in filtrado[f][cap["pista"][f]][2:6]]
            for f in frames
            if f in cap["pista"]
        }
        ruta_pista = carpeta / "pista_v2.json"
        ruta_pista.write_text(json.dumps({"cajas": cajas}))
        for variante, csv in (("hoy", "hoy.csv"), ("v2", "v2_anade.csv")):
            tramo = pd.read_csv(salida / csv)
            tramo = tramo[tramo.tiempo_s.between(t0, t1)]
            csv_tramo = carpeta / f"tramo_{variante}.csv"
            tramo.to_csv(csv_tramo, index=False)
            orden = [
                py,
                str(R / "scripts/generar_video_detecciones.py"),
                "--config",
                str(ruta_cfg),
                "--csv",
                str(csv_tramo),
                "--salida",
                str(carpeta / f"video_{nombre}_{variante}.mp4"),
            ]
            if variante == "v2":
                orden += ["--pista", str(ruta_pista)]
            subprocess.run(orden, check=True)
            subprocess.run(
                [
                    py,
                    str(R / "scripts/generar_replay.py"),
                    "--csv",
                    str(csv_tramo),
                    "--salida",
                    str(carpeta / f"pizarra_{nombre}_{variante}.html"),
                    "--config-campo",
                    str(R / "configs/campo_benja.yaml"),
                    "--titulo",
                    f"{int(t0 // 60)}:{int(t0 % 60):02d}-{int(t1 // 60)}:{int(t1 % 60):02d}"
                    f" (archivo) · {variante}",
                ],
                check=True,
            )
        res[nombre] = {
            "archivo_s": [t0, t1],
            "frames": len(frames),
            "frames_con_pista": len(cajas),
            "frames_sin_pista_borde_rojo": len(frames) - len(cajas),
            "ficheros": sorted(
                p.name for p in carpeta.iterdir() if p.suffix in (".mp4", ".html")
            ),
        }
    return res


def main() -> None:
    # Una sola tabla de acciones: los subcomandos válidos salen de ella, así no se desincronizan.
    acciones = {
        "velocidades": velocidades,
        "cruzada": cruzada,
        "porteros": porteros,
        "tabla_filas_b": tabla_filas_b,
        "duplicados": duplicados,
        "clip": clip,
        "clips": clips,
        "relleno": relleno,
    }
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["pista", *acciones])
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    if args.accion == "pista":
        pista_base(salida)
        return
    res = acciones[args.accion](salida)
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / f"{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
