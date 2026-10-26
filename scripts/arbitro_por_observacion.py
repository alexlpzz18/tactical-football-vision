#!/usr/bin/env python
"""El árbitro POR OBSERVACIÓN: fracción de píxeles verde flúor en el torso. Solo medición.

Plan y criterio: `docs/plan_arbitro_por_observacion.md`. El CRITERIO se commitea ANTES de medir.
La señal sale de los PÍXELES del vídeo (no del histograma del caché de color, que es de donde
sale el
proxy contra el que se mide).

Uso:
    python scripts/causas_equipo_equivocado.py pasada --trabajo DIR   # CSV + caja exacta por fila
    python scripts/arbitro_por_observacion.py senal --trabajo DIR     # lee el vídeo (~5-10 min)
    python scripts/arbitro_por_observacion.py medir --trabajo DIR
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
    "torso_filas": (0.15, 0.50),  # fracción del alto de la caja, desde arriba
    "torso_columnas": (0.30, 0.70),  # fracción del ancho
    "h": (
        55,
        75,
    ),  # OpenCV, 0-180: alrededor de 62 (chaleco); el césped cae por debajo de 50
    "s_min": 70,  # el chaleco baja a S≈72-104 la mitad del tiempo
    "v_min": 80,
    "umbrales": [0.05, 0.10, 0.15, 0.20, 0.30],
    "max_conversiones_gt": 1,  # jugadores o porteros convertidos en árbitro, en la ventana del GT
    "n_lista": 20,
}
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
GT = R / "data/annotations/gt_benja/annotations.xml"
OFFSET_GT, PASO_GT = 9750, 15
DESFASE_REPRODUCTOR_S = 93


def fraccion_fluor(img_bgr, caja) -> float | None:
    """Fracción de píxeles verde flúor en el torso de `caja` (x1, y1, x2, y2). None si no cabe."""
    import cv2

    x1, y1, x2, y2 = caja
    alto, ancho = y2 - y1, x2 - x1
    f0, f1 = CRITERIO["torso_filas"]
    c0, c1 = CRITERIO["torso_columnas"]
    ya, yb = int(round(y1 + f0 * alto)), int(round(y1 + f1 * alto))
    xa, xb = int(round(x1 + c0 * ancho)), int(round(x1 + c1 * ancho))
    h, w = img_bgr.shape[:2]
    ya, yb, xa, xb = max(ya, 0), min(yb, h), max(xa, 0), min(xb, w)
    if yb - ya < 2 or xb - xa < 2:
        return None
    hsv = cv2.cvtColor(img_bgr[ya:yb, xa:xb], cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = (H >= CRITERIO["h"][0]) & (H <= CRITERIO["h"][1])
    m &= (S >= CRITERIO["s_min"]) & (V >= CRITERIO["v_min"])
    return float(m.mean())


def umbral_elegido(conversiones: dict[float, int]) -> float | None:
    """El MENOR umbral con conversiones ≤ el máximo; None si ninguno cumple."""
    validos = [
        u
        for u in sorted(conversiones)
        if conversiones[u] <= CRITERIO["max_conversiones_gt"]
    ]
    return validos[0] if validos else None


def _reloj(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:04.1f}"


def senal(args) -> None:
    """Lee el vídeo entero en orden y mide la fracción en cada caja elegible."""
    import cv2
    import pandas as pd
    import yaml

    from src.tracking_data.processor import posicionar_en_frame

    trabajo = Path(args.trabajo)
    cfg = yaml.safe_load(open(CONFIG))
    filas = pd.read_csv(trabajo / "posiciones.csv")
    capt = pickle.load(open(trabajo / "cajas.pkl", "rb"))
    reales = filas[(filas.es_real == 1) & (filas.etiqueta != "staff")]
    elegibles = {}  # frame → [(k, id, etiqueta)]
    for r in reales.itertuples():
        d = capt["obs"].get((int(r.id_jugador), int(r.frame)))
        if d is None:
            continue
        det = capt["cache_filtrado"][int(r.frame)][d]
        if 0 <= det[0] <= 62 and 0 <= det[1] <= 40:
            elegibles.setdefault(int(r.frame), []).append(
                (d, int(r.id_jugador), r.etiqueta)
            )
    cap = cv2.VideoCapture(str(R / cfg["rutas"]["video"]))
    actual = posicionar_en_frame(cap, 0)
    salida = []
    for f in sorted(elegibles):
        while actual < f:
            cap.grab()
            actual += 1
        ok, img = cap.read()
        actual += 1
        if not ok:
            raise RuntimeError(f"no se pudo leer el frame {f}")
        dets = capt["cache_filtrado"][f]
        for d, n, etq in elegibles[f]:
            fr = fraccion_fluor(img, [int(round(v)) for v in dets[d][2:6]])
            salida.append((f, n, etq, d, fr))
    cap.release()
    pd.DataFrame(
        salida, columns=["frame", "id_jugador", "etiqueta", "caja", "frac"]
    ).to_csv(trabajo / "senal.csv", index=False)
    print(f"✓ {len(salida)} cajas medidas")


def medir(args) -> None:
    import cv2
    import pandas as pd
    import yaml

    from src.evaluation.desglose_error import casar_frame, equipo_de_etiqueta
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import posicionar_en_frame

    trabajo = Path(args.trabajo)
    cfg = yaml.safe_load(open(CONFIG))
    filas = pd.read_csv(trabajo / "posiciones.csv")
    reales = filas[filas.es_real == 1]
    S = pd.read_csv(trabajo / "senal.csv").dropna(subset=["frac"])
    spec = importlib.util.spec_from_file_location(
        "am", R / "scripts/arbitro_medicion.py"
    )
    am = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(am)
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    W = am.masa_de_ventana(
        reales, dets, pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    )
    zona_b = (W.x_m >= am.ZONA_PORTERO_B_X) & (
        (W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY
    )
    W["proxy"] = (W.masa >= am.UMBRAL_MASA) & ~zona_b & (W.etiqueta != "portero_B")
    S = S.merge(
        W[["frame", "id_jugador", "proxy", "x_m", "y_m"]], on=["frame", "id_jugador"]
    )
    H = np.load(R / cfg["rutas"]["homografia"])
    gt = gt_a_por_frame(parsear_cvat(GT), H, OFFSET_GT, PASO_GT)
    ventana = set(gt)
    fuera = S[~S.frame.isin(ventana)]

    # personas del GT (jugadores y porteros) casadas con cada fila de la ventana
    casadas = set()
    porf = {f: g for f, g in reales.groupby("frame")}
    for f in sorted(gt):
        g = porf.get(f)
        if g is None:
            continue
        personas = [(equipo_de_etiqueta(o.team), o.pos[0], o.pos[1]) for o in gt[f]]
        fc = casar_frame(
            f, personas, g.x_m.to_numpy(), g.y_m.to_numpy(), g.etiqueta.to_numpy(), 2.0
        )
        for p in fc.personas:
            if p.fila is not None:
                casadas.add((f, int(g.id_jugador.iloc[p.fila])))
    en_gt = S[[(f, n) in casadas for f, n in zip(S.frame, S.id_jugador)]]

    barrido = {}
    for u in CRITERIO["umbrales"]:
        disp = fuera.frac >= u
        barrido[u] = {
            "conversiones_gt": int((en_gt.frac >= u).sum()),
            "recuperacion_proxy_fuera": float(disp[fuera.proxy].mean()),
            "dispara_sin_proxy_fuera": int((disp & ~fuera.proxy).sum()),
            "etiquetas_de_las_conversiones": en_gt[en_gt.frac >= u]
            .etiqueta.value_counts()
            .to_dict(),
        }
    elegido = umbral_elegido({u: v["conversiones_gt"] for u, v in barrido.items()})

    # qué inventa: las 20 cajas de más fracción que el proxy NO marca (todo el partido)
    no = S[~S.proxy].sort_values("frac", ascending=False).head(CRITERIO["n_lista"])
    capt = pickle.load(open(trabajo / "cajas.pkl", "rb"))
    cap = cv2.VideoCapture(str(R / cfg["rutas"]["video"]))
    tiles, lista = [], []
    for k, r in enumerate(no.sort_values("frame").itertuples()):
        posicionar_en_frame(cap, int(r.frame))
        ok, img = cap.read()
        x1, y1, x2, y2 = (
            int(round(v)) for v in capt["cache_filtrado"][r.frame][r.caja][2:6]
        )
        m = max(40, y2 - y1)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        rec = img[max(cy - m, 0) : cy + m, max(cx - m, 0) : cx + m].copy()  # noqa: E203
        cv2.rectangle(
            rec,
            (x1 - max(cx - m, 0), y1 - max(cy - m, 0)),
            (x2 - max(cx - m, 0), y2 - max(cy - m, 0)),
            (0, 0, 255),
            1,
        )
        rec = cv2.resize(rec, (200, 200))
        cv2.putText(
            rec,
            f"{k} {r.etiqueta} {r.frac:.2f}",
            (3, 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            1,
        )
        tiles.append(rec)
        t = r.frame / 29.97002997002997
        lista.append(
            {
                "n": k,
                "frame": int(r.frame),
                "archivo": _reloj(t),
                "reproductor": _reloj(t + DESFASE_REPRODUCTOR_S),
                "id": int(r.id_jugador),
                "etiqueta": r.etiqueta,
                "frac": round(r.frac, 3),
                "x_m": round(r.x_m, 1),
                "y_m": round(r.y_m, 1),
            }
        )
    cap.release()
    filas_img = [
        np.hstack(fila) for fila in np.array_split(tiles, max(1, len(tiles) // 5))
    ]
    cv2.imwrite(str(trabajo / "top20_no_arbitro.jpg"), np.vstack(filas_img))
    res = {
        "criterio": CRITERIO,
        "filas_medidas": int(len(S)),
        "proxy_fuera_de_ventana": int(fuera.proxy.sum()),
        "barrido": {str(k): v for k, v in barrido.items()},
        "umbral_elegido": elegido,
        "top20_no_arbitro": lista,
    }
    (trabajo / "resultado_arbitro.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre in ("senal", "medir"):
        s = sub.add_parser(nombre)
        s.add_argument("--trabajo", required=True)
    args = ap.parse_args()
    senal(args) if args.cmd == "senal" else medir(args)


if __name__ == "__main__":
    main()
