#!/usr/bin/env python
"""Diagnóstico 22-oct (d), bloque 1a-1b: simultaneidad de `otro` en el campo, hoy contra v3.

Criterio en `docs/diagnostico_22oct_d.md`. Lee los CSV y logs de `scripts/diag22c_v3.py`.

Uso:
    python scripts/diag22d_simultaneidad.py --pasadas outputs/diagnostico_22oct_c \\
        --salida outputs/diagnostico_22oct_d
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
LARGO, ANCHO = 62.0, 40.0
VENTANA_GT = (9750, 10635)
UMBRAL_PCT, SUBIDA_MAX_PUNTOS = 3.0, 1.0


def otro_en_campo_por_frame(filas, solo_reales: bool = False):
    """Serie {frame: nº de filas `otro` dentro del campo}, con 0 en los frames sin ninguna."""
    f = filas[filas.es_real == 1] if solo_reales else filas
    dentro = (f.etiqueta == "otro") & f.x_m.between(0, LARGO) & f.y_m.between(0, ANCHO)
    cuenta = f[dentro].groupby("frame").size()
    return cuenta.reindex(sorted(filas.frame.unique()), fill_value=0)


def distribucion(serie) -> dict:
    n = len(serie)
    return {
        "frames": int(n),
        "0": int((serie == 0).sum()),
        "1": int((serie == 1).sum()),
        "2": int((serie == 2).sum()),
        ">=3": int((serie >= 3).sum()),
        "pct_ge2": round(100 * float((serie >= 2).mean()), 2),
        "moda": int(serie.mode().iloc[0]),
    }


def ids_del_tercer_grupo(log: Path) -> list[int]:
    for linea in log.read_text().splitlines():
        if linea.startswith("TERCER GRUPO CON"):
            return [int(x) for x in re.findall(r"(\d+) \(\d+ obs en", linea)]
    return []


def cadenas(intervalos: list[tuple[int, int, int]]) -> int:
    """Nº mínimo de cadenas sin solape (= máxima simultaneidad de intervalos)."""
    eventos = sorted(
        [(a, 1) for _i, a, _b in intervalos] + [(b, -1) for _i, _a, b in intervalos],
        key=lambda e: (e[0], -e[1]),
    )
    actual = maximo = 0
    for _t, d in eventos:
        actual += d
        maximo = max(maximo, actual)
    return maximo


def main() -> None:
    import pandas as pd

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pasadas", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    pas, salida = Path(args.pasadas), Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    res = {}
    for nombre in ("hoy", "v3"):
        filas = pd.read_csv(pas / f"posiciones_{nombre}.csv")
        todas = otro_en_campo_por_frame(filas)
        reales = otro_en_campo_por_frame(filas, solo_reales=True)
        gt = todas[(todas.index >= VENTANA_GT[0]) & (todas.index <= VENTANA_GT[1])]
        ids = ids_del_tercer_grupo(pas / f"posiciones_{nombre}.log")
        sub = filas[filas.id_jugador.isin(ids)]
        presencia = (
            sub.groupby("frame")
            .id_jugador.nunique()
            .reindex(sorted(filas.frame.unique()), fill_value=0)
        )
        interv = [
            (int(i), int(g.frame.min()), int(g.frame.max()))
            for i, g in sub.groupby("id_jugador")
        ]
        # ¿el segundo `otro` es otra persona o un duplicado de la misma? (frames con 2 o más)
        dentro = filas[
            (filas.etiqueta == "otro")
            & filas.x_m.between(0, LARGO)
            & filas.y_m.between(0, ANCHO)
        ]
        dmin = []
        for _f, g in dentro.groupby("frame"):
            if len(g) < 2:
                continue
            P = g[["x_m", "y_m"]].to_numpy()
            d = np.hypot(*(P[:, None, :] - P[None, :, :]).transpose(2, 0, 1))
            np.fill_diagonal(d, np.inf)
            dmin.append(float(d.min()))
        dmin = np.array(dmin)
        res[nombre] = {
            "pares_otro_distancia_minima_m": {
                "frames": int(len(dmin)),
                "pct_<1,5m_(duplicado)": (
                    round(100 * float((dmin < 1.5).mean()), 1) if len(dmin) else None
                ),
                "p10_50_90": (
                    [round(float(x), 1) for x in np.percentile(dmin, [10, 50, 90])]
                    if len(dmin)
                    else None
                ),
            },
            "todas_las_filas": distribucion(todas),
            "solo_reales": distribucion(reales),
            "ventana_gt_control": distribucion(gt),
            "tercer_grupo": {
                "identidades": ids,
                "max_simultaneas_por_frames": int(presencia.max()) if len(ids) else 0,
                "pct_frames_con_2_o_mas_a_la_vez": round(
                    100 * float((presencia >= 2).mean()), 2
                ),
                "cadenas_minimas_por_intervalos": cadenas(interv) if interv else 0,
                "intervalos_frames": interv,
            },
        }
    h, n = res["hoy"]["todas_las_filas"], res["v3"]["todas_las_filas"]
    res["criterio_1a"] = {
        "v3_pct_ge2_<=3": n["pct_ge2"] <= UMBRAL_PCT,
        "v3_sube_<=1_punto": n["pct_ge2"] - h["pct_ge2"] <= SUBIDA_MAX_PUNTOS,
    }
    res["criterio_1a"]["v3_sana"] = all(res["criterio_1a"].values())
    (salida / "bloque1a.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
