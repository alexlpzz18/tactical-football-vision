#!/usr/bin/env python
"""Intercambios de identidad entre rivales con una sola caja. Criterios en
`docs/intercambios_con_una_caja.md`. SOLO MIDE.

Uso:
    python scripts/intercambios_una_caja.py contar            # entorno normal (numpy 2)
    VENV/bin/python scripts/intercambios_una_caja.py cajas    # venv numpy 1.26 (torch en CPU)
    python scripts/intercambios_una_caja.py recortes          # hoja de recortes para mirar a ojo
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/intercambios_una_caja"
CSV_MAIN = (
    R / "outputs/staff_dentro/benja_despues.csv"
)  # main: arreglo de interpoladas + staff
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
MODELO = R / "models/weights/best_v4pre.pt"
FPS = 29.97002997002997
# definiciones (docs/intercambios_con_una_caja.md), fijadas antes de contar
DIST_MAX_M = 3.0
HUECO_MAX_FRAMES = 6  # el caché va de 3 en 3: un paso perdido como mucho
VENTANA_LEJOS_S, VENTANA_CERCA_S = 2.25, 0.75
MIN_FILAS = 3
MAX_MUESTRA, SEMILLA = 20, 30
CASO_CONTROL = {272, 291}
AMPLIAR = 0.20


def relojes(t: float) -> str:
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} archivo · {int(r // 60)}:{r % 60:04.1f} reproductor"


def equipo(et) -> str | None:
    et = str(et)
    return (
        "A" if et in ("A", "portero_A") else ("B" if et in ("B", "portero_B") else None)
    )


def _mayoria(etiquetas) -> str | None:
    eqs = [e for e in (equipo(x) for x in etiquetas) if e]
    if len(eqs) < MIN_FILAS:
        return None
    a = eqs.count("A")
    if a * 2 == len(eqs):
        return None
    return "A" if a * 2 > len(eqs) else "B"


def contar() -> dict:
    import pandas as pd

    df = pd.read_csv(CSV_MAIN)
    por_frame = {f: g for f, g in df.groupby("frame")}
    # 1. frames «dos personas, una caja»: i real, j interpolada a ≤ 3 m
    marcas: dict[tuple, list] = {}
    for f, g in por_frame.items():
        reales, interp = g[g.es_real == 1], g[g.es_real == 0]
        if not len(interp) or not len(reales):
            continue
        xr, yr = reales.x_m.to_numpy(), reales.y_m.to_numpy()
        for j, xj, yj in zip(interp.id_jugador, interp.x_m, interp.y_m):
            d = np.hypot(xr - xj, yr - yj)
            for k in np.where(d <= DIST_MAX_M)[0]:
                i = int(reales.id_jugador.iloc[k])
                marcas.setdefault((i, int(j)), []).append(int(f))
    # 2. episodios: frames seguidos por pareja (i con caja, j sin caja)
    episodios = []
    for (i, j), fs in marcas.items():
        fs = sorted(fs)
        ini = prev = fs[0]
        for f in fs[1:] + [None]:
            if f is None or f - prev > HUECO_MAX_FRAMES:
                episodios.append((i, j, ini, prev))
                if f is not None:
                    ini = f
            if f is not None:
                prev = f
    # 3. rivales e intercambio
    reales = df[df.es_real == 1]
    por_id = {i: g.sort_values("tiempo_s") for i, g in reales.groupby("id_jugador")}

    def mayoria(i, t0, t1):
        g = por_id.get(i)
        if g is None:
            return None
        return _mayoria(g.etiqueta[(g.tiempo_s >= t0) & (g.tiempo_s <= t1)])

    filas, vistos = [], set()
    for i, j, f0, f1 in episodios:
        s, e = f0 / FPS, f1 / FPS
        clave = (min(i, j), max(i, j), round(s, 1))
        if clave in vistos:
            continue
        vistos.add(clave)
        ai = mayoria(i, s - VENTANA_LEJOS_S, s - VENTANA_CERCA_S)
        aj = mayoria(j, s - VENTANA_LEJOS_S, s - VENTANA_CERCA_S)
        if ai is None or aj is None or ai == aj:
            continue  # no son rivales (o no hay con qué saberlo)
        di = mayoria(i, e + VENTANA_CERCA_S, e + VENTANA_LEJOS_S)
        dj = mayoria(j, e + VENTANA_CERCA_S, e + VENTANA_LEJOS_S)
        filas.append(
            {
                "con_caja": i,
                "sin_caja": j,
                "frame_ini": f0,
                "frame_fin": f1,
                "t_ini": round(s, 2),
                "dura_s": round(e - s, 2),
                "relojes": relojes(s),
                "antes": f"{ai}/{aj}",
                "despues": f"{di}/{dj}",
                "intercambio": bool(di == aj and dj == ai),
                "sin_dato_despues": di is None or dj is None,
            }
        )
    ep = pd.DataFrame(filas).sort_values("t_ini")
    SALIDA.mkdir(parents=True, exist_ok=True)
    ep.to_csv(SALIDA / "episodios_rivales.csv", index=False)
    inter = ep[ep.intercambio]
    control = bool(
        any(
            {r.con_caja, r.sin_caja} == CASO_CONTROL and 309 < r.t_ini < 313
            for r in inter.itertuples()
        )
    )
    res = {
        "episodios_una_caja_entre_rivales": len(ep),
        "con_intercambio": len(inter),
        "sin_dato_despues": int(ep.sin_dato_despues.sum()),
        "tasa_intercambio_pct": round(
            100 * len(inter) / max(1, len(ep) - ep.sin_dato_despues.sum()), 1
        ),
        "control_5_11_contado": control,
        "intercambios": inter[
            ["relojes", "con_caja", "sin_caja", "dura_s", "antes", "despues"]
        ].to_dict("records"),
    }
    json.dump(res, open(SALIDA / "contar.json", "w"), indent=1, ensure_ascii=False)
    return res


def _muestra():
    import pandas as pd

    ep = pd.read_csv(SALIDA / "episodios_rivales.csv")
    inter = ep[ep.intercambio].reset_index(drop=True)
    if len(inter) > MAX_MUESTRA:
        control = inter[
            [{a, b} == CASO_CONTROL for a, b in zip(inter.con_caja, inter.sin_caja)]
        ]
        resto = inter.drop(control.index).sample(
            MAX_MUESTRA - len(control), random_state=SEMILLA
        )
        inter = pd.concat([control, resto]).sort_values("t_ini")
    cap = pickle.load(open(CAPTURA, "rb"))
    casos = []
    for r in inter.itertuples():
        # el frame del centro del episodio en que la identidad con caja TIENE observación real
        dets = dict(cap["identidades"][int(r.con_caja) - 1])
        fs = [f for f in dets if r.frame_ini <= f <= r.frame_fin]
        if not fs:
            continue
        f = sorted(fs)[len(fs) // 2]
        casos.append({"relojes": r.relojes, "frame": int(f), "con_caja": int(r.con_caja),
                      "sin_caja": int(r.sin_caja), "det": int(dets[f])})  # fmt: skip
    return casos


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def cajas() -> dict:
    """Detección en CPU de los frames de la muestra: producción y sin fusión (como el 28-oct)."""
    import yaml
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    casos = _muestra()
    cfg = yaml.safe_load(open(CONFIG))
    det = cfg["deteccion"]
    modelo = AutoDetectionModel.from_pretrained(
        model_type="ultralytics", model_path=str(MODELO),
        confidence_threshold=det["confianza"], device="cpu",
    )  # fmt: skip
    pp = {
        "produccion": dict(postprocess_type="GREEDYNMM", postprocess_match_metric="IOS",
                           postprocess_match_threshold=0.5),
        "sin_fusion": dict(postprocess_type="NMS", postprocess_match_metric="IOU",
                           postprocess_match_threshold=0.99),
    }  # fmt: skip
    cap = pickle.load(open(CAPTURA, "rb"))
    filtrado = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    crudo = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(open(R / cfg["rutas"]["cache"], "rb"))["cache"]
    }
    por_frame = {c["frame"]: c for c in casos}
    for f, img in leer_frames_ffmpeg(R / cfg["rutas"]["video"], sorted(por_frame)):
        h, w = img.shape[:2]
        salidas = {}
        for nombre, p in pp.items():
            r = get_sliced_prediction(
                img, modelo,
                slice_height=h // det["sahi"]["filas"], slice_width=w // det["sahi"]["columnas"],
                overlap_height_ratio=det["sahi"]["solape"],
                overlap_width_ratio=det["sahi"]["solape"],
                verbose=0, **p,
            )  # fmt: skip
            salidas[nombre] = [
                [b.minx, b.miny, b.maxx, b.maxy, float(q.score.value)]
                for q in r.object_prediction_list
                for b in [q.bbox]
                if q.score.value >= det["confianza"]
                and (b.maxx - b.minx) * (b.maxy - b.miny)
                <= det["max_area_caja"] * w * h
            ]
        c = por_frame[f]
        caja = [float(v) for v in filtrado[f][c["det"]][2:6]]
        cw, ch = caja[2] - caja[0], caja[3] - caja[1]
        ampl = [
            caja[0] - AMPLIAR * cw,
            caja[1] - AMPLIAR * ch,
            caja[2] + AMPLIAR * cw,
            caja[3] + AMPLIAR * ch,
        ]

        def dentro(b):
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            return ampl[0] <= cx <= ampl[2] and ampl[1] <= cy <= ampl[3]

        cach = [list(d[2:7]) for d in crudo[f]]
        casadas = sum(
            any(iou(x, p) >= 0.9 for p in salidas["produccion"]) for x in cach
        )
        c.update(
            caja_produccion=caja,
            control=f"{casadas}/{len(cach)}",
            control_ok=casadas >= 0.95 * len(cach),
            produccion_en_la_region=[b for b in salidas["produccion"] if dentro(b)],
            sin_fusion_en_la_region=[b for b in salidas["sin_fusion"] if dentro(b)],
        )
        c["propuesta_automatica"] = len(c["sin_fusion_en_la_region"])
        print(c["relojes"], c["control"], c["propuesta_automatica"], flush=True)
    json.dump(casos, open(SALIDA / "cajas.json", "w"), indent=1, ensure_ascii=False)
    return {"casos": len(casos), "control_ok": all(c.get("control_ok") for c in casos)}


def recortes() -> str:
    """Hoja con un recorte por caso: verde = producción, rojo = sin fusión (para mirarlo a ojo)."""
    import base64
    import subprocess

    casos = json.load(open(SALIDA / "cajas.json"))
    tarjetas = []
    for n, c in enumerate(casos):
        x0, y0, x1, y1 = c["caja_produccion"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        lado = max(160, 2.2 * (y1 - y0))
        filtros = (
            [
                f"drawbox=x={b[0]:.0f}:y={b[1]:.0f}:w={b[2] - b[0]:.0f}:h={b[3] - b[1]:.0f}"
                ":color=red:t=1"
                for b in c["sin_fusion_en_la_region"]
            ]
            + [  # TODAS las cajas de producción de la región, en azul (no solo la de la fila)
                f"drawbox=x={b[0] - 1:.0f}:y={b[1] - 1:.0f}:w={b[2] - b[0] + 2:.0f}"
                f":h={b[3] - b[1] + 2:.0f}:color=blue:t=1"
                for b in c["produccion_en_la_region"]
            ]
            + [
                f"drawbox=x={x0 - 3:.0f}:y={y0 - 3:.0f}:w={x1 - x0 + 6:.0f}:h={y1 - y0 + 6:.0f}"
                ":color=lime:t=1"
            ]
        )
        filtros.append(
            f"crop={lado:.0f}:{lado:.0f}:{max(0, cx - lado / 2):.0f}:{max(0, cy - lado / 2):.0f}"
            ",scale=640:-2"
        )
        jpg = SALIDA / f"caso_{n}.jpg"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{c['frame'] / FPS:.3f}",
             "-i", str(R / "data/raw/benja_gredos_p1_20min.mp4"), "-frames:v", "1",
             "-vf", ",".join(filtros), str(jpg)],
            check=True,
        )  # fmt: skip
        b64 = base64.b64encode(jpg.read_bytes()).decode()
        tarjetas.append(
            f'<div><img src="data:image/jpeg;base64,{b64}"><p>{n} · {c["relojes"]} · '
            f'ids {c["con_caja"]}/{c["sin_caja"]} · rojas: {c["propuesta_automatica"]}</p></div>'
        )
    html = SALIDA / "recortes.html"
    html.write_text(
        "<!doctype html><meta charset=utf-8><title>Intercambios con una caja</title>"
        "<style>body{background:#111;color:#eee;font:13px system-ui}"
        "div{display:inline-block;margin:6px;width:640px}</style>"
        "<p>verde = caja de la fila · azul = todas las de producción · rojo = sin fusión</p>"
        + "".join(tarjetas)
    )
    return str(html)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["contar", "cajas", "recortes"])
    args = ap.parse_args()
    out = {"contar": contar, "cajas": cajas, "recortes": recortes}[args.accion]()
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
