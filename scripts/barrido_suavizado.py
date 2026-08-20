#!/usr/bin/env python
"""Barrido de suavizado × interpolación, con DOS varas de medir.

El informe y el replay no quieren lo mismo, y hasta ahora se les servía
la misma configuración. El informe agrega posiciones en mapas de calor y
métricas colectivas: le conviene cobertura, aunque la trayectoria
individual tiemble. El replay se mira jugada a jugada: le conviene que
nada dé saltos imposibles, aunque se pierda algo de cobertura.

Por eso cada combinación se juzga con los dos criterios a la vez, y la
salida propone un preset para cada uno.

Uso:
    python scripts/barrido_suavizado.py
"""

import argparse
import itertools
import logging
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)
from src.tracking.perfiles import correr_perfil  # noqa: E402
from src.tracking.resolucion import ResolucionCampo  # noqa: E402
from src.tracking.suavizado import (  # noqa: E402
    ParametrosSuavizado,
    suavizar_trayectorias,
)

# Por encima de esto un paso es físicamente imposible y en el replay se
# ve como un salto: es el defecto que el suavizado tiene que matar.
V_IMPOSIBLE = 8.5


def numeros_de_replay(trayectorias, tiempos):
    """Los tres que delatan un replay poco creíble."""
    velocidades, n_por_frame = [], {}
    for tray in trayectorias:
        puntos = [(f, p) for f, p, r in tray if r]
        for (f1, p1), (f2, p2) in zip(puntos, puntos[1:]):
            dt = tiempos.get(f2, 0) - tiempos.get(f1, 0)
            if dt > 0:
                velocidades.append(
                    float(np.linalg.norm(np.array(p2) - np.array(p1)) / dt)
                )
        for f, _p, _r in tray:
            n_por_frame[f] = n_por_frame.get(f, 0) + 1
    v = np.array(velocidades) if velocidades else np.array([0.0])
    return {
        "conc_replay": (
            float(np.median(list(n_por_frame.values()))) if n_por_frame else 0.0
        ),
        "v99": float(np.percentile(v, 99)),
        "saltos": float(100 * (v > V_IMPOSIBLE).mean()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/evaluation_v4pre.yaml")
    parser.add_argument("--config-tracking", default="configs/tracking.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    ids = correr_perfil(
        banco.datos["cache"],
        banco.datos["fps"],
        banco.datos["sample"],
        banco.cfg_tracking,
        perfil="bytetrack",
        colores=banco.colores,
        clasificador=banco.clasificador,
        cfg_equipos=banco.cfg_equipos,
    )
    equipos = banco.clasificar(ids)
    resolucion = ResolucionCampo(np.load(banco.cfg["rutas"]["homografia"]), 100.0, 64.0)

    ventanas = [0.3, 0.5, 0.8, 1.2]
    huecos = [1.5, 2.5, 4.0]
    metodos = ["media", "savgol"]

    cab = (
        f"{'ventana':>8}{'hueco':>7}{'método':>9}  "
        f"{'INFORME cob.':>13}{'IDF1':>7}{'quim':>6}  "
        f"{'REPLAY conc':>12}{'v99':>7}{'% saltos':>10}"
    )
    print("\n" + cab)
    print("-" * len(cab))

    filas = []
    for ventana, hueco, metodo in itertools.product(ventanas, huecos, metodos):
        tray = identidades_a_trayectorias(ids)
        tray = suavizar_trayectorias(
            tray,
            ParametrosSuavizado(ventana_s=ventana, metodo=metodo),
            resolucion=resolucion,
            dt=banco.dt,
        )
        rep = numeros_de_replay(tray, banco.tiempos)
        tray = interpolar_trayectorias(tray, banco.frames_ts, max_hueco=hueco)
        m = medir(
            "x", tray, equipos, banco.gt, banco.comunes, banco.tiempos, banco.umbral
        )
        f = dict(ventana=ventana, hueco=hueco, metodo=metodo, **m, **rep)
        filas.append(f)
        print(
            f"{ventana:>8.1f}{hueco:>7.1f}{metodo:>9}  "
            f"{m['cobertura']:>13.3f}{m['idf1']:>7.3f}"
            f"{m['quimeras']:>3}/{m['con10']:<2}  "
            f"{rep['conc_replay']:>12.0f}{rep['v99']:>7.1f}{rep['saltos']:>9.1f}%"
        )

    print("-" * len(cab))
    # INFORME: manda la cobertura, con la pureza como guarda.
    informe = max(
        [f for f in filas if f["quimeras"] <= 6], key=lambda f: f["cobertura"]
    )
    # REPLAY: mandan los saltos imposibles; entre los limpios, más cobertura.
    limpios = sorted(filas, key=lambda f: (f["saltos"], -f["cobertura"]))
    replay = limpios[0]
    print("\n── PRESET INFORME (manda la cobertura) ──")
    print(
        f"  ventana {informe['ventana']} s · hueco {informe['hueco']} s · "
        f"{informe['metodo']}  →  cobertura {informe['cobertura']:.3f}, "
        f"IDF1 {informe['idf1']:.3f}, {informe['quimeras']} quimeras, "
        f"{informe['saltos']:.1f} % de saltos"
    )
    print("\n── PRESET REPLAY (mandan los saltos imposibles) ──")
    print(
        f"  ventana {replay['ventana']} s · hueco {replay['hueco']} s · "
        f"{replay['metodo']}  →  {replay['saltos']:.1f} % de saltos, "
        f"v99 {replay['v99']:.1f} m/s, cobertura {replay['cobertura']:.3f}"
    )
    if (informe["ventana"], informe["hueco"], informe["metodo"]) == (
        replay["ventana"],
        replay["hueco"],
        replay["metodo"],
    ):
        print("\n  → COINCIDEN: no hacen falta dos presets.")
    else:
        print(
            f"\n  → SON DISTINTOS: el informe compra "
            f"{1000*(informe['cobertura']-replay['cobertura']):.0f} milésimas "
            f"de cobertura a cambio de {informe['saltos']-replay['saltos']:+.1f} "
            f"puntos de saltos imposibles."
        )


if __name__ == "__main__":
    main()
