#!/usr/bin/env python
"""¿El desplazamiento hacia la cámara está en la CAJA del detector o en el CLIC del GT?

Solo medición, local, sin tocar producción. El CRITERIO de abajo se commitea ANTES de medir.

Contexto (docs/traza_por_etapas.md): las filas «mal puestas» 2-5 m del desglose (DES, el 17 % del
error del centroide) están desplazadas en profundidad y el 85 % hacia la cámara, y lo mismo aparece
ya en la caja cruda. El GT del benjamín es un CLIC por persona (`data/annotations/gt_benja/
clics.csv`, sin corregir) que el XML guarda BAJADO 0,129 × el alto de la caja más cercana
(`src/evaluation/correccion_pies.py`; +7 px de mediana).

Se compara el PIE de la caja del detector (centro del borde inferior) con el clic sin corregir y
con el corregido, por franjas de alto de caja. dy > 0 = el pie de la caja está MÁS ABAJO en la
imagen que el clic = más cerca de la cámara.

⚠️ Aritmética antes de medir: la corrección solo BAJA el clic, así que dy_sin = dy_corr + corrección
> dy_corr. El signo solo puede cambiar si dy_corr < 0 < dy_sin (la corrección se pasa). Si en las
filas mal puestas dy_corr ya es > 0, el signo no puede cambiar y lo que hay que mirar es el TAMAÑO.

El emparejado caja↔clic NO se condiciona en la distancia vertical (que es lo que se mide): coste
= |dx| / ancho de caja + lo que el clic SIN corregir cae FUERA de la caja (alargada un 25 % por
abajo) / alto. Húngaro por frame, puerta coste < 1.

Uso:
    python scripts/sesgo_pies_gt.py --traza DIR    # DIR de traza_por_etapas.py (casos.csv)
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

# ── Fijado ANTES de medir (commit aparte) ─────────────────────────────────────
CRITERIO = {
    "franjas_alto_px": [0, 30, 45, 60, 90, 1e9],
    "puerta_coste": 1.0,
    "alargar_abajo_frac": 0.25,
    # 1) la pregunta de Alex: si la mediana de dy cambia de signo entre el clic sin corregir y el
    #    corregido EN LAS FILAS MAL PUESTAS, el sesgo es un artefacto del GT.
    # 2) si no cambia: ¿es la CAJA? Lo es si en las filas mal puestas la caja es anormalmente alta
    #    (alto implícito mediano ≥ 1,3 × el de las parejas normales: dos cuerpos o la caja estirada)
    #    o su dy en FRACCIÓN de alto es ≥ 2 × el de las normales.
    "caja_alta_factor": 1.3,
    "dy_frac_factor": 2.0,
}
OFFSET_GT, PASO_GT = 9750, 15


def emparejar(cajas: list, clics: list, crit: dict = CRITERIO) -> list[tuple[int, int]]:
    """Pares (índice de clic, índice de caja), 1-a-1, sin mirar dónde cae el pie."""
    from scipy.optimize import linear_sum_assignment

    if not cajas or not clics:
        return []
    coste = np.full((len(clics), len(cajas)), 1e6)
    for i, (u, v) in enumerate(clics):
        for j, (x1, y1, x2, y2) in enumerate(cajas):
            w, h = max(x2 - x1, 1.0), max(y2 - y1, 1.0)
            abajo = y2 + crit["alargar_abajo_frac"] * h
            fuera = max(0.0, y1 - v, v - abajo)
            coste[i, j] = abs((x1 + x2) / 2.0 - u) / w + fuera / h
    pares = []
    for i, j in zip(*linear_sum_assignment(coste)):
        if coste[i, j] < crit["puerta_coste"]:
            pares.append((int(i), int(j)))
    return pares


def cambia_de_signo(dy_sin: list[float], dy_corr: list[float]) -> bool:
    return bool(np.sign(np.median(dy_sin)) != np.sign(np.median(dy_corr)))


def main() -> None:
    import pandas as pd
    import yaml

    from src.evaluation.gt_parser import parsear_cvat, proyectar_punto
    from src.tracking.cache_io import cargar_cache
    from src.tracking.plausibilidad_fisica import (
        medidas_implicadas,
        referencia_del_partido,
    )

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--traza", required=True)
    args = ap.parse_args()
    trabajo = Path(args.traza)

    cfg = yaml.safe_load(open(R / "configs/processor_benja_parte_entera.yaml"))
    H = np.load(R / cfg["rutas"]["homografia"])
    datos = cargar_cache(R / cfg["rutas"]["cache"])
    cache = [
        e for e in datos["cache"] if OFFSET_GT <= e["frame_idx"] <= OFFSET_GT + 15 * 60
    ]
    med = medidas_implicadas(cache, H)
    ref = referencia_del_partido(medidas_implicadas(datos["cache"], H))
    por_frame = {e["frame_idx"]: e["dets"] for e in cache}

    clics = pd.read_csv(R / "data/annotations/gt_benja/clics.csv")
    clics["track"] = clics.jugador - 1  # comprobado: id de la tabla = track del XML + 1
    corr = {}
    for t in parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"):
        for c in t.cajas:
            corr[(t.track_id, OFFSET_GT + PASO_GT * c.frame_local)] = c.ybr
    C = pd.read_csv(trabajo / "casos.csv")
    # Filas mal puestas = sin fila a 2 m pero con fila a 2-5 m. Pandas renombra las columnas
    # con «@» en itertuples: se leen por posición.
    col2, col5 = C.columns.get_loc("e_csv@2"), C.columns.get_loc("e_csv@5")
    des = {
        (int(r[0]), int(r[1]))
        for r in C.itertuples(index=False)
        if not r[col2] and r[col5]
    }

    filas = []
    for f, g in clics.groupby("frame"):
        dets = por_frame.get(f, [])
        cajas = [tuple(d[2:6]) for d in dets]
        pts = list(zip(g.x_px, g.y_px))
        for i, j in emparejar(cajas, pts):
            r = g.iloc[i]
            x1, y1, x2, y2 = cajas[j]
            h = y2 - y1
            y_corr = corr[(int(r.track), f)]
            pie = proyectar_punto((x1 + x2) / 2.0, y2, H)
            p_sin = proyectar_punto(r.x_px, r.y_px, H)
            p_corr = proyectar_punto(r.x_px, y_corr, H)
            filas.append({
                "frame": f, "track": int(r.track), "alto_px": h,
                "dy_sin_px": y2 - r.y_px, "dy_corr_px": y2 - y_corr,
                # profundidad: la cámara está detrás de x = 0, así que «hacia la cámara» es x menor
                "dx_sin_m": p_sin[0] - pie[0], "dx_corr_m": p_corr[0] - pie[0],
                "alto_implicito_frac": med.get((f, j), (np.nan,))[0] / ref,
                "des": (f, int(r.track)) in des,
            })  # fmt: skip
    D = pd.DataFrame(filas)
    D["franja"] = pd.cut(D.alto_px, CRITERIO["franjas_alto_px"], right=False)

    def resumen(sub):
        return {
            "n": int(len(sub)),
            "dy_sin_px_mediana": float(sub.dy_sin_px.median()),
            "dy_corr_px_mediana": float(sub.dy_corr_px.median()),
            "dy_corr_frac_alto": float((sub.dy_corr_px / sub.alto_px).median()),
            "frac_dy_corr_pos": float((sub.dy_corr_px > 0).mean()),
            "hacia_camara_sin_m": float(sub.dx_sin_m.median()),
            "hacia_camara_corr_m": float(sub.dx_corr_m.median()),
            "alto_implicito_frac_mediana": float(sub.alto_implicito_frac.median()),
            "alto_px_mediana": float(sub.alto_px.median()),
        }

    normales, malas = D[~D.des], D[D.des]
    res = {
        "criterio": CRITERIO,
        "emparejados": int(len(D)),
        "de_814_clics": int(len(clics)),
        "filas_mal_puestas_en_casos": len(des),
        "filas_mal_puestas_emparejadas": int(len(malas)),
        "todas": resumen(D),
        "normales": resumen(normales),
        "mal_puestas": resumen(malas) if len(malas) else None,
        "por_franja": {
            str(k): {
                "todas": resumen(g),
                "mal_puestas": resumen(g[g.des]) if g.des.any() else None,
            }
            for k, g in D.groupby("franja", observed=True)
        },
    }
    if len(malas):
        m, n = res["mal_puestas"], res["normales"]
        res["signo_cambia_en_mal_puestas"] = cambia_de_signo(
            list(malas.dy_sin_px), list(malas.dy_corr_px)
        )
        res["signo_cambia_en_todas"] = cambia_de_signo(
            list(D.dy_sin_px), list(D.dy_corr_px)
        )
        res["caja_anormalmente_alta"] = bool(
            m["alto_implicito_frac_mediana"]
            >= CRITERIO["caja_alta_factor"] * n["alto_implicito_frac_mediana"]
        )
        res["dy_frac_excesivo"] = bool(
            m["dy_corr_frac_alto"]
            >= CRITERIO["dy_frac_factor"] * max(n["dy_corr_frac_alto"], 1e-9)
        )
    (trabajo / "sesgo_pies.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    D.to_csv(trabajo / "sesgo_pies_pares.csv", index=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
