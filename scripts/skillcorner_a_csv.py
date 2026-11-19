#!/usr/bin/env python
"""Convierte un partido de los datos abiertos de SkillCorner a NUESTRO formato de CSV de posiciones.

Datos: github.com/SkillCorner/opendata (licencia MIT, © SkillCorner; hay que acreditarles). Tracking
de retransmisión a 10 fps, en metros con el origen en el CENTRO del campo.

Salida: el mismo formato que `procesar_desde_cache` (frame, tiempo_s, id_jugador, equipo, etiqueta,
x_m, y_m, es_real), con el origen en la esquina (0..largo, 0..ancho), el local como A y el visitante
como B, sus porteros como `portero_A` / `portero_B`, y una columna más, `posesion` (A, B o vacía),
que nuestro pipeline no tiene todavía. `es_real` = 1 si SkillCorner lo detectó en la imagen y 0 si
lo extrapoló. El balón va como etiqueta `balon`.

Uso:
    python scripts/skillcorner_a_csv.py --partido ~/Developer/externos/skillcorner-opendata \\
        --id 1874553 --tracking .../lfs/1874553_tracking_extrapolated.jsonl \\
        --salida outputs/literatura/skillcorner/1874553.csv
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--partido", type=Path, required=True, help="raíz del repositorio opendata"
    )
    ap.add_argument("--id", required=True)
    ap.add_argument(
        "--tracking", type=Path, required=True, help="el .jsonl (descargado de LFS)"
    )
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    meta = json.loads(
        (a.partido / f"data/matches/{a.id}/{a.id}_match.json").read_text()
    )
    largo, ancho = float(meta["pitch_length"]), float(meta["pitch_width"])
    local = meta["home_team"]["id"]
    etiqueta, equipo = {}, {}
    for p in meta["players"]:
        e = "A" if p["team_id"] == local else "B"
        es_portero = p["player_role"]["name"] == "Goalkeeper"
        etiqueta[p["id"]] = f"portero_{e}" if es_portero else e
        equipo[p["id"]] = 0 if e == "A" else 1
    grupo = {"home team": "A", "away team": "B"}
    filas = []
    with open(a.tracking) as f:
        for linea in f:
            d = json.loads(linea)
            if d.get("period") is None:
                continue
            t, fr = d["frame"] / 10.0, d["frame"]
            pos = grupo.get((d.get("possession") or {}).get("group"), "")
            for p in d["player_data"]:
                if p["player_id"] not in etiqueta:
                    continue
                filas.append(
                    (fr, t, p["player_id"], equipo[p["player_id"]], etiqueta[p["player_id"]],
                     round(p["x"] + largo / 2, 2), round(p["y"] + ancho / 2, 2),
                     int(bool(p["is_detected"])), pos, d["period"])
                )  # fmt: skip
            b = d.get("ball_data") or {}
            if b.get("x") is not None:
                filas.append(
                    (fr, t, -1, -1, "balon", round(b["x"] + largo / 2, 2),
                     round(b["y"] + ancho / 2, 2), int(bool(b.get("is_detected"))), pos,
                     d["period"])
                )  # fmt: skip
    df = pd.DataFrame(
        filas,
        columns=["frame", "tiempo_s", "id_jugador", "equipo", "etiqueta", "x_m", "y_m",
                 "es_real", "posesion", "parte"],
    )  # fmt: skip
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.salida, index=False)
    (a.salida.with_suffix(".json")).write_text(
        json.dumps(
            {
                "fuente": "SkillCorner Open Data (MIT), github.com/SkillCorner/opendata",
                "partido": f"{meta['home_team']['name']} - {meta['away_team']['name']}",
                "marcador": f"{meta['home_team_score']}-{meta['away_team_score']}",
                "campo_m": [largo, ancho],
                "A": meta["home_team"]["name"],
                "B": meta["away_team"]["name"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    print(f"✓ {a.salida}: {len(df)} filas, {df.frame.nunique()} frames")


if __name__ == "__main__":
    main()
