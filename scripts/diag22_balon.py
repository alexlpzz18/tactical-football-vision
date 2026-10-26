#!/usr/bin/env python
"""Diagnóstico 22-oct, bloque 1: el balón, bien en el vídeo y mal en la pizarra. Solo medición.

Criterios en `docs/diagnostico_22oct.md` (commiteados antes). El balón del VÍDEO es el de
`generar_video_detecciones.balon_activo` (lo que se pinta); el de la PIZARRA son las filas
`balon`/`balon_aereo` del CSV de `procesar_balon.py` (lo que dibuja `replay_tactico`).

Uso:
    python scripts/diag22_balon.py --trabajo outputs/diagnostico_22oct \\
        --csv-jugadores outputs/arbitro_obs/posiciones.csv
"""

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
FPS = 29.97002997002997
TRAMO = (8991, 10790)  # 5:00-6:00 de archivo (6:33-7:33 del reproductor)
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
CAMPO = R / "configs/campo_benja.yaml"
X_LEJOS_M = 10.0  # fijado en el criterio (p95 del balón real al jugador: 8,3 m)
ZONAS = [(0, 20), (20, 40), (40, 62)]


def huecos(frames_video: list[int], con_pizarra: set[int]) -> list[float]:
    """Duración (s) de cada racha de frames del vídeo consecutivos SIN balón en la pizarra."""
    rachas, actual = [], []
    for f in sorted(frames_video):
        if f in con_pizarra:
            if actual:
                rachas.append(actual)
            actual = []
        else:
            actual.append(f)
    if actual:
        rachas.append(actual)
    return [
        ((r[-1] - r[0]) / FPS) + 2 / FPS for r in rachas
    ]  # +1 paso del caché (sample 2)


def pasos(df, columna_id=None):
    """(velocidad m/s, salto m, dt s) entre filas consecutivas (por identidad si se da)."""
    out = []
    grupos = [df] if columna_id is None else [g for _i, g in df.groupby(columna_id)]
    for g in grupos:
        g = g.sort_values("frame")
        P, F = g[["x_m", "y_m"]].to_numpy(), g.frame.to_numpy()
        for k in range(1, len(P)):
            dt = (F[k] - F[k - 1]) / FPS
            if dt <= 0:
                continue
            d = float(np.linalg.norm(P[k] - P[k - 1]))
            out.append((d / dt, d, dt))
    return np.array(out).reshape(-1, 3)


