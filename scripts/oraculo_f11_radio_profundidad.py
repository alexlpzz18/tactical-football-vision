#!/usr/bin/env python
"""Opción 3 del embudo lejano (27-nov-2026): el oráculo de F11 con un radio que crece con la
profundidad, y el efecto de la mediana espacial en centroide, líneas y anchura.

Dos preguntas de Alex:

1. **¿Cuánto del error viene de verdad de la PRESENCIA?** Con el radio fijo de 2 m, en el fondo
   (1 px de pie ≈ 0,9 m de profundidad) el temblor normal del pie cuenta como «falta». Aquí una fila
   casa con una persona si está a ≤ max(2 m, K px × metros por píxel en el pie de esa persona). K es
   el p90 de la diferencia vertical (px) entre el pie de la detección y el del GT en las parejas
   casadas por caja del tercio lejano (se mide, no se elige). Con ese casado se repite la escalera
   de oráculos y Shapley, y el criterio («arreglar solo faltan baja la anchura > 30 %»).

2. **¿Mediana en vez de media?** Sobre el sistema SIN arreglos, contra el GT calculado con el MISMO
   estimador (y también contra la media del GT):
   - centroide: media frente a mediana;
   - líneas (defensa, medio, ataque: corte 1D óptimo en x, como la superposición): media frente a
     mediana dentro de cada línea;
   - anchura: máx − mín (la de hoy) frente a 2.º máx − 2.º mín. ⚠️ Recortar extremos en la anchura
     borra al lateral o extremo que la define: se informa para verlo, no como propuesta.

Solo lee el CSV de producción de `main` (el del oráculo).

Uso:
    python scripts/oraculo_f11_radio_profundidad.py \\
        --csv outputs/literatura/banco/villa/posiciones_actual.csv \\
        --salida outputs/oraculo_f11_radio
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

from desglose_del_error import _valor_por_subconjunto  # noqa: E402
from embudo_tercio_lejano import casar_cajas  # noqa: E402
from src.evaluation import desglose_error as de  # noqa: E402
from src.evaluation.gt_parser import parsear_cvat  # noqa: E402
from superposicion_tactica import cortes_1d  # noqa: E402

GT = R / "data/annotations/ground_truth_tracking/annotations.xml"
HOMOGRAFIA = R / "data/calibracion/homografia.npy"
CACHE = R / "data/tracking/cache_detecciones_v4pre.pkl"
OFFSET, PASO, ANCHO, RADIO = 7500, 15, 68.0, 2.0


def metros(H, u, v):
    p = H @ np.array([u, v, 1.0])
    return p[:2] / p[2]


def gt_con_pies(H) -> dict:
    """{frame: [(equipo, x, y, caja, metros_por_px_vertical)]} (solo A/B)."""
    gt = {}
    for tr in parsear_cvat(GT):
        for c in tr.cajas:
            e = de.equipo_de_etiqueta(c.team if c.team is not None else tr.team)
            if e not in de.EQUIPOS:
                continue
            u, v = (c.xtl + c.xbr) / 2, c.ybr
            p, q = metros(H, u, v), metros(H, u, v + 1)
            gt.setdefault(OFFSET + PASO * c.frame_local, []).append(
                (
                    e,
                    float(p[0]),
                    float(p[1]),
                    (c.xtl, c.ytl, c.xbr, c.ybr),
                    float(np.hypot(*(q - p))),
                )
            )
    return gt


def k_px_medido(gt: dict) -> float:
    """p90 de |pie de detección − pie del GT| en vertical (px), tercio lejano, casado por caja."""
    crudo = {e["frame_idx"]: e["dets"] for e in pickle.load(open(CACHE, "rb"))["cache"]}
    dif = []
    for f, ps in gt.items():
        g = np.array([p[3] for p in ps], float)
        dd = np.array([d[2:6] for d in crudo.get(f, [])], float).reshape(-1, 4)
        for i, j in casar_cajas(g, dd).items():
            if ps[i][2] >= ANCHO * 2 / 3:
                dif.append(abs(dd[j, 3] - g[i, 3]))
    return float(np.percentile(dif, 90))


def casar(f, personas, x, y, etq, radios) -> de.FrameCasado:
    """`casar_frame` con un radio POR PERSONA (mismo húngaro, misma segunda pasada)."""
    ps = [de.Persona(e, px, py) for e, px, py in personas]
    persona_de_fila = {}
    if ps and len(x):
        coste = np.hypot(
            x[None, :] - np.array([p.x for p in ps])[:, None],
            y[None, :] - np.array([p.y for p in ps])[:, None],
        )
        coste = np.where(coste > np.asarray(radios)[:, None], 1e6, coste)
        for i, j in zip(*linear_sum_assignment(coste)):
            if coste[i, j] < 1e6:
                ps[i].fila = int(j)
                persona_de_fila[int(j)] = int(i)
    etiquetas = np.array([de.equipo_de_etiqueta(e) for e in etq], dtype=object)
    pareja = de._emparejar_desplazadas(
        ps, x, y, etiquetas, persona_de_fila, de.RADIO_PAREJA_M
    )
    return de.FrameCasado(f, ps, x, y, etiquetas, persona_de_fila, pareja)


def construir(gt, reales, radio_de) -> list:
    por_frame = {f: g for f, g in reales.groupby("frame")}
    frames = []
    for f in sorted(gt):
        s = por_frame.get(f)
        x, y, e = (
            (s.x_m.to_numpy(), s.y_m.to_numpy(), s.etiqueta.to_numpy())
            if s is not None
            else (np.array([]), np.array([]), np.array([], dtype=object))
        )
        ps = gt[f]
        frames.append(
            casar(
                f, [(p[0], p[1], p[2]) for p in ps], x, y, e, [radio_de(p) for p in ps]
            )
        )
    return frames


def resumen_escalera(frames) -> dict:
    filas, _desc = de.escalera_por_frame_equipo(frames)
    Rr = pd.DataFrame(filas)
    lejos = [p for fc in frames for p in fc.personas if p.y >= ANCHO * 2 / 3]
    out = {
        "faltan_tercio_lejano_pct": round(
            100 * np.mean([p.fila is None for p in lejos]), 1
        ),
        "faltan_total_pct": round(
            100 * np.mean([p.fila is None for fc in frames for p in fc.personas]), 1
        ),
    }
    for m in ("centroide", "ancho", "prof"):
        v = _valor_por_subconjunto(Rr, m, "media")
        sh = de.shapley(v)
        base = v[frozenset()]
        out[m] = {
            "sistema_m": round(base, 2),
            "shapley_pct": {k: round(100 * sh[k] / base) for k in de.FACTORES},
            "solo_faltan_baja_pct": round(100 * (1 - v[frozenset({"MIS"})] / base)),
            "solo_localizacion_baja_pct": round(
                100 * (1 - v[frozenset({"LOC"})] / base)
            ),
        }
    return out


def lineas(P: np.ndarray, est) -> list[float]:
    if len(P) < 6:
        return []
    orden = np.argsort(P[:, 0])
    grupos = cortes_1d(P[orden, 0], 3)
    return [float(est(g)) for g in grupos]


def estimadores(frames) -> dict:
    """Error del sistema SIN arreglos con cada estimador (contra el GT con el mismo estimador)."""
    nombres = ("centroide_media", "centroide_mediana", "centroide_mediana_vs_media_gt",
               "lineas_media", "lineas_mediana", "ancho_max_min", "ancho_2o")  # fmt: skip
    err = {k: [] for k in nombres}

    def ancho2(P):
        y = np.sort(P[:, 1])
        return y[-2] - y[1] if len(y) >= 4 else np.nan

    for fc in frames:
        for eq in de.EQUIPOS:
            V, S = de.conjunto_gt(fc, eq), de.conjunto_del_equipo(fc, eq)
            if len(V) < 3 or len(S) < 3:
                continue
            err["centroide_media"].append(np.hypot(*(S.mean(0) - V.mean(0))))
            err["centroide_mediana"].append(
                np.hypot(*(np.median(S, 0) - np.median(V, 0)))
            )
            err["centroide_mediana_vs_media_gt"].append(
                np.hypot(*(np.median(S, 0) - V.mean(0)))
            )
            err["ancho_max_min"].append(abs(np.ptp(S[:, 1]) - np.ptp(V[:, 1])))
            err["ancho_2o"].append(abs(ancho2(S) - ancho2(V)))
            for nombre, est in (
                ("lineas_media", np.mean),
                ("lineas_mediana", np.median),
            ):
                a, b = lineas(S, est), lineas(V, est)
                if a and b:
                    err[nombre].append(
                        float(np.mean(np.abs(np.array(a) - np.array(b))))
                    )
    return {
        k: {"media_m": round(float(np.nanmean(v)), 2),
            "mediana_m": round(float(np.nanmedian(v)), 2), "n": len(v)}
        for k, v in err.items()
    }  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    H = np.load(HOMOGRAFIA)
    gt = gt_con_pies(H)
    reales = pd.read_csv(a.csv)
    reales = reales[reales.es_real == 1].reset_index(drop=True)
    k = k_px_medido(gt)
    fijo = construir(gt, reales, lambda p: RADIO)
    escalado = construir(gt, reales, lambda p: max(RADIO, k * p[4]))
    radios_lejos = [
        max(RADIO, k * p[4]) for ps in gt.values() for p in ps if p[2] >= ANCHO * 2 / 3
    ]
    res = {
        "k_px_p90_pie_vertical": round(k, 2),
        "radio_tercio_lejano_m_p10_p50_p90": [
            round(float(v), 2) for v in np.percentile(radios_lejos, [10, 50, 90])
        ],
        "radio_fijo_2m": resumen_escalera(fijo),
        "radio_por_profundidad": resumen_escalera(escalado),
        "estimadores_sistema_sin_arreglos": estimadores(fijo),
    }
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
