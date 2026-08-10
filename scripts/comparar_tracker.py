#!/usr/bin/env python
"""¿Aporta nuestro tracking artesanal sobre un tracker estándar?

La pregunta de fondo del proyecto. Este script la responde con datos:
corre ByteTrack TAL CUAL sobre las MISMAS detecciones cacheadas y lo mide
con el MISMO banco (cobertura colectiva, concurrencia, IDF1, IDSW,
quimeras y accuracy de equipos con nuestro propio clasificador sobre las
identidades que produzca cada uno).

Cuatro pipelines, para separar dónde está el valor (si lo hay):

  1. ByteTrack tal cual                → el estándar, sin ayudas
  2. ByteTrack + nuestro post-proceso  → ¿el valor está en el post?
  3. Nuestro perfil candidato          → nuestra Etapa A + cosido, sin post
  4. Nuestro pipeline completo         → lo que corre hoy en producción

Comparar 1 vs 3 dice si nuestro tracker aporta; 1 vs 2 y 3 vs 4 dicen
cuánto aporta el post-proceso a cada uno.

Nota sobre ByteTrack: se usa la implementación de `supervision` (la misma
que el pipeline legacy del repo). Está deprecada en 0.28 pero funciona, y
evita instalar `boxmot`, que rompió el entorno en su día. Es un tracker
por IoU en píxeles con Kalman, el estándar de facto.

Uso:
    python scripts/comparar_tracker.py
    python scripts/comparar_tracker.py --config configs/evaluation_v4pre.yaml
"""

import argparse
import logging
import pickle
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

warnings.filterwarnings("ignore")