def main() -> None:
    import cv2
    import pandas as pd

    from src.tracking_data.processor import posicionar_en_frame

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trabajo", required=True)
    ap.add_argument("--csv-jugadores", required=True)
    args = ap.parse_args()
    trabajo = Path(args.trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    # La pizarra: el CSV conjunto de producción (se regenera, no se toca nada)
    conjunto = trabajo / "conjunto.csv"
    if not conjunto.exists():
        subprocess.run(
            [
                py,
                str(R / "scripts/procesar_balon.py"),
                "--cache-balon",
                str(CACHE_BALON),
                "--csv-jugadores",
                args.csv_jugadores,
                "--salida",
                str(conjunto),
            ],
            check=True,
            capture_output=True,
        )
    todo = pd.read_csv(conjunto)
    es_balon = todo.etiqueta.astype(str).str.startswith("balon")
    piz = todo[es_balon]
    jug = pd.read_csv(args.csv_jugadores)
    piz_t = piz[piz.frame.between(*TRAMO)]

    # El vídeo: el balón activo, con la función que pinta el vídeo
    spec = importlib.util.spec_from_file_location(
        "gvd", R / "scripts/generar_video_detecciones.py"
    )
    gvd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gvd)
    activo = gvd.balon_activo(str(CACHE_BALON), args.csv_jugadores, str(CAMPO))
    vid = {f: v for f, v in activo.items() if TRAMO[0] <= f <= TRAMO[1]}

    res = {"tramo_frames": TRAMO, "frames_video_con_balon": len(vid)}

    # 1a
    con_piz = set(piz_t.frame)
    sin = [f for f in vid if f not in con_piz]
    h = huecos(list(vid), con_piz)
    res["1a"] = {
        "frames_video_sin_pizarra": len(sin),
        "pct": 100 * len(sin) / max(len(vid), 1),
        "n_huecos": len(h),
        "hueco_s_mediana_p90_max": (
            [float(np.median(h)), float(np.percentile(h, 90)), float(max(h))]
            if h
            else None
        ),
        "frames_pizarra_en_tramo": int(len(piz_t)),
        "pizarra_aereo": int((piz_t.etiqueta == "balon_aereo").sum()),
    }

    # 1b: centro contra base de la caja, en metros
    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")

    def proy(u, v):
        p = H @ np.array([u, v, 1.0])
        return np.array([p[0] / p[2], p[1] / p[2]])

    filas_b = []
    for f, (det, _aer) in vid.items():
        x1, y1, x2, y2 = det[2:6]
        base, centro = proy((x1 + x2) / 2, y2), proy((x1 + x2) / 2, (y1 + y2) / 2)
        filas_b.append((base[0], float(np.linalg.norm(base - centro)), y2 - y1))
    B = np.array(filas_b)
    res["1b"] = {
        "pixel_proyectado": "base de la caja: ((x1+x2)/2, y2) (detectar_balon.py)"
    }
    for a, b in ZONAS:
        s = B[(B[:, 0] >= a) & (B[:, 0] < b)]
        res["1b"][f"x{a}-{b}"] = (
            {
                "n": len(s),
                "dif_m_mediana": float(np.median(s[:, 1])),
                "dif_m_p90": float(np.percentile(s[:, 1], 90)),
                "alto_caja_px_mediana": float(np.median(s[:, 2])),
            }
            if len(s)
            else None
        )

    # 1c: velocidad y saltos en la pizarra, contra jugadores
    pb = pasos(piz_t)
    pj = pasos(jug[jug.frame.between(*TRAMO)], "id_jugador")
    for nombre, P in (("balon_pizarra", pb), ("jugadores_control", pj)):
        consecutivos = P[P[:, 2] <= 0.2] if len(P) else P
        res.setdefault("1c", {})[nombre] = {
            "pasos": int(len(P)),
            "pct_v_mayor_35": float(100 * (P[:, 0] > 35).mean()) if len(P) else None,
            "pct_salto_mayor_10m": (
                float(100 * (P[:, 1] > 10).mean()) if len(P) else None
            ),
            "solo_dt<=0,2s_pct_v_mayor_35": (
                float(100 * (consecutivos[:, 0] > 35).mean())
                if len(consecutivos)
                else None
            ),
        }

    # 1d: fuera del campo, y rodando lejos de todos
    fuera = ~(piz_t.x_m.between(0, 62) & piz_t.y_m.between(0, 40))
    jporf = {
        f: g[["x_m", "y_m"]].to_numpy()
        for f, g in jug[
            jug.etiqueta.isin(["A", "B", "portero_A", "portero_B"])
        ].groupby("frame")
    }
    fr_j = np.array(sorted(jporf))
    dist = []
    for r in piz_t[piz_t.etiqueta == "balon"].itertuples():
        fj = fr_j[np.argmin(np.abs(fr_j - r.frame))]
        dist.append(float(np.min(np.hypot(*(jporf[fj] - [r.x_m, r.y_m]).T))))
    dist = np.array(dist)
    res["1d"] = {
        "pct_fuera_del_campo": float(100 * fuera.mean()),
        "rodando_n": int(len(dist)),
        f"pct_rodando_a_mas_de_{X_LEJOS_M:g}m": float(100 * (dist > X_LEJOS_M).mean()),
    }

    # 1e: 30 paneles estratificados (frames del vídeo con balón)
    rng = np.random.default_rng(0)
    base_x = {f: proy((v[0][2] + v[0][4]) / 2, v[0][5])[0] for f, v in vid.items()}
    suelo = [f for f, v in vid.items() if not v[1] and base_x[f] < 40]
    alto = [f for f, v in vid.items() if v[1]]
    lejos = [f for f in vid if base_x[f] >= 40]
    estratos = {}
    for nombre, lista in (("suelo", suelo), ("alto", alto), ("lejos", lejos)):
        elegidos = (
            rng.choice(lista, min(10, len(lista)), replace=False) if lista else []
        )
        estratos[nombre] = sorted(int(x) for x in elegidos)
    res["1e_estratos_disponibles"] = {
        "suelo": len(suelo),
        "alto": len(alto),
        "lejos": len(lejos),
    }
    d_out = R / "outputs/diagnostico_balon"
    d_out.mkdir(parents=True, exist_ok=True)
    piz_por_f = {f: g for f, g in piz.groupby("frame")}
    cap = cv2.VideoCapture(str(R / "data/raw/benja_gredos_p1_20min.mp4"))
    paneles = []
    pedidos = sorted((f, n) for n, fs in estratos.items() for f in fs)
    actual = posicionar_en_frame(cap, pedidos[0][0]) if pedidos else 0
    for f, nombre in pedidos:
        while actual < f:
            cap.grab()
            actual += 1
        ok, img = cap.read()
        actual += 1
        det, aer = vid[f]
        x1, y1, x2, y2 = (int(round(v)) for v in det[2:6])
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        fy, fx = slice(max(cy - 160, 0), cy + 160), slice(max(cx - 240, 0), cx + 240)
        rec = img[fy, fx].copy()
        ox, oy = max(cx - 240, 0), max(cy - 160, 0)
        cv2.rectangle(
            rec,
            (x1 - ox - 4, y1 - oy - 4),
            (x2 - ox + 4, y2 - oy + 4),
            (0, 255, 255),
            2,
        )
        rec = cv2.resize(rec, (480, 320))
        # pizarra: 62x40 m a 8 px/m
        piz_img = np.full((320, 496, 3), (40, 110, 40), np.uint8)
        cv2.rectangle(piz_img, (0, 0), (495, 319), (255, 255, 255), 1)
        fj = fr_j[np.argmin(np.abs(fr_j - f))]
        for x, y in jporf.get(fj, []):
            cv2.circle(piz_img, (int(x * 8), int(y * 8)), 4, (200, 200, 200), -1)
        bv = proy((det[2] + det[4]) / 2, det[5])
        cv2.circle(
            piz_img, (int(bv[0] * 8), int(bv[1] * 8)), 6, (0, 255, 255), 2
        )  # vídeo
        g = piz_por_f.get(f)
        txt = "pizarra: SIN balon"
        if g is not None:
            r = g.iloc[0]
            cv2.circle(piz_img, (int(r.x_m * 8), int(r.y_m * 8)), 5, (0, 0, 255), -1)
            txt = (
                f"pizarra {r.etiqueta} a {np.hypot(r.x_m - bv[0], r.y_m - bv[1]):.1f} m"
            )
        t = f / FPS
        cab = (
            f"{nombre} f{f} {int(t // 60)}:{t % 60:04.1f} arch / "
            f"{int((t + 93) // 60)}:{(t + 93) % 60:04.1f} repr  aereo={aer}  {txt}"
        )
        panel = np.hstack([rec, piz_img])
        panel = cv2.copyMakeBorder(panel, 24, 0, 0, 0, cv2.BORDER_CONSTANT)
        cv2.putText(
            panel, cab, (4, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1
        )
        nombre_png = f"{nombre}_{f}.jpg"
        cv2.imwrite(str(d_out / nombre_png), panel)
        paneles.append(
            {
                "estrato": nombre,
                "frame": f,
                "archivo": f"{int(t // 60)}:{t % 60:04.1f}",
                "aereo_video": bool(aer),
                "pizarra": txt,
                "panel": nombre_png,
            }
        )
    cap.release()
    res["1e_paneles"] = paneles
    (trabajo / "bloque1.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(
        json.dumps(
            {k: v for k, v in res.items() if k != "1e_paneles"},
            indent=1,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
