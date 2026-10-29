#!/usr/bin/env python
"""Etiqueta por trozos de identidad cortados donde puede cambiar de persona. Criterios en
`docs/etiqueta_por_trozos.md`. SOLO mide: escribe un CSV APARTE; los de datos no se tocan.

Uso:
    python scripts/etiqueta_por_trozos.py --intento 1
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
CSV_MAIN = R / "outputs/diagnostico_26oct_b/posiciones_main.csv"
CSV_PARTE = R / "data/tracking_benja/posiciones_benja_p1.csv"
CRUDO = R / "data/tracking_benja/cache_detecciones_benja_p1.pkl"
HOMOGRAFIA = R / "data/calibracion_benja/homografia_benja.npy"
HOJA = R / "outputs/hoja_equipos"
FPS = 29.97002997002997
# intento 1 (docs/etiqueta_por_trozos.md)
RIVAL_M = 2.0
V_IMPOSIBLE_M_S = 12.0
JITTER_PX, K_JITTER = 3.5, 3.0
RADIO_CASADO_M = 2.0


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def equipo(et) -> str | None:
    et = str(et)
    return (
        "A" if et in ("A", "portero_A") else ("B" if et in ("B", "portero_B") else None)
    )


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── las etiquetas por trozo ──────────────────────────────────────────────────────────────────


def etiquetas_por_trozo(cap) -> tuple[dict, dict]:
    """{(id, frame): etiqueta nueva} para las observaciones A/B de identidades A/B."""
    from src.balon.tracking_balon import escala_px_por_m

    H = np.load(HOMOGRAFIA)
    Hinv = np.linalg.inv(H)
    cache = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    etq = {}
    pos = {}
    por_frame = {}
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            f, k = int(f), int(k)
            e = str(cap["final"].get((i, f)) or cap["voto"].get(i, "otro"))
            etq[(i, f)] = e
            d = cache[f][k]
            pos[(i, f)] = (float(d[0]), float(d[1]))
            por_frame.setdefault(f, []).append(i)
    # en cruce: rival del equipo contrario a ≤ 2 m en el mismo frame
    en_cruce = set()
    for f, ids in por_frame.items():
        xy = np.array([pos[(i, f)] for i in ids])
        eq = np.array([equipo(etq[(i, f)]) for i in ids], dtype=object)
        d = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
        for a, i in enumerate(ids):
            if eq[a] is None:
                continue
            rival = (d[a] <= RIVAL_M) & np.array(
                [e is not None and e != eq[a] for e in eq]
            )
            if rival.any():
                en_cruce.add((i, f))

    def m_por_px(x, y):
        p = Hinv @ np.array([x, y, 1.0])
        return 1.0 / escala_px_por_m(H, p[0] / p[2], p[1] / p[2])

    nuevas, stats = {}, Counter()
    largos = []
    for i, ident in enumerate(cap["identidades"], start=1):
        if str(cap["voto"].get(i)) not in ("A", "B"):
            continue  # porteros, staff y otro: los decide la posición, no se tocan
        frames = sorted({int(f) for f, _k in ident})
        trozos, actual = [], []
        prev = None
        for f in frames:
            if (i, f) in en_cruce:
                if actual:
                    trozos.append(actual)
                actual, prev = [], None
                stats["obs_en_cruce"] += 1
                continue
            if prev is not None:
                (x0, y0), (x1, y1) = pos[(i, prev)], pos[(i, f)]
                salto = np.hypot(x1 - x0, y1 - y0)
                dt = (f - prev) / FPS
                if (
                    salto > V_IMPOSIBLE_M_S * dt
                    and salto > K_JITTER * JITTER_PX * m_por_px(x1, y1)
                ):
                    trozos.append(actual)
                    actual = []
                    stats["cortes_por_salto"] += 1
            actual.append(f)
            prev = f
        if actual:
            trozos.append(actual)
        for tr in trozos:
            ab = [etq[(i, f)] for f in tr if etq[(i, f)] in ("A", "B")]
            if not ab:
                continue
            largos.append((tr[-1] - tr[0]) / FPS)
            c = Counter(ab).most_common()
            if len(c) > 1 and c[0][1] == c[1][1]:
                stats["trozos_empate"] += 1
                continue
            ganador = c[0][0]
            for f in tr:
                if etq[(i, f)] in ("A", "B") and etq[(i, f)] != ganador:
                    nuevas[(i, f)] = ganador
            stats["trozos"] += 1
    stats["observaciones_que_cambian"] = len(nuevas)
    lg = np.array(largos) if largos else np.zeros(1)
    stats["duracion_trozos_s_p50_p90_max"] = [
        round(float(np.median(lg)), 1),
        round(float(np.percentile(lg, 90)), 1),
        round(float(lg.max()), 1),
    ]
    return nuevas, dict(stats)


def csv_por_trozos(nuevas: dict, salida: Path) -> int:
    """El CSV de main con las etiquetas por trozo (las interpoladas siguen a su fila real)."""
    df = pd.read_csv(CSV_MAIN)
    nueva = df.etiqueta.astype(str).to_numpy().copy()
    cambiadas = 0
    for i, g in df.groupby("id_jugador"):
        reales = g[g.es_real == 1]
        if reales.empty:
            continue
        fr = reales.frame.to_numpy()
        vieja_r = reales.etiqueta.astype(str).to_numpy()
        nueva_r = np.array(
            [nuevas.get((int(i), int(f)), v) for f, v in zip(fr, vieja_r)]
        )
        if (nueva_r == vieja_r).all():
            continue
        idx = g.index.to_numpy()
        j = np.clip(np.searchsorted(fr, g.frame.to_numpy()), 0, len(fr) - 1)
        j0 = np.clip(j - 1, 0, len(fr) - 1)
        mas_cerca = np.where(
            np.abs(fr[j0] - g.frame.to_numpy()) <= np.abs(fr[j] - g.frame.to_numpy()),
            j0,
            j,
        )
        es_real = g.es_real.to_numpy() == 1
        for n, (k, r) in enumerate(zip(mas_cerca, es_real)):
            if r:
                k = int(np.searchsorted(fr, g.frame.to_numpy()[n]))
            if nueva_r[k] != vieja_r[k] and nueva[idx[n]] == vieja_r[k]:
                nueva[idx[n]] = nueva_r[k]
                cambiadas += 1
    df["etiqueta"] = nueva
    df.to_csv(salida, index=False)
    return cambiadas


# ── exactitud ────────────────────────────────────────────────────────────────────────────────


def errores_gt(ruta_csv: Path) -> dict:
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    ce = _mod("comparar_escalas")
    H = np.load(HOMOGRAFIA)
    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"), H, 9750, 15
    )
    df = pd.read_csv(ruta_csv)
    df = df[df.es_real == 1]
    pf = {f: g for f, g in df.groupby("frame")}
    frames = sorted(gt)
    malas, casadas = {}, 0
    for f in frames:
        gente = [o for o in gt[f] if ce.equipo_gt(o) in ("A", "B")]
        if f not in pf or not gente:
            continue
        sub = pf[f]
        xy = sub[["x_m", "y_m"]].to_numpy()
        et = sub.etiqueta.to_numpy()
        c = np.hypot(
            xy[None, :, 0] - np.array([o.pos[0] for o in gente])[:, None],
            xy[None, :, 1] - np.array([o.pos[1] for o in gente])[:, None],
        )
        c = np.where(c > RADIO_CASADO_M, 1e6, c)
        for a, b in zip(*linear_sum_assignment(c)):
            if c[a, b] >= 1e6:
                continue
            casadas += 1
            s = str(et[b]).replace("portero_", "")
            if s in ("A", "B") and s != ce.equipo_gt(gente[a]):
                malas[(f, int(gente[a].obj_id))] = True
    # episodios de error: rachas de frames del GT seguidos con la misma persona mal
    pos_de = {f: n for n, f in enumerate(frames)}
    episodios = []
    for p in sorted({p for _f, p in malas}):
        ks = sorted(pos_de[f] for f, q in malas if q == p)
        largo = 1
        for a, b in zip(ks[:-1], ks[1:]):
            if b == a + 1:
                largo += 1
            else:
                episodios.append(largo * 0.5)
                largo = 1
        episodios.append(largo * 0.5)
    e = np.array(episodios) if episodios else np.zeros(0)
    return {
        "errores": len(malas),
        "casadas": casadas,
        "episodios": len(e),
        "duracion_episodios_s_p50_max": (
            [float(np.median(e)), float(e.max())] if len(e) else [0.0, 0.0]
        ),
        "detalle": sorted(f"{f}:{p}" for f, p in malas),
    }


def errores_hoja(ruta_csv: Path, cap) -> dict:
    """La marca de Alex contra la etiqueta del DUEÑO de la caja que vio (auditoría del 28-oct)."""
    aud = _mod("auditar_hojas")
    filt = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    crudo = {e["frame_idx"]: e["dets"] for e in pickle.load(open(CRUDO, "rb"))["cache"]}
    dueno = {}
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            dueno[(int(f), int(k))] = i
    df = pd.read_csv(ruta_csv)
    et = {
        (int(r.frame), int(r.id_jugador)): str(r.etiqueta)
        for r in df[df.es_real == 1].itertuples()
    }
    marcas = {
        r["imagen"]: r["equipo_correcto"]
        for r in csv.DictReader(
            open(
                R / "outputs/diagnostico_28oct_c/revision_equipo_por_obs_20min_alex.csv"
            )
        )
    }
    mapa = {"A": "A", "B": "B", "portero_A": "A", "portero_B": "B"}
    malas = []
    for r in csv.DictReader(open(HOJA / "clave_equipo_por_obs_20min.csv")):
        f = int(r["frame"])
        caja = [float(v) for v in crudo[f][int(r["k"])][2:6]]
        kf = [
            j
            for j, d in enumerate(filt[f])
            if aud.iou(caja, [float(x) for x in d[2:6]]) > 0.99
        ]
        d = dueno.get((f, kf[0])) if kf else None
        s = et.get((f, d), str(cap["voto"].get(d, "?"))).replace("portero_", "")
        if mapa.get(marcas[r["imagen"]], "ERR") != s:
            malas.append(r["imagen"])
    return {"errores": len(malas), "filas": 120, "detalle": malas}


# ── pizarra ──────────────────────────────────────────────────────────────────────────────────


def cambios_pizarra(ruta_csv: Path, html: Path, titulo: str) -> dict:
    fp = _mod("fichas_pizarra")
    fp.pizarra(ruta_csv, fp.TRAMO, html, titulo, ["--histeresis-visual-s", "0"])
    Hinv = np.linalg.inv(np.load(HOMOGRAFIA))
    m = fp.metricas(html, fp.TRAMO, Hinv)
    return {
        "cambios_de_color_por_minuto": m["cambios_de_color_por_minuto"],
        "eventos_por_minuto": m["eventos_aparicion_desaparicion_por_minuto"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--intento", type=int, choices=[1, 2], default=1)
    args = ap.parse_args()
    salida = R / f"outputs/etiqueta_por_trozos_intento{args.intento}"
    salida.mkdir(parents=True, exist_ok=True)
    antes = {p.name: _sha(p) for p in (CSV_MAIN, CSV_PARTE)}
    cap = pickle.load(open(CAPTURA, "rb"))
    nuevas, stats = etiquetas_por_trozo(cap)
    csv_t = salida / "posiciones_por_trozos.csv"
    stats["filas_del_csv_que_cambian"] = csv_por_trozos(nuevas, csv_t)
    rel = "14:00-15:30 (archivo) · 15:33-17:03 (reproductor)"
    res = {
        "trozos": stats,
        "base": {
            "gt": errores_gt(CSV_MAIN),
            "hoja_120": errores_hoja(CSV_MAIN, cap),
            "pizarra": cambios_pizarra(CSV_MAIN, salida / "base.html", f"main · {rel}"),
        },
        "trozos_etiqueta": {
            "gt": errores_gt(csv_t),
            "hoja_120": errores_hoja(csv_t, cap),
            "pizarra": cambios_pizarra(
                csv_t,
                salida / "por_trozos.html",
                f"etiqueta por trozos (prueba) · {rel}",
            ),
        },
    }
    b, t = res["base"], res["trozos_etiqueta"]
    res["criterio"] = {
        "gt_no_sube": t["gt"]["errores"] <= b["gt"]["errores"],
        "hoja_no_sube": t["hoja_120"]["errores"] <= b["hoja_120"]["errores"],
        "pizarra_<=17,5_cambios_min": t["pizarra"]["cambios_de_color_por_minuto"]
        <= 17.5,
    }
    res["csv_de_datos_identicos"] = antes == {
        p.name: _sha(p) for p in (CSV_MAIN, CSV_PARTE)
    }
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=float)
    (salida / "resultado.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
