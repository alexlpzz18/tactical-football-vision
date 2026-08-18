#!/usr/bin/env python
"""Barrido fino de la puerta con embedding, en las DOS patas del banco.

Criterio de siempre: bajar quimeras SIN degradar cobertura, IDF1 ni
concurrencia. Y una comprobación que ya nos ha salvado una vez: **si los
puntos del barrido dan resultados idénticos, el parámetro no está
haciendo nada** y la tabla no dice lo que parece.

Uso:
    python scripts/barrido_puerta_embedding.py
    python scripts/barrido_puerta_embedding.py --eje hueco
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from calibrar_puerta_embedding import (  # noqa: E402
    cargar_emb,
    quimeras_por_equipo,
)
from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.tracking.asociacion_bytetrack import (  # noqa: E402
    ParametrosByteTrack,
    asociar_con_bytetrack,
)
from src.tracking.cosido_pureza import (  # noqa: E402
    ParametrosCosidoPureza,
    coser_por_pureza,
)
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)
from src.tracking.puerta_reentrada import (  # noqa: E402
    ParametrosPuertaReentrada,
    aplicar_puerta_reentrada,
)

REFERENCIA = {"nids": 79, "cobertura": 0.622, "conc": 21, "idf1": 0.542, "quim": 4}


def alturas_de(cache):
    return {
        (e["frame_idx"], i): float(d[5] - d[3])
        for e in cache
        for i, d in enumerate(e["dets"])
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    p.add_argument("--emb", default="data/tracking/emb_villa_siglip.pkl")
    p.add_argument(
        "--eje",
        default="umbral",
        choices=["umbral", "hueco", "min_obs", "tamano"],
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    emb = cargar_emb(args.emb)
    alturas = alturas_de(banco.datos["cache"])
    base = asociar_con_bytetrack(
        banco.datos["cache"],
        banco.datos["fps"],
        banco.datos["sample"],
        ParametrosByteTrack.desde_dict(banco.cfg_tracking.get("bytetrack")),
    )

    fijos = dict(activa=True, hueco_min_s=0.5, emb_max_dist=0.08, min_obs_firma=3)
    if args.eje == "umbral":
        variantes = [
            (f"umbral {u:.3f}", {**fijos, "emb_max_dist": u})
            for u in (0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12)
        ]
    elif args.eje == "hueco":
        variantes = [
            (f"hueco {h} s", {**fijos, "hueco_min_s": h})
            for h in (0.3, 0.5, 0.8, 1.2, 2.0)
        ]
    elif args.eje == "min_obs":
        variantes = [
            (f"min_obs {m}", {**fijos, "min_obs_firma": m}) for m in (1, 2, 3, 5, 8)
        ]
    else:
        variantes = [
            ("sin ponderar", {**fijos, "ponderar_por_tamano": False}),
            ("ponderado por tamaño", {**fijos, "ponderar_por_tamano": True}),
        ]

    cab = (
        f"{'variante':<24}{'nIds':>6}{'cob.':>8}{'conc':>6}{'IDF1':>8}"
        f"{'tasa':>7}{'quim':>6}{'mismo eq':>10}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    filas = []
    for nombre, kw in variantes:
        ids = aplicar_puerta_reentrada(
            base,
            banco.colores,
            banco.dt,
            ParametrosPuertaReentrada(**kw),
            embeddings=emb,
            alturas=alturas,
        )
        ids = coser_por_pureza(
            ids,
            banco.colores,
            ParametrosCosidoPureza(max_hueco=4.0, color_max_dist=0.9),
            dt=banco.dt,
        )
        eq = banco.clasificar(ids)
        tr = interpolar_trayectorias(
            identidades_a_trayectorias(ids), banco.frames_ts, max_hueco=6.0
        )
        m = medir("x", tr, eq, banco.gt, banco.comunes, banco.tiempos, banco.umbral)
        mismo, _d = quimeras_por_equipo(ids, banco)
        m.update(nombre=nombre, mismo=mismo)
        filas.append(m)
        print(
            f"{nombre:<24}{m['nids']:>6}{m['cobertura']:>8.3f}{m['conc']:>6.0f}"
            f"{m['idf1']:>8.3f}{m['tasa']:>7.3f}{m['quimeras']:>6}{mismo:>10}"
        )

    r = REFERENCIA
    print("-" * len(cab))
    print(
        f"{'PUERTA DE COLOR 0.9':<24}{r['nids']:>6}{r['cobertura']:>8.3f}"
        f"{r['conc']:>6}{r['idf1']:>8.3f}{'—':>7}{r['quim']:>6}{2:>10}"
    )

    # La comprobación que acordamos: ¿los puntos hacen algo?
    firmas = {
        (f["nids"], round(f["cobertura"], 4), f["quimeras"], round(f["idf1"], 4))
        for f in filas
    }
    print(
        f"\nPuntos distintos: {len(firmas)} de {len(filas)}."
        + (
            "  ✓ el parámetro mueve el resultado."
            if len(firmas) > 1
            else "  ⚠ TODOS IGUALES: el parámetro NO está haciendo nada, "
            "el rango está mal elegido y la tabla no dice lo que parece."
        )
    )

    ganan = [
        f
        for f in filas
        if f["quimeras"] <= r["quim"]
        and f["cobertura"] >= r["cobertura"]
        and f["idf1"] >= r["idf1"]
        and abs(f["conc"] - 22) <= abs(r["conc"] - 22)
    ]
    print(f"\nCumplen el criterio (sin degradar nada): {len(ganan)}")
    for f in sorted(ganan, key=lambda x: (x["quimeras"], -x["cobertura"])):
        print(
            f"  ✓ {f['nombre']:<22} quim {f['quimeras']} (mismo eq {f['mismo']}), "
            f"cob {f['cobertura']:.3f}, IDF1 {f['idf1']:.3f}"
        )


if __name__ == "__main__":
    main()
