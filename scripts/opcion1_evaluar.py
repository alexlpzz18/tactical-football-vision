#!/usr/bin/env python
"""Evalúa la opción 1 (detecciones débiles que solo alargan pistas) en el alevín A.

Plan, variantes y criterios: `docs/plan_opcion1_dos_etapas.md`. Lee el caché que deja la celda de
Colab (`colab_villa_dos_etapas.py`), construye las variantes V1-V3, las pasa por producción con los
configs de `main` (exportados con `git show` a la carpeta de salida) y mide con el oráculo de radio
por profundidad (K fijo = 3,48 px). Solo lee y escribe en la carpeta de salida.

Uso:
    python scripts/opcion1_evaluar.py --cache data/tracking/cache_villa_conf010.pkl \\
        --colores data/tracking/colores_villa_conf010.pkl --salida outputs/opcion1
"""

import argparse
import json
import logging
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

import oraculo_f11_radio_profundidad as orc  # noqa: E402

K_PX = 3.48  # medido sobre producción (docs/segunda_opinion_27nov.md, sección 5)
PRODUCCION = R / "data/tracking/cache_detecciones_v4pre.pkl"
CONF_FUERTE = 0.30
QUIETO_S, QUIETO_PX, QUIETO_FRAC = 2.0, 2.0, 0.5


def exportar_configs_main(destino: Path) -> Path:
    for f in subprocess.run(
        ["git", "ls-tree", "--name-only", "main", "configs/"],
        capture_output=True, text=True, check=True, cwd=R,
    ).stdout.split():  # fmt: skip
        if f.endswith(".yaml"):
            (destino / f).parent.mkdir(parents=True, exist_ok=True)
            (destino / f).write_text(
                subprocess.run(
                    ["git", "show", f"main:{f}"],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=R,
                ).stdout
            )
    return destino


def quedarse(datos: dict, colores: dict, conservar) -> tuple[dict, dict]:
    """Quita detecciones y RENUMERA las claves de color (frame, j); si no, apuntan a otra caja."""
    cache, col = [], {}
    for e in datos["cache"]:
        nuevas = []
        for j, d in enumerate(e["dets"]):
            if conservar(e, j, d):
                if (e["frame_idx"], j) in colores:
                    col[(e["frame_idx"], len(nuevas))] = colores[(e["frame_idx"], j)]
                nuevas.append(d)
        cache.append({**e, "dets": nuevas})
    return {**datos, "cache": cache}, col


def quietas(datos: dict) -> set:
    """(frame, j) de las débiles QUIETAS: en ≥ 50 % de los frames de ± 2 s, una caja a ≤ 2 px."""
    centros = {
        e["frame_idx"]: np.array(
            [((d[2] + d[4]) / 2, (d[3] + d[5]) / 2) for d in e["dets"]]
        )
        for e in datos["cache"]
    }
    t = {e["frame_idx"]: e["t"] for e in datos["cache"]}
    frames = sorted(centros)
    salida = set()
    for e in datos["cache"]:
        f = e["frame_idx"]
        vecinos = [g for g in frames if g != f and abs(t[g] - t[f]) <= QUIETO_S]
        for j, d in enumerate(e["dets"]):
            if d[6] >= CONF_FUERTE or not vecinos:
                continue
            c = centros[f][j]
            hits = sum(
                len(centros[g])
                and np.min(np.linalg.norm(centros[g] - c, axis=1)) <= QUIETO_PX
                for g in vecinos
            )
            if hits >= QUIETO_FRAC * len(vecinos):
                salida.add((f, j))
    return salida


def control_fuertes(datos: dict) -> float:
    prod = {
        e["frame_idx"]: e["dets"] for e in pickle.load(open(PRODUCCION, "rb"))["cache"]
    }

    def iou(a, b):
        iw = max(0, min(a[4], b[4]) - max(a[2], b[2]))
        ih = max(0, min(a[5], b[5]) - max(a[3], b[3]))
        i = iw * ih
        return i / ((a[4] - a[2]) * (a[5] - a[3]) + (b[4] - b[2]) * (b[5] - b[3]) - i)

    tot = rep = 0
    for e in datos["cache"]:
        fuertes = [d for d in e["dets"] if d[6] >= CONF_FUERTE]
        for p in prod.get(e["frame_idx"], []):
            tot += 1
            rep += any(iou(p, q) >= 0.9 for q in fuertes)
    return round(100 * rep / max(tot, 1), 1)


