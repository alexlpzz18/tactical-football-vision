#!/usr/bin/env python
"""Salidas de balón en la pizarra: candidatas y visor vídeo + pizarra. Criterios en
`docs/pizarra_salida_balon.md`.

Solo DIBUJO: lee el CSV del arreglo de interpoladas y el balón de `outputs/salida_balon/`; no
escribe en `data/`.

Uso:
    python scripts/salida_balon.py candidatas
    python scripts/salida_balon.py visor --ids A1 A2 B2 --modulos <dir>

`--modulos`: carpeta con `fichas_pizarra.py` (rama `pizarra-sin-identidades`, sin fusionar), el
simulador que reproduce `posicionEn` de la pizarra. Se carga como si estuviera en `scripts/`.
"""

import argparse
import base64
import json
import pickle
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/salida_balon"
CSV_CONJUNTO = SALIDA / "conjunto.csv"  # jugadores (arreglo de interpoladas) + balón
CONTACTOS = SALIDA / "contactos.csv"
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
VIDEO = R / "data/raw/benja_gredos_p1_20min.mp4"
FPS = 29.97002997002997
DESFASE_REPRODUCTOR_S = 93.0
LARGO, ANCHO = 62.0, 40.0
# la regla (docs/pizarra_salida_balon.md), fijada antes de buscar
AREA_FONDO_M, AREA_ANCHO_M = 12.0, 26.0
PORTERO_CERCA_M = 2.0
VENTANA_DUENO_S = 8.0
MAX_SALIDA_S = 8.0
PROGRESION_S = 10.0
AVANCE_MIN_M = 15.0
COBERTURA_MIN = 0.5
ANTES_S, DESPUES_S = 5.0, 25.0
SEPARACION_S = 30.0
N_POR_EQUIPO = 3


def relojes(t: float) -> str:
    """Los dos relojes: archivo y reproductor (+1:33)."""
    r = t + DESFASE_REPRODUCTOR_S
    return f"{int(t // 60)}:{t % 60:04.1f} archivo · {int(r // 60)}:{r % 60:04.1f} reproductor"


def avance(x: np.ndarray, equipo: str) -> np.ndarray:
    """Distancia a la portería PROPIA a lo largo del campo (A defiende x = 0, B x = 62)."""
    return x if equipo == "A" else LARGO - x


def en_area_propia(x, y, equipo: str):
    return (avance(x, equipo) <= AREA_FONDO_M) & (
        np.abs(y - ANCHO / 2) <= AREA_ANCHO_M / 2
    )


def equipo_de(et) -> str | None:
    et = str(et)
    return (
        "A" if et in ("A", "portero_A") else ("B" if et in ("B", "portero_B") else None)
    )


