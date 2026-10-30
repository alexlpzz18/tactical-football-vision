#!/usr/bin/env python
"""Punto 3 de docs/lente_f11.md: sistema contra GT de Villaviciosa, calibración actual y nueva.

Mismas detecciones (`cache_detecciones_v4pre`): solo cambia cómo se lleva el pie a metros. Se corre
`desde_cache` entero con cada calibración, porque el tracker trabaja en metros.

⚠️ El GT son cajas en píxeles y sus metros salen de LA MISMA calibración que se juzga: si una lente
encoge las distancias, este error baja sin mejorar nada. Por eso se informa la razón de escala y el
error dividido por ella, y por eso manda la medida A (marcas del campo, `lente_camara.py`).

Uso:
    python scripts/medir_lente.py --camara outputs/lente_f11/camara_ojo_pez.npz
"""

import argparse
import hashlib
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/lente_f11"
CONFIG = R / "configs/processor.yaml"
CACHE = R / "data/tracking/cache_detecciones_v4pre.pkl"
GT = R / "data/annotations/ground_truth_tracking/annotations.xml"
H_ACTUAL = R / "data/calibracion/homografia.npy"
OFFSET, PASO = 7500, 15
RADIO_CASADO_M = 2.0
FUERA = -1000.0  # un pie que la calibración no sabe convertir queda lejos del campo
N_BOOT = 2000
CORTES_VILLA = (0.635, 0.877)


