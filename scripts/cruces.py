#!/usr/bin/env python
"""¿Cuántos cruces falla el sistema, y los resolvería la GEOMETRÍA?

El 4b dejó el frente aquí: el 91 % del margen está en el 12 % de
contaminación que la apariencia no ve, y ese 12 % son los cruces entre
compañeros del MISMO equipo — dos niños con la misma camiseta y casi los
mismos píxeles.

La hipótesis es que la geometría sí los distingue: cada uno entra al
cruce con su dirección y su velocidad y debería salir de forma coherente.
Es información que nunca hemos usado.

Este script no construye nada. Responde dos preguntas, en orden:

1. **¿Cuántos cruces hay y cuántos falla el sistema?** Si son cinco, no
   merece la pena; si son cincuenta, sí.
2. **En los que falla, ¿la continuidad de movimiento habría dado la
   respuesta correcta?** Si en la mayoría no la da, la geometría tampoco
   es la vía y hay que decirlo ANTES de construir.

Uso:
    python scripts/cruces.py
"""

import argparse
import logging
import pickle
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from pureza_sin_reentrada import duenos  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402

logger = logging.getLogger("cruces")

DIST_CRUCE = 2.5  # m: por debajo de esto, dos personas "se cruzan"
VENTANA = 2  # muestras del GT a cada lado (0,5 s cada una)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--dist", type=float, default=DIST_CRUCE)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    H = np.load(cfg["rutas"]["homografia"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    conf = float(cfg_tr.get("confianza_min", 0) or 0)
    cache, colores = filtrar_por_confianza(datos["cache"], colores, conf)
    gt = gt_a_por_frame(parsear_cvat(args.gt), H, frame_offset=9750, paso_gt=15)
    mapa = duenos(cache, gt)

    ids = asociar_con_bytetrack(
        cache,
        datos["fps"],
        datos["sample"],
        ParametrosByteTrack.desde_dict(cfg_tr.get("bytetrack")),
    )
    # A qué identidad del sistema fue a parar cada observación del GT
    sistema = {}
    for k, ident in enumerate(ids, start=1):
        for tr in ident:
            for par in tr.det_idxs:
                g = mapa.get(tuple(par))
                if g is not None:
                    sistema[(par[0], g)] = k

    # Trayectoria del GT por persona
    frames = sorted(gt)
    pos = {}
    equipo = {}
    for f in frames:
        for o in gt[f]:
            pos[(f, o.obj_id)] = np.array([float(o.pos[0]), float(o.pos[1])])
            equipo.setdefault(o.obj_id, str(o.team).replace("portero_", ""))
    personas = sorted(equipo)

    # ── 1. Localizar los cruces ──
    cruces = []
    for i, a in enumerate(personas):
        for b in personas[i + 1 :]:  # noqa: E203
            for k in range(1, len(frames) - 1):
                f0, f1, f2 = frames[k - 1], frames[k], frames[k + 1]
                if any((f, x) not in pos for f in (f0, f1, f2) for x in (a, b)):
                    continue
                d0 = np.linalg.norm(pos[(f0, a)] - pos[(f0, b)])
                d1 = np.linalg.norm(pos[(f1, a)] - pos[(f1, b)])
                d2 = np.linalg.norm(pos[(f2, a)] - pos[(f2, b)])
                # Se acercan y luego se separan, con mínimo por debajo del umbral
                if d1 < args.dist and d1 <= d0 and d1 <= d2 and d2 > d1:
                    cruces.append((f1, a, b, float(d1)))

    mismo = [c for c in cruces if equipo[c[1]] == equipo[c[2]]]
    print(f"\nCruces detectados (a menos de {args.dist} m): {len(cruces)}")
    print(f"  del MISMO equipo: {len(mismo)} ({len(mismo)/max(len(cruces),1):.0%})")
    print(f"  de equipos distintos: {len(cruces)-len(mismo)}")

    def id_dominante(persona, desde, hasta):
        v = [
            sistema[(f, persona)]
            for f in frames[desde:hasta]
            if (f, persona) in sistema
        ]
        return Counter(v).most_common(1)[0][0] if v else None

    # ── 2. ¿Los resuelve el sistema? ¿Y los resolvería la geometría? ──
    ok_sistema = mal_sistema = sin_datos = 0
    geo_acierta = geo_falla = geo_sin_datos = 0
    fallos = []
    for f1, a, b, d in cruces:
        k = frames.index(f1)
        ini, fin = max(0, k - VENTANA), min(len(frames), k + VENTANA + 1)
        antes_a, antes_b = id_dominante(a, ini, k), id_dominante(b, ini, k)
        desp_a, desp_b = id_dominante(a, k + 1, fin), id_dominante(b, k + 1, fin)
        if None in (antes_a, antes_b, desp_a, desp_b):
            sin_datos += 1
            continue
        if antes_a == desp_a and antes_b == desp_b:
            ok_sistema += 1
            continue
        mal_sistema += 1
        fallos.append((f1, a, b, d))

        # ¿La continuidad de movimiento habría acertado?
        # Se extrapola cada trayectoria desde ANTES del cruce y se mira
        # qué posición de DESPUÉS le corresponde por cercanía.
        f_ant, f_post = frames[k - 1], frames[min(k + 1, len(frames) - 1)]
        if any(
            (ff, x) not in pos
            for ff in (frames[max(0, k - 2)], f_ant, f_post)
            for x in (a, b)
        ):
            geo_sin_datos += 1
            continue
        f_ant2 = frames[max(0, k - 2)]
        # Factor de extrapolación: la velocidad se estima sobre
        # (f_ant2 → f_ant) y se proyecta sobre (f_ant → f_post). Es la
        # razón entre los dos tramos, sin más — la versión anterior la
        # multiplicaba por dos y extrapolaba el doble de lejos.
        tramo_v = max(f_ant - f_ant2, 1)
        dt = (f_post - f_ant) / tramo_v
        pred_a = pos[(f_ant, a)] + (pos[(f_ant, a)] - pos[(f_ant2, a)]) * dt
        pred_b = pos[(f_ant, b)] + (pos[(f_ant, b)] - pos[(f_ant2, b)]) * dt
        real_a, real_b = pos[(f_post, a)], pos[(f_post, b)]
        # Asignación correcta vs cruzada
        coste_ok = np.linalg.norm(pred_a - real_a) + np.linalg.norm(pred_b - real_b)
        coste_cruzado = np.linalg.norm(pred_a - real_b) + np.linalg.norm(
            pred_b - real_a
        )
        if coste_ok < coste_cruzado:
            geo_acierta += 1
        else:
            geo_falla += 1

    print("\n── ¿LOS RESUELVE EL SISTEMA? ──\n")
    n = ok_sistema + mal_sistema
    print(f"  bien: {ok_sistema} ({ok_sistema/max(n,1):.0%})")
    print(
        f"  MAL (intercambio de identidad): {mal_sistema} ({mal_sistema/max(n,1):.0%})"
    )
    print(f"  sin datos suficientes: {sin_datos}")

    print("\n── EN LOS QUE FALLA, ¿ACERTARÍA LA GEOMETRÍA? ──\n")
    m = geo_acierta + geo_falla
    if m:
        print(
            f"  la continuidad de movimiento acierta: {geo_acierta} "
            f"({geo_acierta/m:.0%})"
        )
        print(f"  se equivoca igual: {geo_falla} ({geo_falla/m:.0%})")
    print(f"  sin datos para extrapolar: {geo_sin_datos}")
    if m:
        print(
            "\n  Es un oráculo optimista: extrapola con las posiciones del GT,\n"
            "  no con las del sistema. Si aquí la geometría no acierta, con\n"
            "  posiciones ruidosas mucho menos."
        )


if __name__ == "__main__":
    main()