def candidatas() -> dict:
    df = pd.read_csv(CSV_CONJUNTO)
    es_balon = df.etiqueta.astype(str).str.startswith("balon")
    balon = df[es_balon].sort_values("tiempo_s")
    jug = df[~es_balon]
    det = balon[(balon.es_real == 1) & (balon.etiqueta == "balon")]
    t_b, x_b, y_b = det.tiempo_s.to_numpy(), det.x_m.to_numpy(), det.y_m.to_numpy()
    # frames del caché de balón (detectado o no): el denominador de la cobertura.
    # ⚠️ NO las filas de balón del CSV: solo existen donde hay pista de balón, y dividir por
    # ellas daba 72-95 % donde la cobertura real era 35-44 % (docs/pizarra_salida_balon.md).
    t_todos = np.array([e["t"] for e in pickle.load(open(CACHE_BALON, "rb"))["cache"]])
    con = pd.read_csv(CONTACTOS).dropna(subset=["equipo"]).sort_values("t")
    con["eq_contacto"] = con.equipo.map(equipo_de)

    res = {}
    for T in ("A", "B"):
        porteros = jug[jug.etiqueta == f"portero_{T}"]
        pt = porteros.groupby("tiempo_s")[["x_m", "y_m"]].first()
        cerca_portero = np.zeros(len(t_b), bool)
        idx = pt.index.to_numpy()
        for k, t in enumerate(t_b):
            j = np.searchsorted(idx, t)
            for jj in (j - 1, j):
                if 0 <= jj < len(idx) and abs(idx[jj] - t) <= 0.2:
                    px, py = pt.iloc[jj]
                    if np.hypot(px - x_b[k], py - y_b[k]) <= PORTERO_CERCA_M:
                        cerca_portero[k] = True
        inicio = en_area_propia(x_b, y_b, T) | cerca_portero
        dentro = en_area_propia(x_b, y_b, T)
        lista, ultimo = [], -1e9
        for k in np.where(inicio)[0]:
            ts = t_b[k]
            if ts - ultimo < SEPARACION_S or ts < ANTES_S:
                continue
            # dueño: primer contacto atribuido en [ts, ts + 8]
            c = con[(con.t >= ts) & (con.t <= ts + VENTANA_DUENO_S)]
            if not len(c) or c.eq_contacto.iloc[0] != T:
                continue
            # salida del área
            fuera = np.where((t_b > ts) & (t_b <= ts + MAX_SALIDA_S) & ~dentro)[0]
            if not len(fuera):
                continue
            ko = fuera[0]
            t_out = t_b[ko]
            ventana = (t_b >= t_out) & (t_b <= t_out + PROGRESION_S)
            if dentro[ventana].any():
                continue
            if avance(x_b[ventana], T).max() - avance(x_b[[ko]], T)[0] < AVANCE_MIN_M:
                continue
            a, b = ts - ANTES_S, ts + DESPUES_S
            n_tot = ((t_todos >= a) & (t_todos <= b)).sum()
            n_det = ((t_b >= a) & (t_b <= b)).sum()
            cob = n_det / n_tot if n_tot else 0.0
            if cob < COBERTURA_MIN:
                continue
            lista.append(
                {
                    "equipo": T,
                    "t_inicio_balon": round(float(ts), 2),
                    "tramo": [round(float(a), 2), round(float(b), 2)],
                    "relojes_tramo": f"{relojes(a)} → {relojes(b)}",
                    "cobertura_balon": round(float(cob), 3),
                    "inicio_por": "portero" if cerca_portero[k] else "área",
                    "avance_m": round(
                        float(avance(x_b[ventana], T).max() - avance(x_b[[ko]], T)[0]),
                        1,
                    ),
                }
            )
            ultimo = ts
        res[T] = {
            "que_cumplen_la_regla": len(lista),
            "propuestas": sorted(lista, key=lambda d: -d["cobertura_balon"])[
                :N_POR_EQUIPO
            ],
        }
    # miniaturas y página
    Hinv = np.linalg.inv(np.load(R / "data/calibracion_benja/homografia_benja.npy"))
    tarjetas = []
    for T in ("A", "B"):
        for n, c in enumerate(res[T]["propuestas"], start=1):
            c["id"] = f"{T}{n}"
            jpg = SALIDA / f"mini_{c['id']}.jpg"
            # recuadro amarillo en el balón: su posición en metros llevada a píxeles
            k = int(np.argmin(np.abs(t_b - c["t_inicio_balon"])))
            u, v, w = Hinv @ np.array([x_b[k], y_b[k], 1.0])
            u, v = u / w, v / w
            caja = (
                f"drawbox=x={u - 30:.0f}:y={v - 30:.0f}:w=60:h=60:color=yellow:t=4,"
                "scale=640:-1"
            )
            subprocess.run(
                [
                    "ffmpeg", "-loglevel", "error", "-y",
                    "-ss", f"{c['t_inicio_balon']:.3f}", "-i", str(VIDEO),
                    "-frames:v", "1", "-vf", caja, str(jpg),
                ],
                check=True,
            )  # fmt: skip
            b64 = base64.b64encode(jpg.read_bytes()).decode()
            tarjetas.append(
                f'<div class="t"><img src="data:image/jpeg;base64,{b64}">'
                f"<h3>{c['id']} · sale el equipo {T}</h3>"
                f"<p>tramo: {c['relojes_tramo']}</p>"
                f"<p>balón en su {c['inicio_por']} a los {relojes(c['t_inicio_balon'])}; "
                f"avanza {c['avance_m']} m · balón detectado en el "
                f"{100 * c['cobertura_balon']:.0f} % del tramo</p></div>"
            )
    html = SALIDA / "candidatas.html"
    html.write_text(
        "<!doctype html><meta charset=utf-8><title>Salidas de balón · candidatas</title>"
        "<style>body{font:15px system-ui;background:#111;color:#eee;margin:16px}"
        ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:16px}"
        ".t{background:#1d1d1d;padding:10px;border-radius:8px}img{width:100%}"
        "h3{margin:8px 0 4px}p{margin:2px 0;color:#bbb}</style>"
        "<h1>Salidas de balón: 3 candidatas por equipo</h1>"
        "<p>A (blanco) defiende la portería cercana a la cámara; B (naranja), la lejana. "
        "La miniatura es el "
        "instante en que el balón está en su área o con su portero (recuadro amarillo). Elige "
        "las que quieras por su id.</p>"
        f'<div class="g">{"".join(tarjetas)}</div>'
    )
    json.dump(res, open(SALIDA / "candidatas.json", "w"), indent=1, ensure_ascii=False)
    return res


