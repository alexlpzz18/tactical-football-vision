#!/usr/bin/env python
"""Diagnóstico 28-oct (f). Criterios en `docs/diagnostico_28oct_f.md`. SOLO mide.

Uso:
    python scripts/diag28f.py tiras     # tiras de recortes de la ventana de 1,5 s de cada error
    python scripts/diag28f.py recuento  # la marca contra el dueño de la caja que vio Alex
    python scripts/diag28f.py oraculo   # ruta 1: excluir las filas en cruce de las métricas
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/diagnostico_28oct_f"
FPS = 29.97002997002997
VENTANA_S = 1.5
VIDEO = R / "data/raw/benja_gredos_p1_20min.mp4"
ALTO_TIRA = 140
# oráculo
RADIO_EXCLUIR_M = 2.5
VENTANAS_FRAMES = [6, 10, 20]  # 3, 5 y 10 s (frames del GT a 0,5 s)
LIMITE_CENTROIDE, LIMITE_ANCHURA = 1.0, 1.5


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


# ── 1. tiras ──────────────────────────────────────────────────────────────────────────────────


def tiras() -> dict:
    import cv2

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    errores = json.loads((R / "outputs/diagnostico_28oct_c/equipo.json").read_text())[
        "errores"
    ]
    clave = {}
    import csv

    for r in csv.DictReader(
        open(R / "outputs/hoja_equipos/clave_equipo_por_obs_20min.csv")
    ):
        clave[r["imagen"]] = int(r["k"])
    cap = pickle.load(open(R / "outputs/diagnostico_26oct_b/captura_main.pkl", "rb"))
    cache = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    final = cap["final"]
    crudo = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(
            open(R / "data/tracking_benja/cache_detecciones_benja_p1.pkl", "rb")
        )["cache"]
    }
    medio = VENTANA_S / 2 * FPS
    casos = []
    for n, e in enumerate(errores):
        f0, ident = int(e["frame"]), int(e["id"])
        obs = sorted(
            (int(f), int(k))
            for f, k in cap["identidades"][ident - 1]
            if abs(int(f) - f0) <= medio
        )
        # la `k` de la hoja indexa el caché SIN filtrar por confianza; las identidades, el
        # filtrado. Se toma la detección de la identidad en f0 y se comprueba que es la caja
        # que vio Alex
        k0 = next(k for f, k in obs if f == f0)
        caja_hoja = [float(v) for v in crudo[f0][clave[e["imagen"]]][2:6]]
        caja_id = [float(v) for v in cache[f0][k0][2:6]]
        casos.append(
            {
                "n": n,
                "error": e,
                "k": k0,
                "obs": obs,
                "iou_con_hoja": iou(caja_hoja, caja_id),
            }
        )
    frames = sorted({f for c in casos for f, _ in c["obs"]})
    imgs = {}
    for f, img in leer_frames_ffmpeg(VIDEO, frames):
        imgs[f] = img
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "tiras").mkdir(exist_ok=True)
    resumen = []
    for c in casos:
        paneles, solapes, saltos, etiquetas = [], 0, 0, []
        prev = None
        for f, k in c["obs"]:
            dets = cache[f]
            d = dets[k]
            caja = [float(v) for v in d[2:6]]
            otras = [[float(v) for v in o[2:6]] for j, o in enumerate(dets) if j != k]
            if any(iou(caja, o) > 0.1 for o in otras):
                solapes += 1
            if prev is not None and np.hypot(d[0] - prev[0], d[1] - prev[1]) > 2.0:
                saltos += 1
            prev = d
            et = final.get((c["error"]["id"], f), "?")
            etiquetas.append(et)
            img = imgs[f].copy()
            for o in otras:
                cv2.rectangle(
                    img,
                    (int(o[0]), int(o[1])),
                    (int(o[2]), int(o[3])),
                    (160, 160, 160),
                    1,
                )
            color = (
                (0, 0, 255)
                if (f, k) == (int(c["error"]["frame"]), c["k"])
                else (0, 220, 0)
            )
            cv2.rectangle(
                img,
                (int(caja[0]), int(caja[1])),
                (int(caja[2]), int(caja[3])),
                color,
                1,
            )
            cx, cy = (caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2
            h = max(caja[3] - caja[1], 30) * 1.6
            x0, x1 = int(max(cx - h * 0.6, 0)), int(cx + h * 0.6)
            y0, y1 = int(max(cy - h / 2, 0)), int(cy + h / 2)
            rec = img[y0:y1, x0:x1]
            esc = ALTO_TIRA / max(rec.shape[0], 1)
            rec = cv2.resize(rec, None, fx=esc, fy=esc, interpolation=cv2.INTER_NEAREST)
            cv2.putText(
                rec,
                f"{(f - c['error']['frame']) / FPS:+.1f}s {et}",
                (2, 12),
                0,
                0.4,
                (255, 255, 255),
                1,
            )
            paneles.append(rec)
        ancho = max(p.shape[1] for p in paneles)
        paneles = [
            cv2.copyMakeBorder(p, 0, 0, 0, ancho - p.shape[1], cv2.BORDER_CONSTANT)
            for p in paneles
        ]
        filas = [np.hstack(paneles[i:][:8]) for i in range(0, len(paneles), 8)]
        w = max(fl.shape[1] for fl in filas)
        filas = [
            cv2.copyMakeBorder(fl, 0, 0, 0, w - fl.shape[1], cv2.BORDER_CONSTANT)
            for fl in filas
        ]
        e = c["error"]
        nombre = f"caso{c['n']:02d}_f{e['frame']}_id{e['id']}.png"
        cv2.imwrite(str(SALIDA / "tiras" / nombre), np.vstack(filas))
        resumen.append(
            {
                "caso": c["n"],
                "relojes": e["relojes"],
                "frame": e["frame"],
                "id": e["id"],
                "marca_alex": e["marca"],
                "etiqueta_sistema": e["etiqueta_observacion"],
                "cruce": e["cruce"],
                "iou_caja_identidad_con_caja_hoja": round(c["iou_con_hoja"], 3),
                "recortes_en_ventana": len(c["obs"]),
                "recortes_con_iou>0,1": solapes,
                "saltos_>2m": saltos,
                "etiquetas_en_ventana": "".join(x[0] if x else "?" for x in etiquetas),
                "tira": nombre,
            }
        )
    return {"casos": resumen}


# ── 1b. recuento contra el DUEÑO de la caja que vio Alex ─────────────────────────────────────


def recuento() -> dict:
    """La hoja casaba la posición SUAVIZADA del CSV con la detección más cercana en metros (en un
    cruce, a veces la de OTRA persona). Aquí se compara la marca con la etiqueta de la identidad
    que es DUEÑA de la caja que Alex vio en la hoja."""
    import csv

    cap = pickle.load(open(R / "outputs/diagnostico_26oct_b/captura_main.pkl", "rb"))
    cache = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    crudo = {
        e["frame_idx"]: e["dets"]
        for e in pickle.load(
            open(R / "data/tracking_benja/cache_detecciones_benja_p1.pkl", "rb")
        )["cache"]
    }
    duenos = {}
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            duenos[(int(f), int(k))] = i
    clave = list(
        csv.DictReader(open(R / "outputs/hoja_equipos/clave_equipo_por_obs_20min.csv"))
    )
    marcas = {
        r["imagen"]: r["equipo_correcto"]
        for r in csv.DictReader(
            open(
                R / "outputs/diagnostico_28oct_c/revision_equipo_por_obs_20min_alex.csv"
            )
        )
    }
    mapa = {"A": "A", "B": "B", "portero_A": "A", "portero_B": "B"}
    filas = []
    for r in clave:
        f = int(r["frame"])
        caja = [float(v) for v in crudo[f][int(r["k"])][2:6]]
        kf = [
            j
            for j, d in enumerate(cache[f])
            if iou(caja, [float(v) for v in d[2:6]]) > 0.99
        ]
        dueno = duenos.get((f, kf[0])) if kf else None
        # la ventana decide el A/B; los porteros (y el staff) los decide la posición, en el voto
        et = (cap["final"].get((dueno, f)) or cap["voto"].get(dueno)) if dueno else None
        sis = str(et).replace("portero_", "") if et else None
        filas.append(
            {
                "imagen": r["imagen"],
                "cruce": r["cruce"] == "True",
                "dueno_es_la_identidad_de_la_fila": dueno == int(r["id"]),
                "con_dueno": dueno is not None,
                "error": dueno is not None
                and mapa.get(marcas[r["imagen"]], "ERR") != sis,
            }
        )

    def corte(g):
        v = [x for x in g if x["con_dueno"]]
        k = sum(x["error"] for x in v)
        return {
            "errores": f"{k}/{len(v)}",
            "pct": round(100 * k / max(len(v), 1), 1),
            "ic95": _wilson(k, len(v)),
        }

    return {
        "filas": len(filas),
        "caja_de_la_hoja_de_otra_identidad": sum(
            x["con_dueno"] and not x["dueno_es_la_identidad_de_la_fila"] for x in filas
        ),
        "caja_sin_identidad_(excluidas)": sum(not x["con_dueno"] for x in filas),
        "total": corte(filas),
        "cruce": corte([x for x in filas if x["cruce"]]),
        "no_cruce": corte([x for x in filas if not x["cruce"]]),
        "errores": [x["imagen"] for x in filas if x["error"]],
    }


def _wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * max(c - h, 0.0), 1), round(100 * min(c + h, 1.0), 1)]


# ── 2. oráculo de la ruta 1 ───────────────────────────────────────────────────────────────────


def _excluir(df, eq, k):
    """Máscara de filas a ≤ 2,5 m de alguien del equipo contrario (según `eq`), por frame."""
    x, y = df.x.to_numpy(), df.y.to_numpy()
    fuera = np.zeros(len(df), bool)
    for f in np.unique(k):
        s = np.where(k == f)[0]
        d = np.hypot(x[s, None] - x[None, s], y[s, None] - y[None, s])
        fuera[s] = ((d <= RADIO_EXCLUIR_M) & (eq[s, None] != eq[None, s])).any(axis=1)
    return fuera


def oraculo(p_cruce: float | None = None, p_fuera: float | None = None) -> dict:
    import importlib.util

    spec = importlib.util.spec_from_file_location("d28e", R / "scripts/diag28e.py")
    d28e = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d28e)
    pc = d28e.P_CRUCE if p_cruce is None else p_cruce
    pf = d28e.P_FUERA if p_fuera is None else p_fuera
    df, n_ep = d28e._cargar_gt()
    n_frames = int(df.k.max()) + 1
    eq = df["eq"].to_numpy()
    k = df.k.to_numpy()
    cruce = df.cruce.to_numpy()
    episodio = df.episodio.to_numpy()
    verdad = d28e._por_frame(df, eq, n_frames)
    otro = np.where(eq == "A", "B", "A")
    excl_gt = _excluir(df, eq, k)
    res = {}
    for modo in ("filas", "rachas"):
        acum = {(v, t): ([], []) for v in ("i", "ii", "ii_gt") for t in VENTANAS_FRAMES}
        descartadas, descartadas_gt = [], float(excl_gt.mean())
        for semilla in range(d28e.REPETICIONES):
            rng = np.random.default_rng(semilla)
            if modo == "filas":
                inv = rng.random(len(eq)) < np.where(cruce, pc, pf)
            else:
                ep_inv = rng.random(n_ep) < pc
                inv = np.where(
                    cruce,
                    ep_inv[np.maximum(episodio, 0)],
                    rng.random(len(eq)) < pf,
                )
            eq2 = np.where(inv, otro, eq)
            excl = _excluir(df, eq2, k)
            descartadas.append(excl.mean())
            w_i = d28e._por_frame(df, eq2, n_frames)
            w_ii = d28e._por_frame(df[~excl], eq2[~excl], n_frames)
            w_iig = d28e._por_frame(df[~excl_gt], eq2[~excl_gt], n_frames)
            for t in VENTANAS_FRAMES:
                for v, w in (("i", w_i), ("ii", w_ii), ("ii_gt", w_iig)):
                    dc, da = d28e._ventanas(verdad, w, t)
                    acum[(v, t)][0].append(dc)
                    acum[(v, t)][1].append(da)
        tabla = {}
        for (v, t), (lc, la) in acum.items():
            dc, da = np.concatenate(lc), np.concatenate(la)
            p95c, p95a = float(np.percentile(dc, 95)), float(np.percentile(da, 95))
            tabla.setdefault(v, {})[f"{t * d28e.PASO_GT_S:g} s"] = {
                "centroide_p95": round(p95c, 3),
                "anchura_p95": round(p95a, 3),
                "pares": int(len(dc)),
                "cumple": bool(p95c <= LIMITE_CENTROIDE and p95a <= LIMITE_ANCHURA),
            }
        res[modo] = {
            "tabla": tabla,
            "filas_descartadas_pct_(etiquetas_inyectadas)": round(
                100 * float(np.mean(descartadas)), 1
            ),
            "filas_descartadas_pct_(etiquetas_reales)": round(100 * descartadas_gt, 1),
            "ventana_mas_corta_que_cumple": {
                v: next((kk for kk, x in tabla[v].items() if x["cumple"]), None)
                for v in tabla
            },
        }
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["tiras", "recuento", "oraculo"])
    ap.add_argument("--p-cruce", type=float, default=None)
    ap.add_argument("--p-fuera", type=float, default=None)
    ap.add_argument("--sufijo", default="")
    args = ap.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)
    if args.accion == "oraculo":
        res = oraculo(args.p_cruce, args.p_fuera)
    else:
        res = {"tiras": tiras, "recuento": recuento}[args.accion]()
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=float)
    (SALIDA / f"{args.accion}{args.sufijo}.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
