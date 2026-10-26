#!/usr/bin/env python
"""CELDA DE COLAB: feature v3 en Villaviciosa, hoy contra v3 con las métricas del 22-oct (d).

docs/diagnostico_22oct_d.md, bloque 2. **No se ejecuta en el Mac**: el vídeo de Villaviciosa
(`data/raw/partido.mp4`) solo está en Drive. En Colab, desde la raíz del repo con `data/` montado:

    !apt-get -qq install -y ffmpeg          # el ffmpeg de LÍNEA DE COMANDOS (suele venir ya)
    !python scripts/colab_v3_villa.py --salida outputs/v3_villa

Coste estimado: SIN GPU (no corre el detector). El tramo de la caché son 60 s (1.500 frames a
25 fps, 1 de cada 3 muestreado): decodificar + undistort + dos features por caja, unos 2-4 min de
CPU; las dos pasadas `desde_cache`, ~1 min cada una.

Pasos, y dónde para:
1. Caché v1 + v3 desde el vídeo con el ffmpeg CLI y la MISMA corrección de distorsión del modo
   `full` (`diag22b_feature_v3.calcular_v1_v3`). **CONTROL**: la v1 tiene que reproducir ≥ 99 %
   de la caché de producción (`cache_colores_v4pre.pkl`). Si no, PARA: el montaje no es el de
   producción y nada de lo que siga se puede leer.
2. `desde_cache` con la caché de color de hoy y con la v3 (solo cambia esa ruta).
3. Para las dos: error de equipo y casadas (casado 1-a-1 a 2 m, `comparar_escalas.casar`),
   cobertura, árbitro dentro de un equipo (el GT de Villaviciosa SÍ anota al árbitro) y
   simultaneidad de `otro` en el campo (100 × 64), con su control en la ventana del GT.

`--sin-v3` hace solo la parte de «hoy» con la caché de producción (sirve para probar el script
en local, donde sí están las cachés y el GT pero no el vídeo).
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor.yaml"
GT = R / "data/annotations/ground_truth_tracking/annotations.xml"
H_GT = R / "data/calibracion/homografia.npy"
OFFSET, PASO = 7500, 15
MIN_IDENTICAS = 0.99
RADIO = 2.0
EQUIPOS = ("A", "B")


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pasada(nombre: str, salida: Path, cache_colores: Path) -> Path:
    import yaml

    from src.tracking_data.processor import procesar_desde_cache

    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["cache_colores"] = str(cache_colores)
    cfg["rutas"]["salida_csv"] = str(salida / f"posiciones_{nombre}.csv")
    cfg["rutas"]["salida_meta"] = str(salida / f"posiciones_{nombre}_meta.json")
    procesar_desde_cache(cfg)
    return salida / f"posiciones_{nombre}.csv"


def arbitro_en_equipo(filas, gt) -> dict:
    """Apariciones del árbitro del GT casadas (1-a-1 con todas las personas) con una fila A/B."""
    from scipy.optimize import linear_sum_assignment

    porf = {f: g for f, g in filas.groupby("frame")}
    casadas = en_equipo = apariciones = 0
    for f, obs in gt.items():
        g = porf.get(f)
        arb = [i for i, o in enumerate(obs) if o.label == "referee"]
        if g is None or not arb:
            continue
        apariciones += len(arb)
        P = np.array([o.pos for o in obs])
        xy = g[["x_m", "y_m"]].to_numpy()
        coste = np.hypot(xy[None, :, 0] - P[:, None, 0], xy[None, :, 1] - P[:, None, 1])
        coste = np.where(coste > RADIO, 1e6, coste)
        etq = g.etiqueta.astype(str).str.replace("portero_", "").to_numpy()
        for i, j in zip(*linear_sum_assignment(coste)):
            if i in arb and coste[i, j] < 1e6:
                casadas += 1
                en_equipo += etq[j] in EQUIPOS
    return {
        "apariciones_gt": apariciones,
        "casadas": casadas,
        "en_un_equipo": en_equipo,
        "pct_de_las_casadas": 100 * en_equipo / casadas if casadas else None,
    }


def simultaneidad(filas, largo: float, ancho: float, gt_frames) -> dict:
    dentro = (
        (filas.etiqueta == "otro")
        & filas.x_m.between(0, largo)
        & filas.y_m.between(0, ancho)
    )
    serie = (
        filas[dentro]
        .groupby("frame")
        .size()
        .reindex(sorted(filas.frame.unique()), fill_value=0)
    )

    def dist(s):
        return {
            "frames": int(len(s)),
            "0": int((s == 0).sum()),
            "1": int((s == 1).sum()),
            "2": int((s == 2).sum()),
            ">=3": int((s >= 3).sum()),
            "pct_ge2": round(100 * float((s >= 2).mean()), 2) if len(s) else None,
        }

    return {
        "tramo": dist(serie),
        "ventana_gt": dist(serie[serie.index.isin(gt_frames)]),
    }


def metricas(csv: Path, gt, largo: float, ancho: float) -> dict:
    import pandas as pd

    ce, c3 = _mod("comparar_escalas"), _mod("diag22c_v3")
    filas = pd.read_csv(csv)
    # MISMO protocolo que `comparar_escalas.py`: solo filas reales y frames comunes con el GT.
    reales = filas[filas.es_real == 1]
    comunes = sorted(set(reales.frame) & set(gt))
    resumen = ce.informar(csv.stem, ce.casar(reales, {f: gt[f] for f in comunes}))
    return {
        "equipo_equivocado_pct": 100 * resumen["mal"] / max(resumen["en_equipo"], 1),
        "casado": resumen,
        "cobertura": c3.cobertura(filas, gt),
        "arbitro_en_equipo_gt": arbitro_en_equipo(filas, gt),
        "simultaneidad_otro": simultaneidad(filas, largo, ancho, set(gt)),
    }


def main() -> None:
    import yaml

    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--sin-v3", action="store_true", help="solo «hoy» (prueba local)")
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(CONFIG))
    largo, ancho = cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"]
    res = {}

    caches = {"hoy": R / cfg["rutas"]["cache_colores"]}
    if not args.sin_v3:
        fv = _mod("diag22b_feature_v3")
        v3, control = fv.calcular_v1_v3(CONFIG)
        res["control_v1"] = control
        (salida / "feature_v3_control.json").write_text(json.dumps(control, indent=1))
        if (
            not control["frac_identicas_1e-6"]
            or control["frac_identicas_1e-6"] < MIN_IDENTICAS
        ):
            print(json.dumps(control, indent=1))
            raise SystemExit(
                "CONTROL FALLIDO: la v1 recalculada no reproduce la caché de producción. "
                "El montaje (decodificador, distorsión o recorte) no es el de producción: "
                "no se mide nada más."
            )
        caches["v3"] = salida / "cache_colores_v3.pkl"
        pickle.dump(v3, open(caches["v3"], "wb"))

    gt = gt_a_por_frame(parsear_cvat(GT), np.load(H_GT), OFFSET, PASO)
    for nombre, cache in caches.items():
        res[nombre] = metricas(pasada(nombre, salida, cache), gt, largo, ancho)
    (salida / "bloque2_villa.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
