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
import yaml

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


# ── bloque 3: recall y precisión de los jugadores por zona ────────────────────────────────────

PATAS = {
    "benja": dict(
        gt="data/annotations/gt_benja/annotations.xml",
        config="configs/processor_benja_parte_entera.yaml",
        offset=9750,
        largo=62.0,
        ancho=40.0,
    ),
    "villa": dict(
        gt="data/annotations/ground_truth_tracking/annotations.xml",
        config="configs/processor.yaml",
        offset=7500,
        largo=100.0,
        ancho=64.0,
    ),
}


def _iou_matriz(G: np.ndarray, D: np.ndarray) -> np.ndarray:
    """IoU de cada caja del GT (filas) con cada detección (columnas); cajas x1, y1, x2, y2."""
    ix = np.clip(
        np.minimum(G[:, None, 2], D[None, :, 2])
        - np.maximum(G[:, None, 0], D[None, :, 0]),
        0,
        None,
    )
    iy = np.clip(
        np.minimum(G[:, None, 3], D[None, :, 3])
        - np.maximum(G[:, None, 1], D[None, :, 1]),
        0,
        None,
    )
    inter = ix * iy
    area_g = (G[:, 2] - G[:, 0]) * (G[:, 3] - G[:, 1])
    area_d = (D[:, 2] - D[:, 0]) * (D[:, 3] - D[:, 1])
    return inter / (area_g[:, None] + area_d[None, :] - inter + 1e-9)


def _casar(G, D, criterio: str):
    """Pares (i_gt, j_det) 1-a-1 (húngaro). 'iou': IoU ≥ 0,5; 'centro': el centro de la caja del GT
    cae dentro de la detección (coste = distancia de centros)."""
    from scipy.optimize import linear_sum_assignment

    if not len(G) or not len(D):
        return []
    if criterio == "iou":
        iou = _iou_matriz(G, D)
        valido = iou >= 0.5
        coste = np.where(valido, 1 - iou, 1e6)
    else:
        cx, cy = (G[:, 0] + G[:, 2]) / 2, (G[:, 1] + G[:, 3]) / 2
        valido = (
            (cx[:, None] >= D[None, :, 0])
            & (cx[:, None] <= D[None, :, 2])
            & (cy[:, None] >= D[None, :, 1])
            & (cy[:, None] <= D[None, :, 3])
        )
        dcx, dcy = (D[:, 0] + D[:, 2]) / 2, (D[:, 1] + D[:, 3]) / 2
        dist = np.hypot(cx[:, None] - dcx[None, :], cy[:, None] - dcy[None, :])
        coste = np.where(valido, dist, 1e6)
    filas, cols = linear_sum_assignment(coste)
    return [(int(i), int(j)) for i, j in zip(filas, cols) if valido[i, j]]


