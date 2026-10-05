#!/usr/bin/env python
"""¿Qué 4-6 clics bastan para calibrar? Subconjuntos, regla y validadores. SOLO MEDICIÓN.

Plan: docs/plan_calibracion_semiautomatica.md. El CRITERIO se commiteó ANTES de medir.

Uso:
    python scripts/medir_subconjuntos_clics.py
"""

# ══════════════════════════ CRITERIO (fijado ANTES de medir) ══════════════════════════
CRITERIO = {
    "ks": (4, 5, 6),
    "borde_px": 30,  # R1/R2: puntos elegibles a ≥ esto del borde de la imagen
    # 1. R1 (k puntos con máxima envolvente convexa) ≤ base19 en los puntos no usados,
    #    en los DOS campos
    # 2. validador útil: AUC(buenos vs malos) ≥ esto en los DOS campos
    "auc_min": 0.80,
    "malo_factor": 2.0,  # "malo" = error ≥ factor × base19; "bueno" = error ≤ base19
    "tol_linea_px": 4.0,  # V1
    "margen_campo_m": 3.0,  # V2
    "frames_v2": 50,
}
# ═══════════════════════════════════════════════════════════════════════════════════════


def veredicto_regla(r1: dict, base19: dict) -> dict:
    """r1/base19: {campo: {k: error}} y {campo: {k: error}}. Por k: ¿cumple en todos?"""
    salida = {}
    for k in CRITERIO["ks"]:
        salida[k] = all(r1[c][k] <= base19[c][k] for c in r1)
    cumplen = [k for k, ok in salida.items() if ok]
    salida["k_minimo"] = min(cumplen) if cumplen else None
    return salida


def validador_util(aucs: dict) -> bool:
    """aucs: {campo: auc o None}. Útil si llega al mínimo en TODOS los campos."""
    return all(a is not None and a >= CRITERIO["auc_min"] for a in aucs.values())


# ──────────────────────────────────── medición ────────────────────────────────────
import itertools  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.homography import auto_calibracion as ac  # noqa: E402
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.validacion_video import mascara_cesped  # noqa: E402

CAMPOS = {
    "benja": dict(
        frame="data/calibracion_benja/frame.png",
        clics="data/calibracion_benja/puntos_marcados_benja.json",
        cache="data/tracking_benja/cache_detecciones_benja_p1.pkl",
        frames_cache=(9750, 10635),  # la ventana del GT
        largo=62.0, ancho=40.0, area=(26.0, 12.0), radio=6.0,
    ),
    "villa": dict(
        frame="data/calibracion/frame_corregido.png",
        clics="data/calibracion/puntos_marcados.json",
        cache="data/tracking/cache_detecciones_v4pre.pkl",
        frames_cache=(7500, 9000),
        largo=100.0, ancho=64.0, area=(40.32, 16.5), radio=9.15,
    ),
}  # fmt: skip
# Cruces de RECTAS (R2): sin el centro, los puntos del círculo ni los de penalti
NO_RECTAS = ("center", "circulo_", "penalty_")


def h_m2px(metros: np.ndarray, pixeles: np.ndarray):
    H, _ = cv2.findHomography(metros.astype(np.float32), pixeles.astype(np.float32), 0)
    return None if H is None else H / H[2, 2]


def errores(H, metros, pixeles) -> np.ndarray:
    px, delante = ac.proyectar(H, metros)
    e = np.hypot(*(px - pixeles).T)
    return np.where(delante & np.isfinite(e), e, 1e6)


def en_posicion_general(metros: np.ndarray) -> bool:
    """¿Hay 4 puntos sin tres alineados? (si no, la homografía no está determinada)"""
    for cuatro in itertools.combinations(range(len(metros)), 4):
        ok = True
        for tres in itertools.combinations(cuatro, 3):
            a, b, c = metros[list(tres)]
            if abs(np.cross(b - a, c - a)) / 2 < 0.5:  # triángulo de < 0,5 m²
                ok = False
                break
        if ok:
            return True
    return False


def auc(buenos: list, malos: list) -> float | None:
    """P(puntuación de un bueno > la de un malo); empates cuentan medio."""
    if not buenos or not malos:
        return None
    b, m = np.asarray(buenos)[:, None], np.asarray(malos)[None, :]
    return float(((b > m).sum() + 0.5 * (b == m).sum()) / (b.size * m.size))


