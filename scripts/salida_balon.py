#!/usr/bin/env python
"""Salidas de balón en la pizarra: candidatas y visor vídeo + pizarra. Criterios en
`docs/pizarra_salida_balon.md`.

Solo DIBUJO: lee el CSV del arreglo de interpoladas y el balón de `outputs/salida_balon/`; no
escribe en `data/`.

Uso:
    python scripts/salida_balon.py candidatas
"""

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/salida_balon"
CSV_CONJUNTO = SALIDA / "conjunto.csv"  # jugadores (arreglo de interpoladas) + balón
CONTACTOS = SALIDA / "contactos.csv"
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
    # frames del caché de balón (detectado o no): el denominador de la cobertura
    t_todos = np.sort(balon.tiempo_s.unique())
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["candidatas"])
    args = ap.parse_args()
    out = {"candidatas": candidatas}[args.accion]()
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
