#!/usr/bin/env python
"""¿Paga coronar al CONJUNTO de fragmentos del portero en vez de a uno?

La regla por último hombre coronaba UNA identidad por lado y medía su
presencia por separado. Sobre tramos largos el portero se parte —medido
con el GT de Villaviciosa: los ids 16 y 37 son los DOS el `obj 1`, el
mismo portero_B— y el resto se quedaba con su etiqueta de color, que es
lo que la regla existe para evitar.

Aquí se decide la adopción con el criterio de siempre: métricas de
producto en las DOS patas, y nada se adopta si degrada alguna.

Uso:
    python scripts/adoptar_portero_conjunto.py
    python scripts/adoptar_portero_conjunto.py \
        --config configs/processor_villa_v4_cache.yaml \
        --gt data/annotations/ground_truth_tracking/annotations.xml --offset 7500 \
        --cache data/tracking/cache_detecciones_v4pre.pkl \
        --colores data/tracking/cache_colores_v4pre.pkl
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from adoptar_portero import medir  # noqa: E402
from portero_identidades import cargar_todo, porteros_del_gt  # noqa: E402
from src.team_classification import pipeline_equipos as pe  # noqa: E402
from src.team_classification import porteros as mp  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
)

logger = logging.getLogger("conjunto")


def regla_de_un_solo_fragmento(equipos, identidades, modelo, lados, params):
    """La regla TAL Y COMO ERA: corona al mejor y mide su presencia sola.

    Se reconstruye con los mismos helpers que usa la regla nueva, así que
    el A/B compara la decisión y nada más (mismo censo, mismas señales).
    """
    resultado = dict(equipos)
    if not params.activo or not lados:
        return resultado
    areas = modelo.areas_porteria(margen=params.margen_area_m)
    censo = mp.censar_candidatas(identidades, equipos, modelo)
    if censo is None:
        return resultado
    for equipo, lado in lados.items():
        mejor = mp.puntuar_candidatas(identidades, censo, areas, lado)[0]
        if (
            mejor["pisa"] < params.min_pisa_area
            or mejor["presencia"] < params.min_presencia
        ):
            continue
        resultado[mejor["id"]] = f"portero_{equipo}"
    return resultado


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    p.add_argument("--cache", default=None)
    p.add_argument("--colores", default=None)
    p.add_argument(
        "--equipos",
        default=None,
        help="config de equipos alternativo (si el processor no lo trae)",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg, cfg_tr, cfg_eq0, datos, cache, colores, gt_m, gt_px = cargar_todo(
        args.config,
        args.gt,
        args.offset,
        args.paso,
        recortar=False,
        ruta_eq=args.equipos,
    )
    if args.cache:
        import pickle

        from src.tracking.cache_io import cargar_cache
        from src.tracking.filtro_confianza import filtrar_por_confianza

        datos = cargar_cache(args.cache)
        with open(args.colores, "rb") as f:
            colores = pickle.load(f)
        cache, colores = filtrar_por_confianza(
            datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
        )
    modelo, _prof = _profundidad_configurada(cfg_eq0)
    print(f"\n{args.config} · porteros del GT: {porteros_del_gt(gt_m)}")
    print(f"  {len(cache)} frames, {sum(len(e['dets']) for e in cache)} detecciones")

    cfg_eq = {
        **cfg_eq0,
        "porteros": {
            **cfg_eq0.get("porteros", {}),
            "activo": True,
            "metodo": "ultimo_hombre",
        },
    }
    resultados = {}
    original = pe.aplicar_regla_portero_ultimo_hombre
    for nombre, funcion in (
        ("ANTES (un fragmento)", regla_de_un_solo_fragmento),
        ("AHORA (conjunto)", original),
    ):
        pe.aplicar_regla_portero_ultimo_hombre = funcion
        try:
            r = medir(cfg_eq, cache, colores, datos, cfg_tr, gt_m, gt_px, modelo)
        finally:
            pe.aplicar_regla_portero_ultimo_hombre = original
        r["porteros"] = sorted(
            k for k, v in r["equipos"].items() if str(v).startswith("portero_")
        )
        resultados[nombre] = r

    cab = (
        f"  {'variante':<24}{'mediana':>9}{'media':>9}{'p90':>9}"
        f"{'anchura':>9}{'ocup':>8}{'pts':>7}  porteros"
    )
    print("\n" + cab)
    print("  " + "-" * (len(cab) - 12))
    for nombre, r in resultados.items():
        print(
            f"  {nombre:<24}{r['med']:>9.2f}{r['mea']:>9.2f}{r['p90']:>9.2f}"
            f"{r['anc']:>9.2f}{r['oc']:>8.3f}{r['pts']:>7}  {r['porteros']}"
        )
    a, b = resultados["ANTES (un fragmento)"], resultados["AHORA (conjunto)"]
    print("\n  delta (conjunto − antes; negativo = mejor):")
    for clave, nom in (
        ("med", "centroide mediano"),
        ("mea", "centroide medio"),
        ("p90", "centroide p90"),
        ("anc", "anchura"),
        ("oc", "ocupación"),
    ):
        d = b[clave] - a[clave]
        print(f"    {nom:<20}{d:>+8.3f}")


if __name__ == "__main__":
    main()
