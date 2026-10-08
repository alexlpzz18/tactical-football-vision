#!/usr/bin/env python
"""Líneas tácticas (defensa, presión, distancia, anchura) sobre el vídeo REAL del benjamín.

Plan y reglas: docs/plan_lineas_tacticas.md. El CRITERIO se commiteó ANTES de ver números del
sistema. Solo local: lee la salida de producción, no la cambia.

Tres órdenes:
    python scripts/lineas_tacticas.py regenerar --trabajo DIR   # CSV de producción HOY + lados
    python scripts/lineas_tacticas.py medir --trabajo DIR       # contra el GT de 14
    python scripts/lineas_tacticas.py clip --trabajo DIR --salida outputs/lineas_tacticas.mp4
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

# ══════════════════════════ CRITERIO (fijado ANTES de medir) ══════════════════════════
CRITERIO = {
    "x_visible_m": 28.0,  # desde aquí la cámara ve el campo entero (desglose_por_episodios)
    "min_jugadores": 3,  # jugadores de campo mínimos para calcular una línea
    "mediana_max_m": 2.0,  # "enseñable": mediana del error ≤ esto…
    "p90_max_m": 5.0,  # …y p90 ≤ esto…
    "n_min": 10,  # …con al menos estos pares (frame, equipo); si no, NO CONCLUYENTE
    "radio_casado_m": 2.0,  # para decidir qué equipo del sistema es cuál del GT
}
# ═══════════════════════════════════════════════════════════════════════════════════════
LARGO, ANCHO = 62.0, 40.0
FPS = 30000 / 1001
ADELANTO_REPRODUCTOR_S = 93  # el reproductor de Alex va 1:33 por delante del archivo
METRICAS = ("defensa", "presion", "distancia", "anchura")


def lineas_equipo(xs, ys, defiende_bajo: bool, crit: dict = CRITERIO) -> dict | None:
    """Las líneas de un equipo (solo jugadores de campo), o None si hay menos del mínimo.

    `defiende_bajo`: el equipo defiende la portería x = 0. `medible`: el bloque está ENTERO en la
    zona donde se ve todo el campo (x mínima ≥ x_visible); la anchura vale siempre.
    """
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if len(xs) < crit["min_jugadores"]:
        return None
    defensa, presion = (xs.min(), xs.max()) if defiende_bajo else (xs.max(), xs.min())
    return {
        "defensa": float(defensa),
        "presion": float(presion),
        "distancia": float(abs(presion - defensa)),
        "anchura": float(ys.max() - ys.min()),
        "y_min": float(ys.min()),
        "y_max": float(ys.max()),
        "x_media": float(xs.mean()),
        "medible": bool(xs.min() >= crit["x_visible_m"]),
    }


def veredicto_metrica(errores, crit: dict = CRITERIO) -> dict:
    e = np.abs(np.asarray(errores, float))
    if len(e) < crit["n_min"]:
        return {"n": int(len(e)), "ensenable": None}
    med, p90 = float(np.median(e)), float(np.percentile(e, 90))
    return {"n": int(len(e)), "mediana": med, "p90": p90,
            "ensenable": med <= crit["mediana_max_m"] and p90 <= crit["p90_max_m"]}  # fmt: skip


def reloj(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


# ──────────────────────────────── regenerar ────────────────────────────────
def regenerar(args) -> None:
    """La pasada de producción desde el caché (código de HOY), capturando `deducir_lados`."""
    import yaml

    import src.team_classification.pipeline_equipos as pe
    from src.tracking_data.processor import procesar_desde_cache

    trabajo = Path(args.trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(trabajo / "posiciones.csv")
    cfg["rutas"]["salida_meta"] = str(trabajo / "posiciones_meta.json")
    capturas = []
    original = pe.deducir_lados

    def espia(*a, **k):
        r = original(*a, **k)
        capturas.append(r)
        return r

    pe.deducir_lados = espia
    try:
        procesar_desde_cache(cfg)
    finally:
        pe.deducir_lados = original
    (trabajo / "lados.json").write_text(json.dumps({"llamadas": capturas}))
    print(f"✓ CSV de producción en {trabajo}; deducir_lados devolvió {capturas}")


def _lados(trabajo: Path, csv: pd.DataFrame) -> dict:
    """{equipo: defiende_bajo} desde deducir_lados, COMPROBADO con los porteros."""
    llamadas = [
        c for c in json.loads((trabajo / "lados.json").read_text())["llamadas"] if c
    ]
    if not llamadas or len({tuple(c) for c in llamadas}) != 1:
        raise SystemExit(f"deducir_lados no dio una respuesta única: {llamadas}. PARA")
    bajo, alto = llamadas[0]
    for eq, esperado in ((bajo, "bajo"), (alto, "alto")):
        p = csv[csv.etiqueta == f"portero_{eq}"]
        if len(p) == 0:
            print(
                f"⚠️ no hay filas de portero_{eq}: el lado no se puede comprobar con él"
            )
            continue
        x = float(p.x_m.median())
        real = "bajo" if x < LARGO / 2 else "alto"
        print(
            f"portero_{eq}: x mediana {x:.1f} m → defiende la portería {real} "
            f"({'coincide' if real == esperado else 'NO COINCIDE'} con deducir_lados)"
        )
        if real != esperado:
            raise SystemExit("deducir_lados y los porteros no coinciden. PARA")
    return {bajo: True, alto: False}


def _de_campo(filas: pd.DataFrame, equipo: str) -> pd.DataFrame:
    return filas[filas.etiqueta == equipo]  # A/B: sin porteros, otro ni staff


# ──────────────────────────────── medir ────────────────────────────────
def medir(args) -> None:
    from scipy.optimize import linear_sum_assignment

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    trabajo = Path(args.trabajo)
    csv = pd.read_csv(trabajo / "posiciones.csv")
    lados = _lados(trabajo, csv)
    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    gt = gt_a_por_frame(parsear_cvat(str(R / "data/annotations/gt_benja/annotations.xml")),
                        H, 9750, 15)  # fmt: skip
    por_frame = {f: g for f, g in csv.groupby("frame")}

    # qué equipo del sistema es cuál del GT: el casado 1-a-1 a 2 m
    acuerdo = {"directo": 0, "cruzado": 0}
    for f, obs in gt.items():
        sub = por_frame.get(f)
        gente = [o for o in obs if o.team in ("A", "B")]
        if sub is None or not gente:
            continue
        sub = sub[sub.etiqueta.isin(["A", "B"])]
        gx = np.array([o.pos[0] for o in gente])[:, None]
        gy = np.array([o.pos[1] for o in gente])[:, None]
        c = np.hypot(sub.x_m.values[None] - gx, sub.y_m.values[None] - gy)
        c = np.where(c > CRITERIO["radio_casado_m"], 1e6, c)
        for i, j in zip(*linear_sum_assignment(c)):
            if c[i, j] < 1e6:
                igual = gente[i].team == sub.etiqueta.values[j]
                acuerdo["directo" if igual else "cruzado"] += 1
    a_gt = (
        {"A": "A", "B": "B"}
        if acuerdo["directo"] >= acuerdo["cruzado"]
        else {"A": "B", "B": "A"}
    )
    print(f"equipos sistema→GT: {a_gt} (casado: {acuerdo})")
    print(f"sentido (deducir_lados, sistema): {lados}")

    err = {m: [] for m in METRICAS}
    zona = {
        "ambos_medible": 0,
        "solo_gt": 0,
        "solo_sistema": 0,
        "ninguno": 0,
        "sin_sistema": 0,
    }
    for f, obs in sorted(gt.items()):
        sub = por_frame.get(f, csv.iloc[0:0])
        for eq_s, eq_g in a_gt.items():
            g = [o for o in obs if o.team == eq_g]
            lg = lineas_equipo(
                [o.pos[0] for o in g], [o.pos[1] for o in g], lados[eq_s]
            )
            s = _de_campo(sub, eq_s)
            ls = lineas_equipo(s.x_m, s.y_m, lados[eq_s])
            if lg is None:
                continue
            if ls is None:
                zona["sin_sistema"] += 1
                continue
            err["anchura"].append(ls["anchura"] - lg["anchura"])  # la anchura, siempre
            clave = {(True, True): "ambos_medible", (True, False): "solo_gt",
                     (False, True): "solo_sistema", (False, False): "ninguno"}  # fmt: skip
            zona[clave[(lg["medible"], ls["medible"])]] += 1
            if lg["medible"]:  # las líneas, solo donde la VERDAD está en zona visible
                for m in ("defensa", "presion", "distancia"):
                    err[m].append(ls[m] - lg[m])
    res = {m: veredicto_metrica(e) for m, e in err.items()}
    for m, v in res.items():
        sesgo = float(np.median(err[m])) if err[m] else float("nan")
        print(f"{m:<10} {v} · sesgo (mediana con signo) {sesgo:+.2f} m")
    print(f"zona visible (GT vs sistema), por (frame, equipo): {zona}")
    (trabajo / "medicion.json").write_text(json.dumps(
        {"criterio": CRITERIO, "equipos": a_gt, "lados": lados, "resultado": res,
         "zona": zona, "errores": err}, indent=1))  # fmt: skip


# ──────────────────────────────── clip ────────────────────────────────
def _ventana(csv: pd.DataFrame, lados: dict, segundos: float) -> tuple[int, int, float]:
    """La ventana de `segundos` con más frames en que LOS DOS bloques son medibles."""
    marcos = sorted(csv.frame.unique())
    ok = []
    for f, g in csv.groupby("frame"):
        lin = [
            lineas_equipo(_de_campo(g, e).x_m, _de_campo(g, e).y_m, b)
            for e, b in lados.items()
        ]
        ok.append(all(x is not None and x["medible"] for x in lin))
    ok = np.array(ok, float)
    paso = int(round(segundos * FPS / (marcos[1] - marcos[0])))
    suma = np.convolve(ok, np.ones(paso), "valid")
    i = int(np.argmax(suma))
    return int(marcos[i]), int(marcos[i + paso - 1]), float(suma[i] / paso)


def _a_px(Hinv, x, y):
    p = Hinv @ np.array([x, y, 1.0])
    return (float(p[0] / p[2]), float(p[1] / p[2]))


def _hex_bgr(h: str) -> tuple:
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def _texto(img, s, org, color=(255, 255, 255), escala=0.7):
    import cv2

    cv2.putText(
        img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), 4, cv2.LINE_AA
    )
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, color, 2, cv2.LINE_AA)


def dibujar(img, g: pd.DataFrame, lados: dict, colores: dict, Hinv, frame: int) -> None:
    """Las líneas de los dos equipos sobre el fotograma (en su sitio, desde metros)."""
    import cv2

    t = frame / FPS
    _texto(
        img,
        f"archivo {reloj(t)} | reproductor {reloj(t + ADELANTO_REPRODUCTOR_S)}",
        (20, 40),
    )
    for k, (eq, bajo) in enumerate(lados.items()):
        col = _hex_bgr(colores.get(eq, "#ffffff"))
        s = _de_campo(g, eq)
        lin = lineas_equipo(s.x_m, s.y_m, bajo)
        y_txt = 80 + 34 * k
        if lin is None:
            _texto(
                img,
                f"{eq}: menos de {CRITERIO['min_jugadores']} jugadores",
                (20, y_txt),
                col,
            )
            continue
        # anchura: siempre (no depende del encuadre)
        a, b = _a_px(Hinv, lin["x_media"], lin["y_min"]), _a_px(
            Hinv, lin["x_media"], lin["y_max"]
        )
        cv2.line(img, tuple(map(int, a)), tuple(map(int, b)), col, 2, cv2.LINE_AA)
        if not lin["medible"]:
            _texto(img, f"{eq}: anchura {lin['anchura']:.1f} m · lineas NO MEDIBLES "
                        f"(bloque fuera de la zona visible)", (20, y_txt), col)  # fmt: skip
            continue
        for x in (lin["defensa"], lin["presion"]):
            p0, p1 = _a_px(Hinv, x, 0.0), _a_px(Hinv, x, ANCHO)
            cv2.line(img, tuple(map(int, p0)), tuple(map(int, p1)), col, 3, cv2.LINE_AA)
        _texto(img, f"{eq}: defensa-presion {lin['distancia']:.1f} m · anchura "
                    f"{lin['anchura']:.1f} m", (20, y_txt), col)  # fmt: skip


def clip(args) -> None:
    import cv2

    from src.tracking_data.processor import posicionar_en_frame

    trabajo = Path(args.trabajo)
    csv = pd.read_csv(trabajo / "posiciones.csv")
    lados = _lados(trabajo, csv)
    colores = json.loads((trabajo / "posiciones_meta.json").read_text())[
        "colores_equipo"
    ]
    f0, f1, frac = _ventana(csv, lados, args.segundos)
    t0 = f0 / FPS
    print(
        f"ventana: frames {f0}-{f1} · archivo {reloj(t0)}-{reloj(f1 / FPS)} · reproductor "
        f"{reloj(t0 + ADELANTO_REPRODUCTOR_S)}-{reloj(f1 / FPS + ADELANTO_REPRODUCTOR_S)} · "
        f"los dos bloques medibles en el {100 * frac:.0f} % · SIN GT: no hay verdad aquí"
    )
    Hinv = np.linalg.inv(np.load(R / "data/calibracion_benja/homografia_benja.npy"))
    por_frame = {f: g for f, g in csv.groupby("frame")}
    marcos = np.array(sorted(por_frame))
    cap = cv2.VideoCapture(str(R / "data/raw/benja_gredos_p1_20min.mp4"))
    pos = posicionar_en_frame(cap, f0)
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", "1280x720", "-r", f"{FPS}", "-i", "-", "-c:v", "libx264", "-crf", "24",
         "-preset", "medium", "-pix_fmt", "yuv420p", args.salida],
        stdin=subprocess.PIPE,
    )  # fmt: skip
    while pos <= f1:
        ok, img = cap.read()
        if not ok:
            break
        # el CSV va a 1 de cada 3 frames: se usa la fila más cercana hacia atrás
        fc = int(marcos[np.searchsorted(marcos, pos, side="right") - 1])
        dibujar(img, por_frame[fc], lados, colores, Hinv, pos)
        ffmpeg.stdin.write(cv2.resize(img, (1280, 720)).tobytes())
        pos += 1
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(f"✓ {args.salida} ({Path(args.salida).stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("orden", choices=["regenerar", "medir", "clip"])
    ap.add_argument("--trabajo", required=True)
    ap.add_argument("--salida", default="outputs/lineas_tacticas.mp4")
    ap.add_argument("--segundos", type=float, default=30.0)
    args = ap.parse_args()
    {"regenerar": regenerar, "medir": medir, "clip": clip}[args.orden](args)


if __name__ == "__main__":
    main()
