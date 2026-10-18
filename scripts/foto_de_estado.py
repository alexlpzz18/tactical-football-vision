#!/usr/bin/env python
"""La foto completa: las dos patas, en las cinco métricas que importan.

Encargo de Alex: *"benja y Villaviciosa, antes de esta semana y ahora, en
centroide, anchura, ocupación, recuento correcto por equipo y
observaciones con equipo equivocado. Quiero la foto completa."*

Todo contra el GT de CVAT de cada pata, con el pipeline de PRODUCCIÓN tal
y como está hoy (no una variante de banco).

⚠️ Dos cosas que hay que leer con la tabla:

- **El casado GT↔sistema es 1-a-1** (asignación óptima, radio 2 m). Con
  "la fila más cercana" el error de equipo salía 4,0 % y el 79 % de eso
  eran detecciones que FALTABAN, no clasificación. Y el NIVEL depende del
  radio: 3,1 % a 1,0 m · 6,5 % a 5,0.
- **El GT del benjamín cubre 29,5 s** y el de Villaviciosa 60 s. Son
  ventanas cortas: la tabla dice dónde estamos, no cuánto aguanta.

Uso:
    python scripts/foto_de_estado.py
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

logger = logging.getLogger("foto")
RADIO = 2.0


def eq_base(e):
    e = str(e)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def medir(csv, gt_m, gt_px, largo, ancho):
    from oraculos import metricas_producto
    from scipy.optimize import linear_sum_assignment

    df = pd.read_csv(csv)
    df = df[df.es_real == 1].copy()
    df["eqb"] = df.etiqueta.map(eq_base)

    # ── centroide, anchura, ocupación ────────────────────────────────
    pf, pf_gt = {}, {}
    for _, r in df[df.eqb.isin(["A", "B"])].iterrows():
        if r.frame in gt_m:
            pf.setdefault((int(r.frame), r.eqb), []).append((r.x_m, r.y_m))
    for f, obs in gt_m.items():
        for o in obs:
            e = eq_base(o.team)
            if e in ("A", "B"):
                pf_gt.setdefault((f, e), []).append((float(o.pos[0]), float(o.pos[1])))
    v = metricas_producto(pf_gt).set_index(["frame", "equipo"])
    m = (
        metricas_producto(pf)
        .set_index(["frame", "equipo"])
        .join(v, rsuffix="_gt", how="inner")
    )
    err = np.hypot(m.cx - m.cx_gt, m.cy - m.cy_gt)
    anch = (m.ancho - m.ancho_gt).abs()

    def ocupacion(p):
        z = {}
        for (_f, e), pts in p.items():
            for x, y in pts:
                k = (e, min(int(x / largo * 3), 2), min(int(y / ancho * 3), 2))
                z[k] = z.get(k, 0) + 1
        t = sum(z.values()) or 1
        return {k: n / t for k, n in z.items()}

    oc, ocg = ocupacion(pf), ocupacion(pf_gt)
    dif_oc = sum(abs(oc.get(k, 0) - ocg.get(k, 0)) for k in set(oc) | set(ocg)) / 2

    # ── equipo equivocado y recuento, con casado 1-a-1 ───────────────
    mal = casadas = 0
    ok_a = ok_b = ok_2 = n_frames = 0
    for f in sorted(set(df.frame) & set(gt_m)):
        sub = df[df.frame == f]
        gente = [o for o in gt_m[f] if eq_base(o.team) in ("A", "B")]
        if not gente:
            continue
        n_frames += 1
        n_gt = Counter(eq_base(o.team) for o in gente)
        n_s = Counter(sub[sub.eqb.isin(["A", "B"])].eqb)
        ok_a += n_s["A"] == n_gt["A"]
        ok_b += n_s["B"] == n_gt["B"]
        ok_2 += (n_s["A"] == n_gt["A"]) and (n_s["B"] == n_gt["B"])
        if not len(sub):
            continue
        xy = sub[["x_m", "y_m"]].to_numpy()
        etq = sub.eqb.to_numpy()
        coste = np.hypot(
            xy[None, :, 0] - np.array([o.pos[0] for o in gente])[:, None],
            xy[None, :, 1] - np.array([o.pos[1] for o in gente])[:, None],
        )
        coste = np.where(coste > RADIO, 1e6, coste)
        fi, fj = linear_sum_assignment(coste)
        pares = [(i, j) for i, j in zip(fi, fj) if coste[i, j] < 1e6]
        for i, j in pares:
            if etq[j] in ("A", "B"):
                casadas += 1
                mal += etq[j] != eq_base(gente[i].team)
    # las etiquetas A/B son arbitrarias: se elige el emparejamiento bueno
    mal = min(mal, casadas - mal)
    return {
        "centroide": err.median(),
        "anchura": anch.median(),
        "ocupacion": 100 * dif_oc,
        "ok_A": 100 * ok_a / max(n_frames, 1),
        "ok_B": 100 * ok_b / max(n_frames, 1),
        "ok_2": 100 * ok_2 / max(n_frames, 1),
        "mal": 100 * mal / max(casadas, 1),
        "n": casadas,
    }


def config_de_antes(cfg_eq):
    """Reconstruye el estado ANTERIOR a esta semana, apagando lo adoptado.

    Todas las adopciones de la semana son de config, así que el "antes" se
    reconstruye sin tocar código — y sobre todo **con el mismo arnés**,
    que es la única forma de que las dos columnas sean comparables. Los
    números históricos de docs/ salieron de bancos distintos (uno sin
    etiqueta por observación, con casado a la fila más cercana) y NO son
    comparables con estos: por eso no se copian aquí.
    """
    import copy

    c = copy.deepcopy(cfg_eq)
    # portero por CONJUNTO -> la regla de área que había antes
    c.setdefault("porteros", {})["metodo"] = "area"
    # catálogo arbitral por observación -> por identidad
    c.setdefault("agregacion", {}).setdefault("por_observacion", {})
    c["agregacion"]["por_observacion"]["catalogo_arbitral"] = False
    # staff con distancia CON SIGNO -> sin entrar en el campo
    c.setdefault("staff", {})["tolerancia_lento_m"] = 0.0
    return c


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--villa-csv", default=None, help="CSV alternativo de Villaviciosa")
    p.add_argument(
        "--antes",
        action="store_true",
        help="mide el estado ANTERIOR a esta semana, con el mismo arnés",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    csv_benja = (
        "data/tracking_benja/posiciones_benja_p1_ANTES.csv"
        if args.antes
        else "data/tracking_benja/posiciones_benja_p1_v2.csv"
    )
    csv_villa = (
        "data/tracking/posiciones_v4pre_ANTES.csv"
        if args.antes
        else (args.villa_csv or "data/tracking/posiciones_v4pre_hoy.csv")
    )
    patas = [
        (
            "benjamín (F7)",
            csv_benja,
            "data/annotations/gt_benja/annotations.xml",
            "data/calibracion_benja/homografia_benja.npy",
            9750,
            62.0,
            40.0,
        ),
        (
            "Villaviciosa (F11)",
            csv_villa,
            "data/annotations/ground_truth_tracking/annotations.xml",
            "data/calibracion/homografia.npy",
            7500,
            105.0,
            68.0,
        ),
    ]
    filas = {}
    for nombre, csv, gt, homo, off, largo, ancho in patas:
        if not Path(csv).exists():
            print(f"  (falta {csv})")
            continue
        H = np.load(homo)
        gt_m = gt_a_por_frame(parsear_cvat(gt), H, off, 15)
        filas[nombre] = medir(csv, gt_m, None, largo, ancho)

    print(
        f"\n{'ANTES de esta semana' if args.antes else 'AHORA'} "
        f"— mismo arnés en las dos columnas"
    )
    cab = (
        f"{'pata':<22}{'centroide':>11}{'anchura':>9}{'ocup':>8}"
        f"{'A ok':>7}{'B ok':>7}{'ambos':>7}{'eq. mal':>9}{'n':>7}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    for nombre, r in filas.items():
        print(
            f"{nombre:<22}{r['centroide']:>10.2f}m{r['anchura']:>8.2f}m"
            f"{r['ocupacion']:>7.1f}%{r['ok_A']:>6.0f}%{r['ok_B']:>6.0f}%"
            f"{r['ok_2']:>6.0f}%{r['mal']:>8.1f}%{r['n']:>7}"
        )


if __name__ == "__main__":
    main()
