#!/usr/bin/env python
"""¿Se degrada el sistema a lo largo de una parte entera?

La pasada de 20 minutos es la primera que corre de verdad a esta escala:
un solo fit de color para todo el partido, y reglas (staff, tercer grupo,
exclusividad del árbitro, portero por conjunto) calibradas sobre tramos
de 30 s a 5 min. Este script parte la parte en tramos y compara.

⚠️ LO QUE NO SE PUEDE MEDIR AQUÍ. El GT del benjamín solo cubre los
frames 9750-10635 (t=325-355 s), o sea 30 segundos dentro del segundo
tramo. Fuera de ahí NO hay verdad, así que la exactitud (observaciones
con equipo equivocado) solo se puede dar en esa ventana y NO por tramo.
Lo que sí viaja a toda la parte son señales ESTRUCTURALES que no
necesitan GT y que se rompen de forma reconocible:

  - jugadores en pista por frame y por equipo: en F7 son 7 por lado
    (6 de campo + portero). Un tramo con 5 o con 10 está mal, y no hace
    falta GT para saberlo.
  - reparto A/B de las observaciones: dos equipos juegan el mismo
    partido, así que un desequilibrio grande es el fit tirando de un
    lado.
  - salud del fit: distancia de cada recorte a SU prototipo. Si la luz
    cambia, sube.
  - prototipos por tramo contra el prototipo global: es la prueba
    directa de si UN fit aguanta 20 minutos.

Uso:
    python scripts/deriva_parte_entera.py
    python scripts/deriva_parte_entera.py --minutos 5
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("deriva")

# En F7 juegan 7 por equipo (6 de campo + portero).
JUGADORES_F7 = 7


def por_tramo(df, minutos):
    """Parte el CSV en tramos de `minutos` y devuelve (etiqueta, sub-df)."""
    paso = minutos * 60.0
    fin = df.tiempo_s.max()
    t = 0.0
    while t < fin:
        sub = df[(df.tiempo_s >= t) & (df.tiempo_s < t + paso)]
        if len(sub):
            yield f"{int(t//60):2d}-{int((t+paso)//60):2d}", sub
        t += paso


def metricas_estructurales(sub):
    """Lo que se puede afirmar SIN ground truth."""
    real = sub[sub.es_real == 1]
    out = {"obs": len(real), "ids": real.id_jugador.nunique()}
    for equipo in ("A", "B"):
        marca = real.etiqueta.isin([equipo, f"portero_{equipo}"])
        eq = real[marca]
        out[f"obs_{equipo}"] = len(eq)
        # Jugadores DISTINTOS por frame: la señal que no necesita GT.
        por_frame = eq.groupby("frame").id_jugador.nunique()
        out[f"en_pista_{equipo}"] = float(por_frame.median()) if len(por_frame) else 0.0
        out[f"centroide_{equipo}"] = (
            float(eq.groupby("frame").x_m.mean().median()) if len(eq) else float("nan")
        )
        # Anchura del bloque: la métrica de producto que más se movió
        # esta semana, y se puede calcular sin verdad.
        anchos = eq.groupby("frame").y_m.std()
        out[f"anchura_{equipo}"] = (
            float(anchos.median()) if len(anchos) else float("nan")
        )
    total_ab = out["obs_A"] + out["obs_B"]
    out["sesgo_AB"] = (out["obs_B"] - out["obs_A"]) / total_ab if total_ab else 0.0
    for etq in ("otro", "staff"):
        out[f"%{etq}"] = 100 * (real.etiqueta == etq).sum() / max(len(real), 1)
    return out


def salud_del_fit(cache, colores, cfg_eq, minutos, fps):
    """Distancia a su prototipo y prototipos por tramo contra el global.

    Es la prueba directa de si UN solo fit aguanta 20 minutos: se entrena
    como en producción (una vez, con todo) y además se entrena uno por
    tramo, para ver si los prototipos se mueven.
    """
    from src.team_classification.color_classifier import _solo_hs
    from src.team_classification.pipeline_equipos import entrenar_clasificador

    def protos_de(clf):
        """Los dos prototipos del fit, en la escala en la que se comparan.

        `_solo_hs` no es un detalle: la feature v2 tiene 336 valores y el
        clasificador solo usa los 256 primeros. Comparar los 336 mediría
        otra cosa.
        """
        pr = clf._prototipos
        return np.array([_solo_hs(pr.a), _solo_hs(pr.b)])

    global_clf = entrenar_clasificador(colores, cfg_eq, cache)
    protos = protos_de(global_clf)
    print(f"  colores del fit GLOBAL: {global_clf.colores_equipos()}")
    t_de = {e["frame_idx"]: e["t"] for e in cache}
    paso = minutos * 60.0

    filas = []
    colores_locales: dict = {}
    fin = max(t_de.values())
    t = 0.0
    while t < fin:
        claves = [k for k in colores if t <= t_de.get(k[0], -1) < t + paso]
        if claves:
            X = np.array([_solo_hs(colores[k]) for k in claves])
            d = np.linalg.norm(X[:, None, :] - protos[None, :, :], axis=2)
            asignado = d.min(axis=1)
            margen = np.sort(d, axis=1)
            # Fit SOLO de este tramo, con el mismo filtro de producción.
            sub_cache = [e for e in cache if t <= e["t"] < t + paso]
            sub_col = {k: colores[k] for k in claves}
            try:
                local = entrenar_clasificador(sub_col, cfg_eq, sub_cache)
                p_local = protos_de(local)
                colores_locales[f"{int(t//60):2d}-{int((t+paso)//60):2d}"] = (
                    local.colores_equipos()
                )
                # Los prototipos no tienen orden estable: se emparejan por
                # cercanía al global, nunca por índice.
                dist = np.linalg.norm(p_local[:, None, :] - protos[None, :, :], axis=2)
                desvio = float(
                    min(dist[0, 0] + dist[1, 1], dist[0, 1] + dist[1, 0]) / 2
                )
            except Exception as err:  # pragma: no cover - diagnóstico
                logger.warning("fit local del tramo %.0f s: %s", t, err)
                desvio = float("nan")
            filas.append(
                {
                    "tramo": f"{int(t//60):2d}-{int((t+paso)//60):2d}",
                    "recortes": len(claves),
                    "dist_media": float(asignado.mean()),
                    "dist_p90": float(np.quantile(asignado, 0.9)),
                    "margen": float(np.mean(margen[:, 1] - margen[:, 0])),
                    "desvio_prototipos": desvio,
                }
            )
        t += paso
    return filas, colores_locales


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
    p.add_argument("--minutos", type=int, default=5)
    p.add_argument("--sin-fit", action="store_true", help="salta la parte cara")
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    df = pd.read_csv(args.csv)
    print(f"\n{'='*94}")
    print(f"DERIVA POR TRAMOS DE {args.minutos} MIN — {args.csv}")
    print(f"{'='*94}")

    cab = (
        f"  {'tramo':>6} {'obs':>7} {'ids':>5} | {'en pista A':>10} {'B':>5} | "
        f"{'sesgo B-A':>9} | {'anch A':>7} {'anch B':>7} | {'%otro':>6} {'%staff':>7}"
    )
    print("\n" + cab)
    print("  " + "-" * (len(cab) - 2))
    for etq, sub in por_tramo(df, args.minutos):
        m = metricas_estructurales(sub)
        print(
            f"  {etq:>6} {m['obs']:>7} {m['ids']:>5} | {m['en_pista_A']:>10.1f} "
            f"{m['en_pista_B']:>5.1f} | {100*m['sesgo_AB']:>8.1f}% | "
            f"{m['anchura_A']:>7.2f} {m['anchura_B']:>7.2f} | "
            f"{m['%otro']:>5.1f}% {m['%staff']:>6.1f}%"
        )
    print(f"\n  (en F7 lo correcto son {JUGADORES_F7} por equipo, portero incluido)")

    if args.sin_fit:
        return
    import pickle

    import yaml

    from src.team_classification.pipeline_equipos import cargar_config_equipos
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
    print(f"\n{'='*94}")
    print("SALUD DEL FIT DE COLOR (uno solo para los 20 min)")
    print(f"{'='*94}")
    filas, colores_locales = salud_del_fit(
        cache, colores, cfg_eq, args.minutos, datos["fps"]
    )
    cab = (
        f"  {'tramo':>6} {'recortes':>9} {'dist. a su prototipo':>21} "
        f"{'p90':>7} {'margen A-B':>11} {'prototipos vs global':>21}"
    )
    print("\n" + cab)
    print("  " + "-" * (len(cab) - 2))
    for f in filas:
        print(
            f"  {f['tramo']:>6} {f['recortes']:>9} {f['dist_media']:>21.4f} "
            f"{f['dist_p90']:>7.4f} {f['margen']:>11.4f} "
            f"{f['desvio_prototipos']:>21.4f}"
        )
    print("\n  colores que aprendería un fit hecho SOLO con cada tramo:")
    for tramo, cols in colores_locales.items():
        print(f"    {tramo}: {cols}")


if __name__ == "__main__":
    main()