# ── visor: vídeo y pizarra sincronizados ─────────────────────────────────────────────────────

META = R / "outputs/fix_interpoladas/benja_despues_meta.json"
CAMPO = R / "configs/campo_benja.yaml"
HISTERESIS_S = 1.0
PASO_VISOR_S = (
    0.05  # la pizarra se precalcula a 20 Hz y se dibuja al instante del vídeo
)
BALON_CERCA_S = 0.07  # el caché de balón va a 15 Hz: una detección a ≤ 1 muestra
PLANTILLA_VISOR = R / "scripts/plantilla_salida_balon.html"
MODULOS: Path | None = None


def _mod(nombre):
    """Un script de `scripts/`, o de `--modulos` con `__file__` dentro de `scripts/`."""
    ruta = R / f"scripts/{nombre}.py"
    fuente = ruta if ruta.exists() else MODULOS / f"{nombre}.py"
    m = types.ModuleType(nombre)
    m.__file__ = str(ruta)
    exec(compile(fuente.read_text(), str(fuente), "exec"), m.__dict__)
    return m


def datos_de_un_tramo(c: dict, df: pd.DataFrame, carpeta: Path) -> dict:
    """Fichas (lo que pinta la pizarra), balón y la calidad del tramo, muestreados a 20 Hz."""
    fp = _mod("fichas_pizarra")
    a, b = c["tramo"]
    es_balon = df.etiqueta.astype(str).str.startswith("balon")
    # (1) la pizarra de producción del tramo: arreglo de interpoladas + histéresis de 1 s
    html = carpeta / f"pizarra_{c['id']}.html"
    corte = df[~es_balon & (df.tiempo_s >= a - 5) & (df.tiempo_s <= b + 5)]
    corte_csv = carpeta / f"pizarra_{c['id']}.csv"
    corte.to_csv(corte_csv, index=False)
    subprocess.run(
        [
            sys.executable, str(R / "scripts/generar_replay.py"),
            "--csv", str(corte_csv), "--salida", str(html),
            "--config-campo", str(CAMPO), "--meta", str(META),
            "--suavizado-visual-ventana", "1",
            "--histeresis-visual-s", str(HISTERESIS_S),
            "--titulo", c["id"],
        ],
        check=True, capture_output=True,
    )  # fmt: skip
    datos, catalogo = fp.leer_pizarra(html)
    Ts = np.arange(a, b, PASO_VISOR_S)
    fichas = fp.simular(datos, catalogo, Ts)
    # (2) el balón: solo DETECCIONES dentro del campo; si proyecta fuera no se pinta
    bal = df[es_balon & (df.es_real == 1)].sort_values("tiempo_s")
    dentro = bal.x_m.between(0, LARGO) & bal.y_m.between(0, ANCHO)
    tb = bal.tiempo_s.to_numpy()
    j = np.clip(np.searchsorted(tb, Ts), 1, len(tb) - 1)
    k = np.where(np.abs(tb[j - 1] - Ts) <= np.abs(tb[j] - Ts), j - 1, j)
    cerca = np.abs(tb[k] - Ts) <= BALON_CERCA_S
    estado = np.where(
        ~cerca, "no visible", np.where(dentro.to_numpy()[k], "detectado", "fuera")
    )
    aereo = bal.etiqueta.to_numpy()[k] == "balon_aereo"
    balon = [
        (
            [
                round(float(bal.x_m.iloc[kk]), 2),
                round(float(bal.y_m.iloc[kk]), 2),
                int(ae),
            ]
            if e == "detectado"
            else e
        )
        for kk, e, ae in zip(k, estado, aereo)
    ]
    # (3) por instante: fichas visibles DENTRO del campo, por etiqueta pintada
    muestras = []
    por_equipo = {"A": [], "B": []}
    for n in range(len(Ts)):
        vis = []
        cuenta = {"A": 0, "B": 0}
        for f in fichas:
            if not f["vis"][n]:
                continue
            x, y, et = float(f["x"][n]), float(f["y"][n]), str(f["col"][n])
            if not (0 <= x <= LARGO and 0 <= y <= ANCHO):
                continue
            vis.append([round(x, 2), round(y, 2), et])
            eq = equipo_de(et)
            if eq:
                cuenta[eq] += 1
        for e in cuenta:
            por_equipo[e].append(cuenta[e])
        muestras.append(vis)
    n_det = int((estado == "detectado").sum())
    calidad = {
        "balon_detectado_pct": round(100 * n_det / len(Ts), 1),
        "balon_fuera_del_campo_pct": round(100 * float((estado == "fuera").mean()), 1),
        "balon_no_visible_pct": round(100 * float((estado == "no visible").mean()), 1),
        "fichas_media": {e: round(float(np.mean(v)), 2) for e, v in por_equipo.items()},
        "fichas_p10_p90": {
            e: [int(np.percentile(v, 10)), int(np.percentile(v, 90))]
            for e, v in por_equipo.items()
        },
        "instantes_con_7_o_mas": {
            e: round(100 * float(np.mean(np.array(v) >= 7)), 1)
            for e, v in por_equipo.items()
        },
    }
    return {
        "id": c["id"],
        "equipo": c["equipo"],
        "t0": a,
        "paso": PASO_VISOR_S,
        "muestras": muestras,
        "balon": balon,
        "calidad": calidad,
        "relojes": c["relojes_tramo"],
        "video": f"clip_{c['id']}.mp4",
    }