def recall_pata(pata: str) -> dict:
    """Recall/precisión por zona (terciles de metros por píxel en el pie del GT)."""
    import pandas as pd

    from src.evaluation.gt_parser import parsear_cvat
    from src.tracking.cache_io import cargar_cache

    P = PATAS[pata]
    cfg = yaml.safe_load(open(R / P["config"]))
    H = np.load(R / cfg["rutas"]["homografia"])
    alto_img = cargar_cache(R / cfg["rutas"]["cache"])["wh"][1]
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    por_frame: dict[int, list] = {}
    for t in parsear_cvat(R / P["gt"]):
        for c in t.cajas:
            por_frame.setdefault(P["offset"] + 15 * c.frame_local, []).append(
                (t.label, c)
            )

    def proy(u, v):
        q = H @ np.array([u, v, 1.0])
        return q[:2] / q[2]

    def m_por_px(u, v):
        return float(np.linalg.norm(proy(u, v + 1) - proy(u, v)))

    filas_gt, filas_det = [], []
    for f, obs in sorted(por_frame.items()):
        D = np.array([d[2:6] for d in dets.get(f, [])], float).reshape(-1, 4)
        G = np.array([[c.xtl, c.ytl, c.xbr, c.ybr] for _l, c in obs], float).reshape(
            -1, 4
        )
        pares = {k: dict(_casar(G, D, k)) for k in ("iou", "centro")}
        iou = _iou_matriz(G, D) if len(D) else np.zeros((len(G), 0))
        for i, (lab, c) in enumerate(obs):
            g = G[i]
            fila = {
                "frame": f,
                "label": lab,
                "m_por_px": m_por_px((g[0] + g[2]) / 2, g[3]),
                "alto_px": g[3] - g[1],
                "casa_iou": i in pares["iou"],
                "casa_centro": i in pares["centro"],
                "iou_max": float(iou[i].max()) if iou.shape[1] else 0.0,
                "toca_borde": bool(g[3] >= alto_img - 2 or g[1] <= 1),
            }
            # ¿FUNDIDA? una detección casada (por centro) con OTRA persona solapa a esta
            otras = [pares["centro"][k] for k in pares["centro"] if k != i]
            fila["fundida"] = (
                bool(any(iou[i, j] >= 0.3 for j in otras)) if iou.shape[1] else False
            )
            filas_gt.append(fila)
        casadas = {k: set(v.values()) for k, v in pares.items()}
        for j, d in enumerate(dets.get(f, [])):
            mx, my = float(d[0]), float(d[1])
            en_campo = 0 <= mx <= P["largo"] and 0 <= my <= P["ancho"]
            if not en_campo:
                continue
            u, v = (d[2] + d[4]) / 2, d[5]
            filas_det.append(
                {
                    "frame": f,
                    "m_por_px": m_por_px(u, v),
                    "casa_iou": j in casadas["iou"],
                    "casa_centro": j in casadas["centro"],
                }
            )
    gt = pd.DataFrame(filas_gt)
    det = pd.DataFrame(filas_det)
    jug = gt[gt.label == "player"]
    cortes = jug.m_por_px.quantile([1 / 3, 2 / 3]).tolist()

    def zona(m):
        return "cerca" if m <= cortes[0] else ("media" if m <= cortes[1] else "lejos")

    jug = jug.assign(zona=jug.m_por_px.map(zona))
    det = det.assign(zona=det.m_por_px.map(zona))

    def clase_fallo(r):
        if r.fundida:
            return "fundida"
        if r.toca_borde:
            return "cortada"
        if r.alto_px < 20:
            return "muy_pequena"
        if r.iou_max > 0.1:
            return "mal_localizada"
        return "nada"

    res = {"cortes_m_por_px": [round(c, 3) for c in cortes], "zonas": {}}
    for z in ("cerca", "media", "lejos"):
        g, d = jug[jug.zona == z], det[det.zona == z]
        faltan = g[~g.casa_centro]
        res["zonas"][z] = {
            "gt_jugadores": len(g),
            "alto_gt_px_mediana": round(float(g.alto_px.median()), 1),
            "recall_iou_0_5": round(float(g.casa_iou.mean()), 3),
            "recall_centro": round(float(g.casa_centro.mean()), 3),
            "precision_iou_0_5": round(float(d.casa_iou.mean()), 3) if len(d) else None,
            "precision_centro": (
                round(float(d.casa_centro.mean()), 3) if len(d) else None
            ),
            "detecciones_en_campo": len(d),
            "faltan_centro_por_tipo": faltan.apply(clase_fallo, axis=1)
            .value_counts()
            .to_dict(),
            "faltan_iou_por_tipo": g[~g.casa_iou]
            .apply(clase_fallo, axis=1)
            .value_counts()
            .to_dict(),
        }
    # IC 95 % del recall por centro, remuestreando FRAMES (las personas de un frame no son
    # independientes: un frame malo pierde a varias a la vez)
    rng = np.random.default_rng(0)
    por_f = jug.groupby("frame").casa_centro.agg(["sum", "size"])
    boot = []
    for _ in range(2000):
        m = por_f.iloc[rng.integers(0, len(por_f), len(por_f))]
        boot.append(m["sum"].sum() / m["size"].sum())
    res["recall_centro_ic95"] = [
        round(float(q), 3) for q in np.quantile(boot, [0.025, 0.975])
    ]
    res["total"] = {
        "recall_iou_0_5": round(float(jug.casa_iou.mean()), 3),
        "recall_centro": round(float(jug.casa_centro.mean()), 3),
        "precision_iou_0_5": round(float(det.casa_iou.mean()), 3),
        "precision_centro": round(float(det.casa_centro.mean()), 3),
    }
    return res


def recall(salida: Path) -> dict:
    return {pata: recall_pata(pata) for pata in PATAS}


def paneles_balon(salida: Path) -> dict:
    """Los 30 paneles del 22-oct (outputs/diagnostico_balon/) con TODAS las candidatas (≥ 0,35)."""
    import cv2

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    nombres = sorted(p.stem for p in (R / "outputs/diagnostico_balon").glob("*.jpg"))
    frames = sorted({int(n.split("_")[1]) for n in nombres})
    cand = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(open(CACHE_BALON_P1, "rb"))["cache"]
    }
    carpeta = salida / "paneles_balon_todas"
    carpeta.mkdir(parents=True, exist_ok=True)
    lista = []
    for f, img in leer_frames_ffmpeg(VIDEO_BENJA, frames):
        for k, d in enumerate(cand.get(f, [])):
            x1, y1, x2, y2 = (int(round(float(v))) for v in d[2:6])
            cv2.rectangle(img, (x1 - 6, y1 - 6), (x2 + 6, y2 + 6), (0, 0, 255), 2)
            cv2.putText(
                img,
                f"{k}:{float(d[6]):.2f}",
                (x1 - 6, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
            )
        cv2.putText(
            img,
            f"f{f}  {relojes(f)}  candidatas: {len(cand.get(f, []))}",
            (10, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
        )
        cv2.imwrite(str(carpeta / f"f{f}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        lista.append(
            {"frame": f, "relojes": relojes(f), "candidatas": len(cand.get(f, []))}
        )
    return {"paneles": lista, "estratos": nombres}


def main() -> None:
    acciones = {
        "candidatas": candidatas,
        "segunda_tanda": segunda_tanda,
        "hoja_control_regla": hoja_control_regla,
        "regla": regla,
        "recall": recall,
        "paneles_balon": paneles_balon,
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
