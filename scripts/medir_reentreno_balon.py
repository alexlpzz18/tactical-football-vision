#!/usr/bin/env python
"""Veredicto del reentreno del balón: los 9 criterios del plan, v1 contra el candidato.

docs/plan_reentreno_balon.md. El CRITERIO de abajo es el del plan, tal cual, y se commiteó
ANTES de ver ningún número del modelo nuevo. Declarado también antes (Alex, 6-oct-2026):
- el CANDIDATO es `best.pt` (época 13). `last.pt` (época 28) solo se mide si best.pt no
  pasa los 9 criterios;
- los 3 frames de test a ≤ 2 frames del dataset original (1586, 18412, 32240) SE QUEDAN en
  el test; el criterio 1 se informa con y sin ellos, con el MISMO umbral de 6 balones
  (calculado sobre 23 positivos). Decide la medida CON ellos.

Tres medidas:
A. test del pool (36 imágenes): `colab_test_pool_balon.py` deja un JSON;
B. partido entero por la cadena de producción: los dos cachés de balón (el de producción
   y el del candidato, `configs/processor_benja_balon_v2pegado.yaml`);
C. lo ganado a ojo: este script saca la hoja de 30 frames donde el candidato elige balón y
   v1 no; el juicio de cada uno se apunta en un CSV (`n,juicio` con juicio = balon /
   basura / dudoso) y el criterio 9 se lee de ahí.

Uso:
    python scripts/medir_reentreno_balon.py --medida-a RUTA/medida_A.json \\
        --cache-v2 RUTA/cache_balon_p1_v2pegado.pkl [--juicio-c RUTA/juicio_c.csv]
"""

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))

# ══════════════════════ CRITERIO (el del plan, fijado ANTES de medir) ══════════════════════
CRITERIO = {
    # 1. A: el candidato acierta al menos esto MÁS balones que v1 (⌈0,25 × 23 positivos⌉)
    "balones_mas": 6,
    # 2. A: falsos positivos por imagen del candidato ≤ los de v1 + esto
    "fp_margen": 0.10,
    # 3. B: GT de desempates (con la vara de medir_umbral_balon.py: caja a ≤ 15 px)
    "desempates_min": 35,
    # 4. B: cambios de objeto por minuto
    "cambios_max": 3.0,
    # 5. B: fracción de la trayectoria en las 5 marcas de verdad
    "marcas_max": 0.0,
    # 6. B: duración anclada (s); si la supera, se mira y solo vale si es una parada
    "anclada_max_s": 19.4,
    # 7. B: en los dos tramos etiquetados, lo que no es balón no sube (por tramo)
    # 8. B: de los 8 casos visibles del GT de vuelo NO usados para entrenar, ≥ esto
    "vuelo_casos": ("V03", "V07", "V08", "V09", "V12", "V14", "V17", "V19"),
    "vuelo_min": 2,
    # 9. C: de 30 ganados al azar, ≥ 2/3 balón real y ≤ 1/6 basura clara
    "c_n": 30,
    "c_real_min": 2 / 3,
    "c_basura_max": 1 / 6,
}
CERCANOS_AL_ORIGINAL = (1586, 18412, 32240)  # se informan aparte, no salen del test
# ═══════════════════════════════════════════════════════════════════════════════════════════


def resumen_a(medida_a: dict, excluir: tuple = ()) -> dict:
    """Aciertos, positivos y falsos positivos por imagen de v1 y del candidato (v2)."""
    filas = {
        int(f): v for f, v in medida_a["por_frame"].items() if int(f) not in excluir
    }
    n = len(filas)
    out = {"imagenes": n, "positivos": sum(v["positivo"] for v in filas.values())}
    for m in ("v1", "v2"):
        out[f"aciertos_{m}"] = sum(v[m]["aciertos"] for v in filas.values())
        out[f"fp_img_{m}"] = sum(v[m]["fp"] for v in filas.values()) / max(n, 1)
    out["balones_mas"] = out["aciertos_v2"] - out["aciertos_v1"]
    return out


def veredicto(
    a: dict, b1: dict, b2: dict, c: dict | None, crit: dict = CRITERIO
) -> dict:
    """Los 9 criterios. a: resumen_a (CON los cercanos); b1/b2: métricas B de v1 y del
    candidato; c: {'real', 'basura', 'n'} del juicio a ojo, o None si aún no está.

    Cada punto: True / False / None (None = falta el dato o hace falta mirarlo a ojo).
    `pasa`: False si alguno es False; None si ninguno es False pero alguno es None.
    """
    v = {
        "1_balones_mas": a["balones_mas"] >= crit["balones_mas"],
        "2_fp_por_imagen": a["fp_img_v2"] <= a["fp_img_v1"] + crit["fp_margen"],
        "3_desempates": b2["gt_desempates"] >= crit["desempates_min"],
        "4_cambios_min": b2["cambios_min"] <= crit["cambios_max"],
        "5_marcas": b2["en_marcas"] <= crit["marcas_max"],
        # por encima del tope no suspende sola: se mira y vale si es una parada
        "6_anclada": True if b2["anclada_s"] <= crit["anclada_max_s"] else None,
        "7_no_balon_no_sube": all(
            b2["tramos"][t]["malo"] <= b1["tramos"][t]["malo"] for t in b1["tramos"]
        ),
        "8_vuelo": len(b2["vuelo_recuperados"]) >= crit["vuelo_min"],
        "9_ganados_a_ojo": (
            None
            if c is None
            else (
                c["real"] / c["n"] >= crit["c_real_min"]
                and c["basura"] / c["n"] <= crit["c_basura_max"]
            )
        ),
    }
    valores = list(v.values())
    v["pasa"] = False if False in valores else (None if None in valores else True)
    return v