def visor(ids: list[str]) -> dict:
    carpeta = SALIDA / "visor"
    carpeta.mkdir(parents=True, exist_ok=True)
    cand = json.load(open(SALIDA / "elegidas_por_alex.json"))
    por_id = {c["id"]: c for T in cand for c in cand[T]["propuestas"]}
    df = pd.read_csv(CSV_CONJUNTO)
    tramos = []
    for i in ids:
        c = por_id[i]
        a, b = c["tramo"]
        clip = carpeta / f"clip_{i}.mp4"
        # -ss ANTES de -i con recodificación: corte exacto al frame (ffmpeg CLI, no cv2)
        subprocess.run(
            [
                "ffmpeg", "-loglevel", "error", "-y", "-ss", f"{a:.3f}", "-i", str(VIDEO),
                "-t", f"{b - a:.3f}", "-an", "-vf", "scale=960:-2",
                "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                "-movflags", "+faststart", str(clip),
            ],
            check=True,
        )  # fmt: skip
        tramos.append(datos_de_un_tramo(c, df, carpeta))
    colores = json.load(open(META)).get("colores_equipo", {})
    html = carpeta / "salidas_de_balon.html"
    html.write_text(
        PLANTILLA_VISOR.read_text()
        .replace("__TRAMOS__", json.dumps(tramos, separators=(",", ":")))
        .replace("__COLORES__", json.dumps(colores))
    )
    res = {t["id"]: {"relojes": t["relojes"], **t["calidad"]} for t in tramos}
    res["html"] = str(html)
    json.dump(res, open(carpeta / "calidad.json", "w"), indent=1, ensure_ascii=False)
    return res


def main() -> None:
    global MODULOS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["candidatas", "visor"])
    ap.add_argument("--ids", nargs="+", default=["A1", "A2", "B2"])
    ap.add_argument("--modulos", type=Path, default=None)
    args = ap.parse_args()
    MODULOS = args.modulos
    if args.accion == "candidatas":
        out = candidatas()
    else:
        out = visor(args.ids)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
