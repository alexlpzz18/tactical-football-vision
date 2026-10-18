#!/usr/bin/env python
"""El PARPADEO de la etiqueta por observación, y cómo suavizarlo.

Alex, viendo el vídeo: *"cuando dos jugadores se cruzan hay segundos en
que se intercambian el color y al siguiente vuelven al suyo"*. Es el
precio de etiquetar por observación: el recorte del instante del cruce
está contaminado con la camiseta del otro y ese frame vota mal. Pero se
corrige solo al frame siguiente, así que se puede suavizar en el TIEMPO
sin volver al voto por identidad.

Dos formas, y se miden las dos:

- **mediana móvil** sobre la etiqueta ya decidida (no sobre el color):
  cada observación se queda con la etiqueta mayoritaria de su vecindad
  temporal.
- **histéresis**: se mantiene el equipo anterior salvo que N frames
  seguidos digan lo contrario. Asimétrica a propósito — cuesta más
  cambiar que quedarse.

Con dos métricas, porque una sola engaña:

1. **parpadeo**: cambios de equipo por segundo dentro de una identidad.
2. **acierto**: observaciones con el equipo equivocado contra el GT.

⚠️ Y el aviso de Alex, que es el riesgo real: **una ventana larga es el
voto por identidad otra vez**, que es justo lo que acabamos de dejar
atrás. Por eso se barre y se mira dónde el parpadeo deja de bajar pero el
acierto empieza a empeorar.

Uso:
    python scripts/parpadeo.py
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from fugas_en_el_campo import casar_con_gt  # noqa: E402
from portero_identidades import cargar_todo  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    clasificar_identidades,
    entrenar_clasificador,
    etiquetar_por_observacion,
)
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("parpadeo")


def mediana_movil(serie, ventana_s):
    """Etiqueta mayoritaria en la vecindad temporal de cada observación."""
    salida = []
    for i, (t, lab) in enumerate(serie):
        cerca = [b for t2, b in serie if abs(t2 - t) <= ventana_s / 2]
        cuenta = {}
        for b in cerca:
            cuenta[b] = cuenta.get(b, 0) + 1
        salida.append((t, max(cuenta, key=cuenta.get)))
    return salida


def histeresis(serie, n_seguidos):
    """Mantiene el equipo anterior salvo que N seguidos digan lo contrario.

    Asimétrica a propósito: cambiar cuesta N confirmaciones, quedarse no
    cuesta ninguna. Es la misma doctrina de "no actuar salvo donde hay
    evidencia" que ya funcionó en la puerta de re-entrada.
    """
    if not serie:
        return serie
    salida = [serie[0]]
    actual = serie[0][1]
    pendiente, n_pend = None, 0
    for t, lab in serie[1:]:
        if lab == actual:
            pendiente, n_pend = None, 0
        elif lab == pendiente:
            n_pend += 1
            if n_pend >= n_seguidos:
                actual, pendiente, n_pend = lab, None, 0
        else:
            pendiente, n_pend = lab, 1
        salida.append((t, actual))
    return salida


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_acumulado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    # ⚠️ La etiqueta que corre HOY ya lleva una ventana de 1,5 s, así que
    # suavizarla otra vez es redundante. Con 0 se parte de la etiqueta
    # CRUDA (un recorte, un voto), que es el escenario que describía Alex.
    p.add_argument("--ventana-base", type=float, default=None)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg, cfg_tr, cfg_eq, datos, cache, colores, gt_m, gt_px = cargar_todo(
        args.config, args.gt, args.offset, 15, recortar=False, sin_porteros=False
    )
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
    eq = clasificar_identidades(ids, colores, clf, cfg_eq)
    if args.ventana_base is not None:
        cfg_eq = {
            **cfg_eq,
            "agregacion": {
                **cfg_eq.get("agregacion", {}),
                "por_observacion": {
                    **cfg_eq.get("agregacion", {}).get("por_observacion", {}),
                    "ventana_s": args.ventana_base,
                },
            },
        }
    et_obs = etiquetar_por_observacion(ids, eq, colores, clf, cfg_eq)
    por_frame = {e["frame_idx"]: e for e in cache}
    duenos = {}
    for f in sorted(set(por_frame) & set(gt_px)):
        casado, _ = casar_con_gt(por_frame[f]["dets"], gt_px[f])
        for i, o in casado.items():
            duenos[(f, i)] = o["id"]
    eq_gt = {}
    for _f, obs in gt_m.items():
        for o in obs:
            eq_gt[o.obj_id] = str(o.team).replace("portero_", "")
    dur = max(e["t"] for e in cache) - min(e["t"] for e in cache)

    # Series por identidad: (t, etiqueta, par)
    series = {}
    for k, ident in enumerate(ids, start=1):
        if str(eq.get(k, "otro")) not in ("A", "B"):
            continue
        series[k] = sorted(
            (
                (t, et_obs.get((k, par[0]), str(eq[k])), tuple(par))
                for tr in ident
                for t, par in zip(tr.ts, tr.det_idxs)
            ),
            key=lambda z: z[0],
        )

    def evaluar(transformar):
        cambios = mal = tot = 0
        for _k, serie in series.items():
            base = [(t, lab) for t, lab, _p in serie]
            nueva = transformar(base) if transformar else base
            for i in range(1, len(nueva)):
                cambios += nueva[i][1] != nueva[i - 1][1]
            for (_t, lab), (_t2, _l2, par) in zip(nueva, serie):
                g = duenos.get(par)
                if g is None:
                    continue
                tot += 1
                mal += lab != eq_gt.get(g)
        return cambios / dur, mal / max(tot, 1), tot

    cab = (
        f"  {'suavizado':<26}{'parpadeo (cambios/s)':>22}" f"{'equipo equivocado':>20}"
    )
    v_base = (
        cfg_eq.get("agregacion", {}).get("por_observacion", {}).get("ventana_s", 1.5)
    )
    print(f"\n{args.config} · {len(series)} identidades de jugador · {dur:.0f} s")
    print(f"  ventana de la etiqueta BASE: {v_base:.1f} s")
    print("\n" + cab)
    print("  " + "-" * (len(cab) - 2))
    base_p, base_e, n = evaluar(None)
    print(f"  {'sin suavizar (hoy)':<26}{base_p:>21.2f}{base_e:>19.1%}")
    for v in (0.3, 0.5, 0.8, 1.0, 1.5, 2.5, 4.0):
        pp, ee, _n = evaluar(lambda s, v=v: mediana_movil(s, v))
        print(f"  {f'mediana móvil {v:.1f} s':<26}{pp:>21.2f}{ee:>19.1%}")
    for n_seg in (1, 2, 3, 4, 6):
        pp, ee, _n = evaluar(lambda s, n=n_seg: histeresis(s, n))
        print(f"  {f'histéresis {n_seg} frames':<26}{pp:>21.2f}{ee:>19.1%}")
    print(
        f"\n  ({n} observaciones casadas con el GT; el dt del caché es "
        f"{datos['sample']/datos['fps']:.2f} s, así que 'histéresis 3' son "
        f"{3*datos['sample']/datos['fps']:.2f} s)"
    )


if __name__ == "__main__":
    main()
