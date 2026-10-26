#!/usr/bin/env python
"""Diagnóstico 22-oct (e), bloque 1: etiqueta con tope de cardinalidad contra hoy y el control.

Criterio en `docs/diagnostico_22oct_e.md`. Pasadas `desde_cache` (sin vídeo) del benjamín (parte
entera) y de Villaviciosa (60 s), con el flag `equipos.tope_cardinalidad` encendido, con los costes
de color reales y PERMUTADOS (control). Producción no cambia: el flag se enciende en una copia del
config, en memoria.

Uso:
    python scripts/diag22e_tope.py --salida outputs/diagnostico_22oct_e [--sin-hoja]
"""

import argparse
import importlib.util
import json
import logging
import re
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
PATAS = {
    "benja": dict(
        config=R / "configs/processor_benja_parte_entera.yaml",
        hoy=R / "outputs/diagnostico_22oct_d/posiciones_hoy.csv",
    ),
    "villa": dict(
        config=R / "configs/processor.yaml",
        hoy=R / "outputs/diagnostico_22oct/villa/posiciones.csv",
    ),
}
SEMILLA_CONTROL, SEMILLA_HOJA, N_HOJA = 0, 0, 60


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pasada(
    pata: str, variante: str, salida: Path, permutar: bool, unidad: str = "identidad"
) -> tuple[Path, list[str]]:
    import yaml

    from src.tracking_data.processor import procesar_desde_cache

    c3 = _mod("diag22c_v3")
    cfg = yaml.safe_load(open(PATAS[pata]["config"]))
    cfg["modo"] = "desde_cache"
    cfg["equipos"]["tope_cardinalidad"]["activo"] = True
    cfg["equipos"]["tope_cardinalidad"]["unidad"] = unidad
    if permutar:
        cfg["equipos"]["tope_cardinalidad"][
            "control_permutar_semilla"
        ] = SEMILLA_CONTROL
    pre = "tope" if unidad == "identidad" else f"tope_{unidad}"
    csv = salida / f"{pre}_{pata}_{variante}.csv"
    cfg["rutas"]["salida_csv"] = str(csv)
    cfg["rutas"]["salida_meta"] = str(salida / f"{pre}_{pata}_{variante}_meta.json")
    cap = c3._Captura()
    raiz = logging.getLogger()
    nivel = raiz.level
    raiz.addHandler(cap)
    raiz.setLevel(logging.INFO)
    try:
        procesar_desde_cache(cfg)
    finally:
        raiz.removeHandler(cap)
        raiz.setLevel(nivel)
    (salida / f"{pre}_{pata}_{variante}.log").write_text("\n".join(cap.mensajes))
    return csv, cap.mensajes


