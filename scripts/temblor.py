#!/usr/bin/env python
"""Segunda línea base: TEMBLOR de las posiciones, sin depender del GT.

Por qué hace falta otra métrica. La línea base de localización (0,88 m)
no puede juzgar un cambio de anclaje: la corrección de los clics se
derivó de las cajas del detector, así que el GT quedó anclado como el
detector. Y su suelo de ruido (0,42 m de sesgo residual + 0,91 m de
calibración) es del orden de lo que mide, con lo que una mejora de
58 cm → 11 cm caería entera por debajo del instrumento.

El temblor no tiene ese problema: se mide **sobre la propia trayectoria**,
sin referencia externa, y es exactamente lo que se ve en el replay.

## Cómo se separa el temblor del fútbol de verdad

Con la **segunda diferencia**: `Δ² = p[i+1] − 2·p[i] + p[i−1]`.

- Vale **cero exacto** para movimiento rectilíneo uniforme: un niño
  esprintando en línea recta no cuenta como temblor.
- Vale una **constante** para aceleración constante, así que su
  DISPERSIÓN tampoco se entera de una carrera que arranca.
- El ruido de medida, en cambio, pasa entero: si el error de posición
  tiene desviación σ, la de Δ² es σ·√6.

De ahí el estimador: **σ_ruido ≈ desviación(Δ²) / √6**, y se usa la
versión robusta (MAD) para que un cambio brusco de dirección real —un
regate— no infle la cifra.

Lo que SÍ contamina: el *jerk* real, o sea cambios de aceleración. Un
regate de verdad mete algo de señal aquí. Por eso la comparación
importante no es el valor absoluto sino **sistema frente a los clics
humanos sobre las mismas jugadas**: los dos ven el mismo fútbol, así que
la diferencia es método.

Uso:
    python scripts/temblor.py
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking_data.processor import project_point  # noqa: E402

FRANJAS = [("10-20 m", 10, 20), ("20-30 m", 20, 30), ("30+ m", 30, 1e9)]
RAIZ6 = np.sqrt(6.0)

logger = logging.getLogger("temblor")


def sigma_robusta(v: np.ndarray) -> float:
    """Desviación típica robusta (MAD escalada) de un vector."""
    if len(v) < 4:
        return float("nan")
    mad = float(np.median(np.abs(v - np.median(v))))
    return 1.4826 * mad


def temblor_de(trayectorias, etiqueta, paso=1):
    """(franja → σ de ruido en metros) a partir de segundas diferencias.

    `paso` submuestrea para poder comparar series con cadencias
    distintas: el ruido estimado es independiente del dt, pero el jerk
    real no, así que hay que igualar la cadencia antes de comparar.
    """
    por_franja = {n: [] for n, _l, _h in FRANJAS}
    n_series = 0
    for _id, obs in trayectorias:
        obs = sorted(obs, key=lambda o: o[0])[::paso]
        if len(obs) < 5:
            continue
        n_series += 1
        P = np.array([[o[1], o[2]] for o in obs])
        d2 = P[2:] - 2 * P[1:-1] + P[:-2]
        y = P[1:-1, 1]
        for nombre, lo, hi in FRANJAS:
            sel = (y >= lo) & (y < hi)
            if sel.sum() >= 4:
                # Cada eje aporta su propio ruido; se combinan en módulo.
                sx = sigma_robusta(d2[sel, 0]) / RAIZ6
                sy = sigma_robusta(d2[sel, 1]) / RAIZ6
                por_franja[nombre].append(float(np.hypot(sx, sy)))
    return por_franja, n_series


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/tracking_benja/posiciones_benja_emb.csv")
    p.add_argument("--clics", default="data/annotations/gt_benja/clics.csv")
    p.add_argument("--config", default="configs/processor_benja_emb.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    H = np.load(cfg["rutas"]["homografia"])

    # CRUDO: posiciones tal como salen del tracker, ANTES del suavizado.
    # Medir sobre el CSV exportado daba 0,01 m — que es el suavizador
    # haciendo su trabajo, no el detector. Comparar eso con los clics de
    # Alex habría dicho que el sistema tiembla 60 veces menos que su
    # mano, y la conclusión habría sido que no hay margen. Falsa.
    import pickle

    from src.team_classification.pipeline_equipos import (
        cargar_config_equipos,
        entrenar_clasificador,
    )
    from src.tracking.cache_io import cargar_cache
    from src.tracking.filtro_confianza import filtrar_por_confianza
    from src.tracking.perfiles import correr_perfil

    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as fh:
        col = pickle.load(fh)
    cache, col = filtrar_por_confianza(
        datos["cache"], col, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    clf = entrenar_clasificador(col, cfg_eq, cache)
    ids = correr_perfil(
        cache,
        datos["fps"],
        datos["sample"],
        cfg_tr,
        perfil="bytetrack",
        colores=col,
        clasificador=clf,
        cfg_equipos=cfg_eq,
    )
    tray_crudo = []
    for k, ident in enumerate(ids, start=1):
        obs = [
            (par[0], float(pos[0]), float(pos[1]))
            for tr in ident
            for pos, par in zip(tr.pos, tr.det_idxs)
        ]
        if len(obs) >= 5:
            tray_crudo.append((k, obs))

    sis = pd.read_csv(args.csv)
    if "es_real" in sis.columns:
        sis = sis[sis.es_real == 1]
    tray_sis = [
        (i, [(f.frame, f.x_m, f.y_m) for f in g.itertuples()])
        for i, g in sis.groupby("id_jugador")
    ]

    # Clics SIN corregir: referencia independiente, no derivada de las cajas
    clics = pd.read_csv(args.clics)
    tray_gt = []
    for j, g in clics.groupby("jugador"):
        obs = []
        for f in g.sort_values("frame").itertuples():
            mx, my = project_point(float(f.x_px), float(f.y_px), H)
            obs.append((f.frame, mx, my))
        tray_gt.append((j, obs))

    cab = f"{'fuente':<34}" + "".join(f"{n:>12}" for n, _l, _h in FRANJAS)
    print("\n── TEMBLOR (σ de ruido de posición, metros) ──\n")
    print(cab)
    print("-" * len(cab))
    for nombre, tray, paso in (
        ("SISTEMA CRUDO (0,10 s)", tray_crudo, 1),
        ("SISTEMA CRUDO a 0,50 s", tray_crudo, 5),
        ("SISTEMA suavizado+interp (0,50 s)", tray_sis, 5),
        ("CLICS de Alex (0,50 s, sin corregir)", tray_gt, 1),
    ):
        por_franja, n = temblor_de(tray, nombre, paso)
        fila = f"{nombre:<34}"
        for f_nombre, _l, _h in FRANJAS:
            v = por_franja[f_nombre]
            fila += f"{np.median(v):>12.2f}" if v else f"{'—':>12}"
        print(fila)

    print(
        "\n  σ se estima con la segunda diferencia: cero para velocidad\n"
        "  constante, insensible a aceleración constante, y el ruido pasa\n"
        "  entero (desviación de Δ² = σ·√6). Robusta con MAD para que un\n"
        "  regate real no la infle."
    )
    print(
        "\n  La comparación que importa es SISTEMA vs CLICS a la MISMA\n"
        "  cadencia: los dos ven el mismo fútbol, así que la diferencia es\n"
        "  método, no jugadores."
    )


if __name__ == "__main__":
    main()