def metricas_b(ruta_cache: str, args) -> tuple[dict, dict]:
    """Las métricas B de un caché por la cadena de producción (selector incluido)."""
    from medir_umbral_balon import (
        GT_VISIBLES,
        MARCAS_VERDAD,
        cambios_por_minuto,
        centro,
        gt_desempates,
        punto_gt,
        RADIO_GT_PX,
        tramos_etiquetados,
    )
    from src.balon.carga import cargar_detecciones_limpias, contexto_del_selector
    from src.balon.metricas_adopcion import duracion_maxima_anclada, fraccion_en_marcas
    from src.balon.tracking_balon import ParametrosBalon, seleccionar_balon_activo
    from src.campo_modelo import cargar_modelo

    modelo = cargar_modelo(config=args.campo)
    with contextlib.redirect_stdout(io.StringIO()):
        dets, tiempos, meta = cargar_detecciones_limpias(ruta_cache, modelo)
    jug, ctx = contexto_del_selector(
        args.csv_jugadores, tiempos, dets, args.campo, modelo, meta["fuera_de_campo"]
    )
    pos = {f: [(j[0], j[1]) for j in jug.get(f, [])] for f in dets}
    sel = seleccionar_balon_activo(dets, pos, ParametrosBalon(), **ctx)
    fr = sorted(sel)
    meta_vuelo = json.loads(Path(args.gt_vuelo).read_text())
    recuperados = []
    for caso in CRITERIO["vuelo_casos"]:
        celdas, ancla = GT_VISIBLES[caso]
        f = meta_vuelo[caso]["frame"]
        punto = punto_gt(celdas, ancla, meta_vuelo[caso])
        if f in sel and np.linalg.norm(centro(sel[f]) - punto) <= RADIO_GT_PX:
            recuperados.append(caso)
    m = {
        "gt_desempates": gt_desempates(sel, pd.read_csv(args.gt_desempates)),
        "cambios_min": round(cambios_por_minuto(sel, tiempos), 2),
        "en_marcas": fraccion_en_marcas(
            [(f, tuple(centro(sel[f]))) for f in fr], MARCAS_VERDAD
        ),
        "anclada_s": round(
            duracion_maxima_anclada(
                [(f, (sel[f][0], sel[f][1])) for f in fr], tiempos, 1.0, 1.0
            ),
            1,
        ),
        "tramos": tramos_etiquetados(sel, Path(args.tramos)),
        "vuelo_recuperados": recuperados,
        "frames_balon": len(sel),
    }
    return m, sel


def leer_juicio(ruta) -> dict | None:
    if not ruta or not Path(ruta).exists():
        return None
    j = pd.read_csv(ruta)
    return {"n": len(j), "real": int((j.juicio == "balon").sum()),
            "basura": int((j.juicio == "basura").sum())}  # fmt: skip


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--medida-a", required=True)
    p.add_argument("--cache-v2", required=True)
    p.add_argument("--cache-v1", default="data/tracking_benja/cache_balon_p1.pkl")
    p.add_argument("--juicio-c", default=None)
    p.add_argument(
        "--csv-jugadores", default="data/tracking_benja/posiciones_benja_p1_v3.csv"
    )
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    p.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    p.add_argument(
        "--gt-desempates", default="data/tracking_benja/gt_desempates_balon.csv"
    )
    p.add_argument("--gt-vuelo", default="outputs/gt_balon_en_vuelo/metadatos.json")
    p.add_argument("--tramos", default="data/tracking_benja/tramos_balon_etiquetados")
    p.add_argument("--salida", default="outputs/reentreno_balon")
    args = p.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)

    medida_a = json.loads(Path(args.medida_a).read_text())
    a = resumen_a(medida_a)
    a_sin = resumen_a(medida_a, CERCANOS_AL_ORIGINAL)
    print(
        f"A (test del pool, {a['imagenes']} imágenes, {a['positivos']} positivos): {a}"
    )
    print(
        f"A SIN los 3 cercanos al original (informativo, mismo umbral de "
        f"{CRITERIO['balones_mas']}): {a_sin}"
    )
    b1, sel1 = metricas_b(args.cache_v1, args)
    b2, sel2 = metricas_b(args.cache_v2, args)
    print(f"B v1 (producción): {b1}")
    print(f"B candidato:       {b2}")

    ganados = sorted(set(sel2) - set(sel1))
    from medir_umbral_balon import hoja_ganados

    if ganados:
        hoja_ganados(
            ganados, sel2, args.video, salida / "hoja_ganados.jpg", n=CRITERIO["c_n"]
        )
        print(
            f"C: {len(ganados)} frames ganados; hoja de {min(CRITERIO['c_n'], len(ganados))} "
            f"en {salida / 'hoja_ganados.jpg'} (juicio en un CSV n,juicio)"
        )
    v = veredicto(a, b1, b2, leer_juicio(args.juicio_c))
    print(f"\nVEREDICTO (candidato best.pt): {v}")
    json.dump({"criterio": {k: list(x) if isinstance(x, tuple) else x for k, x in CRITERIO.items()},
               "A": a, "A_sin_cercanos": a_sin, "B_v1": b1, "B_v2": b2,
               "ganados": len(ganados), "veredicto": v},
              open(salida / "veredicto.json", "w"), indent=1, default=str)  # fmt: skip


if __name__ == "__main__":
    main()
