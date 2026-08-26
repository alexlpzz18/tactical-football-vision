#!/usr/bin/env python
"""¿Cuánto se mueven las métricas del banco POR NADA?

Hallazgo del 25-ago-2026 que obliga a escribir esto: en Villaviciosa,
quitar CINCO detecciones de 28.000 movía el centroide de 3,55 a 4,13 m.
Se midió quitando detecciones al azar y el suelo de ruido resultó ser de
0,83 m en la mediana del centroide y 2,45 m en el p90.

Pero eso son las métricas de PRODUCTO. Las conclusiones históricas del
proyecto —qué detector se adopta, qué radio de fit, qué configuración de
asociación— se decidieron con OTRAS métricas: cobertura, IDF1, quimeras,
accuracy de equipos. **De esas el suelo no estaba medido**, y sin él no
se sabe cuáles de aquellas decisiones se apoyan en una diferencia real.

Cómo se mide: se quitan N detecciones AL AZAR —o sea una perturbación que
no debería cambiar nada— y se mira la dispersión del resultado con varias
semillas. Lo que quede por debajo de esa dispersión no es señal.

⚠️ El canal del ruido no es el que parecía. Medido detección a detección
en Villaviciosa: quitando 5 detecciones, una semilla cambia de equipo
1.411 de 9.507 detecciones y solo 55 de identidad. El culpable no es la
asociación sino **el fit del clasificador de color**, cuyo umbral de
fusión se elige por argmax sobre una rejilla (`_umbral_auto`): es una
decisión DISCRETA y una detección de más la hace saltar de escalón. En el
benjamín no salta nunca; en Villaviciosa, en una de cada tres semillas.

Uso:
    python scripts/suelo_de_ruido.py                       # Villaviciosa
    python scripts/suelo_de_ruido.py --config configs/evaluation_v4pre.yaml
"""

import argparse
import logging
import random
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("ruido")

METRICAS = [
    ("nids", "nIds", "{:.0f}"),
    ("cobertura", "cobertura", "{:.3f}"),
    ("idf1", "IDF1", "{:.3f}"),
    ("tasa", "tasa IDSW", "{:.3f}"),
    ("quimeras", "quimeras", "{:.0f}"),
    ("acc", "equipos", "{:.3f}"),
]


def quitar_al_azar(cache, colores, n, semilla, modo="azar"):
    """Caché sin n detecciones, con los colores remapeados.

    `modo` cambia QUÉ se quita, porque un muestreo uniforme es la
    perturbación más benigna posible y no prueba gran cosa:
      - "azar": n detecciones al azar.
      - "frame": todas las detecciones de un frame entero elegido al azar
        (imita que el detector se atragante con un fotograma).
      - "confianza": las n detecciones de MAYOR confianza, que son las que
        más pesan en el fit. Es el caso adverso.
    """
    rnd = random.Random(semilla)
    todas = [(e["frame_idx"], i) for e in cache for i in range(len(e["dets"]))]
    if modo == "frame":
        objetivo = rnd.choice([e["frame_idx"] for e in cache if e["dets"]])
        fuera = {(f, i) for f, i in todas if f == objetivo}
    elif modo == "confianza":
        por_conf = sorted(
            todas,
            key=lambda k: -float(
                next(e for e in cache if e["frame_idx"] == k[0])["dets"][k[1]][6]
            ),
        )
        fuera = set(por_conf[:n])
    else:
        fuera = set(rnd.sample(todas, min(n, len(todas))))
    nuevo, nuevos_colores = [], {}
    for entrada in cache:
        f = entrada["frame_idx"]
        dets = []
        for i, det in enumerate(entrada["dets"]):
            if (f, i) in fuera:
                continue
            j = len(dets)
            dets.append(det)
            if (f, i) in colores:
                nuevos_colores[(f, j)] = colores[(f, i)]
        nuevo.append({**entrada, "dets": dets})
    return nuevo, nuevos_colores


