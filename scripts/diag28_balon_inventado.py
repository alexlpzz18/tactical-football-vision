#!/usr/bin/env python
"""Diagnóstico 28-oct: el balón elegido tras un hueco. Criterio en
`docs/diagnostico_28oct_balon_inventado.md`. SOLO mide: el balón activo de `main` tal cual.

Uso:
    python scripts/diag28_balon_inventado.py --captura outputs/diagnostico_26oct_b \\
        --salida outputs/diagnostico_28oct
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
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
CAMPO = R / "configs/campo_benja.yaml"
FPS = 29.97002997002997
HUECO_MIN_S = 0.3
V_MAX_M_S = 35.0
SALTO_MIN_PX = 150.0
AMPLIAR_CAJA = 0.10
IDA_Y_VUELTA_S, IDA_Y_VUELTA_M = 2.0, 2.0
CONTROLES = {"14:46-14:48": (886.0, 888.5), "15:12-15:15": (912.0, 915.5)}  # archivo, s


def relojes(frame: int) -> str:
    t = frame / FPS
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int(r // 60)}:{r % 60:04.1f} repr"


def _mod(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sobre_jugador(det, jugadores) -> str | None:
    """'arriba' / 'medio' / 'abajo' si el centro del balón cae en una caja de jugador ampliada."""
    cx, cy = (det[2] + det[4]) / 2, (det[3] + det[5]) / 2
    for j in jugadores:
        x1, y1, x2, y2 = (float(v) for v in j[2:6])
        mx, my = AMPLIAR_CAJA * (x2 - x1), AMPLIAR_CAJA * (y2 - y1)
        if x1 - mx <= cx <= x2 + mx and y1 - my <= cy <= y2 + my:
            rel = (cy - y1) / max(y2 - y1, 1.0)
            return "arriba" if rel < 1 / 3 else ("medio" if rel < 2 / 3 else "abajo")
    return None


def medir(captura: Path, salida: Path) -> dict:
    gv = _mod(R / "scripts/generar_video_detecciones.py", "gv")
    activo = gv.balon_activo(CACHE_BALON, captura / "posiciones_main.csv", CAMPO)
    cap = pickle.load(open(captura / "captura_main.pkl", "rb"))
    jug = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    frames_balon = sorted(
        e["frame_idx"] for e in pickle.load(open(CACHE_BALON, "rb"))["cache"]
    )

    def jugadores_en(f):
        for d in (0, -1, 1, -2, 2):
            if f + d in jug:
                return jug[f + d]
        return []

    con = [f for f in frames_balon if f in activo]
    eventos = []
    for a, b in zip(con[:-1], con[1:]):
        dt = (b - a) / FPS
        da, db = activo[a][0], activo[b][0]
        salto_m = float(np.hypot(db[0] - da[0], db[1] - da[1]))
        cxa, cya = (da[2] + da[4]) / 2, (da[3] + da[5]) / 2
        cxb, cyb = (db[2] + db[4]) / 2, (db[3] + db[5]) / 2
        salto_px = float(np.hypot(cxb - cxa, cyb - cya))
        v = salto_m / max(dt, 1e-6)
        incompatible = v > V_MAX_M_S and salto_px > SALTO_MIN_PX
        hueco = dt >= HUECO_MIN_S
        if not (incompatible or hueco):
            continue
        # ida y vuelta: ¿vuelve a ≤ 2 m de la posición de ANTES en los 2 s siguientes?
        vuelve = False
        for c in con:
            if b < c <= b + IDA_Y_VUELTA_S * FPS:
                dc = activo[c][0]
                if np.hypot(dc[0] - da[0], dc[1] - da[1]) <= IDA_Y_VUELTA_M:
                    vuelve = True
                    break
        eventos.append(
            {
                "frame_antes": int(a),
                "frame_despues": int(b),
                "relojes": relojes(int(b)),
                "hueco_s": round(dt, 2),
                "es_hueco": bool(hueco),
                "salto_m": round(salto_m, 2),
                "salto_px": round(salto_px, 1),
                "v_m_s": round(v, 1),
                "incompatible": bool(incompatible),
                "sobre_jugador": sobre_jugador(db, jugadores_en(b)),
                "aereo": bool(activo[b][1]),
                "ida_y_vuelta": bool(vuelve),
                "conf": round(float(db[6]), 3),
            }
        )
    (salida / "eventos.json").write_text(
        json.dumps(eventos, indent=1, ensure_ascii=False)
    )

    def resumen(ev):
        inc = [e for e in ev if e["incompatible"]]
        sobre = [e for e in inc if e["sobre_jugador"]]
        partes = {}
        for e in sobre:
            partes[e["sobre_jugador"]] = partes.get(e["sobre_jugador"], 0) + 1
        return {
            "eventos": len(ev),
            "incompatibles": len(inc),
            "incompatibles_pct": round(100 * len(inc) / max(len(ev), 1), 1),
            "incompatibles_sobre_jugador": len(sobre),
            "sobre_jugador_pct_de_incompatibles": round(
                100 * len(sobre) / max(len(inc), 1), 1
            ),
            "sobre_jugador_por_parte": partes,
            "incompatibles_con_ida_y_vuelta": sum(e["ida_y_vuelta"] for e in inc),
            "incompatibles_aereos": sum(e["aereo"] for e in inc),
        }

    tras_hueco = [e for e in eventos if e["es_hueco"]]
    sin_hueco = [e for e in eventos if not e["es_hueco"]]
    control = {}
    for nombre, (t0, t1) in CONTROLES.items():
        en = [
            e
            for e in eventos
            if t0 * FPS <= e["frame_despues"] <= t1 * FPS and e["incompatible"]
        ]
        control[nombre] = {
            "incompatibles_marcados": len(en),
            "sobre_jugador": sum(1 for e in en if e["sobre_jugador"]),
            "detalle": [
                {
                    k: e[k]
                    for k in (
                        "relojes",
                        "hueco_s",
                        "salto_m",
                        "salto_px",
                        "sobre_jugador",
                    )
                }
                for e in en
            ],
        }
    th = resumen(tras_hueco)
    return {
        "frames_de_balon": len(frames_balon),
        "frames_con_balon_elegido": len(con),
        "control_casos_de_Alex": control,
        "control_pasa": all(c["incompatibles_marcados"] > 0 for c in control.values()),
        "tras_hueco": th,
        "sin_hueco_saltos_incompatibles": resumen(sin_hueco),
        "lectura": {
            "incompatibles_>=20%_de_huecos": th["incompatibles_pct"] >= 20,
            "de_ellos_>=50%_sobre_jugador": th["sobre_jugador_pct_de_incompatibles"]
            >= 50,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--captura", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    res = medir(Path(args.captura), salida)
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / "balon_inventado.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
