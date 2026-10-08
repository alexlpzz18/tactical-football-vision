#!/usr/bin/env python
"""Ablación 1/3 contra 1/1 en el piloto de 5 min del benjamín — SOLO PREPARADA.

Plan y criterio en `docs/plan_ablacion_1a1.md`. El CRITERIO de abajo se commitea ANTES de que
exista el caché 1/1 (que sale de Colab, `scripts/colab_cache_1a1.py`, sin lanzar).

La idea del control de ruido: el caché 1/1 contiene TRES submuestreos 1/3 distintos (fase 0, 1 y
2: los frames con f % 3 == fase). Son tres corridas «iguales» que solo cambian qué frames ven, con
el mismo detector. Su dispersión es el suelo de ruido: una diferencia de 1/1 menor que eso no
cuenta. (Repetir dos veces la misma corrida no sirve: el pipeline es determinista desde el caché y
daría ruido 0 — `docs/suelo_de_ruido.md`.)

Uso (local, CPU, cuando el caché 1/1 esté en data/ablacion_1a1/):
    python scripts/ablacion_muestreo.py inventario
    python scripts/ablacion_muestreo.py correr --trabajo DIR          # 4 pasadas: 1/1 y 3 fases
    python scripts/ablacion_muestreo.py medir --trabajo DIR
    python scripts/ablacion_muestreo.py prueba --trabajo DIR          # el banco sobre el 1/3 de hoy
"""

import argparse
import contextlib
import copy
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

# ── Fijado ANTES de medir (commit aparte) ─────────────────────────────────────
# dir: +1 = más es mejor, −1 = menos es mejor, 0 = control (tiene que salir IGUAL)
METRICAS = {
    "dets_en_campo_por_frame": 0,  # el mismo detector: si cambia, algo no cuadra
    "faltan_por_equipo_frame": -1,
    "sobran_por_equipo_frame": -1,
    "fragmentaciones": -1,
    "identidades_por_persona": -1,
    "quimeras": -1,
    "DetA": +1,
    "AssA": +1,
    "IDF1": +1,
}
CRITERIO = {
    "radio_m": 2.0,  # el del banco y del desglose
    "lado_caja_trackeval": 2.0,
    # Una diferencia cuenta solo si supera el RANGO (max − min) de las tres fases 1/3.
    "ruido": "rango_de_las_3_fases",
    # Adopción (además, nada se adopta sin el OK de Alex, y cuesta ×3 de GPU):
    "debe_mejorar": ["faltan_por_equipo_frame"],
    "y_al_menos_una_de": ["DetA", "AssA", "IDF1"],
    "ninguna_empeora": True,  # ninguna métrica con dir ≠ 0 peor que la media de las fases + ruido
    "control_igual_tolerancia": 0.10,  # dets/frame: |Δ| ≤ ruido + 0,10, o el banco está roto
    # quimera: identidad con ≥ 2 personas del GT, la segunda con ≥ 3 frames casados
    "quimera_min_frames_segunda": 3,
}

PILOTO = {
    "frame_ini": 8991,
    "frame_fin": 17982,
}  # 5:00-10:00 de archivo (6:33-11:33 reproductor)
OFFSET_GT, PASO_GT = 9750, 15
GT = R / "data/annotations/gt_benja/annotations.xml"
CONFIG_BASE = R / "configs/processor_benja_piloto5min.yaml"
CACHE_1A1 = R / "data/ablacion_1a1/cache_detecciones_benja_piloto5min_1a1.pkl"
COLORES_1A1 = R / "data/ablacion_1a1/cache_colores_benja_piloto5min_1a1.pkl"