def etiquetas_por_identidad_y_minuto(filas) -> float:
    r = filas[filas.es_real == 1]
    return round(
        float(r.groupby([r.id_jugador, (r.tiempo_s // 60)]).etiqueta.nunique().mean()),
        3,
    )


def resumen_solver(mensajes: list[str]) -> dict | None:
    for m in mensajes:
        if m.startswith("Tope de cardinalidad"):
            g = re.search(
                r"(\d+) unidades libres, (\d+) fijadas, (\d+) restricciones; exceso total "
                r"(\d+) persona-frame; (\d+) identidades cambian; ([\d.]+) s",
                m,
            )
            if g:
                k = [
                    "libres",
                    "fijadas",
                    "restricciones",
                    "exceso_persona_frame",
                    "cambian",
                    "s",
                ]
                return {a: float(b) for a, b in zip(k, g.groups())}
    return None


def filas_que_cambian(hoy, nueva):
    """Filas reales que cambian de etiqueta (casadas por frame y posición, no por id)."""
    cols = ["frame", "x_m", "y_m"]
    a = hoy[hoy.es_real == 1][cols + ["etiqueta", "id_jugador"]]
    b = nueva[nueva.es_real == 1][cols + ["etiqueta"]]
    j = a.merge(b, on=cols, suffixes=("_hoy", "_tope"))
    return j, j[j.etiqueta_hoy != j.etiqueta_tope]


def metricas_benja(csv: Path, hoy_k_proxy) -> dict:
    import pandas as pd

    b3, c3, inv = (
        _mod("diag22b_bloque3_medir"),
        _mod("diag22c_v3"),
        _mod("diag22e_invariantes"),
    )
    dets, det_arb = hoy_k_proxy
    filas = pd.read_csv(csv)
    return {
        "a_equipo_equivocado_pct": b3.error_equipo(csv),
        "a_cobertura_pct": round(c3.cobertura(filas, c3.gt_benja())["pct"], 2),
        "b_arbitro_en_equipo_ventana_gt": inv.arbitro_en_equipo_ventana_gt(
            inv.con_caja(filas, dets), det_arb
        ),
        "d_etiquetas_por_identidad_y_minuto": etiquetas_por_identidad_y_minuto(filas),
        "invariantes_(por_construccion)": inv.invariantes(
            inv.recuento_por_frame(filas, 62.0, 40.0), 7
        ),
    }


def metricas_villa(csv: Path) -> dict:
    import pandas as pd

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    cv, inv = _mod("colab_v3_villa"), _mod("diag22e_invariantes")
    gt = gt_a_por_frame(parsear_cvat(cv.GT), np.load(cv.H_GT), cv.OFFSET, cv.PASO)
    m = cv.metricas(csv, gt, 100.0, 64.0)
    filas = pd.read_csv(csv)
    return {
        "c_equipo_equivocado_pct": round(m["equipo_equivocado_pct"], 2),
        "c_arbitro_en_equipo_pct": (
            round(m["arbitro_en_equipo_gt"]["pct_de_las_casadas"], 2)
            if m["arbitro_en_equipo_gt"]["pct_de_las_casadas"] is not None
            else None
        ),
        "cobertura_pct": round(m["cobertura"]["pct"], 2),
        "d_etiquetas_por_identidad_y_minuto": etiquetas_por_identidad_y_minuto(filas),
        "invariantes_(por_construccion)": inv.invariantes(
            inv.recuento_por_frame(filas, 100.0, 64.0), 11
        ),
    }


def main() -> None:
    import pandas as pd
    import yaml

    from src.tracking.cache_io import cargar_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--sin-hoja", action="store_true")
    ap.add_argument(
        "--unidad",
        choices=["identidad", "trozo"],
        default="identidad",
        help="identidad = intento 1; trozo = intento 2 (trozos de 1,5 s)",
    )
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    inv = _mod("diag22e_invariantes")

    cfg_b = yaml.safe_load(open(PATAS["benja"]["config"]))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg_b["rutas"]["cache"])["cache"]
    }
    hoy_b = pd.read_csv(PATAS["benja"]["hoy"])
    det_arb = inv.proxy_arbitro(hoy_b, dets)  # el árbitro, fijado con la pasada de HOY

    res = {"benja": {}, "villa": {}}
    res["benja"]["hoy"] = metricas_benja(PATAS["benja"]["hoy"], (dets, det_arb))
    res["villa"]["hoy"] = metricas_villa(PATAS["villa"]["hoy"])
    csvs = {}
    for pata in ("benja", "villa"):
        for variante, permutar in (("real", False), ("permutado", True)):
            csv, mensajes = pasada(pata, variante, salida, permutar, args.unidad)
            csvs[(pata, variante)] = csv
            m = (
                metricas_benja(csv, (dets, det_arb))
                if pata == "benja"
                else metricas_villa(csv)
            )
            m["solver"] = resumen_solver(mensajes)
            casadas, cambian = filas_que_cambian(
                pd.read_csv(PATAS[pata]["hoy"]), pd.read_csv(csv)
            )
            m["filas_reales_comparadas"] = int(len(casadas))
            m["filas_que_cambian_de_etiqueta"] = int(len(cambian))
            m["cambios_hoy_a_tope"] = {
                f"{a}->{b}": int(n)
                for (a, b), n in cambian.groupby(["etiqueta_hoy", "etiqueta_tope"])
                .size()
                .items()
            }
            res[pata][variante] = m

    hb, rb = res["benja"]["hoy"], res["benja"]["real"]
    hv, rv = res["villa"]["hoy"], res["villa"]["real"]
    crit = {
        "a_error": rb["a_equipo_equivocado_pct"] <= hb["a_equipo_equivocado_pct"] + 0.3,
        "a_cobertura": rb["a_cobertura_pct"] >= hb["a_cobertura_pct"] - 0.5,
        "b_arbitro_<=20": (rb["b_arbitro_en_equipo_ventana_gt"]["pct"] or 0) <= 20.0,
        "c_villa_arbitro": (rv["c_arbitro_en_equipo_pct"] or 0)
        <= hv["c_arbitro_en_equipo_pct"],
        "c_villa_error": rv["c_equipo_equivocado_pct"] <= hv["c_equipo_equivocado_pct"],
        "d_etiquetas": rb["d_etiquetas_por_identidad_y_minuto"]
        <= hb["d_etiquetas_por_identidad_y_minuto"]
        and rv["d_etiquetas_por_identidad_y_minuto"]
        <= hv["d_etiquetas_por_identidad_y_minuto"],
        "d_tiempo_<60s": rb["solver"] is not None and rb["solver"]["s"] < 60,
    }
    crit["cumple"] = all(crit.values())
    crit["control_permutado_peor_en_5_puntos"] = (
        res["benja"]["permutado"]["a_equipo_equivocado_pct"]
        >= rb["a_equipo_equivocado_pct"] + 5.0
    )
    res["criterio"] = crit

    if not args.sin_hoja:
        hoja = _mod("hoja_otro_v3")
        hoy_k = inv.con_caja(hoy_b, dets)
        nueva = pd.read_csv(csvs[("benja", "real")])
        _c, cambian = filas_que_cambian(hoy_b, nueva)
        cambian = cambian.merge(
            hoy_k[["frame", "x_m", "y_m", "k"]], on=["frame", "x_m", "y_m"]
        )
        elegidas = cambian.sample(
            n=min(N_HOJA, len(cambian)), random_state=SEMILLA_HOJA
        )
        n = hoja.escribir_hoja(
            (
                "tope_cardinalidad"
                if args.unidad == "identidad"
                else f"tope_{args.unidad}"
            ),
            elegidas.sort_values("frame"),
            dets,
            R / cfg_b["rutas"]["video"],
            lambda r: {
                "id": int(r.id_jugador),
                "etiqueta_hoy": r.etiqueta_hoy,
                "etiqueta_tope": r.etiqueta_tope,
            },
        )
        res["hoja_recortes"] = n
    sufijo = "" if args.unidad == "identidad" else f"_{args.unidad}"
    (salida / f"bloque1{sufijo}.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
