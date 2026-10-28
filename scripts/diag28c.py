#!/usr/bin/env python
"""Diagnóstico 28-oct (c): las hojas de Alex. Criterios en `docs/diagnostico_28oct_c.md`.

Uso:
    python scripts/diag28c.py equipo --marcas outputs/diagnostico_28oct_c/revision_…csv
    python scripts/diag28c.py balon
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/diagnostico_28oct_c"
FPS = 29.97002997002997
MAPEO = {
    "A": "A",
    "B": "B",
    "portero_A": "A",
    "portero_B": "B",
    "arbitro": "ERR",
    "staff": "ERR",
}
EXCLUIDAS = {"jugador", "no_es_persona", "dudoso"}


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    """IC 95 % de Wilson de una proporción k/n, en %."""
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * (c - m), 1), round(100 * (c + m), 1)]


def equipo_base(e) -> str:
    e = str(e)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def equipo(marcas: Path) -> dict:
    m = pd.read_csv(marcas)
    clave = pd.read_csv(R / "outputs/hoja_equipos/clave_equipo_por_obs_20min.csv")
    d = clave.merge(m[["imagen", "equipo_correcto", "nota"]], on="imagen", how="left")
    d["marca"] = d.equipo_correcto.fillna("")
    excl = d[d.marca.isin(EXCLUIDAS) | (d.marca == "")]
    d = d[~d.index.isin(excl.index)].copy()
    d["verdad"] = d.marca.map(MAPEO)
    d["sis_obs"] = d.etiqueta_observacion.map(equipo_base)
    d["sis_id"] = d.etiqueta_identidad.map(equipo_base)
    d["mal_obs"] = d.verdad != d.sis_obs
    d["mal_id"] = d.verdad != d.sis_id

    def corte(g) -> dict:
        k, n = int(g.mal_obs.sum()), len(g)
        ki = int(g.mal_id.sum())
        return {
            "n": n,
            "errores_obs": k,
            "error_obs_pct": round(100 * k / max(n, 1), 1),
            "ic95_obs": wilson(k, n),
            "errores_voto_identidad": ki,
            "error_id_pct": round(100 * ki / max(n, 1), 1),
            "ic95_id": wilson(ki, n),
        }

    res = {
        "filas_hoja": len(clave),
        "excluidas": {
            str(k): int(v)
            for k, v in excl.marca.replace("", "sin_marca").value_counts().items()
        },
        "total": corte(d),
        "cruce": corte(d[d.cruce.astype(bool)]),
        "no_cruce": corte(d[~d.cruce.astype(bool)]),
        "por_equipo_de_la_marca": {
            e: corte(g)
            for e, g in d.groupby(d.verdad.where(d.verdad != "ERR", "arbitro_o_staff"))
        },
        "por_tramo_2min": {
            f"{int(t) * 2:02d}-{int(t) * 2 + 2:02d} min": corte(g)
            for t, g in d.groupby("tramo_2min")
        },
        "errores": d[d.mal_obs][
            [
                "imagen",
                "frame",
                "id",
                "etiqueta_observacion",
                "etiqueta_identidad",
                "marca",
                "cruce",
            ]
        ]
        .assign(
            relojes=lambda x: [
                f"{int(f / FPS // 60)}:{f / FPS % 60:04.1f} arch / "
                f"{int((f / FPS + 93) // 60)}:{(f / FPS + 93) % 60:04.1f} repr"
                for f in x.frame
            ]
        )
        .to_dict("records"),
    }
    k = res["total"]["errores_obs"]
    n = res["total"]["n"]
    res["criterio"] = (
        "se sostiene"
        if k <= max(6, 0.05 * n)
        else ("NO se sostiene" if k >= min(12, 0.10 * n) else "no decidido")
    )
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["equipo", "balon"])
    ap.add_argument("--marcas", default=None)
    args = ap.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)
    res = equipo(Path(args.marcas)) if args.accion == "equipo" else balon()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (SALIDA / f"{args.accion}.json").write_text(texto)
    print(texto)


def balon() -> dict:
    """Visibilidad, recall y falsos positivos por zona (la de la hoja y la del juego)."""
    from src.balon.tracking_balon import escala_px_por_m

    gt = pd.read_csv(R / "data/annotations/gt_balon_benja/gt_balon_por_frame.csv")
    meta = json.loads((R / "outputs/gt_balon_rapido/frames.json").read_text())["filas"]
    eleg = {int(r["frame"]): r["elegida"] for r in meta}
    gt["elegida"] = gt.frame.map(eleg)
    gt["con_candidata"] = gt.elegida.notna()
    # zona del juego (la del 14,9 %): tercio donde está la mediana de x de los jugadores
    pos = pd.read_csv(R / "outputs/diagnostico_26oct_b/posiciones_main.csv")
    r = pos[(pos.es_real == 1) & pos.x_m.between(0, 62) & pos.y_m.between(0, 40)]
    med = r.groupby("frame").x_m.median()
    fr = np.array(sorted(med.index))

    def x_juego(f):
        i = np.searchsorted(fr, f)
        cand = [fr[j] for j in (i - 1, i) if 0 <= j < len(fr)]
        return float(med[min(cand, key=lambda c: abs(c - f))])

    gt["x_juego"] = gt.frame.map(x_juego)
    gt["zona_juego"] = pd.cut(
        gt.x_juego, [-1, 62 / 3, 2 * 62 / 3, 63], labels=["cerca", "media", "lejos"]
    ).astype(str)
    gt = gt[gt.respuesta != "no_se"]
    gt["visible"] = gt.respuesta.isin(["acepta", "clic"])

    def corte(g) -> dict:
        n = len(g)
        vis = int(g.visible.sum())
        vis_cc = g[g.visible & g.con_candidata]
        acierta = int((vis_cc.respuesta == "acepta").sum())
        cc = g[g.con_candidata]
        fp = int((cc.respuesta == "rechaza_no_visible").sum())
        return {
            "frames": n,
            "visible_pct": round(100 * vis / max(n, 1), 1),
            "visible_ic95": wilson(vis, n),
            "recall_elegida_sobre_visibles_con_candidata": f"{acierta}/{len(vis_cc)}",
            "recall_pct": round(100 * acierta / max(len(vis_cc), 1), 1),
            "recall_ic95": wilson(acierta, len(vis_cc)),
            "falsos_positivos": f"{fp}/{len(cc)}",
            "fp_pct": round(100 * fp / max(len(cc), 1), 1),
            "fp_ic95": wilson(fp, len(cc)),
            "visible_sin_candidata": int((g.visible & ~g.con_candidata).sum()),
        }

    res = {
        "zona_de_la_hoja": {z: corte(g) for z, g in gt.groupby("zona")},
        "zona_del_juego": {z: corte(g) for z, g in gt.groupby("zona_juego")},
        "zona_del_juego_solo_sin_candidata": {
            z: corte(g) for z, g in gt[~gt.con_candidata].groupby("zona_juego")
        },
    }
    # balón inventado (provisional hasta la mini-hoja de control): candidata elegida donde el GT
    # dice que no hay balón, o donde el balón marcado está a > 2 m (escala local) del elegido
    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    inv = []
    for row in gt[gt.con_candidata].itertuples():
        e = row.elegida
        cx, cy = (e[0] + e[2]) / 2, (e[1] + e[3]) / 2
        if row.respuesta == "rechaza_no_visible":
            inv.append((row.frame, row.zona, row.zona_juego, "sin balón visible", None))
        elif row.respuesta == "clic":
            d_px = float(np.hypot(cx - row.x_px, cy - row.y_px))
            lim = 2.0 * escala_px_por_m(H, row.x_px, row.y_px)
            if d_px > lim:
                inv.append(
                    (
                        row.frame,
                        row.zona,
                        row.zona_juego,
                        "balón en otro sitio",
                        round(d_px),
                    )
                )
    n_cc = int(gt.con_candidata.sum())
    res["inventado_provisional"] = {
        "frames_con_candidata": n_cc,
        "inventados": len(inv),
        "pct": round(100 * len(inv) / max(n_cc, 1), 1),
        "ic95": wilson(len(inv), n_cc),
        "detalle": [
            {
                "frame": int(f),
                "relojes": f"{int(f / FPS // 60)}:{f / FPS % 60:04.1f} arch / "
                f"{int((f / FPS + 93) // 60)}:{(f / FPS + 93) % 60:04.1f} repr",
                "zona_hoja": z,
                "zona_juego": zj,
                "tipo": t,
                "dist_px": d,
            }
            for f, z, zj, t, d in inv
        ],
    }
    return res


if __name__ == "__main__":
    main()