# ── Inventario: qué parámetros están en FRAMES/observaciones y cuáles en segundos ──
# Solo lo que corre en producción (perfil `bytetrack`) o lo que la decide. `ruta` es la clave en
# el YAML (None = está escrito en el código). `convertir`: se multiplica por el factor de muestreo
# para que valga los mismos SEGUNDOS (1/3 → 1/1: ×3).
INVENTARIO = [
    # tracking (configs/tracking_benja.yaml)
    dict(
        param="bytetrack.buffer_perdido_s",
        unidad="s",
        convertir=False,
        nota="ya en segundos (× 30 por la fórmula de supervision, independiente del fps)",
    ),
    dict(
        param="bytetrack.usar_fps_efectivo",
        unidad="-",
        convertir=False,
        nota="le pasa fps/sample a ByteTrack: se adapta solo",
    ),
    dict(
        param="bytetrack.min_frames_consecutivos",
        unidad="frames",
        convertir=False,
        nota="vale 1 = sin requisito; 1 es 1 en cualquier muestreo",
    ),
    dict(
        param="bytetrack.umbral_emparejamiento",
        unidad="1−IoU por paso",
        convertir=False,
        nota="NO es una unidad: a 1/1 las cajas se solapan más entre pasos. Es parte de lo que "
        "se mide; 0,995 ya es casi el máximo permisivo",
    ),
    dict(
        param="(supervision) filtro de Kalman",
        unidad="por paso",
        convertir=False,
        nota="ruido de proceso por PASO, sin dt: a 1/1 hay 3× pasos. Irreducible: es el efecto "
        "que se quiere medir",
    ),
    dict(
        param="cosido_pureza.max_hueco / tol_por_seg / v_max_salto",
        unidad="s, m/s",
        convertir=False,
        nota="en segundos y m/s",
    ),
    dict(
        param="cosido_pureza.solape_max_frames",
        unidad="frames",
        convertir=False,
        nota="vale 0: cero es cero en cualquier muestreo",
    ),
    dict(
        param="cosido_pureza.max_pasadas",
        unidad="iteraciones",
        convertir=False,
        nota="no es tiempo",
    ),
    dict(
        param="cosido_pureza._velocidad_final(ventana=3)",
        unidad="muestras",
        convertir=True,
        ruta=None,
        nota="ESCRITO EN EL CÓDIGO: velocidad de salida con 3 muestras = 0,3 s a 1/3 "
        "y 0,1 s a 1/1. Se parchea en la ablación (×3), no en producción",
    ),
    dict(
        param="escalado_resolucion.jitter_px (3,5)",
        unidad="px por paso",
        convertir=False,
        nota="MEDIDO a 1/3 (residuo sobre 5 muestras). A 1/1 hay que RE-MEDIRLO con el mismo "
        "método antes de correr: el ruido de cajas consecutivas puede estar correlacionado",
    ),
    dict(
        param="suavizado.ventana_s",
        unidad="s",
        convertir=False,
        nota="en segundos (base = ventana_s / dt)",
    ),
    dict(
        param="suavizado: tope de 61 muestras",
        unidad="muestras",
        convertir=True,
        ruta=None,
        nota="ESCRITO EN EL CÓDIGO: 6,1 s a 1/3, 2,0 s a 1/1. Se comprueba si llega a tocarse",
    ),
    dict(
        param="interpolacion.max_hueco / hueco_min",
        unidad="s",
        convertir=False,
        nota="en segundos",
    ),
    dict(
        param="consolidacion.min_frames_comunes / corte_velocidad.min_observaciones",
        unidad="frames",
        convertir=False,
        nota="NO corren con el perfil bytetrack (_SOLO_INTERPOLA)",
    ),
    dict(
        param="puerta_reentrada.min_obs_firma",
        unidad="obs",
        convertir=False,
        nota="la puerta está apagada en el benjamín",
    ),
    # equipos (configs/team_classification_benja.yaml)
    dict(
        param="agregacion.por_observacion.ventana_s",
        unidad="s",
        convertir=False,
        nota="en segundos",
    ),
    dict(
        param="agregacion.min_obs_para_otro",
        unidad="obs",
        convertir=True,
        ruta=("agregacion", "min_obs_para_otro"),
        nota="25 obs = 2,5 s a 1/3",
    ),
    dict(
        param="staff.min_observaciones",
        unidad="obs",
        convertir=True,
        ruta=("staff", "min_observaciones"),
        nota="5 obs = 0,5 s",
    ),
    dict(
        param="staff.min_obs_lento",
        unidad="obs",
        convertir=True,
        ruta=("staff", "min_obs_lento"),
        nota="25 obs = 2,5 s: juzga una VELOCIDAD",
    ),
    dict(
        param="arbitro.min_observaciones",
        unidad="obs",
        convertir=True,
        ruta=("arbitro", "min_observaciones"),
        nota="25 obs = 2,5 s",
    ),
    dict(
        param="entrenamiento.min_features",
        unidad="recortes",
        convertir=False,
        nota="tamaño mínimo de muestra del fit, no tiempo: a 1/1 se alcanza antes",
    ),
    dict(
        param="porteros.min_frames_nuevos",
        unidad="fracción",
        convertir=False,
        nota="es una fracción: no depende del muestreo",
    ),
    dict(
        param="pipeline_equipos: 25 en avisar_tercer_grupo, 100 en arbitro",
        unidad="obs",
        convertir=False,
        ruta=None,
        nota="ESCRITOS EN EL CÓDIGO pero solo deciden un AVISO del "
        "log, no una etiqueta",
    ),
]


