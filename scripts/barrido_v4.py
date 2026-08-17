#!/usr/bin/env python
"""Re-barrido COMPLETO de la asociación sobre los cachés del v4.

Por qué existe: toda la caja de cambios del tracking —buffer, umbral de
emparejamiento, umbrales del cosido, confianza de detección— se ajustó
sobre las detecciones del **v4pre**. Al cambiar de detector se dejó
puesta la configuración del anterior, y el v4 da más detecciones, más
pequeñas y más lejanas: la asociación necesita otros números. Declarar
peor al v4 sin re-barrer sería comparar el v4 mal ajustado contra el
v4pre bien ajustado.

Aviso sobre la confianza: el caché del v4 se generó con `confianza: 0.3`,
así que aquí solo se puede SUBIR el umbral (0.3 / 0.4 / 0.5). Probar 0.25
exige otra pasada de Colab; si el barrido dice que conviene bajar, es que
hay que pedirla.

Uso:
    python scripts/barrido_v4.py
    python scripts/barrido_v4.py --etapa 2 --conf 0.4 --buffer 3.0
"""

import argparse
import itertools
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    entrenar_clasificador,
)
from src.tracking.cosido_pureza import (  # noqa: E402
    ParametrosCosidoPureza,
    coser_por_pureza,
)
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)

# Los dos puntos contra los que se compara todo (medición del 17-ago-2026,
# scripts/medir_v4.py). El v4 gana en todo menos en quimeras: 5 → 8.
REF = {
    "v4pre": {"nids": 115, "cobertura": 0.559, "conc": 25, "idf1": 0.453, "quim": 5},
    "v4": {"nids": 83, "cobertura": 0.598, "conc": 23, "idf1": 0.484, "quim": 8},
}


def filtrar_por_confianza(banco, conf_min):
    """Recorta el caché del banco a las detecciones con conf ≥ conf_min.

    OJO, y es la razón de que esto no sea un one-liner: el caché de
    colores está indexado por `(frame_idx, det_idx)`, donde det_idx es la
    POSICIÓN en la lista de detecciones del frame. Si se tiran entradas,
    todos los índices posteriores se desplazan y cada caja quedaría
    emparejada con el color de otra — sin fallar, que es lo peor. Así que
    se remapea el caché de colores a la vez, y se comprueba.
    """
    if conf_min <= 0.3:  # el caché ya se generó a 0.3
        return
    nuevo_cache, nuevos_colores = [], {}
    for entrada in banco.datos["cache"]:
        f = entrada["frame_idx"]
        dets = []
        for idx_viejo, det in enumerate(entrada["dets"]):
            if det[6] < conf_min:
                continue
            idx_nuevo = len(dets)
            dets.append(det)
            if (f, idx_viejo) in banco.colores:
                nuevos_colores[(f, idx_nuevo)] = banco.colores[(f, idx_viejo)]
        nuevo_cache.append({**entrada, "dets": dets})
    total = sum(len(e["dets"]) for e in nuevo_cache)
    assert len(nuevos_colores) <= total, "remapeo de colores inconsistente"
    banco.datos["cache"] = nuevo_cache
    banco.colores = nuevos_colores
    # El clasificador se entrenó con TODAS las detecciones: hay que
    # rehacerlo o estaría ajustado a una población que ya no existe.
    banco.clasificador = entrenar_clasificador(
        banco.colores, banco.cfg_equipos, banco.datos["cache"]
    )


def evaluar(banco, buf, emp, minf, kw_cosido):
    base = banco.bytetrack(
        buffer_perdido_s=buf,
        umbral_emparejamiento=emp,
        min_frames_consecutivos=minf,
    )
    cosidas = coser_por_pureza(
        base, banco.colores, ParametrosCosidoPureza(**kw_cosido), dt=banco.dt
    )
    eq = banco.clasificar(cosidas)
    tr = interpolar_trayectorias(
        identidades_a_trayectorias(cosidas), banco.frames_ts, max_hueco=6.0
    )
    return medir("x", tr, eq, banco.gt, banco.comunes, banco.tiempos, banco.umbral)


def linea(etiqueta, f, ancho=30):
    return (
        f"{etiqueta:<{ancho}}{f['nids']:>6}{f['cobertura']:>8.3f}{f['conc']:>6.0f}"
        f"{f['idf1']:>8.3f}{f['tasa']:>7.3f}{f['quimeras']:>5}"
    )


def cabecera(ancho=30):
    cab = (
        f"{'variante':<{ancho}}{'nIds':>6}{'cob.':>8}{'conc':>6}"
        f"{'IDF1':>8}{'tasa':>7}{'quim':>5}"
    )
    print("\n" + cab)
    print("-" * len(cab))
    return len(cab)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/evaluation_v4.yaml")
    parser.add_argument("--config-tracking", default="configs/tracking.yaml")
    parser.add_argument("--etapa", type=int, default=1, choices=[1, 2])
    parser.add_argument("--conf", type=float, default=0.3)
    parser.add_argument("--buffer", type=float, default=2.0)
    parser.add_argument("--empar", type=float, default=0.995)
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cosido_base = dict(max_hueco=4.0, margen_ambiguedad=0.15)

    if args.etapa == 1:
        # Etapa 1: la geometría de la asociación. El cosido se deja fijo
        # porque mover seis ejes a la vez no se puede leer.
        n = cabecera(30)
        for conf in (0.3, 0.4, 0.5):
            banco = Banco(args.config, args.config_tracking)
            filtrar_por_confianza(banco, conf)
            n_dets = sum(len(e["dets"]) for e in banco.datos["cache"])
            print(f"── confianza ≥ {conf}  ({n_dets} detecciones) ──")
            for buf, emp in itertools.product((1.5, 2.0, 3.0), (0.98, 0.995)):
                f = evaluar(banco, buf, emp, 1, cosido_base)
                print(linea(f"  buffer {buf} · empar {emp}", f, 30))
    else:
        # Etapa 2: fijada la geometría ganadora, se mueve el cosido y el
        # mínimo de frames consecutivos.
        banco = Banco(args.config, args.config_tracking)
        filtrar_por_confianza(banco, args.conf)
        n = cabecera(30)
        print(f"── conf {args.conf} · buffer {args.buffer} · empar {args.empar} ──")
        cosidos = [
            ("hueco 3 / ambig 0.15", dict(max_hueco=3.0, margen_ambiguedad=0.15)),
            ("hueco 4 / ambig 0.15", cosido_base),
            ("hueco 4 / ambig 0.30", dict(max_hueco=4.0, margen_ambiguedad=0.30)),
            ("hueco 6 / ambig 0.30", dict(max_hueco=6.0, margen_ambiguedad=0.30)),
            ("hueco 4 / color 0.9", dict(max_hueco=4.0, color_max_dist=0.9)),
            ("hueco 2 / ambig 0.05", dict(max_hueco=2.0, margen_ambiguedad=0.05)),
        ]
        for minf in (1, 2):
            for nombre, kw in cosidos:
                f = evaluar(banco, args.buffer, args.empar, minf, kw)
                print(linea(f"  minf {minf} · {nombre}", f, 30))

    print("-" * n)
    for nombre, r in REF.items():
        print(
            f"{'REFERENCIA ' + nombre:<30}{r['nids']:>6}{r['cobertura']:>8.3f}"
            f"{r['conc']:>6}{r['idf1']:>8.3f}{'—':>7}{r['quim']:>5}"
        )
    print(
        "\nCriterio: bajar quimeras SIN degradar cobertura (0.598), "
        "IDF1 (0.484) ni concurrencia (23, GT 22)."
    )


if __name__ == "__main__":
    main()
