#!/usr/bin/env python
"""La línea defensiva como POLIGONAL de los N defensas, y su altura media. SOLO MEDICIÓN.

Plan y reglas: docs/plan_poligonal_defensa.md. El CRITERIO se commiteó ANTES de ver números del
sistema.

    python scripts/poligonal_defensa.py oraculo               # paso 1: solo el GT
    python scripts/poligonal_defensa.py sistema --trabajo DIR # paso 2

DIR es la carpeta de `lineas_tacticas.py regenerar` (CSV de producción de hoy + lados).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

# ══════════════════════════ CRITERIO (fijado ANTES de medir) ══════════════════════════
CRITERIO = {
    "N": {"A": 4},  # parámetro de entrada: el blanco juega con 4 defensas (decide)
    "N_supuesto": {
        "B": 4
    },  # naranja: su sistema NO se conoce; se informa, sin veredicto
    "x_visible_m": 28.0,
    "altura_mediana_max_m": 1.0,
    "altura_p90_max_m": 3.0,
    "vertices_mediana_max_m": 1.5,
    "n_min": 10,
}
# ═══════════════════════════════════════════════════════════════════════════════════════
LARGO = 62.0
DEFENSAS_BLANCO_GT = {
    0,
    1,
    2,
    3,
}  # tracks del XML = id de docs/gt_identidad_benja.md − 1
LADOS = {
    "A": True,
    "B": False,
}  # defiende x = 0 (deducir_lados, comprobado con porteros)


def mas_retrasados(xs, ids, n: int, defiende_bajo: bool) -> list:
    """Los `ids` de los n jugadores más cercanos a su propia portería."""
    orden = np.argsort(np.asarray(xs, float))
    if not defiende_bajo:
        orden = orden[::-1]
    return [ids[i] for i in orden[:n]]


def poligonal(
    xs, ys, n: int, defiende_bajo: bool, crit: dict = CRITERIO
) -> dict | None:
    """Vértices (ordenados por y) de los n más retrasados y su altura media, o None si no hay n.

    `altura_m`: distancia media de esos n a su PROPIA portería. `visible`: los n en la zona
    donde se ve el campo entero (x ≥ x_visible).
    """
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if len(xs) < n:
        return None
    idx = mas_retrasados(xs, list(range(len(xs))), n, defiende_bajo)
    vx, vy = xs[idx], ys[idx]
    orden = np.argsort(vy)
    vertices = np.c_[vx[orden], vy[orden]]
    altura = float(vx.mean()) if defiende_bajo else float(LARGO - vx.mean())
    return {"vertices": vertices, "altura_m": altura,
            "visible": bool(vx.min() >= crit["x_visible_m"])}  # fmt: skip


def veredicto(err_altura, err_vertices, crit: dict = CRITERIO) -> dict:
    ea, ev = np.abs(np.asarray(err_altura, float)), np.asarray(err_vertices, float)
    if len(ea) < crit["n_min"]:
        return {"frames": int(len(ea)), "pasa": None}
    r = {
        "frames": int(len(ea)),
        "altura_mediana": float(np.median(ea)),
        "altura_p90": float(np.percentile(ea, 90)),
        "vertices_mediana": float(np.median(ev)),
    }
    r["pasa"] = (
        r["altura_mediana"] <= crit["altura_mediana_max_m"]
        and r["altura_p90"] <= crit["altura_p90_max_m"]
        and r["vertices_mediana"] <= crit["vertices_mediana_max_m"]
    )
    return r


def _gt():
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    return gt_a_por_frame(parsear_cvat(str(R / "data/annotations/gt_benja/annotations.xml")),
                          H, 9750, 15)  # fmt: skip


def oraculo(args) -> None:
    """Paso 1: ¿la regla de los 4 más retrasados elige a los 4 defensas reales del blanco?"""
    gt = _gt()
    filas = []
    for f, obs in sorted(gt.items()):
        campo = [o for o in obs if o.team == "A"]
        ids = [o.obj_id for o in campo]
        if not DEFENSAS_BLANCO_GT <= set(ids):
            filas.append({"frame": f, "completo": False})
            continue
        xs = [o.pos[0] for o in campo]
        elegidos = set(mas_retrasados(xs, ids, 4, LADOS["A"]))
        filas.append({"frame": f, "completo": True, "coincide": elegidos == DEFENSAS_BLANCO_GT,
                      "x_media_bloque": float(np.mean(xs)),
                      "intrusos": sorted(elegidos - DEFENSAS_BLANCO_GT),
                      "fuera": sorted(DEFENSAS_BLANCO_GT - elegidos)})  # fmt: skip
    t = pd.DataFrame(filas)
    c = t[t.completo].copy()
    c["coincide"] = c.coincide.astype(
        bool
    )  # las filas incompletas la dejaban de tipo objeto
    print(f"blanco: {len(t)} frames del GT, {len(c)} con los 4 defensas anotados")
    print(
        f"la regla elige EXACTAMENTE a los 4 en {int(c.coincide.sum())} de {len(c)} "
        f"({100 * c.coincide.mean():.0f} %)"
    )
    c = c.assign(
        tercio=pd.qcut(c.x_media_bloque, 3, labels=["retrasado", "medio", "adelantado"])
    )
    for ter, g in c.groupby("tercio", observed=True):
        print(
            f"  bloque {ter:<10} (x media {g.x_media_bloque.min():.1f}-"
            f"{g.x_media_bloque.max():.1f} m): coincide {int(g.coincide.sum())}/{len(g)}"
        )
    nombres = {4: "mediocentro #10", 5: "delantero #11", 0: "central dcho #4",
               1: "central izdo #7", 2: "lateral dcho #2", 3: "lateral izdo #8"}  # fmt: skip
    fallos = c[~c.coincide]
    if len(fallos):
        print(
            "  cuando falla, se cuela:",
            pd.Series([nombres[i] for x in fallos.intrusos for i in x])
            .value_counts()
            .to_dict(),
            "· se queda fuera:",
            pd.Series([nombres[i] for x in fallos.fuera for i in x])
            .value_counts()
            .to_dict(),
        )
    print(
        "naranja: el GT solo nombra un central y un lateral (dos jugadores sin rol): NO se mide"
    )


def sistema(args) -> None:
    """Paso 2: poligonal y altura media del sistema contra las del GT (misma regla)."""
    trabajo = Path(args.trabajo)
    csv = pd.read_csv(trabajo / "posiciones.csv")
    llamadas = [
        c for c in json.loads((trabajo / "lados.json").read_text())["llamadas"] if c
    ]
    if not llamadas or tuple(llamadas[0]) != ("A", "B"):
        raise SystemExit(
            f"deducir_lados dio {llamadas}, no (A, B) como se comprobó. PARA"
        )
    gt = _gt()
    por_frame = {f: g for f, g in csv.groupby("frame")}
    resultado = {}
    for eq, n in {**CRITERIO["N"], **CRITERIO["N_supuesto"]}.items():
        ea, ev, faltan, fuera = [], [], 0, 0
        for f, obs in sorted(gt.items()):
            g = [o for o in obs if o.team == eq]
            pg = poligonal([o.pos[0] for o in g], [o.pos[1] for o in g], n, LADOS[eq])
            s = por_frame.get(f, csv.iloc[0:0])
            s = s[s.etiqueta == eq]
            ps = poligonal(s.x_m, s.y_m, n, LADOS[eq])
            if ps is None:
                faltan += 1
                continue
            if not ps["visible"]:
                fuera += 1
                continue
            if pg is None:
                continue
            ea.append(ps["altura_m"] - pg["altura_m"])
            ev += list(np.hypot(*(ps["vertices"] - pg["vertices"]).T))
        v = veredicto(ea, ev)
        v.update(sin_n_en_sistema=faltan, fuera_de_zona=fuera,
                 sesgo_altura=float(np.median(ea)) if ea else None)  # fmt: skip
        resultado[eq] = v
        tipo = "DECIDE" if eq in CRITERIO["N"] else "informativo (N supuesto)"
        print(f"{eq} (N={n}, {tipo}): {v}")
    (trabajo / "poligonal.json").write_text(json.dumps(resultado, indent=1))


def _ventana_blanco(
    csv: pd.DataFrame, segundos: float, fps: float
) -> tuple[int, int, float]:
    """La ventana desde el minuto 5 con más frames de poligonal del BLANCO visible."""
    fr, ok = [], []
    for f, g in csv.groupby("frame"):
        s = g[g.etiqueta == "A"]
        p = poligonal(s.x_m, s.y_m, CRITERIO["N"]["A"], LADOS["A"])
        fr.append(f)
        ok.append(bool(p and p["visible"]))
    fr, ok = np.array(fr), np.array(ok, float)
    paso = int(round(segundos * fps / (fr[1] - fr[0])))
    suma = np.convolve(ok, np.ones(paso), "valid") / paso
    desde_min5 = (
        fr[: len(suma)] >= 300 * fps
    )  # los minutos 0-5 son otro régimen (CLAUDE.md)
    i = int(np.argmax(np.where(desde_min5, suma, -1)))
    return int(fr[i]), int(fr[i + paso - 1]), float(suma[i])


def clip(args) -> None:
    """Paso 3: solo si el paso 2 PASÓ para el blanco. La poligonal, solo con N vértices visibles."""
    import subprocess

    import cv2

    from lineas_tacticas import (
        ADELANTO_REPRODUCTOR_S,
        FPS,
        _a_px,
        _hex_bgr,
        _texto,
        reloj,
    )
    from src.tracking_data.processor import posicionar_en_frame

    trabajo = Path(args.trabajo)
    med = json.loads((trabajo / "poligonal.json").read_text())
    if med["A"]["pasa"] is not True:
        raise SystemExit(
            f"el paso 2 no pasó para el blanco ({med['A']}): no se dibuja nada"
        )
    csv = pd.read_csv(trabajo / "posiciones.csv")
    colores = json.loads((trabajo / "posiciones_meta.json").read_text())[
        "colores_equipo"
    ]
    f0, f1, frac = _ventana_blanco(csv, args.segundos, FPS)
    print(
        f"ventana: archivo {reloj(f0 / FPS)}-{reloj(f1 / FPS)} · reproductor "
        f"{reloj(f0 / FPS + ADELANTO_REPRODUCTOR_S)}-{reloj(f1 / FPS + ADELANTO_REPRODUCTOR_S)}"
        f" · poligonal blanca visible el {100 * frac:.0f} % · SIN GT: no hay verdad aquí"
    )
    Hinv = np.linalg.inv(np.load(R / "data/calibracion_benja/homografia_benja.npy"))
    por_frame = {f: g for f, g in csv.groupby("frame")}
    marcos = np.array(sorted(por_frame))
    equipos = {
        "A": (CRITERIO["N"]["A"], ""),
        "B": (CRITERIO["N_supuesto"]["B"], ", N supuesto"),
    }
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
        g = por_frame[int(marcos[np.searchsorted(marcos, pos, side="right") - 1])]
        t = pos / FPS
        _texto(img, f"archivo {reloj(t)} | reproductor {reloj(t + ADELANTO_REPRODUCTOR_S)}",
               (20, 40))  # fmt: skip
        for k, (eq, (n, nota)) in enumerate(equipos.items()):
            col = _hex_bgr(colores.get(eq, "#ffffff"))
            s = g[g.etiqueta == eq]
            p = poligonal(s.x_m, s.y_m, n, LADOS[eq])
            y_txt = 80 + 34 * k
            if p is None or not p["visible"]:
                _texto(
                    img, f"{eq}: {n} mas retrasados NO MEDIBLES aqui", (20, y_txt), col
                )
                continue
            pts = np.array([_a_px(Hinv, x, y) for x, y in p["vertices"]], np.int32)
            cv2.polylines(img, [pts], False, col, 3, cv2.LINE_AA)
            for q in pts:
                cv2.circle(img, tuple(int(v) for v in q), 6, col, -1, cv2.LINE_AA)
            _texto(img, f"{eq}: {n} mas retrasados{nota} - altura media {p['altura_m']:.1f} m "
                        f"de su porteria", (20, y_txt), col)  # fmt: skip
        _texto(img, "'4 mas retrasados' NO es siempre la defensa: con el GT, lo es en el 37 % "
                    "de los frames (se cuela el mediocentro)", (20, img.shape[0] - 30),
               (0, 200, 255), 0.65)  # fmt: skip
        ffmpeg.stdin.write(cv2.resize(img, (1280, 720)).tobytes())
        pos += 1
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(f"✓ {args.salida} ({Path(args.salida).stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("orden", choices=["oraculo", "sistema", "clip"])
    ap.add_argument("--trabajo", default=None)
    ap.add_argument("--salida", default="outputs/poligonal_defensa_benja.mp4")
    ap.add_argument("--segundos", type=float, default=30.0)
    args = ap.parse_args()
    {"oraculo": oraculo, "sistema": sistema, "clip": clip}[args.orden](args)


if __name__ == "__main__":
    main()