# ─────────────────────────────── piezas puras (con tests) ─────────────────────
def convertir_configs(cfg_equipos: dict, factor: int) -> dict:
    """Copia de la config de equipos con los recuentos de observaciones × `factor`."""
    cfg = copy.deepcopy(cfg_equipos)
    for item in INVENTARIO:
        ruta = item.get("ruta")
        if not item["convertir"] or not ruta:
            continue
        nodo = cfg
        for k in ruta[:-1]:
            nodo = nodo[k]
        nodo[ruta[-1]] = int(nodo[ruta[-1]]) * factor
    return cfg


@contextlib.contextmanager
def velocidad_final_en_segundos(factor: int):
    """Parchea `cosido_pureza._velocidad_final` (ventana 3 muestras) a 3 × factor muestras."""
    import src.tracking.cosido_pureza as cp

    original = cp._velocidad_final

    def parcheada(identidad, ventana=3):
        return original(identidad, ventana=ventana * factor)

    cp._velocidad_final = parcheada
    try:
        yield
    finally:
        cp._velocidad_final = original


def submuestrear(datos: dict, colores: dict | None, fase: int, paso: int = 3):
    """Los frames con frame_idx % paso == fase. Los det_idx no cambian (frames enteros)."""
    cache = [e for e in datos["cache"] if e["frame_idx"] % paso == fase]
    frames = {e["frame_idx"] for e in cache}
    sub = {**datos, "cache": cache, "sample": datos["sample"] * paso}
    col = (
        None
        if colores is None
        else {k: v for k, v in colores.items() if k[0] in frames}
    )
    return sub, col


def frame_de_evaluacion(f_gt: int, fase: int, paso: int = 3) -> int:
    """El frame del caché más cercano a un frame del GT (los del GT son múltiplos de 3)."""
    candidatos = [f_gt + d for d in range(-paso, paso + 1) if (f_gt + d) % paso == fase]
    return min(candidatos, key=lambda f: abs(f - f_gt))


def ruido(valores_fases: list[float]) -> float:
    return float(max(valores_fases) - min(valores_fases))


def veredicto(m_11: dict, m_fases: list[dict]) -> dict:
    """Aplica CRITERIO. Devuelve cada métrica con Δ, ruido y lectura, y el veredicto final."""
    filas, mejoran, empeoran, control_roto = {}, set(), set(), False
    for nombre, direccion in METRICAS.items():
        fases = [m[nombre] for m in m_fases]
        media, r = float(np.mean(fases)), ruido(fases)
        delta = float(m_11[nombre]) - media
        if direccion == 0:
            lectura = (
                "igual"
                if abs(delta) <= r + CRITERIO["control_igual_tolerancia"]
                else "ROTO"
            )
            control_roto |= lectura == "ROTO"
        elif delta * direccion > r:
            lectura = "mejora"
            mejoran.add(nombre)
        elif -delta * direccion > r:
            lectura = "empeora"
            empeoran.add(nombre)
        else:
            lectura = "dentro del ruido"
        filas[nombre] = {
            "1/1": m_11[nombre],
            "media_fases": media,
            "delta": delta,
            "ruido": r,
            "lectura": lectura,
        }
    if control_roto:
        final = "NO CONCLUYENTE (el control de detecciones no sale igual: el banco está roto)"
    elif empeoran:
        final = f"NO SE ADOPTA (empeora: {sorted(empeoran)})"
    elif not set(CRITERIO["debe_mejorar"]) <= mejoran:
        final = "NO SE ADOPTA (los faltantes no bajan más que el ruido)"
    elif not mejoran & set(CRITERIO["y_al_menos_una_de"]):
        final = "NO SE ADOPTA (ni DetA, ni AssA, ni IDF1 mejoran más que el ruido)"
    else:
        final = "PASA EL CRITERIO (se adopta solo con el OK de Alex: cuesta ×3 de GPU)"
    return {"metricas": filas, "veredicto": final}


