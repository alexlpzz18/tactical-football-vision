#!/usr/bin/env python
"""Diagnóstico 23-oct (e), bloques 2 y 3: candidatas de balón y recall de los detectores por zona.

Criterios en `docs/diagnostico_23oct_e.md`. Solo medición: producción no se toca.

Uso:
    python scripts/diag23e.py candidatas --salida outputs/diagnostico_23oct_e   # 2a: hojas
    python scripts/diag23e.py regla --salida outputs/diagnostico_23oct_e        # 2a: separación
    python scripts/diag23e.py recall --salida outputs/diagnostico_23oct_e       # 3: jugadores
    python scripts/diag23e.py paneles_balon --salida outputs/diagnostico_23oct_e  # 3: balón
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
FPS = 29.97002997002997
VIDEO_BENJA = R / "data/raw/benja_gredos_p1_20min.mp4"
CACHE_BALON_TRAMO = (
    R / "data/tracking_benja/cache_balon_piloto.pkl"
)  # 5 min desde el min 5
CACHE_BALON_P1 = R / "data/tracking_benja/cache_balon_p1.pkl"  # la parte entera
TRAMO_S = (300.0, 360.0)  # el tramo de 60 s del benjamín (minuto 5)
TRAMO_CONTROL_S = (840.0, 960.0)  # minutos 14-16: contiene f27048 (campo de al lado)
LARGO, ANCHO = 62.0, 40.0
CLASES = ("campo_al_lado", "balon_real", "otro")


def relojes(frame: int) -> str:
    """Los dos relojes: archivo y reproductor de Alex (+1:33)."""
    t = frame / FPS
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int(r // 60)}:{r % 60:04.1f} repr"


def fuera_m(mx: float, my: float) -> float:
    """Metros fuera del campo de la proyección (0 si cae dentro)."""
    dx = max(0.0, -mx, mx - LARGO)
    dy = max(0.0, -my, my - ANCHO)
    return float(np.hypot(dx, dy))


# ── 2a: todas las candidatas y la hoja para etiquetarlas a ojo ────────────────────────────────


def todas_las_candidatas(cache_ruta: Path, tramo_s: tuple[float, float]) -> list[dict]:
    """Una fila por candidata de balón del detector en el tramo (conf ≥ 0,35, la de la caché)."""
    datos = pickle.load(open(cache_ruta, "rb"))
    filas = []
    for e in datos["cache"]:
        if not tramo_s[0] <= e["frame_idx"] / FPS < tramo_s[1]:
            continue
        for k, d in enumerate(e["dets"]):
            mx, my, x1, y1, x2, y2, conf = (float(v) for v in d)
            filas.append(
                {
                    "frame": int(e["frame_idx"]),
                    "k": k,
                    "n_candidatas": len(e["dets"]),
                    "x1": round(x1, 1),
                    "y1": round(y1, 1),
                    "x2": round(x2, 1),
                    "y2": round(y2, 1),
                    "cx": round((x1 + x2) / 2, 1),
                    "cy": round((y1 + y2) / 2, 1),
                    "ancho_px": round(x2 - x1, 1),
                    "alto_px": round(y2 - y1, 1),
                    "conf": round(conf, 3),
                    "mx": round(mx, 2),
                    "my": round(my, 2),
                    "fuera_m": round(fuera_m(mx, my), 2),
                }
            )
    return filas


def hoja(nombre: str, elegidas: list[dict], salida: Path) -> list[dict]:
    """Hoja de recortes: zoom de cada candidata + miniatura con su sitio en el fotograma."""
    import cv2

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    carpeta = salida / f"hoja_{nombre}"
    carpeta.mkdir(parents=True, exist_ok=True)
    por_frame: dict[int, list] = {}
    for n, c in enumerate(elegidas):
        c["id"] = f"{nombre[0].upper()}{n:02d}"
        por_frame.setdefault(c["frame"], []).append(c)
    fichas = {}
    for f, img in leer_frames_ffmpeg(VIDEO_BENJA, sorted(por_frame)):
        h, w = img.shape[:2]
        for c in por_frame[f]:
            cx, cy = int(c["cx"]), int(c["cy"])
            r = 60
            x0, y0 = max(0, cx - r), max(0, cy - r)
            y1, x1 = min(h, cy + r), min(w, cx + r)
            zoom = img[y0:y1, x0:x1].copy()
            cv2.rectangle(
                zoom,
                (int(c["x1"]) - x0 - 2, int(c["y1"]) - y0 - 2),
                (int(c["x2"]) - x0 + 2, int(c["y2"]) - y0 + 2),
                (0, 0, 255),
                1,
            )
            zoom = cv2.resize(zoom, (240, 240), interpolation=cv2.INTER_NEAREST)
            mini = cv2.resize(img, (427, 240))
            cv2.circle(mini, (int(cx * 427 / w), int(cy * 240 / h)), 9, (0, 0, 255), 2)
            ficha = np.hstack([zoom, mini])
            cv2.putText(
                ficha,
                f"{c['id']}  f{f}  conf {c['conf']:.2f}  fuera {c['fuera_m']:.0f} m",
                (4, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                1,
            )
            fichas[c["id"]] = ficha
    ids = [c["id"] for c in elegidas]
    paginas = []
    for p in range(0, len(ids), 8):
        bloque = [fichas[i] for i in ids[p:][:8]]
        while len(bloque) < 8:
            bloque.append(np.zeros_like(bloque[0]))
        filas = [np.hstack(bloque[i:][:2]) for i in range(0, 8, 2)]
        ruta = carpeta / f"pagina_{p // 8:02d}.jpg"
        cv2.imwrite(str(ruta), np.vstack(filas), [cv2.IMWRITE_JPEG_QUALITY, 90])
        paginas.append(ruta.name)
    (carpeta / "candidatas.json").write_text(json.dumps(elegidas, indent=1))
    return paginas


def candidatas(salida: Path) -> dict:
    """Las candidatas de los dos tramos y sus hojas (para etiquetar a ojo).

    Caché de PRODUCCIÓN (`cache_balon_p1`, la de los 30 paneles del 22-oct). La selección para la
    hoja NO mira la posición: son las candidatas de los frames con DOS O MÁS candidatas (cuando hay
    dos balones a la vez, suele ser uno de cada campo). Elegirlas por región haría que luego la
    región las separara por construcción.
    """
    import pandas as pd

    res = {}
    for nombre, tramo, tope in (
        ("tramo", TRAMO_S, 64),
        ("control", TRAMO_CONTROL_S, 40),
    ):
        df = pd.DataFrame(todas_las_candidatas(CACHE_BALON_P1, tramo))
        df.to_csv(salida / f"candidatas_{nombre}.csv", index=False)
        varias = df[df.n_candidatas >= 2]
        rng = np.random.default_rng(0)
        if len(varias) > tope:
            varias = varias.iloc[np.sort(rng.choice(len(varias), tope, replace=False))]
        paginas = hoja(
            nombre, varias.sort_values(["frame", "k"]).to_dict("records"), salida
        )
        res[nombre] = {
            "tramo_s": tramo,
            "frames_con_candidatas": int(df.frame.nunique()),
            "candidatas": len(df),
            "frames_con_2_o_mas": int(df[df.n_candidatas >= 2].frame.nunique()),
            "en_la_hoja": len(varias),
            "paginas": paginas,
        }
    # la otra pasada del detector, para comparar: ¿tiene las candidatas del campo de al lado?
    piloto = pd.DataFrame(todas_las_candidatas(CACHE_BALON_TRAMO, TRAMO_S))
    piloto.to_csv(salida / "candidatas_tramo_piloto.csv", index=False)
    res["piloto_mismo_tramo"] = {
        "candidatas": len(piloto),
        "frames_con_2_o_mas": int(piloto[piloto.n_candidatas >= 2].frame.nunique()),
    }
    return res


def segunda_tanda(salida: Path) -> dict:
    """Otra muestra con la MISMA selección (frames con ≥ 2 candidatas, semilla 1), sin repetir."""
    import pandas as pd

    res = {}
    for nombre, tope in (("tramo", 64), ("control", 40)):
        df = pd.read_csv(salida / f"candidatas_{nombre}.csv")
        ya = pd.DataFrame(
            json.loads((salida / f"hoja_{nombre}/candidatas.json").read_text())
        )
        varias = df[df.n_candidatas >= 2].merge(
            ya[["frame", "k"]], on=["frame", "k"], how="left", indicator=True
        )
        varias = varias[varias["_merge"] == "left_only"].drop(columns="_merge")
        rng = np.random.default_rng(1)
        if len(varias) > tope:
            varias = varias.iloc[np.sort(rng.choice(len(varias), tope, replace=False))]
        res[nombre] = hoja(
            f"{nombre}_b", varias.sort_values(["frame", "k"]).to_dict("records"), salida
        )
    return res


# La regla en píxeles, fijada en el tramo de 60 s como el CENTRO de su meseta (cx 490-1390,
# cy 566-640): una candidata está en el campo de al lado si cae a la izquierda y por encima.
REGLA_PX = {"cx_max": 940.0, "cy_max": 603.0}


def en_campo_al_lado(cx: float, cy: float) -> bool:
    return cx < REGLA_PX["cx_max"] and cy < REGLA_PX["cy_max"]


def hoja_control_regla(salida: Path) -> dict:
    """Control: TODAS las candidatas del tramo de control que la regla deja fuera (hasta 24, al
    azar) más 24 al azar que deja dentro, para etiquetarlas sin mirar qué dice la regla.
    """
    import pandas as pd

    df = pd.read_csv(salida / "candidatas_control.csv")
    fuera = df[[en_campo_al_lado(x, y) for x, y in zip(df.cx, df.cy)]]
    dentro = df.drop(fuera.index)
    rng = np.random.default_rng(2)
    elegir = [
        fuera.iloc[np.sort(rng.choice(len(fuera), min(24, len(fuera)), replace=False))],
        dentro.iloc[np.sort(rng.choice(len(dentro), 24, replace=False))],
    ]
    muestra = pd.concat(elegir).sample(
        frac=1, random_state=3
    )  # barajadas: no se ve cuál es cuál
    paginas = hoja("control_regla", muestra.to_dict("records"), salida)
    return {"fuera_por_la_regla": len(fuera), "dentro": len(dentro), "paginas": paginas}


def regla(salida: Path) -> dict:
    """2a: ¿separa la regla en píxeles? Ajuste en el tramo, control en otro tramo SIN reajustar."""
    import cv2
    import pandas as pd

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    E = json.loads((R / "docs/etiquetas_balon_23oct_e.json").read_text())

    def carga(hojas):
        partes = []
        for h in hojas:
            c = pd.DataFrame(
                json.loads((salida / f"hoja_{h}/candidatas.json").read_text())
            )
            c["clase"] = c.id.map(E[h])
            c["hoja"] = h
            partes.append(c[c.clase.notna()])
        d = pd.concat(partes)
        d["fuera_por_la_regla"] = [en_campo_al_lado(x, y) for x, y in zip(d.cx, d.cy)]
        return d

    def tasas(d):
        al, re = d[d.clase == "campo_al_lado"], d[d.clase == "balon_real"]
        return {
            "campo_al_lado": len(al),
            "balon_real": len(re),
            "otro": int((d.clase == "otro").sum()),
            "campo_al_lado_fuera_pct": round(100 * al.fuera_por_la_regla.mean(), 1),
            "balon_real_dentro_pct": round(100 * (~re.fuera_por_la_regla).mean(), 1),
            "reales_que_saca": re[re.fuera_por_la_regla][
                ["hoja", "id", "frame", "cx", "cy", "fuera_m"]
            ].to_dict("records"),
            "por_variable": {
                v: {
                    c: [
                        round(float(x), 2)
                        for x in d[d.clase == c][v].quantile([0, 0.5, 1])
                    ]
                    for c in ("campo_al_lado", "balon_real")
                }
                for v in ("cx", "cy", "ancho_px", "conf")
            },
        }

    tramo, control = carga(["tramo", "tramo_b"]), carga(["control", "control_regla"])
    res = {
        "regla": REGLA_PX,
        "tramo_ajuste": tasas(tramo),
        "control_min_14_16": tasas(control),
    }
    for k in ("tramo_ajuste", "control_min_14_16"):
        t = res[k]
        t["cumple"] = (
            t["campo_al_lado_fuera_pct"] >= 90 and t["balon_real_dentro_pct"] >= 95
        )
    # las posiciones dibujadas sobre un fotograma
    _f, img = next(leer_frames_ffmpeg(VIDEO_BENJA, [9306]))
    colores = {
        "campo_al_lado": (0, 0, 255),
        "balon_real": (0, 220, 0),
        "otro": (200, 200, 200),
    }
    for d, marca in ((tramo, cv2.MARKER_CROSS), (control, cv2.MARKER_TRIANGLE_UP)):
        for r in d.itertuples():
            cv2.drawMarker(img, (int(r.cx), int(r.cy)), colores[r.clase], marca, 14, 2)
    cv2.rectangle(
        img,
        (0, 0),
        (int(REGLA_PX["cx_max"]), int(REGLA_PX["cy_max"])),
        (0, 255, 255),
        2,
    )
    cv2.putText(
        img,
        "rojo: campo de al lado  verde: balon real  gris: otro  (cruz: tramo, triangulo: control)"
        "  amarillo: la regla",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
    )
    cv2.imwrite(
        str(salida / "candidatas_en_la_imagen.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88]
    )
    return res


def main() -> None:
    acciones = {
        "candidatas": candidatas,
        "segunda_tanda": segunda_tanda,
        "hoja_control_regla": hoja_control_regla,
        "regla": regla,
    }
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=list(acciones))
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    res = acciones[args.accion](salida)
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / f"{args.accion}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