def medir(csv: Path) -> dict:
    H = np.load(orc.HOMOGRAFIA)
    gt = orc.gt_con_pies(H)
    reales = pd.read_csv(csv)
    reales = reales[reales.es_real == 1].reset_index(drop=True)
    frames = orc.construir(gt, reales, lambda p: max(orc.RADIO, K_PX * p[4]))
    r = orc.resumen_escalera(frames)
    sobran = sum(
        1
        for fc in frames
        for i in range(len(fc.x))
        if i not in fc.persona_de_fila and fc.etiqueta[i] in orc.de.EQUIPOS
    )
    return {
        "faltan_tercio_lejano_pct": r["faltan_tercio_lejano_pct"],
        "anchura_m": r["ancho"]["sistema_m"],
        "sobran_en_anchura_pct": r["ancho"]["shapley_pct"]["EXT"],
        "centroide_m": r["centroide"]["sistema_m"],
        "profundidad_m": r["prof"]["sistema_m"],
        "sobran_filas_por_frame": round(sobran / len(frames), 2),
        "identidades": int(pd.read_csv(csv).id_jugador.nunique()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--colores", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    import banco_mision as bm

    a.salida = a.salida.resolve()
    a.salida.mkdir(parents=True, exist_ok=True)
    bm.SALIDA = a.salida
    bm.BASE_CONFIGS = exportar_configs_main(a.salida / "configs_main")
    datos = pickle.load(open(a.cache, "rb"))
    colores = pickle.load(open(a.colores, "rb"))
    res = {"control_fuertes_reproducen_produccion_pct": control_fuertes(datos)}
    fijas = quietas(datos)
    n_deb = sum(d[6] < CONF_FUERTE for e in datos["cache"] for d in e["dets"])
    res["debiles"] = {"total": n_deb, "quietas_quitadas": len(fijas)}
    variantes = {
        "V1_solo_fuertes": (lambda e, j, d: d[6] >= CONF_FUERTE, {}),
        "V2_debiles_activacion_0.2": (
            lambda e, j, d: True,
            {"bytetrack": {"umbral_activacion": 0.2}},
        ),
        "V3_V2_mas_quietos": (
            lambda e, j, d: (e["frame_idx"], j) not in fijas,
            {"bytetrack": {"umbral_activacion": 0.2}},
        ),
    }
    csv_v0 = R / "outputs/literatura/banco/villa/posiciones_actual.csv"
    res["V0_produccion"] = medir(csv_v0)
    for nombre, (conservar, tracking) in variantes.items():
        d2, c2 = quedarse(datos, colores, conservar)
        rc, rk = a.salida / f"cache_{nombre}.pkl", a.salida / f"colores_{nombre}.pkl"
        pickle.dump(d2, open(rc, "wb"))
        pickle.dump(c2, open(rk, "wb"))
        bm.PATAS["villa"]["cache"] = str(rc.relative_to(R))
        bm.PATAS["villa"]["cache_colores"] = str(rk.relative_to(R))
        res[nombre] = medir(bm.correr("villa", nombre, tracking, {}))
    v0, v3 = res["V0_produccion"], res["V3_V2_mas_quietos"]
    res["criterio"] = {
        "1_faltan_lejanos_le_25": v3["faltan_tercio_lejano_pct"] <= 25.0,
        "2_anchura_le_4.85": v3["anchura_m"] <= 4.85,
        "3_sobran_en_anchura_le_5": v3["sobran_en_anchura_pct"] <= 5,
        "referencia_V0": {k: v0[k] for k in ("faltan_tercio_lejano_pct", "anchura_m")},
    }
    (a.salida / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    )
    print(json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item()))


if __name__ == "__main__":
    main()