def quimeras_e_ids(
    casados: list[tuple[int, int]], min_segunda: int
) -> tuple[int, float]:
    """(nº de quimeras, identidades por persona) desde pares (id_sistema, persona_gt) por frame."""
    from collections import Counter, defaultdict

    por_id, por_persona = defaultdict(Counter), defaultdict(set)
    for ident, persona in casados:
        por_id[ident][persona] += 1
        por_persona[persona].add(ident)
    quimeras = sum(
        1
        for c in por_id.values()
        if len(c) >= 2 and c.most_common(2)[1][1] >= min_segunda
    )
    ids = float(np.mean([len(s) for s in por_persona.values()])) if por_persona else 0.0
    return quimeras, ids


# ─────────────────────────────── corridas y métricas ──────────────────────────
def _pasada(datos, colores, cfg_eq, factor, trabajo: Path, nombre: str):
    """Pasada de producción desde caché (código de HOY) sobre un caché dado."""
    import yaml

    from src.tracking_data.processor import procesar_desde_cache

    d = trabajo / nombre
    d.mkdir(parents=True, exist_ok=True)
    pickle.dump(datos, open(d / "cache.pkl", "wb"))
    pickle.dump(colores, open(d / "colores.pkl", "wb"))
    yaml.safe_dump(cfg_eq, open(d / "equipos.yaml", "w"), allow_unicode=True)
    cfg = yaml.safe_load(open(CONFIG_BASE))
    cfg["modo"] = "desde_cache"
    cfg["config_equipos"] = str(d / "equipos.yaml")
    cfg["rutas"].update(
        cache=str(d / "cache.pkl"),
        cache_colores=str(d / "colores.pkl"),
        salida_csv=str(d / "posiciones.csv"),
        salida_meta=str(d / "meta.json"),
    )
    with velocidad_final_en_segundos(factor):
        procesar_desde_cache(cfg)
    (d / "cache.pkl").unlink()  # disco justo: el caché ya está en data/
    (d / "colores.pkl").unlink()


def correr(args) -> None:
    import yaml

    trabajo = Path(args.trabajo)
    datos = pickle.load(open(CACHE_1A1, "rb"))
    colores = pickle.load(open(COLORES_1A1, "rb"))
    assert datos["sample"] == 1, "el caché 1/1 tiene que venir con sample = 1"
    cfg_eq = yaml.safe_load(
        open(R / yaml.safe_load(open(CONFIG_BASE))["config_equipos"])
    )
    _pasada(datos, colores, convertir_configs(cfg_eq, 3), 3, trabajo, "1a1")
    for fase in (0, 1, 2):
        sub, col = submuestrear(datos, colores, fase)
        _pasada(sub, col, cfg_eq, 1, trabajo, f"fase{fase}")
    print(f"✓ cuatro pasadas en {trabajo}")


