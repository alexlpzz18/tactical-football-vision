#!/usr/bin/env python
"""Las fugas que quedan HOY, una foto por identidad, para mirarlas.

GT barato: en vez de anotar un ground truth de staff —caro para un
fenómeno pequeño— se sacan las identidades que hoy se cuelan en el campo,
con recortes, y Alex dice en dos minutos qué es cada una.

Una fuga es una identidad que sale etiquetada como jugador de un equipo
pero cuyas observaciones NO casan con ninguna de las 14 personas del GT.
Se agrupan POR IDENTIDAD y no por detección: son ~10 fotos en vez de 26.

De cada una se sacan varios recortes repartidos por su vida, porque uno
solo puede caer en un frame malo.

Uso:
    python scripts/fugas_para_mirar.py
    python scripts/fugas_para_mirar.py --config configs/processor_benja_v4_ajustado.yaml
"""

import argparse
import logging
import sys
import warnings
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from fugas_en_el_campo import casar_con_gt  # noqa: E402
from mirar_recortes_sueltos import texto  # noqa: E402
from portero_identidades import cargar_todo  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.team_classification.staff import velocidad_media  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402
from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("fugas_mirar")
BLANCO = (255, 255, 255)
GRIS = (150, 150, 150)
N_RECORTES = 4  # por identidad, repartidos por su vida


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    p.add_argument("--salida", default="outputs/fugas_para_mirar")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg, cfg_tr, cfg_eq, datos, cache, colores, gt_m, gt_px = cargar_todo(
        args.config,
        args.gt,
        args.offset,
        args.paso,
        recortar=False,
        sin_porteros=False,
    )
    modelo, _prof = _profundidad_configurada(cfg_eq)
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    ids = correr_perfil(
        cache,
        datos["fps"],
        datos["sample"],
        cfg_tr,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=cfg_eq,
    )
    equipos = clasificar_identidades(ids, colores, clf, cfg_eq)
    por_frame = {e["frame_idx"]: e for e in cache}
    duenos = {}
    for f in sorted(set(por_frame) & set(gt_px)):
        casado, _ = casar_con_gt(por_frame[f]["dets"], gt_px[f])
        for i, o in casado.items():
            duenos[(f, i)] = o["id"]

    fugas = []
    for k, ident in enumerate(ids, start=1):
        etiqueta = str(equipos.get(k, "otro"))
        if etiqueta not in ("A", "B"):
            continue
        pares = [tuple(par) for tr in ident for par in tr.det_idxs]
        # solo cuentan como fuga las observaciones EN FRAMES CON GT: en
        # los demás no se puede saber si son una de las 14
        juzgables = [par for par in pares if par[0] in gt_px]
        if not juzgables:
            continue
        casadas = [par for par in juzgables if par in duenos]
        n_fuga = len(juzgables) - len(casadas)
        if n_fuga == 0:
            continue
        gs = [duenos[par] for par in casadas]
        # Si la MAYORÍA de sus observaciones juzgables casan con la misma
        # persona, es esa persona con algún hueco: no es una fuga.
        if gs and Counter(gs).most_common(1)[0][1] / len(juzgables) > 0.5:
            continue
        pos = np.array([p for tr in ident for p in tr.pos])
        fugas.append(
            dict(
                k=k,
                etiqueta=etiqueta,
                n=len(pares),
                n_juzgables=len(juzgables),
                n_fuga=n_fuga,
                pares=pares,
                mx=float(np.median(pos[:, 0])),
                my=float(np.median(pos[:, 1])),
                vel=velocidad_media(ident) or 0.0,
                dentro=(
                    0 <= np.median(pos[:, 0]) <= modelo.largo
                    and 0 <= np.median(pos[:, 1]) <= modelo.ancho
                ),
            )
        )
    fugas.sort(key=lambda f: -f["n_fuga"])

    print(f"\n{args.config}")
    print(
        f"  {len(fugas)} identidades se cuelan como jugador "
        f"({sum(f['n_fuga'] for f in fugas)} observaciones en frames con GT)"
    )
    cab = (
        f"    {'id':>5}{'equipo':>8}{'obs':>7}{'fugadas':>9}{'mediana (m)':>16}"
        f"{'vel':>7}{'¿dentro?':>10}"
    )
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    for f in fugas:
        pos_txt = f"({f['mx']:.1f},{f['my']:.1f})"
        print(
            f"    {f['k']:>5}{f['etiqueta']:>8}{f['n']:>7}{f['n_fuga']:>9}"
            f"{pos_txt:>16}{f['vel']:>7.2f}"
            f"{('sí' if f['dentro'] else 'FUERA'):>10}"
        )

    # ── los recortes ──────────────────────────────────────────────────
    quiere = set()
    for f in fugas:
        elegidos = f["pares"][:: max(len(f["pares"]) // N_RECORTES, 1)][:N_RECORTES]
        f["muestra"] = elegidos
        quiere.update(par[0] for par in elegidos)
    quiere = sorted(quiere)
    if not quiere:
        return
    cap = cv2.VideoCapture(cfg["rutas"]["video"])
    frames = {}
    pos_v = posicionar_en_frame(cap, quiere[0])
    for objetivo in quiere:
        while pos_v < objetivo and cap.grab():
            pos_v += 1
        ok, img = cap.read()
        if ok:
            frames[objetivo] = img
            pos_v += 1
    cap.release()

    ALTO, PIE, CELDA = 170, 46, 130
    ancho_total = 30 + N_RECORTES * CELDA + 300
    hoja = np.full((60 + len(fugas) * (ALTO + PIE), ancho_total, 3), 28, np.uint8)
    texto(
        hoja,
        "FUGAS QUE QUEDAN HOY: identidades etiquetadas como jugador "
        "que no son ninguna de las 14",
        (12, 26),
        BLANCO,
        0.55,
        1,
    )
    texto(
        hoja,
        "una fila por identidad, varios recortes repartidos por su vida",
        (12, 46),
        (190, 190, 190),
        0.44,
        1,
    )
    for fila, f in enumerate(fugas):
        y0 = 60 + fila * (ALTO + PIE)
        for col, par in enumerate(f["muestra"]):
            img = frames.get(par[0])
            if img is None:
                continue
            det = por_frame[par[0]]["dets"][par[1]]
            x1, y1, x2, y2 = [max(int(v), 0) for v in det[2:6]]
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            nw = max(int(crop.shape[1] * ALTO / crop.shape[0]), 8)
            crop = cv2.resize(
                crop, (min(nw, CELDA - 12), ALTO), interpolation=cv2.INTER_NEAREST
            )
            x0 = 15 + col * CELDA
            y_fin, x_fin = y0 + ALTO, x0 + crop.shape[1]
            hoja[y0:y_fin, x0:x_fin] = crop
            cv2.rectangle(
                hoja, (x0 - 2, y0 - 2), (x0 + crop.shape[1] + 1, y0 + ALTO + 1), GRIS, 1
            )
            texto(hoja, f"f{par[0]}", (x0, y0 + ALTO + 14), (170, 170, 170), 0.36, 1)
        x_txt = 20 + N_RECORTES * CELDA
        texto(
            hoja,
            f"id {f['k']}  -  equipo {f['etiqueta']}",
            (x_txt, y0 + 24),
            BLANCO,
            0.6,
            1,
        )
        texto(
            hoja,
            f"{f['n']} observaciones, {f['n_fuga']} sin casar",
            (x_txt, y0 + 48),
            (200, 200, 200),
            0.46,
            1,
        )
        texto(
            hoja,
            f"mediana ({f['mx']:.1f}, {f['my']:.1f}) m   "
            f"{'DENTRO' if f['dentro'] else 'FUERA'} del campo",
            (x_txt, y0 + 70),
            (200, 200, 200),
            0.46,
            1,
        )
        texto(
            hoja,
            f"velocidad media {f['vel']:.2f} m/s",
            (x_txt, y0 + 92),
            (200, 200, 200),
            0.46,
            1,
        )
        texto(
            hoja,
            "que es: ______________________",
            (x_txt, y0 + 120),
            (0, 200, 255),
            0.5,
            1,
        )
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    nombre = Path(args.config).stem
    cv2.imwrite(str(salida / f"FUGAS_{nombre}.png"), hoja)
    print(f"\n  Hoja en {salida}/FUGAS_{nombre}.png")


if __name__ == "__main__":
    main()
