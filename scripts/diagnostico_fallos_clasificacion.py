#!/usr/bin/env python
"""¿De quién es la culpa de un fallo de equipo: del clasificador o del tracker?

El diagnóstico que ordena el trabajo. Un jugador puede salir con el equipo
equivocado por dos motivos MUY distintos, y la solución no es la misma:

(a) IDENTIDAD PURA mal clasificada — el tracker hizo bien su trabajo (una
    identidad = una persona) y el clasificador de color se equivocó. Se
    arregla mejorando la clasificación (embeddings en vez de histograma
    HSV, p. ej.).

(b) IDENTIDAD CONTAMINADA — la identidad mezcla a dos personas (quimera),
    así que NO EXISTE una etiqueta correcta: la mitad de sus
    observaciones van a estar mal se elija lo que se elija. Se arregla
    mejorando la ASOCIACIÓN, y ningún clasificador lo puede salvar.

Criterio acordado con Alex: si más del 30 % de las observaciones mal
etiquetadas caen en (b), la prioridad es el tracker y no el clasificador.

Uso:
    python scripts/diagnostico_fallos_clasificacion.py
    python scripts/diagnostico_fallos_clasificacion.py --sin-puerta
"""

import argparse
import copy
import logging
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco  # noqa: E402
from src.tracking.perfiles import correr_perfil, postprocesar  # noqa: E402


# El árbitro y el cuerpo técnico van al mismo cajón: ninguno entra en las
# métricas por equipo. En el GT el árbitro viene con team=None.
def normalizar(t) -> str:
    s = str(t)
    if s in ("arbitro", "staff", "None", "none", "nan"):
        return "otro"
    return s


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    p.add_argument(
        "--min-contaminacion",
        type=float,
        default=0.0,
        help=(
            "Fracción mínima de las observaciones de una identidad que debe "
            "pertenecer a la segunda persona para llamarla contaminada. Con 0 "
            "basta UNA observación suelta, que puede ser ruido de asociación "
            "en un cruce y no una quimera de verdad."
        ),
    )
    p.add_argument(
        "--sin-puerta",
        action="store_true",
        help="Desactiva la puerta de re-entrada, para ver cuánto arregla",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    cfg = copy.deepcopy(banco.cfg_tracking)
    if args.sin_puerta:
        cfg.setdefault("puerta_reentrada", {})["activa"] = False

    identidades = correr_perfil(
        banco.datos["cache"],
        banco.datos["fps"],
        banco.datos["sample"],
        cfg,
        perfil="bytetrack",
        colores=banco.colores,
        clasificador=banco.clasificador,
        cfg_equipos=banco.cfg_equipos,
    )
    equipos = banco.clasificar(identidades)
    _tr, equipos = postprocesar(
        identidades, dict(equipos), banco.frames_ts, cfg, perfil="bytetrack"
    )

    # Equipo real de cada id del GT
    equipo_gt = {}
    for g in banco.gt.values():
        for o in g:
            equipo_gt.setdefault(o.obj_id, normalizar(o.team))

    puras = contaminadas = 0
    obs_total = obs_mal_puras = obs_mal_contaminadas = 0
    obs_en_puras = obs_en_contaminadas = 0
    confusiones_puras: Counter = Counter()

    for i, ident in enumerate(identidades, start=1):
        pred = normalizar(equipos.get(i, "otro"))
        # A quién pertenece cada observación, según el GT
        de_quien = []
        for tr in ident:
            for pos, (f, _d) in zip(tr.pos, tr.det_idxs):
                g = banco.gt.get(f)
                if not g:
                    continue
                mejor, dmin = None, banco.umbral.para(float(pos[1]))
                for o in g:
                    d = float(np.linalg.norm(np.asarray(o.pos) - np.asarray(pos)))
                    if d < dmin:
                        mejor, dmin = o.obj_id, d
                if mejor is not None:
                    de_quien.append(mejor)
        if not de_quien:
            continue

        obs_total += len(de_quien)
        cuenta = Counter(de_quien)
        # Personas con presencia REAL en la identidad, no de paso
        minimo = args.min_contaminacion * len(de_quien)
        personas = {g for g, n in cuenta.items() if n >= max(1, minimo)}
        mal = sum(1 for gid in de_quien if equipo_gt.get(gid) != pred)

        if len(personas) <= 1:
            puras += 1
            obs_en_puras += len(de_quien)
            obs_mal_puras += mal
            if mal:
                dominante = cuenta.most_common(1)[0][0]
                confusiones_puras[(equipo_gt.get(dominante), pred)] += mal
        else:
            contaminadas += 1
            obs_en_contaminadas += len(de_quien)
            obs_mal_contaminadas += mal

    mal_total = obs_mal_puras + obs_mal_contaminadas
    print("\n── IDENTIDADES ──\n")
    print(f"  puras (1 persona):        {puras}")
    print(f"  contaminadas (quimeras):  {contaminadas}")
    print(f"  observaciones casadas con el GT: {obs_total}")

    print("\n── DE DÓNDE SALEN LOS FALLOS DE EQUIPO ──\n")
    cab = f"{'cubo':<40}{'obs mal':>9}{'% de los fallos':>17}"
    print(cab)
    print("-" * len(cab))
    if mal_total:
        for nombre, n in (
            ("(a) identidad PURA mal clasificada", obs_mal_puras),
            ("(b) identidad CONTAMINADA (quimera)", obs_mal_contaminadas),
        ):
            print(f"{nombre:<40}{n:>9}{n / mal_total:>16.1%}")
    print(f"{'TOTAL mal etiquetadas':<40}{mal_total:>9}")
    if obs_total:
        print(f"\n  (sobre {obs_total} observaciones: {mal_total / obs_total:.1%} mal)")

    if obs_en_puras and obs_en_contaminadas:
        print(
            f"\n  Tasa de error DENTRO de cada cubo: "
            f"puras {obs_mal_puras / obs_en_puras:.1%}, "
            f"contaminadas {obs_mal_contaminadas / obs_en_contaminadas:.1%}"
        )

    if confusiones_puras:
        print("\n  Confusiones del clasificador (solo identidades puras):")
        for (real, pred), n in confusiones_puras.most_common(6):
            print(f"    {real} → {pred}: {n} obs")

    if mal_total:
        pct_b = obs_mal_contaminadas / mal_total
        print("\n── VEREDICTO ──\n")
        if pct_b > 0.30:
            print(
                f"  {pct_b:.1%} de los fallos son de ASOCIACIÓN (>30 %):\n"
                "  la prioridad es el TRACKER, no el clasificador."
            )
        else:
            print(
                f"  Solo {pct_b:.1%} de los fallos son de asociación (<30 %):\n"
                "  la prioridad es el CLASIFICADOR."
            )


if __name__ == "__main__":
    main()
