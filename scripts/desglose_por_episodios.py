#!/usr/bin/env python
"""¿Se sostiene el desglose del error en los minutos MALOS? (proxies, sin GT)

Alex (21-sep-2026): *«extiende el desglose a más de una ventana de 30 s, aunque sea
con proxies menos precisos (recuento, detecciones crudas). Quiero saber si el 83 %
de "quién está presente" se sostiene en los minutos malos o si ahí aparece algo
distinto; el error se triplica dentro del minuto "bueno" y me hace desconfiar de
generalizar con una sola muestra.»*

Qué hace, todo sin GT salvo la calibración del último paso:

1. **Geometría del encuadre**: el campo visible es un trapecio (proyectando la
   cuadrícula del campo a la imagen con la homografía inversa).
2. **Episodios**: parte la pasada en bins de 15 s y los clasifica por detecciones
   crudas EN CAMPO (malo < 12, bueno ≥ 13,5). Es episódico, no estacionario.
3. **¿Aparece algo distinto en los malos?** Compara bueno/malo en los proxies de
   cada trozo: árbitro dentro de equipo (EXT), filas lejos de toda detección
   (DES/LOC), filas `otro/staff` sin firma de árbitro y cambios de etiqueta (LAB).
4. **Error esperado** por clase, con el mapa «error de centroide según el recuento
   del equipo» calibrado en el GT (⚠️ extrapolación: solo 10 pares del GT tienen
   ≤ 5 personas).
5. **Ventanas candidatas** para un GT de recuento: las de 30 s con menos detecciones.

Uso:
    python scripts/desglose_por_episodios.py
"""

import argparse
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from arbitro_medicion import (  # noqa: E402
    UMBRAL_MASA,
    ZONA_PORTERO_B_DY,
    ZONA_PORTERO_B_X,
    masa_de_ventana,
)
from desglose_del_error import construir_frames  # noqa: E402
from src.evaluation.desglose_error import (  # noqa: E402
    equipo_de_etiqueta,
    escalera_por_frame_equipo,
)
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402

BIN_S = 15
MALO_D, BUENO_D = 12.0, 13.5  # detecciones crudas en campo por frame
LARGO_M, ANCHO_M = 62.0, 40.0
IMAGEN_W, IMAGEN_H = 1920, 1080


def en_campo(D: np.ndarray) -> np.ndarray:
    return (D[:, 0] >= 0) & (D[:, 0] <= LARGO_M) & (D[:, 1] >= 0) & (D[:, 1] <= ANCHO_M)


# ─────────────────────────── 1. geometría del encuadre ───────────────────────────
def campo_visible(homografia: np.ndarray) -> None:
    """Rango de y visible para cada x: el campo que la cámara ve es un TRAPECIO."""
    Hi = np.linalg.inv(homografia)
    print("1. CAMPO VISIBLE (el pie de un jugador tiene que caer dentro de la imagen)")
    print(f"   {'x (m)':>6s}  {'y visible (m)':>16s}   de un ancho de {ANCHO_M:.0f} m")
    ys = np.arange(-6, 46, 0.5)
    for x in (4, 8, 12, 16, 20, 24, 28, 40):
        pts = np.array([[x, y] for y in ys], np.float32).reshape(-1, 1, 2)
        px = cv2.perspectiveTransform(pts, Hi).reshape(-1, 2)
        ok = (
            (px[:, 0] >= 0)
            & (px[:, 0] <= IMAGEN_W)
            & (px[:, 1] >= 0)
            & (px[:, 1] <= IMAGEN_H)
        )
        v = ys[ok]
        rango = (
            f"[{max(v.min(), 0):.1f}, {min(v.max(), ANCHO_M):.1f}]"
            if len(v)
            else "nada"
        )
        print(f"   {x:6d}  {rango:>16s}")


