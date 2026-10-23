#!/usr/bin/env python
"""CELDA DE COLAB: el árbitro como seguimiento de un único objeto, en Villaviciosa (el GT lo anota).

docs/diagnostico_23oct_c.md, bloque 2. **No se ejecuta en el Mac**: el vídeo de Villaviciosa
(`data/raw/partido.mp4`) solo está en Drive. En Colab, desde la raíz del repo con `data/` montado:

    !python scripts/colab_arbitro_villa.py --salida outputs/arbitro_villa

Pasos:
1. La banda del amarillo flúor, medida igual que la del benjamín: p5-p95 de H, p5 de S y V de los
   píxeles candidatos (S ≥ 100, V ≥ 150) del torso del árbitro del GT, en la primera mitad de su
   ventana (`diag23a_chaleco.py --pata villa`).
2. La caché de chaleco con esa banda (`cache_chaleco.py`).
3. El modelo de emisión con el árbitro del GT (casado a ≤ 2 m) contra los jugadores (≤ 1 m).
4. Hoy, variante 1 (sustituye) y variante 2 (añade), `desde_cache`.
5. Para cada una:
   - fracción de frames del GT con la pista a < 1,5 m del árbitro del GT;
   - fracción de apariciones del árbitro del GT con una fila de EQUIPO a < 1,5 m;
   - equipo equivocado.

   Línea base de hoy: árbitro dentro de un equipo 5,3 %, equipo equivocado 23,6 %.
"""

import argparse
import importlib.util
import json
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor.yaml"
BINS = [0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 1.0001]


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def modelo_emision(chaleco, dets, gt):
    from src.team_classification.arbitro_viterbi import estimar_modelo

    arb, jug = [], []
    for f, obs in gt.items():
        D = np.array([d[:2] for d in dets.get(f, [])]).reshape(-1, 2)
        if not len(D):
            continue
        for o in obs:
            d = np.hypot(D[:, 0] - o.pos[0], D[:, 1] - o.pos[1])
            j = int(np.argmin(d))
            if o.label == "referee" and d[j] <= 2.0:
                arb.append(chaleco.get((f, j), 0.0))
            elif o.label != "referee" and d[j] <= 1.0:
                jug.append(chaleco.get((f, j), 0.0))
    return estimar_modelo(np.array(arb), np.array(jug), BINS)


def pasada(nombre, salida, cache_chaleco, ruta_modelo, vit):
    import src.team_classification.arbitro_viterbi as av
    import src.team_classification.pipeline_equipos as pe
    from src.tracking_data.processor import procesar_desde_cache

    cfg = yaml.safe_load(open(CONFIG))
    cfg["modo"] = "desde_cache"
    csv = salida / f"villa_{nombre}.csv"
    cfg["rutas"].update(
        salida_csv=str(csv),
        salida_meta=str(salida / f"villa_{nombre}_meta.json"),
        cache_chaleco=str(cache_chaleco),
    )
    captura = {}
    orig_cfg, orig_pista = pe.cargar_config_equipos, av.pista_del_arbitro

    def con_flag(ruta):
        ce = orig_cfg(ruta)
        if vit is not None:
            ce.setdefault("arbitro", {})["viterbi"] = {
                "activo": True,
                "modelo_emision": str(ruta_modelo),
                **vit,
            }
        return ce

    def espia(cache, chaleco, mod, params, dims):
        p = orig_pista(cache, chaleco, mod, params, dims)
        captura.update(pista=p, cache=cache)
        return p

    pe.cargar_config_equipos, av.pista_del_arbitro = con_flag, espia
    try:
        procesar_desde_cache(cfg)
    finally:
        pe.cargar_config_equipos, av.pista_del_arbitro = orig_cfg, orig_pista
    return csv, captura


def medir(csv, captura, gt) -> dict:
    import pandas as pd

    cv = _mod("colab_v3_villa")
    filas = pd.read_csv(csv)
    r = filas[filas.es_real == 1]
    porf = {f: g for f, g in r.groupby("frame")}
    cerca_pista = n_arb = equipo_cerca = 0
    dets = {e["frame_idx"]: e["dets"] for e in captura.get("cache", [])}
    for f, obs in gt.items():
        for o in (o for o in obs if o.label == "referee"):
            n_arb += 1
            if captura.get("pista") and f in captura["pista"]:
                d = dets[f][captura["pista"][f]]
                cerca_pista += np.hypot(d[0] - o.pos[0], d[1] - o.pos[1]) < 1.5
            g = porf.get(f)
            if g is not None:
                eq = g.etiqueta.astype(str).str.replace("portero_", "").isin(["A", "B"])
                dist = np.hypot(g.x_m - o.pos[0], g.y_m - o.pos[1])
                equipo_cerca += bool((eq & (dist < 1.5)).any())
    m = cv.metricas(csv, gt, 100.0, 64.0)
    return {
        "pista_a_menos_de_1_5m_del_arbitro_pct": (
            round(100 * cerca_pista / max(n_arb, 1), 1)
            if captura.get("pista") is not None
            else None
        ),
        "fila_de_equipo_a_menos_de_1_5m_del_arbitro_pct": round(
            100 * equipo_cerca / max(n_arb, 1), 1
        ),
        "equipo_equivocado_pct": round(m["equipo_equivocado_pct"], 2),
    }


def main() -> None:
    from src.tracking.cache_io import cargar_cache

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    # 1. la banda del árbitro de Villaviciosa
    subprocess.run(
        [
            py,
            str(R / "scripts/diag23a_chaleco.py"),
            "--pata",
            "villa",
            "--salida",
            str(salida),
            "--sin-partido",
        ],
        check=True,
    )
    banda = json.loads((salida / "bloque2_villa.json").read_text())[
        "banda_medida_H_S_V"
    ]
    # 2. la caché de chaleco
    cache_chaleco = salida / "cache_chaleco_villa.pkl"
    subprocess.run(
        [
            py,
            str(R / "scripts/cache_chaleco.py"),
            "--config",
            str(CONFIG),
            "--salida",
            str(cache_chaleco),
            "--banda",
            *[str(b) for b in banda],
        ],
        check=True,
    )
    # 3. el modelo de emisión con el árbitro del GT
    cfg = yaml.safe_load(open(CONFIG))
    dets = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    gt = _mod("diag22g_color").gt_de("villa")
    mod = modelo_emision(pickle.load(open(cache_chaleco, "rb")), dets, gt)
    ruta_modelo = salida / "arbitro_viterbi_villa.json"
    ruta_modelo.write_text(json.dumps(mod, indent=1))
    # 4-5. hoy y las dos variantes
    res = {"banda": banda, "modelo": mod}
    for nombre, vit in (
        ("hoy", None),
        ("v1_sustituye", {"variante": "sustituye"}),
        ("v2_anade", {"variante": "anade"}),
    ):
        csv, captura = pasada(nombre, salida, cache_chaleco, ruta_modelo, vit)
        res[nombre] = medir(csv, captura, gt)
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / "arbitro_villa.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