def _lente():
    spec = importlib.util.spec_from_file_location("lc", R / "scripts/lente_camara.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def cargar_camara(ruta: Path, lc):
    d = np.load(ruta)
    return lc.Camara(
        str(d["tipo"]), float(d["f"]), float(d["cx"]), float(d["cy"]),
        d["coefs"], d["rvec"], d["tvec"],
    )  # fmt: skip


def conversor(nombre: str, lc, ruta_camara: Path | None):
    """Función: píxeles de la imagen CORREGIDA (N, 2) → metros (N, 2)."""
    H = np.load(H_ACTUAL)
    if nombre == "actual":

        def f(px):
            p = np.column_stack([px, np.ones(len(px))]) @ H.T
            return p[:, :2] / p[:, 2:3]

        return f
    cam = cargar_camara(ruta_camara, lc)
    return lambda px: cam.pixel_a_metros(lc.corregida_a_original(px))


def correr(nombre: str, convertir, salida: Path) -> Path:
    """`desde_cache` con el pie de cada detección reconvertido. Devuelve el CSV."""
    from src.tracking_data.processor import procesar_desde_cache

    datos = pickle.load(open(CACHE, "rb"))
    for e in datos["cache"]:
        if not e["dets"]:
            continue
        pies = np.array([[(d[2] + d[4]) / 2, d[5]] for d in e["dets"]], float)
        m = convertir(pies)
        nuevos = []
        for d, xy in zip(e["dets"], m):
            x, y = (
                (FUERA, FUERA)
                if not np.isfinite(xy).all()
                else (float(xy[0]), float(xy[1]))
            )
            nuevos.append((x, y, *d[2:]))
        e["dets"] = nuevos
    ruta_cache = salida / f"cache_{nombre}.pkl"
    pickle.dump(datos, open(ruta_cache, "wb"))
    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["cache"] = str(ruta_cache)
    csv = salida / f"posiciones_{nombre}.csv"
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(salida / f"posiciones_{nombre}_meta.json")
    procesar_desde_cache(cfg)
    return csv


def gt_en_metros(convertir) -> dict:
    """{frame: [(persona, equipo 'A'/'B', x, y, zona)]} con el pie del GT por `convertir`."""
    from src.evaluation.gt_parser import parsear_cvat

    por_frame: dict[int, list] = {}
    for t in parsear_cvat(GT):
        if t.label != "player":
            continue
        equipo = str(t.team).replace("portero_", "")
        for c in t.cajas:
            pie = np.array([[(c.xtl + c.xbr) / 2, c.ybr]], float)
            xy = convertir(pie)[0]
            por_frame.setdefault(OFFSET + PASO * c.frame_local, []).append(
                (t.track_id, equipo, float(xy[0]), float(xy[1]), pie[0])
            )
    return por_frame


def por_frame_de(csv: Path) -> dict:
    import pandas as pd

    df = pd.read_csv(csv)
    df = df[df.es_real == 1]
    df = df.assign(
        grupo=df.etiqueta.astype(str).str.replace("portero_", "", regex=False)
    )
    return {f: g for f, g in df.groupby("frame")}


def medir_uno(csv: Path, gt: dict) -> dict:
    """Por frame: errores de posición (1-a-1, ≤ 2 m) y de centroide por equipo."""
    pf = por_frame_de(csv)
    posiciones, centroides = {}, {}
    # qué letra del sistema es cada equipo del GT: la que da menos error de centroide en total
    for permuta in (False, True):
        total = []
        for f, obs in gt.items():
            if f not in pf:
                continue
            for eq in ("A", "B"):
                g = [(o[2], o[3]) for o in obs if o[1] == eq and np.isfinite(o[2])]
                e_sis = {"A": "B", "B": "A"}[eq] if permuta else eq
                s = pf[f][pf[f].grupo == e_sis][["x_m", "y_m"]].to_numpy()
                if g and len(s):
                    total.append(np.hypot(*(np.mean(g, axis=0) - s.mean(axis=0))))
        if not centroides or np.median(total) < centroides["_"]:
            centroides = {"_": float(np.median(total)), "permuta": permuta}
    permuta = centroides["permuta"]
    por_c: dict[int, list] = {}
    for f, obs in gt.items():
        if f not in pf:
            continue
        sub = pf[f]
        xy = sub[["x_m", "y_m"]].to_numpy()
        gente = [o for o in obs if np.isfinite(o[2])]
        G = np.array([[o[2], o[3]] for o in gente]).reshape(-1, 2)
        if len(G) and len(xy):
            d = np.hypot(xy[None, :, 0] - G[:, None, 0], xy[None, :, 1] - G[:, None, 1])
            c = np.where(d > RADIO_CASADO_M, 1e6, d)
            posiciones[f] = [
                float(d[a, b])
                for a, b in zip(*linear_sum_assignment(c))
                if c[a, b] < 1e6
            ]
        for eq in ("A", "B"):
            g = [(o[2], o[3]) for o in gente if o[1] == eq]
            e_sis = {"A": "B", "B": "A"}[eq] if permuta else eq
            s = sub[sub.grupo == e_sis][["x_m", "y_m"]].to_numpy()
            if g and len(s):
                por_c.setdefault(f, []).append(
                    float(np.hypot(*(np.mean(g, 0) - s.mean(0))))
                )
    return {"posiciones": posiciones, "centroides": por_c, "permuta": permuta}


def _mediana(por_frame: dict, frames) -> float:
    v = [x for f in frames for x in por_frame.get(f, [])]
    return float(np.median(v)) if v else float("nan")


def razon_de_escala(c_actual, c_nueva, gt: dict) -> dict:
    """m/px de la nueva entre m/px de la actual, en los pies del GT, por zona."""
    filas = []
    for obs in gt.values():
        for o in obs:
            p = np.array([o[4], o[4] + [0, 1.0], o[4] + [1.0, 0]])
            a, n = c_actual(p), c_nueva(p)
            m_a = np.linalg.norm(a[1] - a[0])
            ancho_a, ancho_n = np.linalg.norm(a[2] - a[0]), np.linalg.norm(n[2] - n[0])
            filas.append((m_a, np.linalg.norm(n[1] - n[0]) / m_a, ancho_n / ancho_a))
    f = np.array(filas)
    out = {}
    for z, q in (
        ("cerca", f[:, 0] <= CORTES_VILLA[0]),
        ("media", (f[:, 0] > CORTES_VILLA[0]) & (f[:, 0] <= CORTES_VILLA[1])),
        ("lejos", f[:, 0] > CORTES_VILLA[1]),
    ):
        out[z] = {
            "fondo_nueva_entre_actual": round(float(np.nanmedian(f[q, 1])), 3),
            "ancho_nueva_entre_actual": round(float(np.nanmedian(f[q, 2])), 3),
        }
    out["global"] = round(float(np.nanmedian(np.sqrt(f[:, 1] * f[:, 2]))), 3)
    return out


def comparar(ruta_camara: Path, salida: Path) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    lc = _lente()
    c_a = conversor("actual", lc, None)
    c_n = conversor("nueva", lc, ruta_camara)
    csv_a, csv_n = correr("actual", c_a, salida), correr("nueva", c_n, salida)
    gt_a, gt_n = gt_en_metros(c_a), gt_en_metros(c_n)
    a, n = medir_uno(csv_a, gt_a), medir_uno(csv_n, gt_n)
    escala = razon_de_escala(c_a, c_n, gt_a)
    frames = sorted(set(a["posiciones"]) & set(n["posiciones"]))
    rng = np.random.default_rng(0)
    res = {
        "frames": len(frames),
        "personas_del_gt": sum(len(v) for v in gt_a.values()),
        "gt_sin_convertir_con_la_nueva": sum(
            not np.isfinite(o[2]) for v in gt_n.values() for o in v
        ),
        "escala": escala,
    }
    for clave in ("posiciones", "centroides"):
        ma, mn = _mediana(a[clave], frames), _mediana(n[clave], frames)
        difs = []
        for _ in range(N_BOOT):
            fs = [frames[k] for k in rng.integers(0, len(frames), len(frames))]
            difs.append(_mediana(n[clave], fs) - _mediana(a[clave], fs))
        res[clave] = {
            "actual_m": round(ma, 3),
            "nueva_m": round(mn, 3),
            "nueva_entre_escala_m": round(mn / escala["global"], 3),
            "diferencia_ic95_m": [
                round(float(q), 3) for q in np.quantile(difs, [0.025, 0.975])
            ],
        }
    res["casadas"] = {
        "actual": sum(len(v) for v in a["posiciones"].values()),
        "nueva": sum(len(v) for v in n["posiciones"].values()),
    }
    # control: con la actual tiene que salir exactamente el CSV de producción
    prod = R / "outputs/fix_interpoladas/villa_despues.csv"
    if prod.exists():
        h = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (csv_a, prod)]
        res["control_actual_identico_a_produccion"] = h[0] == h[1]
    json.dump(res, open(salida / "medida_b.json", "w"), indent=1, ensure_ascii=False)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--camara", type=Path, required=True)
    ap.add_argument("--salida", type=Path, default=SALIDA / "medida_b")
    a = ap.parse_args()
    print(json.dumps(comparar(a.camara, a.salida), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
