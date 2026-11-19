#!/usr/bin/env python
"""Evalúa el punto de suelo por pose (método 3 de docs/plan_literatura.md) contra el de producción.

Para las MISMAS detecciones compara dos puntos de suelo, proyectados con la misma homografía:
- **producción**: el centro del borde inferior de la caja (control: reproduce el (mx, my) del
  caché);
- **pelvis**: x = media de las caderas, y = media de los tobillos (puntos de RTMPose con confianza
  ≥ `--min-conf`). Si faltan, se usa el de producción y la detección cuenta como «sin pose».

Mide:
1. **error contra el GT**, por tercio de profundidad (casado 1-a-1 a ≤ 2 m con el punto de
   producción, para comparar sobre las mismas parejas). ⚠️ El GT del benjamín es una plantilla fija
   y su «pie» no es siempre el pie (CLAUDE.md): vale para comparar los dos puntos entre sí, no como
   cifra absoluta;
2. **temblor de jugadores parados**: personas del GT que se mueven < 0,5 m entre dos frames del GT
   (0,5 s). Su detección se sigue en los fotogramas del caché de en medio por vecino más cercano en
   píxeles, y se mide la desviación típica del punto de suelo a lo largo de ese tramo.

Uso:
    python scripts/lit_evaluar_pose.py --pata villa --pose outputs/literatura/pose/villa.npz
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

EJE = {"benja": 0, "villa": 1}  # eje de profundidad de cada pata


def proyectar(H: np.ndarray, px: np.ndarray) -> np.ndarray:
    p = np.column_stack([px, np.ones(len(px))]) @ H.T
    return p[:, :2] / p[:, 2:3]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pata", required=True, choices=list(EJE))
    ap.add_argument("--pose", type=Path, required=True)
    ap.add_argument("--min-conf", type=float, default=0.3)
    ap.add_argument(
        "--variante",
        default="tobillos",
        choices=["tobillos", "pelvis_x", "tobillos_con_desfase"],
        help="tobillos: (x pelvis, y tobillos) · pelvis_x: (x pelvis, y borde inferior) · "
        "tobillos_con_desfase: y tobillos + desfase mediano tobillo→borde de la pata",
    )
    ap.add_argument("--salida", type=Path, default=None)
    a = ap.parse_args()
    import yaml
    from scipy.optimize import linear_sum_assignment

    import banco_mision as bm
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    d = bm.PATAS[a.pata]
    cfg = yaml.safe_load(open(R / d["config"]))
    cache = pickle.load(open(R / d.get("cache", cfg["rutas"]["cache"]), "rb"))["cache"]
    dets = {e["frame_idx"]: e["dets"] for e in cache}
    H = np.load(R / d["homografia"])
    z = np.load(a.pose)
    kp = {(int(f), int(j)): p for (f, j), p in zip(z["claves"], z["puntos"])}
    # desfase mediano (en altos de caja) entre los tobillos y el borde inferior, en esta pata
    desfases = []
    for (f, j), p in kp.items():
        if min(p[15, 2], p[16, 2]) >= a.min_conf:
            x1, y1, x2, y2 = dets[f][j][2:6]
            desfases.append((y2 - (p[15, 1] + p[16, 1]) / 2) / max(y2 - y1, 1e-6))
    desfase = float(np.median(desfases)) if desfases else 0.0

    def suelo(f: int, j: int) -> tuple[np.ndarray, np.ndarray, bool]:
        """(punto de producción, punto de pelvis) en metros, y si hubo pose."""
        x1, y1, x2, y2 = dets[f][j][2:6]
        pie = np.array([(x1 + x2) / 2, y2])
        p = kp.get((f, j))
        con_pose = (
            p is not None
            and min(p[11, 2], p[12, 2]) >= a.min_conf
            and min(p[15, 2], p[16, 2]) >= a.min_conf
        )
        if not con_pose:
            pelvis = pie
        elif a.variante == "pelvis_x":
            pelvis = np.array([(p[11, 0] + p[12, 0]) / 2, y2])
        elif a.variante == "tobillos_con_desfase":
            pelvis = np.array(
                [
                    (p[11, 0] + p[12, 0]) / 2,
                    (p[15, 1] + p[16, 1]) / 2 + desfase * (y2 - y1),
                ]
            )
        else:
            pelvis = np.array([(p[11, 0] + p[12, 0]) / 2, (p[15, 1] + p[16, 1]) / 2])
        m = proyectar(H, np.vstack([pie, pelvis]))
        return m[0], m[1], bool(con_pose)

    gt_m = gt_a_por_frame(parsear_cvat(R / d["gt"]), H, d["offset"], 15)
    base = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}
    eje = EJE[a.pata]
    lado = d["campo"][eje]
    pares = {}  # (frame, persona) → j
    pos_gt = {}
    filas = []
    for f, obs in gt_m.items():
        gente = [o for o in obs if base.get(str(o.team)) in ("A", "B")]
        if not gente or f not in dets:
            continue
        gt = np.array([o.pos for o in gente], float)
        xy = np.array([dd[:2] for dd in dets[f]], float)
        dist = np.linalg.norm(gt[:, None] - xy[None], axis=2)
        i, j = linear_sum_assignment(np.where(dist <= 2.0, dist, 1e6))
        for p_, q in zip(i, j):
            if dist[p_, q] > 2.0:
                continue
            pie, pel, con = suelo(f, int(q))
            pares[(f, gente[p_].obj_id)] = int(q)
            pos_gt[(f, gente[p_].obj_id)] = gt[p_]
            tercio = min(int(gt[p_][eje] / lado * 3), 2)
            filas.append(
                (
                    tercio,
                    np.linalg.norm(pie - gt[p_]),
                    np.linalg.norm(pel - gt[p_]),
                    con,
                )
            )
    f_ = np.array(filas, dtype=float)
    error = {}
    for k, nombre in enumerate(["cerca", "medio", "lejos"]):
        s = f_[f_[:, 0] == k]
        if len(s):
            error[nombre] = {
                "n": len(s),
                "produccion_mediana_m": round(float(np.median(s[:, 1])), 3),
                "pelvis_mediana_m": round(float(np.median(s[:, 2])), 3),
                "con_pose_pct": round(100 * float(s[:, 3].mean()), 1),
            }
    # temblor de parados: tramos de 0,5 s entre dos frames del GT en los que la persona no se mueve
    frames = sorted(dets)
    temblor = {k: {"produccion": [], "pelvis": []} for k in ("cerca", "medio", "lejos")}
    for (f, per), j in pares.items():
        sig = (f + 15, per)
        if sig not in pos_gt or np.linalg.norm(pos_gt[sig] - pos_gt[(f, per)]) >= 0.5:
            continue
        tercio = ["cerca", "medio", "lejos"][
            min(int(pos_gt[(f, per)][eje] / lado * 3), 2)
        ]
        cadena = [(f, j)]
        for g in [x for x in frames if f < x <= f + 15]:
            fa, ja = cadena[-1]
            c0 = np.array(dets[fa][ja][2:6], float)
            cand = np.array([dd[2:6] for dd in dets[g]], float)
            if not len(cand):
                break
            centro = (c0[:2] + c0[2:]) / 2
            dd = np.linalg.norm((cand[:, :2] + cand[:, 2:]) / 2 - centro, axis=1)
            k = int(np.argmin(dd))
            if dd[k] > 0.3 * (c0[3] - c0[1]):
                break
            cadena.append((g, k))
        if len(cadena) < 4:
            continue
        puntos = np.array([suelo(g, k)[:2] for g, k in cadena])  # (n, 2, 2)
        for n_, nombre in enumerate(("produccion", "pelvis")):
            temblor[tercio][nombre].append(
                float(np.linalg.norm(puntos[:, n_].std(axis=0)))
            )
    res = {
        "pata": a.pata,
        "variante": a.variante,
        "desfase_tobillo_borde_altos": round(desfase, 3),
        "error_contra_gt": error,
        "temblor_parados_mediana_m": {
            t: {
                "tramos": len(v["produccion"]),
                **{k: round(float(np.median(x)), 3) for k, x in v.items() if x},
            }
            for t, v in temblor.items()
        },
        "detecciones_con_pose_pct": round(
            100
            * float(
                np.mean(
                    [
                        min(p[11, 2], p[12, 2], p[15, 2], p[16, 2]) >= a.min_conf
                        for p in z["puntos"]
                    ]
                )
            ),
            1,
        ),
    }
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.salida:
        a.salida.parent.mkdir(parents=True, exist_ok=True)
        a.salida.write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
