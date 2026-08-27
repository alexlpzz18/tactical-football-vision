#!/usr/bin/env python
"""El 46 % del árbitro que NUNCA llega al tercer grupo: ¿por qué?

Medido sobre la parte entera del benjamín: el tercer grupo recoge el
54 % de los frames en que el árbitro está en el campo. El otro 46 % ya
está dentro de un equipo cuando la exclusividad lo mira, así que dos
sesiones puliendo `un_solo_arbitro` solo alcanzaban a la mitad del
problema.

Encargo de Alex (27-ago-2026), UNA sesión: de esas observaciones, ¿cuál
de las tres las explica?

  (a) EL FIT       — el color crudo de ese recorte ya cae en A o en B.
  (b) EL SUAVIZADO — la ventana de 1,5 s lo arrastra al equipo de al lado.
  (c) EL ARQUETIPO — el catálogo arbitral no dispara sobre su identidad.

⚠️ CÓMO SE SABE CUÁLES SON SUS OBSERVACIONES, sin GT. El GT del benjamín
NO anota al árbitro (14 tracks, todos `player`), así que la verdad se
reconstruye por POSICIÓN Y TIEMPO, que es como deben indexarse los GT
aquí: los trozos del tercer grupo son él (7 de sus 10 identidades no
coexisten nunca — es una persona partida), se interpola su trayectoria a
los frames sin cubrir y se busca la detección más cercana. Solo se
interpola sobre huecos cortos: en un hueco largo el árbitro se mueve y la
interpolación sería una posición inventada.

Uso:
    python scripts/arbitro_46.py
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("arbitro46")

# Hueco máximo (s) sobre el que se interpola la posición del árbitro.
HUECO_MAX_S = 8.0
# Radio para dar por suya la detección más cercana del frame.
RADIO_M = 2.5


def trayectoria_del_arbitro(df):
    """(frames, x, y) de las observaciones del tercer grupo, ordenadas."""
    sub = df[(df.etiqueta == "otro") & (df.es_real == 1)]
    g = sub.groupby("frame")[["x_m", "y_m"]].mean().sort_index()
    return g.index.to_numpy(), g.x_m.to_numpy(), g.y_m.to_numpy()


def frames_a_rellenar(frames_vistos, todos, fps_efectivo, hueco_max_s):
    """Frames sin árbitro etiquetado que caen en un hueco CORTO."""
    vistos = set(int(f) for f in frames_vistos)
    salida = []
    for f in todos:
        if f in vistos:
            continue
        antes = frames_vistos[frames_vistos < f]
        despues = frames_vistos[frames_vistos > f]
        if not len(antes) or not len(despues):
            continue
        hueco = (despues[0] - antes[-1]) / fps_efectivo
        if hueco <= hueco_max_s:
            salida.append(f)
    return salida


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_p1.csv")
    p.add_argument(
        "--cache", default="data/tracking_benja/cache_detecciones_benja_p1.pkl"
    )
    p.add_argument(
        "--colores", default="data/tracking_benja/cache_colores_benja_p1.pkl"
    )
    p.add_argument("--equipos", default="configs/team_classification_benja.yaml")
    p.add_argument("--tracking", default="configs/tracking_benja.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    import pickle

    import yaml

    from src.team_classification.arbitro import (
        ARQUETIPOS,
        arquetipos_activos,
        brillo_medio,
        tono_dominante,
    )
    from src.team_classification.color_classifier import _solo_hs
    from src.team_classification.pipeline_equipos import (
        cargar_config_equipos,
        entrenar_clasificador,
    )
    from src.tracking.cache_io import cargar_cache
    from src.tracking.filtro_confianza import filtrar_por_confianza

    cfg_tr = yaml.safe_load(open(args.tracking))
    cfg_eq = cargar_config_equipos(args.equipos)
    datos = cargar_cache(args.cache)
    with open(args.colores, "rb") as f:
        colores = pickle.load(f)
    cache, colores = filtrar_por_confianza(
        datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    pr = clf._prototipos
    A, B = _solo_hs(pr.a), _solo_hs(pr.b)
    sep = float(np.linalg.norm(A - B))
    activos = arquetipos_activos([pr.a, pr.b], ARQUETIPOS)
    print(f"arquetipos activos en este partido: {[a.nombre for a in activos]}")

    df = pd.read_csv(args.csv)
    por_frame = {e["frame_idx"]: e for e in cache}
    fps_ef = datos["fps"] / datos["sample"]

    fr, xs, ys = trayectoria_del_arbitro(df)
    todos = np.array(sorted(por_frame))
    huecos = frames_a_rellenar(fr, todos, fps_ef, HUECO_MAX_S)
    print(
        f"\nel tercer grupo cubre {len(fr)} frames de {len(todos)} "
        f"({100*len(fr)/len(todos):.0f} %)"
    )
    print(
        f"frames sin cubrir en huecos de ≤ {HUECO_MAX_S:.0f} s: {len(huecos)} "
        f"(los huecos largos se descartan: interpolarlos sería inventar)"
    )

    # Tamaño y color medio de cada identidad, que es lo que ve el catálogo.
    reales = df[df.es_real == 1]
    feats_de = {}
    for k, g in reales.groupby("id_jugador"):
        acc = []
        for _, row in g.iterrows():
            e = por_frame.get(int(row.frame))
            if not e:
                continue
            i = min(
                range(len(e["dets"])),
                key=lambda j: (e["dets"][j][0] - row.x_m) ** 2
                + (e["dets"][j][1] - row.y_m) ** 2,
            )
            f = colores.get((int(row.frame), i))
            if f is not None:
                acc.append(f)
        if acc:
            feats_de[k] = (len(acc), np.mean(acc, axis=0))

    def dispara_arquetipo(k):
        """(veredicto, motivo) del catálogo sobre la identidad k."""
        if k not in feats_de:
            return False, "sin recortes"
        n, media = feats_de[k]
        if n < int(cfg_eq.get("arbitro", {}).get("min_observaciones", 25)):
            return False, f"identidad corta ({n} obs < 25)"
        tono = tono_dominante(media)
        if tono is None:
            return False, "sin tono dominante"
        b = brillo_medio(media)
        for arq in activos:
            if arq.contiene(tono[0], tono[1], b):
                return True, arq.nombre
        return False, f"tono H={tono[0]:.0f} S={tono[1]:.0f} fuera del catálogo"

    causas = Counter()
    detalle = Counter()
    n_ok = 0
    for f in huecos:
        e = por_frame[f]
        if not e["dets"]:
            continue
        x = float(np.interp(f, fr, xs))
        y = float(np.interp(f, fr, ys))
        d = [(dd[0] - x) ** 2 + (dd[1] - y) ** 2 for dd in e["dets"]]
        i = int(np.argmin(d))
        if d[i] > RADIO_M**2:
            continue
        feat = colores.get((f, i))
        if feat is None:
            continue
        n_ok += 1
        # ¿Qué le pasó de verdad? Se busca su fila en el CSV.
        fila = reales[
            (reales.frame == f)
            & (
                np.hypot(reales.x_m - e["dets"][i][0], reales.y_m - e["dets"][i][1])
                < 0.5
            )
        ]
        etiqueta_final = str(fila.etiqueta.iloc[0]) if len(fila) else "?"
        k = int(fila.id_jugador.iloc[0]) if len(fila) else None

        crudo = clf.predict_color(feat)
        hs = _solo_hs(feat)
        dist = min(np.linalg.norm(hs - A), np.linalg.norm(hs - B)) / sep
        ok_arq, motivo = dispara_arquetipo(k) if k else (False, "sin identidad")

        if ok_arq:
            causas["(c') el arquetipo SÍ dispara pero se pierde después"] += 1
        elif crudo in ("A", "B") and dist < 0.9:
            causas["(a) EL FIT: el color crudo ya cae en un equipo"] += 1
        elif crudo in ("A", "B"):
            causas["(a') el fit lo mete en un equipo, pero LEJOS (dist ≥ 0,9)"] += 1
        else:
            causas["(b) EL SUAVIZADO: crudo no es de equipo y acaba en uno"] += 1
        if not ok_arq:
            detalle[motivo.split("(")[0].strip() if "obs <" in motivo else motivo] += 1
        if etiqueta_final in ("otro", "staff"):
            causas["(ninguna: acabó fuera de los equipos)"] += 1

    print(f"\nobservaciones del árbitro recuperadas para el análisis: {n_ok}\n")
    print("  POR QUÉ ACABAN EN UN EQUIPO")
    for causa, n in causas.most_common():
        print(f"    {n:5d}  ({100*n/max(n_ok,1):4.1f} %)  {causa}")
    print("\n  POR QUÉ NO DISPARA EL ARQUETIPO (motivo del catálogo)")
    for motivo, n in detalle.most_common(6):
        print(f"    {n:5d}  ({100*n/max(n_ok,1):4.1f} %)  {motivo}")


if __name__ == "__main__":
    main()