def preparar_campo(c: dict) -> dict:
    img = cv2.imread(str(R / c["frame"]))
    _verde, campo = mascara_cesped(img)
    lineas = ac.mascara_lineas(img, campo)
    dt = cv2.distanceTransform((lineas == 0).astype(np.uint8), cv2.DIST_L2, 5)
    modelo = ac.puntos_modelo(
        c["largo"], c["ancho"], area_ancho=c["area"][0], area_prof=c["area"][1],
        radio_circulo=c["radio"],
    )  # fmt: skip
    d = cargar_cache(str(R / c["cache"]))
    en_ventana = [
        e
        for e in d["cache"]
        if c["frames_cache"][0] <= e["frame_idx"] <= c["frames_cache"][1]
    ]
    elegidos = en_ventana[:: max(1, len(en_ventana) // CRITERIO["frames_v2"])]
    pies = np.array(
        [((x[2] + x[4]) / 2, x[5]) for e in elegidos for x in e["dets"]], float
    )
    clics = json.load(open(R / c["clics"]))
    return dict(
        img=img, campo=campo, dt=dt, modelo=modelo, pies=pies, clics=clics,
        nombres=[k["nombre"] for k in clics],
        metros=np.array([k["metros"] for k in clics], float),
        pixeles=np.array([k["pixel"] for k in clics], float),
        h=img.shape[0], w=img.shape[1], **{k: c[k] for k in ("largo", "ancho")},
    )  # fmt: skip


def v1_cobertura(H, P) -> float:
    px, delante = ac.proyectar(H, P["modelo"])
    x, y = px[:, 0], px[:, 1]
    ok = (
        delante
        & np.isfinite(x)
        & (x >= 0)
        & (x < P["w"] - 1)
        & (y >= 0)
        & (y < P["h"] - 1)
    )
    xi, yi = np.rint(x[ok]).astype(int), np.rint(y[ok]).astype(int)
    en = P["campo"][yi, xi] > 0
    if en.sum() < 20:
        return 0.0
    return float((P["dt"][yi, xi][en] <= CRITERIO["tol_linea_px"]).mean())


def v2_dentro(H, P) -> float:
    Hi = np.linalg.inv(H)
    q = np.c_[P["pies"], np.ones(len(P["pies"]))] @ Hi.T
    m = q[:, :2] / q[:, 2:3]
    g = CRITERIO["margen_campo_m"]
    dentro = (
        (m[:, 0] >= -g)
        & (m[:, 0] <= P["largo"] + g)
        & (m[:, 1] >= -g)
        & (m[:, 1] <= P["ancho"] + g)
    )
    return float(dentro.mean())


def v3_coherencia(idx, P) -> float | None:
    if len(idx) < 5:
        return None
    e = []
    for j in idx:
        resto = [i for i in idx if i != j]
        H = h_m2px(P["metros"][resto], P["pixeles"][resto])
        if H is None:
            return None
        e.append(errores(H, P["metros"][[j]], P["pixeles"][[j]])[0])
    return float(np.median(e))


def medir_campo(nombre: str, P: dict) -> dict:
    n = len(P["nombres"])
    H19 = h_m2px(P["metros"], P["pixeles"])
    e19 = errores(H19, P["metros"], P["pixeles"])
    loo = []
    for j in range(n):
        resto = [i for i in range(n) if i != j]
        loo.append(
            errores(
                h_m2px(P["metros"][resto], P["pixeles"][resto]),
                P["metros"][[j]],
                P["pixeles"][[j]],
            )[0]
        )
    lejos = [
        i for i, (x, y) in enumerate(P["pixeles"])
        if min(x, y, P["w"] - 1 - x, P["h"] - 1 - y) >= CRITERIO["borde_px"]
    ]  # fmt: skip
    rectas = [i for i in lejos if not P["nombres"][i].startswith(NO_RECTAS)]
    print(
        f"\n════ {nombre}: {n} clics · a ≥ {CRITERIO['borde_px']} px del borde: {len(lejos)} · "
        f"cruces de rectas: {len(rectas)}"
    )
    print(
        f"  todos ({n}) en muestra: mediana {np.median(e19):.1f} px · dejando uno fuera "
        f"(honesta): {np.median(loo):.1f} px"
    )
    for i in np.argsort(loo)[::-1][:5]:
        print(
            f"    peor dejando uno fuera: {P['nombres'][i]:<24} {loo[i]:7.1f} px "
            f"(en muestra {e19[i]:.1f})"
        )
    filas = []
    for k in CRITERIO["ks"]:
        for idx in itertools.combinations(range(n), k):
            idx = list(idx)
            fuera = [i for i in range(n) if i not in idx]
            if not en_posicion_general(P["metros"][idx]):
                filas.append(dict(k=k, idx=idx, degenerado=True))
                continue
            H = h_m2px(P["metros"][idx], P["pixeles"][idx])
            if H is None:
                filas.append(dict(k=k, idx=idx, degenerado=True))
                continue
            err = float(np.median(errores(H, P["metros"][fuera], P["pixeles"][fuera])))
            area = cv2.contourArea(cv2.convexHull(P["pixeles"][idx].astype(np.float32)))
            filas.append(dict(
                k=k, idx=idx, degenerado=False, err=err, base19=float(np.median(e19[fuera])),
                area=float(area), elegible=set(idx) <= set(lejos), rectas=set(idx) <= set(rectas),
                v1=v1_cobertura(H, P), v2=v2_dentro(H, P), v3=v3_coherencia(idx, P),
            ))  # fmt: skip
    res = {"r1": {}, "r2": {}, "base19": {}, "base19_r2": {}}
    for k in CRITERIO["ks"]:
        fk = [f for f in filas if f["k"] == k and not f["degenerado"]]
        ndeg = sum(1 for f in filas if f["k"] == k and f["degenerado"])
        errs = np.array([f["err"] for f in fk])
        mejor = min(fk, key=lambda f: f["err"])
        print(
            f"  k={k}: {len(fk)} subconjuntos (+{ndeg} degenerados) · mediana de todos "
            f"{np.median(errs):.1f} px · el mejor (SESGADO, elegido sobre estos datos) "
            f"{mejor['err']:.1f} px {[P['nombres'][i] for i in mejor['idx']]}"
        )
        for regla, clave in (("r1", "elegible"), ("r2", "rectas")):
            cand = [f for f in fk if f[clave]]
            if not cand:
                print(f"    {regla.upper()}: sin candidatos")
                res[regla][k] = float("inf")
                res["base19" if regla == "r1" else "base19_r2"][k] = 0.0
                continue
            f = max(cand, key=lambda f: f["area"])
            pct = 100 * (errs < f["err"]).mean()
            res[regla][k] = f["err"]
            res["base19" if regla == "r1" else "base19_r2"][k] = f["base19"]
            print(
                f"    {regla.upper()}: {f['err']:.1f} px (base19 en sus no usados "
                f"{f['base19']:.1f}) · mejor que el {100 - pct:.0f} % de los subconjuntos · "
                f"{[P['nombres'][i] for i in f['idx']]}"
            )
    # efecto de cada punto (k=6): error medio de los subconjuntos CON él contra SIN él
    f6 = [f for f in filas if f["k"] == 6 and not f["degenerado"]]
    efecto = []
    for i in range(n):
        con = [f["err"] for f in f6 if i in f["idx"]]
        sin = [f["err"] for f in f6 if i not in f["idx"]]
        efecto.append((np.median(con) - np.median(sin), P["nombres"][i]))
    print("  efecto de incluir cada punto (k=6, mediana con − sin; + estropea):")
    for d, nom in sorted(efecto, reverse=True):
        print(f"    {nom:<24} {d:+7.1f} px")
    # validadores
    buenos = [f for f in filas if not f["degenerado"] and f["err"] <= f["base19"]]
    malos = [
        f
        for f in filas
        if not f["degenerado"] and f["err"] >= CRITERIO["malo_factor"] * f["base19"]
    ]
    res["auc"] = {
        "v1": auc([f["v1"] for f in buenos], [f["v1"] for f in malos]),
        "v2": auc([f["v2"] for f in buenos], [f["v2"] for f in malos]),
        "v3": auc(
            [-f["v3"] for f in buenos if f["v3"] is not None],
            [-f["v3"] for f in malos if f["v3"] is not None],
        ),
    }
    print(f"  validadores: {len(buenos)} buenos, {len(malos)} malos · AUC {res['auc']}")
    res["loo19"] = float(np.median(loo))
    res["en_muestra19"] = float(np.median(e19))
    return res


def main() -> None:
    res = {c: medir_campo(c, preparar_campo(d)) for c, d in CAMPOS.items()}
    v = veredicto_regla(
        {c: r["r1"] for c, r in res.items()}, {c: r["base19"] for c, r in res.items()}
    )
    v2r = veredicto_regla(
        {c: r["r2"] for c, r in res.items()},
        {c: r["base19_r2"] for c, r in res.items()},
    )
    print(f"\nVEREDICTO R1 (envolvente máxima, lejos del borde): {v}")
    print(f"(informativo) R2 (solo cruces de rectas): {v2r}")
    for val in ("v1", "v2", "v3"):
        aucs = {c: r["auc"][val] for c, r in res.items()}
        print(
            f"validador {val}: AUC {aucs} → {'ENTRA' if validador_util(aucs) else 'no entra'}"
        )
    salida = R / "outputs/calibracion_semiautomatica"
    salida.mkdir(parents=True, exist_ok=True)
    json.dump(
        {"criterio": CRITERIO, "resultados": res, "r1": v, "r2": v2r},
        open(salida / "resultados.json", "w"),
        indent=1,
        default=str,
    )


if __name__ == "__main__":
    main()
