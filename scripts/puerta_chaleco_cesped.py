#!/usr/bin/env python
"""Puerta del intento 2 del árbitro: ¿se separan el chaleco y el césped en (S, V)? Solo medición.

Plan y criterio: `docs/plan_arbitro_intento2_puerta.md`. El CRITERIO se commitea ANTES de medir.

Uso (sobre la pasada de `causas_equipo_equivocado.py pasada --trabajo DIR`):
    python scripts/puerta_chaleco_cesped.py --trabajo DIR
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

# ── Fijado ANTES de medir (commit aparte) ─────────────────────────────────────
CRITERIO = {
    "centro_torso_filas": (0.20, 0.45),
    "centro_torso_columnas": (0.35, 0.65),
    "frames_por_minuto": 20,  # uno cada 3 s
    "minutos": list(range(20)),
    "s_alta_min": 170,  # mediana de S del chaleco en el minuto
    "s_baja_max": 120,
    "percentiles_cesped": (1, 99),  # el rectángulo (S, V) del césped, minuto a minuto
    "cierre_solape_s_baja": 0.10,  # > 10 % de los píxeles de chaleco de S baja dentro → se cierra
    "desplazamientos_caja_vacia": (-6, -3, 3, 6),  # en anchos de caja, en horizontal
    "franjas_x": [(0, 20), (20, 40), (40, 62)],
    "max_px_por_caja": 300,
    "semilla": 0,
}
CONFIG = R / "configs/processor_benja_parte_entera.yaml"


def recorte_centro(img, caja):
    """Píxeles HSV (N×3) del centro del torso de `caja`; vacío si no cabe."""
    import cv2

    x1, y1, x2, y2 = caja
    al, an = y2 - y1, x2 - x1
    f0, f1 = CRITERIO["centro_torso_filas"]
    c0, c1 = CRITERIO["centro_torso_columnas"]
    ya, yb = int(round(y1 + f0 * al)), int(round(y1 + f1 * al))
    xa, xb = int(round(x1 + c0 * an)), int(round(x1 + c1 * an))
    h, w = img.shape[:2]
    ya, yb, xa, xb = max(ya, 0), min(yb, h), max(xa, 0), min(xb, w)
    if yb - ya < 1 or xb - xa < 1:
        return np.zeros((0, 3), np.uint8)
    return cv2.cvtColor(img[ya:yb, xa:xb], cv2.COLOR_BGR2HSV).reshape(-1, 3)


def solape(chaleco_sv: np.ndarray, cesped_sv: np.ndarray, p=(1, 99)) -> float:
    """Fracción de píxeles de chaleco dentro del rectángulo (S, V) p1-p99 del césped."""
    if not len(chaleco_sv) or not len(cesped_sv):
        return float("nan")
    s0, s1 = np.percentile(cesped_sv[:, 0], p)
    v0, v1 = np.percentile(cesped_sv[:, 1], p)
    dentro = (chaleco_sv[:, 0] >= s0) & (chaleco_sv[:, 0] <= s1)
    dentro &= (chaleco_sv[:, 1] >= v0) & (chaleco_sv[:, 1] <= v1)
    return float(dentro.mean())


def clase_de_minuto(mediana_s: float) -> str:
    if mediana_s >= CRITERIO["s_alta_min"]:
        return "S alta"
    if mediana_s <= CRITERIO["s_baja_max"]:
        return "S baja"
    return "mixto"


def veredicto(solape_s_baja: float | None) -> str:
    if solape_s_baja is None or np.isnan(solape_s_baja):
        return "NO CONCLUYENTE (no hay minutos de S baja)"
    if solape_s_baja > CRITERIO["cierre_solape_s_baja"]:
        return "SE CIERRA LA VÍA sin construir (el chaleco de S baja cae en el rango del césped)"
    return "LA PUERTA PASA: se puede construir la señal del paso 3"


def _solapan(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def main() -> None:
    import cv2
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import posicionar_en_frame

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trabajo", required=True)
    args = ap.parse_args()
    trabajo = Path(args.trabajo)
    cfg = yaml.safe_load(open(CONFIG))
    fps = 29.97002997002997
    rng = np.random.default_rng(CRITERIO["semilla"])
    filas = pd.read_csv(trabajo / "posiciones.csv")
    reales = filas[filas.es_real == 1]
    capt = pickle.load(open(trabajo / "cajas.pkl", "rb"))
    spec = importlib.util.spec_from_file_location(
        "am", R / "scripts/arbitro_medicion.py"
    )
    am = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(am)
    crudo = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    W = am.masa_de_ventana(
        reales, crudo, pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    )
    zona_b = (W.x_m >= am.ZONA_PORTERO_B_X) & (
        (W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY
    )
    W["proxy"] = (W.masa >= am.UMBRAL_MASA) & ~zona_b & (W.etiqueta != "portero_B")
    proxy = set(zip(W[W.proxy].frame, W[W.proxy].id_jugador))
    H_pm = np.load(R / cfg["rutas"]["homografia"])

    def a_metros(u, v):
        p = H_pm @ np.array([u, v, 1.0])
        return p[0] / p[2], p[1] / p[2]

    frames_cache = np.array(sorted(capt["cache_filtrado"]))
    objetivo = {}
    for m in CRITERIO["minutos"]:
        for k in range(CRITERIO["frames_por_minuto"]):
            t = m * 60 + k * 60 / CRITERIO["frames_por_minuto"]
            f = int(frames_cache[np.argmin(np.abs(frames_cache - t * fps))])
            objetivo[f] = m
    porf = {f: g for f, g in reales.groupby("frame")}
    px = {"chaleco": {}, "cesped": {}, "portero_B": {}}

    def guardar(pob, m, hsv, franja=None):
        if not len(hsv):
            return
        if len(hsv) > CRITERIO["max_px_por_caja"]:
            hsv = hsv[rng.choice(len(hsv), CRITERIO["max_px_por_caja"], replace=False)]
        px[pob].setdefault((m, franja), []).append(hsv)

    cap = cv2.VideoCapture(str(R / cfg["rutas"]["video"]))
    actual = posicionar_en_frame(cap, 0)
    for f in sorted(objetivo):
        while actual < f:
            cap.grab()
            actual += 1
        ok, img = cap.read()
        actual += 1
        if not ok:
            raise RuntimeError(f"no se pudo leer el frame {f}")
        m = objetivo[f]
        dets = capt["cache_filtrado"].get(f, [])
        cajas = [tuple(d[2:6]) for d in dets]
        g = porf.get(f)
        if g is None:
            continue
        for r in g.itertuples():
            d = capt["obs"].get((int(r.id_jugador), f))
            if d is None:
                continue
            caja = [int(round(v)) for v in cajas[d]]
            if (f, int(r.id_jugador)) in proxy:
                guardar("chaleco", m, recorte_centro(img, caja))
            elif r.etiqueta == "portero_B":
                guardar("portero_B", m, recorte_centro(img, caja))
        # césped: cajas vacías del tamaño de una caja real, desplazadas en horizontal
        for x1, y1, x2, y2 in cajas[:3]:
            an = x2 - x1
            for dx in CRITERIO["desplazamientos_caja_vacia"]:
                c = (x1 + dx * an, y1, x2 + dx * an, y2)
                if (
                    c[0] < 0
                    or c[2] >= img.shape[1]
                    or any(_solapan(c, b) for b in cajas)
                ):
                    continue
                xm, ym = a_metros((c[0] + c[2]) / 2, c[3])
                if not (0 <= xm <= 62 and 0 <= ym <= 40):
                    continue
                fr = next(
                    i for i, (a, b) in enumerate(CRITERIO["franjas_x"]) if a <= xm <= b
                )
                guardar(
                    "cesped", m, recorte_centro(img, [int(round(v)) for v in c]), fr
                )
    cap.release()

    def junta(pob, m=None, franja="todas"):
        trozos = [
            v
            for (mm, fr), lista in px[pob].items()
            for v in lista
            if (m is None or mm == m) and (franja == "todas" or fr == franja)
        ]
        return np.vstack(trozos) if trozos else np.zeros((0, 3), np.uint8)

    por_minuto, s_baja_ch, s_baja_ce = [], [], []
    for m in CRITERIO["minutos"]:
        ch, ce = junta("chaleco", m), junta("cesped", m)
        if not len(ch) or not len(ce):
            continue
        clase = clase_de_minuto(float(np.median(ch[:, 1])))
        sol = solape(ch[:, 1:], ce[:, 1:], CRITERIO["percentiles_cesped"])
        por_minuto.append(
            {
                "minuto": m,
                "clase": clase,
                "px_chaleco": int(len(ch)),
                "px_cesped": int(len(ce)),
                "S_chaleco_mediana": float(np.median(ch[:, 1])),
                "V_chaleco_mediana": float(np.median(ch[:, 2])),
                "H_chaleco_mediana": float(np.median(ch[:, 0])),
                "S_cesped_p1_p99": [float(x) for x in np.percentile(ce[:, 1], [1, 99])],
                "V_cesped_p1_p99": [float(x) for x in np.percentile(ce[:, 2], [1, 99])],
                "H_cesped_p1_p99": [float(x) for x in np.percentile(ce[:, 0], [1, 99])],
                "solape_SV": round(sol, 4),
            }
        )
        if clase == "S baja":
            # el solape de S baja se mide contra el césped del MISMO minuto
            dentro = solape(ch[:, 1:], ce[:, 1:], CRITERIO["percentiles_cesped"]) * len(
                ch
            )
            s_baja_ch.append(len(ch))
            s_baja_ce.append(dentro)
    sol_baja = (sum(s_baja_ce) / sum(s_baja_ch)) if s_baja_ch else None

    def resumen(arr):
        if not len(arr):
            return None
        return {
            c: [float(x) for x in np.percentile(arr[:, i], [1, 25, 50, 75, 99])]
            for i, c in enumerate("HSV")
        }

    res = {
        "criterio": CRITERIO,
        "por_minuto": por_minuto,
        "minutos_por_clase": pd.Series([x["clase"] for x in por_minuto])
        .value_counts()
        .to_dict(),
        "solape_S_baja": sol_baja,
        "veredicto": veredicto(sol_baja),
        "distribuciones_p1_25_50_75_99": {
            "chaleco_S_alta": resumen(
                np.vstack(
                    [
                        junta("chaleco", x["minuto"])
                        for x in por_minuto
                        if x["clase"] == "S alta"
                    ]
                    or [np.zeros((0, 3))]
                )
            ),
            "chaleco_S_baja": resumen(
                np.vstack(
                    [
                        junta("chaleco", x["minuto"])
                        for x in por_minuto
                        if x["clase"] == "S baja"
                    ]
                    or [np.zeros((0, 3))]
                )
            ),
            **{
                f"cesped_x{a}-{b}": resumen(junta("cesped", None, i))
                for i, (a, b) in enumerate(CRITERIO["franjas_x"])
            },
            "portero_B": resumen(junta("portero_B")),
        },
    }
    (trabajo / "puerta.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