# ─────────────────────────── 2-3. episodios y proxies ───────────────────────────
def tabla_por_frame(
    filas: pd.DataFrame, dets: dict, masa: pd.DataFrame
) -> pd.DataFrame:
    """Una fila por frame con las cuentas del embudo y los proxies de cada trozo."""
    m = filas.merge(masa, on=["frame", "id_jugador"], how="left")
    m["equipo_s"] = m.etiqueta.map(equipo_de_etiqueta)
    zona_b = (m.x_m >= ZONA_PORTERO_B_X) & ((m.y_m - 20).abs() <= ZONA_PORTERO_B_DY)
    m["arbitro"] = (
        (m.masa >= UMBRAL_MASA) & ~zona_b & (m.etiqueta != "portero_B")
    ).fillna(False)
    dist = np.full(len(m), np.inf)
    for frame, g in m.groupby("frame"):
        D = dets.get(frame)
        if D is not None and len(D):
            d = np.hypot(
                g.x_m.to_numpy()[:, None] - D[None, :, 0],
                g.y_m.to_numpy()[:, None] - D[None, :, 1],
            )
            dist[m.index.get_indexer(g.index)] = d.min(1)
    m["lejos"] = dist > 1.0
    m = m.sort_values(["id_jugador", "frame"])
    previa = m.groupby("id_jugador").equipo_s.shift()
    m["cambio_ab"] = (
        previa.isin(["A", "B"]) & m.equipo_s.isin(["A", "B"]) & (previa != m.equipo_s)
    )
    esta_en_equipo = m.equipo_s.isin(["A", "B"])
    pf = m.groupby("frame").agg(
        tiempo_s=("tiempo_s", "first"),
        filas=("x_m", "size"),
        lejos=("lejos", "sum"),
        cambio_ab=("cambio_ab", "sum"),
    )
    pf["ab"] = m[esta_en_equipo].groupby("frame").size().reindex(pf.index).fillna(0)
    pf["arbitro_en_equipo"] = m[esta_en_equipo & m.arbitro].groupby("frame").size()
    pf["arbitro_en_equipo"] = pf.arbitro_en_equipo.reindex(pf.index).fillna(0)
    fuera = m[m.equipo_s.isin(["otro", "staff"]) & ~m.arbitro]
    pf["otro_staff_sin_firma"] = (
        fuera.groupby("frame").size().reindex(pf.index).fillna(0)
    )
    pf["dets"] = [
        int(en_campo(dets[f]).sum()) if f in dets and len(dets[f]) else 0
        for f in pf.index
    ]
    pf["dets_x20"] = [
        (
            int((en_campo(dets[f]) & (dets[f][:, 0] < 20)).sum())
            if f in dets and len(dets[f])
            else 0
        )
        for f in pf.index
    ]
    pf["bin"] = (pf.tiempo_s // BIN_S).astype(int)
    return pf


def episodios(pf: pd.DataFrame) -> pd.DataFrame:
    B = pf.groupby("bin").mean(numeric_only=True)
    B["clase"] = np.where(
        B.dets < MALO_D, "malo", np.where(B.dets >= BUENO_D, "bueno", "medio")
    )
    print(
        f"\n2. EPISODIOS (bins de {BIN_S} s por detecciones crudas en campo por frame)"
    )
    print(f"   {B.clase.value_counts().to_dict()}  de {len(B)} bins")
    malos = B[B.clase == "malo"]
    print(
        "   malos:",
        ", ".join(
            f"{int(b * BIN_S // 60)}:{int(b * BIN_S % 60):02d}" for b in malos.index
        ),
    )
    r = B.groupby("clase").mean(numeric_only=True)
    print(f"   corr por bin: dets~dets_x20 {B.dets.corr(B.dets_x20):+.2f}")
    print("\n3. ¿APARECE ALGO DISTINTO EN LOS MALOS? (media por frame; ambos equipos)")
    cols = [
        ("dets", "detecciones crudas en campo"),
        ("filas", "filas reales"),
        ("ab", "filas A/B"),
        ("dets_x20", "detecciones a x<20 m (cerca de cámara)"),
        ("arbitro_en_equipo", "árbitro contado en un equipo  [EXT]"),
        ("lejos", "filas a >1 m de toda detección  [DES/LOC]"),
        ("otro_staff_sin_firma", "filas otro/staff sin firma de árbitro  [LAB]"),
        ("cambio_ab", "cambios de etiqueta A↔B  [LAB]"),
    ]
    print(f"   {'':46s} {'bueno':>7s} {'medio':>7s} {'malo':>7s}")
    for c, nombre in cols:
        print(
            f"   {nombre:46s} "
            + " ".join(f"{r.loc[k, c]:7.2f}" for k in ("bueno", "medio", "malo"))
        )
    return B


# ─────────────────────── 4. error esperado calibrado con el GT ───────────────────────
def error_esperado(filas, pf, B, args) -> None:
    H = np.load(args.homografia)
    gt_m = gt_a_por_frame(parsear_cvat(args.gt), H, args.offset, args.paso)
    R = pd.DataFrame(escalera_por_frame_equipo(construir_frames(gt_m, filas, 2.0))[0])
    R0 = R[R.arreglos == frozenset()]
    err = {
        "≤5": R0[R0.n_sis <= 5].centroide.mean(),
        "6": R0[R0.n_sis == 6].centroide.mean(),
        "7": R0[R0.n_sis == 7].centroide.mean(),
        "≥8": R0[R0.n_sis >= 8].centroide.mean(),
    }
    n_pares = {
        "≤5": int((R0.n_sis <= 5).sum()),
        "6": int((R0.n_sis == 6).sum()),
        "7": int((R0.n_sis == 7).sum()),
        "≥8": int((R0.n_sis >= 8).sum()),
    }
    print(
        "\n4. ERROR ESPERADO (⚠️ EXTRAPOLACIÓN: mapa recuento→error calibrado en el GT)"
    )
    print("   error de centroide del GT según el recuento del equipo (m, n pares):")
    print("   " + " · ".join(f"n={k}: {err[k]:.2f} ({n_pares[k]})" for k in err))
    ab = filas.assign(eqp=filas.etiqueta.map(equipo_de_etiqueta))
    ab = (
        ab[ab.eqp.isin(["A", "B"])]
        .groupby(["frame", "eqp"])
        .size()
        .rename("n")
        .reset_index()
    )
    ab["bin"] = ab.frame.map(pf.bin)
    ab["clase"] = ab.bin.map(B.clase)
    for clase, g in ab.groupby("clase"):
        p = {
            "≤5": (g.n <= 5).mean(),
            "6": (g.n == 6).mean(),
            "7": (g.n == 7).mean(),
            "≥8": (g.n >= 8).mean(),
        }
        esperado = sum(p[k] * err[k] for k in p)
        print(
            f"   {clase:6s} recuento medio {g.n.mean():.2f} · ≤5: {p['≤5']:.0%} · 7: {p['7']:.0%}"
            f" → error esperado ≥ {esperado:.2f} m ({len(g) / len(ab):.0%} del tiempo)"
        )
    print(
        "   ⚠️ Es un SUELO: con 4,5 jugadores de media, el GT solo tiene 10 pares ≤ 5."
    )


# ─────────────────────────── 5. ventanas para el GT ───────────────────────────
def ventanas_candidatas(
    pf: pd.DataFrame, largo_s: int = 30, n: int = 6
) -> pd.DataFrame:
    """Ventanas de `largo_s` segundos sin solape con menos detecciones en campo."""
    t0 = int(pf.tiempo_s.min())
    cand = []
    for ini in range(t0, int(pf.tiempo_s.max()) - largo_s, 5):
        w = pf[(pf.tiempo_s >= ini) & (pf.tiempo_s < ini + largo_s)]
        if len(w) > 0.8 * largo_s * 10:
            cand.append(
                {
                    "ini_s": ini,
                    "dets": w.dets.mean(),
                    "dets_x20": w.dets_x20.mean(),
                    "ab": w.ab.mean(),
                }
            )
    C = pd.DataFrame(cand).sort_values("dets")
    elegidas = []
    for _, r in C.iterrows():
        if all(abs(r.ini_s - e.ini_s) >= largo_s for e in elegidas):
            elegidas.append(r)
        if len(elegidas) == n:
            break
    V = pd.DataFrame(elegidas)
    V["desde"] = [f"{int(s // 60)}:{int(s % 60):02d}" for s in V.ini_s]
    V["hasta"] = [
        f"{int((s + largo_s) // 60)}:{int((s + largo_s) % 60):02d}" for s in V.ini_s
    ]
    V["frame_ini"] = (V.ini_s * 29.97).round().astype(int)
    print(
        f"\n5. VENTANAS DE {largo_s} s PARA EL GT (menos detecciones en campo, sin solape)"
    )
    print(
        V[["desde", "hasta", "frame_ini", "dets", "dets_x20", "ab"]]
        .round(1)
        .to_string(index=False)
    )
    return V


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1_v3.csv")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument(
        "--dets", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument(
        "--colores", default="data/tracking_benja/cache_colores_benja_p1.pkl"
    )
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()

    filas = pd.read_csv(args.csv).query("es_real == 1").reset_index(drop=True)
    with open(args.dets, "rb") as f:
        dets = {
            e["frame_idx"]: np.array(e["dets"]).reshape(-1, 7)
            for e in pickle.load(f)["cache"]
        }
    with open(args.colores, "rb") as f:
        colores = pickle.load(f)
    masa = masa_de_ventana(filas, {k: v.tolist() for k, v in dets.items()}, colores)[
        ["frame", "id_jugador", "masa"]
    ]

    campo_visible(np.load(args.homografia))
    pf = tabla_por_frame(filas, dets, masa)
    B = episodios(pf)
    error_esperado(filas, pf, B, args)
    ventanas_candidatas(pf)


if __name__ == "__main__":
    main()