from src.evaluation.adaptador import trayectorias_a_por_frame  # noqa: E402
from src.evaluation.alineacion import frames_comunes  # noqa: E402
from src.evaluation.asociacion import UmbralProfundidad, asociar_todos  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.evaluation.metricas import (  # noqa: E402
    accuracy_equipos,
    calcular_metricas_tracking,
    cobertura_colectiva,
    resumen_equipos,
)
from src.team_classification.pipeline_equipos import (  # noqa: E402
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.field_tracker import Tracklet  # noqa: E402
from src.tracking.interpolacion import identidades_a_trayectorias  # noqa: E402
from src.tracking.perfiles import correr_perfil, postprocesar  # noqa: E402

logger = logging.getLogger("comparar_tracker")


def correr_bytetrack(cache, fps, sample, **kwargs) -> list[list[Tracklet]]:
    """ByteTrack sobre NUESTRAS detecciones cacheadas → identidades.

    Se le dan las cajas en píxeles y la confianza, que es exactamente lo
    que espera; la posición en metros que ya está en el caché se conserva
    para que las métricas se calculen sobre las MISMAS coordenadas que
    usa nuestro tracker. Es decir: solo cambia quién decide las
    identidades, no de dónde salen las posiciones.
    """
    import supervision as sv

    tracker = sv.ByteTrack(**kwargs)
    por_track: dict[int, list[tuple]] = defaultdict(list)

    for entrada in cache:
        dets = entrada["dets"]
        if not dets:
            continue
        detecciones = sv.Detections(
            xyxy=np.array([[d[2], d[3], d[4], d[5]] for d in dets], dtype=np.float32),
            confidence=np.array([d[6] for d in dets], dtype=np.float32),
            class_id=np.zeros(len(dets), dtype=int),
        )
        seguidas = tracker.update_with_detections(detecciones)
        for caja, track_id in zip(seguidas.xyxy, seguidas.tracker_id):
            if track_id is None:
                continue
            # Recuperar el índice de la detección original (por caja)
            det_idx = int(
                np.argmin(
                    [
                        abs(d[2] - caja[0]) + abs(d[3] - caja[1]) + abs(d[4] - caja[2])
                        for d in dets
                    ]
                )
            )
            d = dets[det_idx]
            por_track[int(track_id)].append(
                (entrada["t"], np.array([d[0], d[1]]), det_idx, entrada["frame_idx"])
            )

    identidades = []
    for track_id, observaciones in por_track.items():
        observaciones.sort(key=lambda o: o[0])
        t0, pos0, det0, frame0 = observaciones[0]
        tracklet = Tracklet(track_id, t0, pos0, det0, frame0)
        for t, pos, det_idx, frame_idx in observaciones[1:]:
            tracklet.anadir(t, pos, det_idx, frame_idx)
        identidades.append([tracklet])
    logger.info("ByteTrack: %d identidades", len(identidades))
    return identidades


def medir(nombre, trayectorias, equipos, gt, comunes, tiempos, umbral):
    """Todas las métricas del banco para un conjunto de trayectorias."""
    pred = trayectorias_a_por_frame(trayectorias, equipos)
    m = calcular_metricas_tracking(gt, pred, comunes, umbral)
    cob = cobertura_colectiva(gt, pred, comunes, umbral)
    todos = sorted(tiempos)
    n_por_frame = np.array([len(pred.get(f, [])) for f in todos], dtype=float)
    res = resumen_equipos(accuracy_equipos(gt, pred, comunes, umbral).detalle)

    pares = asociar_todos(gt, pred, comunes, umbral)
    votos = defaultdict(Counter)
    for _f, emparejados in pares.items():
        for id_gt, id_pred in emparejados:
            votos[id_pred][id_gt] += 1
    quimeras = con10 = 0
    for cuenta in votos.values():
        total = sum(cuenta.values())
        if total >= 10:
            con10 += 1
            if cuenta.most_common(1)[0][1] / total < 0.60:
                quimeras += 1

    emparejadas = int(round(m.recall * m.n_gt))
    return {
        "nombre": nombre,
        "nids": len(trayectorias),
        "cobertura": cob.cobertura,
        "concurrencia": float(np.median(n_por_frame)),
        "idf1": m.idf1,
        "idsw": m.id_switches,
        "tasa": m.id_switches / emparejadas if emparejadas else 0.0,
        "recall": m.recall,
        "quimeras": f"{quimeras}/{con10}",
        "acc": res.accuracy_campo,
    }


def imprimir(filas, gt_concurrencia):
    cabecera = (
        f"{'pipeline':<38} {'nIds':>5} {'cob.':>6} {'conc':>5} {'IDF1':>6} "
        f"{'IDSW':>5} {'tasa':>6} {'recall':>7} {'quimeras':>9} {'equipos':>8}"
    )
    print("\n" + "=" * len(cabecera))
    print(cabecera)
    print("-" * len(cabecera))
    for f in filas:
        acc = f"{f['acc']:.3f}" if f["acc"] is not None else "  N/D"
        print(
            f"{f['nombre']:<38} {f['nids']:>5} {f['cobertura']:>6.3f} "
            f"{f['concurrencia']:>5.0f} {f['idf1']:>6.3f} {f['idsw']:>5} "
            f"{f['tasa']:>6.3f} {f['recall']:>7.3f} {f['quimeras']:>9} {acc:>8}"
        )
    print("-" * len(cabecera))
    print(f"{'referencia GT':<38} {23:>5} {1.0:>6.3f} {gt_concurrencia:>5.0f}")
    print("=" * len(cabecera))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/evaluation_v4pre.yaml")
    parser.add_argument("--config-tracking", default="configs/tracking.yaml")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    with open(args.config_tracking) as f:
        cfg_tracking = yaml.safe_load(f)

    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    homografia = np.load(cfg["rutas"]["homografia"])
    gt = gt_a_por_frame(
        parsear_cvat(cfg["rutas"]["ground_truth"]),
        homografia,
        frame_offset=cfg["alineacion"]["frame_offset"],
        paso_gt=cfg["alineacion"]["paso_gt"],
    )
    umbral = UmbralProfundidad.desde_dict(cfg["asociacion"]["umbral_profundidad"])
    frames_ts = [(e["frame_idx"], e["t"]) for e in datos["cache"]]
    tiempos = dict(frames_ts)
    comunes = frames_comunes(gt, [f for f, _ in frames_ts])

    cfg_equipos = cargar_config_equipos()
    clasificador = entrenar_clasificador(colores, cfg_equipos, datos["cache"])

    def clasificar(identidades):
        return clasificar_identidades(identidades, colores, clasificador, cfg_equipos)

    filas = []

    # ── 1. ByteTrack tal cual (defaults de la librería) ──
    ids_bt = correr_bytetrack(datos["cache"], datos["fps"], datos["sample"])
    filas.append(
        medir(
            "ByteTrack tal cual",
            identidades_a_trayectorias(ids_bt),
            clasificar(ids_bt),
            gt,
            comunes,
            tiempos,
            umbral,
        )
    )

    # ── 1b. ByteTrack con el frame_rate REAL del caché ──
    # El caché es 1 de cada `sample` frames, así que entre dos frames
    # procesados pasa 3× más tiempo del que ByteTrack supone por defecto.
    # Decírselo es darle su mejor oportunidad, no hacerle trampa.
    fps_efectivo = datos["fps"] / datos["sample"]
    ids_bt2 = correr_bytetrack(
        datos["cache"],
        datos["fps"],
        datos["sample"],
        frame_rate=int(round(fps_efectivo)),
        lost_track_buffer=int(round(fps_efectivo * 2)),
    )
    filas.append(
        medir(
            f"ByteTrack con fps real ({fps_efectivo:.1f})",
            identidades_a_trayectorias(ids_bt2),
            clasificar(ids_bt2),
            gt,
            comunes,
            tiempos,
            umbral,
        )
    )

    # ── 2. ByteTrack + NUESTRO post-proceso ──
    mejor_bt = ids_bt if filas[0]["cobertura"] >= filas[1]["cobertura"] else ids_bt2
    eq_bt = clasificar(mejor_bt)
    tray_bt, eq_bt_post = postprocesar(mejor_bt, eq_bt, frames_ts, cfg_tracking)
    filas.append(
        medir(
            "ByteTrack + nuestro post-proceso",
            tray_bt,
            eq_bt_post,
            gt,
            comunes,
            tiempos,
            umbral,
        )
    )

    # ── 2b. ByteTrack + solo INTERPOLACIÓN, y + corte ──
    # Nuestro post-proceso se diseñó para tapar defectos de NUESTRO
    # tracker (fragmentación y fusiones agresivas). Aplicado entero a uno
    # que no los tiene puede restar, así que se prueba pieza a pieza.
    for etiqueta, activar in (
        (
            "ByteTrack + solo interpolación",
            {"consolidacion": False, "corte_velocidad": False},
        ),
        (
            "ByteTrack + interpolación + corte",
            {"consolidacion": False, "corte_velocidad": True},
        ),
    ):
        cfg_parcial = dict(cfg_tracking)
        cfg_parcial["consolidacion"] = dict(
            cfg_tracking.get("consolidacion", {}), activa=activar["consolidacion"]
        )
        cfg_parcial["corte_velocidad"] = dict(
            cfg_tracking.get("corte_velocidad", {}), activo=activar["corte_velocidad"]
        )
        tray_p, eq_p = postprocesar(mejor_bt, dict(eq_bt), frames_ts, cfg_parcial)
        filas.append(medir(etiqueta, tray_p, eq_p, gt, comunes, tiempos, umbral))

    # ── 3. Nuestro perfil candidato, SIN post-proceso ──
    ids_nuestro = correr_perfil(
        datos["cache"],
        datos["fps"],
        datos["sample"],
        cfg_tracking,
        perfil="candidato",
        colores=colores,
        clasificador=clasificador,
        cfg_equipos=cfg_equipos,
    )
    filas.append(
        medir(
            "Nuestro candidato (sin post)",
            identidades_a_trayectorias(ids_nuestro),
            clasificar(ids_nuestro),
            gt,
            comunes,
            tiempos,
            umbral,
        )
    )

    # ── 4. Nuestro pipeline completo (lo de producción) ──
    eq_nuestro = clasificar(ids_nuestro)
    tray_nuestro, eq_post = postprocesar(
        ids_nuestro, eq_nuestro, frames_ts, cfg_tracking
    )
    filas.append(
        medir(
            "Nuestro pipeline COMPLETO (producción)",
            tray_nuestro,
            eq_post,
            gt,
            comunes,
            tiempos,
            umbral,
        )
    )

    gt_conc = np.median([len(gt.get(f, [])) for f in comunes])
    imprimir(filas, gt_conc)
    print(
        "\ncob. = cobertura colectiva (métrica de producto) · conc = identidades\n"
        "simultáneas (GT ≈ 22) · tasa = IDSW por posición emparejada ·\n"
        "quimeras = identidades con ≥10 votos GT y dominante <60 %\n"
    )


if __name__ == "__main__":
    main()