def evaluar(banco, cache, colores, refit):
    """Métricas del banco corriendo el perfil de producción sobre `cache`.

    `refit` decide si el clasificador de color se vuelve a entrenar. Es el
    interruptor del experimento: con refit=False el fit se congela y, si
    el ruido desaparece, es que venía de ahí.
    """
    clf = (
        entrenar_clasificador(colores, banco.cfg_equipos, cache)
        if refit
        else banco.clasificador
    )
    identidades = correr_perfil(
        cache,
        banco.datos["fps"],
        banco.datos["sample"],
        banco.cfg_tracking,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=banco.cfg_equipos,
    )
    equipos = clasificar_identidades(identidades, colores, clf, banco.cfg_equipos)
    trayectorias = interpolar_trayectorias(
        identidades_a_trayectorias(identidades), banco.frames_ts, max_hueco=6.0
    )
    return medir(
        "x",
        trayectorias,
        equipos,
        banco.gt,
        banco.comunes,
        banco.tiempos,
        banco.umbral,
    )


def fila(nombre, valores):
    """Una línea con la dispersión de cada métrica."""
    txt = f"  {nombre:<30}"
    for clave, _etiq, fmt in METRICAS:
        v = np.array([float(r[clave]) for r in valores])
        if len(v) == 1 or v.min() == v.max():
            txt += f"{fmt.format(v.min()):>14}"
        else:
            txt += f"{fmt.format(v.min()) + '-' + fmt.format(v.max()):>14}"
    return txt


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    p.add_argument("--semillas", type=int, default=6)
    p.add_argument("--cantidades", default="5,50,200")
    # Las semillas 1-8 no son sagradas: si la estabilidad solo aparece con
    # ellas, es de las semillas y no del arreglo.
    p.add_argument("--semilla-inicial", type=int, default=1)
    # Un muestreo uniforme es la perturbacion mas benigna posible. "frame"
    # quita un fotograma entero (el detector se atraganta) y "confianza"
    # quita las detecciones que MAS pesan en el fit: el caso adverso.
    p.add_argument("--modo", default="azar", choices=["azar", "frame", "confianza"])
    p.add_argument(
        "--n-init",
        type=int,
        default=0,
        help="si >0, sobrescribe clasificador_color.n_init",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    if args.n_init > 0:
        banco.cfg_equipos = {
            **banco.cfg_equipos,
            "clasificador_color": {
                **banco.cfg_equipos.get("clasificador_color", {}),
                "n_init": args.n_init,
            },
        }
    cache0 = banco.datos["cache"]
    total = sum(len(e["dets"]) for e in cache0)
    print(
        f"\n{args.config} · {total} detecciones · "
        f"{len(banco.comunes)} frames con GT"
    )

    cab = f"  {'perturbación':<30}"
    for _c, etiq, _f in METRICAS:
        cab += f"{etiq:>14}"
    print("\n" + cab)
    print("  " + "-" * (len(cab) - 2))

    base = evaluar(banco, cache0, banco.colores, refit=True)
    print(fila("ninguna (referencia)", [base]))

    semillas = list(range(args.semilla_inicial, args.semilla_inicial + args.semillas))
    for n in [int(x) for x in args.cantidades.split(",")]:
        res = []
        for semilla in semillas:
            cache, colores = quitar_al_azar(
                cache0, banco.colores, n, semilla, args.modo
            )
            res.append(evaluar(banco, cache, colores, refit=True))
        print(fila(f"{n} al azar ({len(semillas)} semillas)", res))

    # ── El interruptor: congelar el fit del color ─────────────────────
    print("\n  Y ahora lo mismo CONGELANDO el fit del clasificador de color")
    print("  (si el ruido desaparece, el canal es el fit y no la asociación):")
    print(cab)
    print("  " + "-" * (len(cab) - 2))
    print(fila("ninguna (referencia)", [evaluar(banco, cache0, banco.colores, False)]))
    for n in [int(x) for x in args.cantidades.split(",")]:
        res = []
        for semilla in semillas:
            cache, colores = quitar_al_azar(
                cache0, banco.colores, n, semilla, args.modo
            )
            res.append(evaluar(banco, cache, colores, refit=False))
        print(fila(f"{n} al azar, fit congelado", res))


if __name__ == "__main__":
    main()