def metricas_de(csv_path: Path, cache: list[dict], fase: int | None) -> dict:
    """Las métricas del CRITERIO para una pasada. `fase` None = 1/1 (frames del GT exactos)."""
    import tempfile

    import pandas as pd

    from src.evaluation.desglose_error import (
        casar_frame,
        cuenta_de_recuento,
        equipo_de_etiqueta,
    )
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.evaluation.metricas import calcular_metricas_tracking
    from src.evaluation.modelo import Observacion
    from src.evaluation.trackeval_runner import evaluar_con_trackeval

    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    gt = gt_a_por_frame(parsear_cvat(GT), H, OFFSET_GT, PASO_GT)
    csv = pd.read_csv(csv_path)
    por_frame = {f: g for f, g in csv.groupby("frame")}

    # Predicción en el formato del banco, sobre los frames del GT (o el más cercano)
    pred, faltan, sobran, n_eq_frame, casados = {}, 0, 0, 0, []
    for f in sorted(gt):
        fe = f if fase is None else frame_de_evaluacion(f, fase)
        g = por_frame.get(fe, csv.iloc[0:0])
        pred[f] = [
            Observacion(int(r.id_jugador), np.array([r.x_m, r.y_m]), str(r.etiqueta))
            for r in g.itertuples()
        ]
        reales = g[g.es_real == 1]
        personas = [(equipo_de_etiqueta(o.team), o.pos[0], o.pos[1]) for o in gt[f]]
        fc = casar_frame(
            f,
            personas,
            reales.x_m.to_numpy(),
            reales.y_m.to_numpy(),
            reales.etiqueta.to_numpy(),
            CRITERIO["radio_m"],
        )
        for eq in ("A", "B"):
            c = cuenta_de_recuento(fc, eq)
            faltan += c["faltan"]
            sobran += c["sobran"]
            n_eq_frame += 1
        ids = reales.id_jugador.to_numpy()
        for k, p in enumerate(fc.personas):
            if p.fila is not None:
                casados.append((int(ids[p.fila]), int(gt[f][k].obj_id)))

    frames = sorted(gt)
    propias = calcular_metricas_tracking(gt, pred, frames, CRITERIO["radio_m"])
    with tempfile.TemporaryDirectory(prefix="trackeval_") as tmp:
        te = evaluar_con_trackeval(
            gt, pred, frames, tmp, CRITERIO["lado_caja_trackeval"]
        )
    quim, ids_pp = quimeras_e_ids(casados, CRITERIO["quimera_min_frames_segunda"])
    en_campo = [
        sum(1 for d in e["dets"] if 0 <= d[0] <= 62 and 0 <= d[1] <= 40) for e in cache
    ]
    return {
        "dets_en_campo_por_frame": float(np.mean(en_campo)),
        "faltan_por_equipo_frame": faltan / n_eq_frame,
        "sobran_por_equipo_frame": sobran / n_eq_frame,
        "fragmentaciones": int(propias.fragmentaciones),
        "identidades_por_persona": ids_pp,
        "quimeras": quim,
        "DetA": te["DetA"],
        "AssA": te["AssA"],
        "IDF1": te["IDF1"],
    }


def medir(args) -> None:
    trabajo = Path(args.trabajo)
    datos = pickle.load(open(CACHE_1A1, "rb"))
    m11 = metricas_de(trabajo / "1a1/posiciones.csv", datos["cache"], None)
    mf = []
    for fase in (0, 1, 2):
        sub, _ = submuestrear(datos, None, fase)
        mf.append(
            metricas_de(trabajo / f"fase{fase}/posiciones.csv", sub["cache"], fase)
        )
    res = {"criterio": CRITERIO, "fases": mf, **veredicto(m11, mf)}
    (trabajo / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


def prueba(args) -> None:
    """El banco sobre el piloto 1/3 de HOY (sin GPU): comprueba que las métricas se calculan."""
    import yaml

    trabajo = Path(args.trabajo)
    cfg = yaml.safe_load(open(CONFIG_BASE))
    datos = pickle.load(open(R / cfg["rutas"]["cache"], "rb"))
    colores = pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    cfg_eq = yaml.safe_load(open(R / cfg["config_equipos"]))
    _pasada(datos, colores, cfg_eq, 1, trabajo, "hoy_1a3")
    m = metricas_de(trabajo / "hoy_1a3/posiciones.csv", datos["cache"], None)
    (trabajo / "prueba.json").write_text(json.dumps(m, indent=1))
    print(json.dumps(m, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventario")
    for nombre in ("correr", "medir", "prueba"):
        s = sub.add_parser(nombre)
        s.add_argument("--trabajo", required=True)
    args = ap.parse_args()
    if args.cmd == "inventario":
        for it in INVENTARIO:
            marca = "×3" if it["convertir"] else "  "
            print(f"{marca} {it['param']:<62} [{it['unidad']}] {it['nota']}")
    else:
        {"correr": correr, "medir": medir, "prueba": prueba}[args.cmd](args)


if __name__ == "__main__":
    main()
