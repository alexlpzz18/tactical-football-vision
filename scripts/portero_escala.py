#!/usr/bin/env python
"""¿La regla del portero es INVARIANTE A LA ESCALA del tramo?

Hoy no lo es. `min_presencia` mide presencia como fracción DEL TRAMO, y
sobre 5 minutos el portero del benjamín cae al 49 % contra un mínimo de
0,50: la regla se abstiene teniéndolo delante, pisando el área el 88 %
(docs/portero.md). El supuesto roto no es el umbral: es que el portero
sea UNA identidad. En el lado alto del piloto son cuatro trozos
(66/51/31/26 %).

Arreglo que se mide aquí (encargo de Alex, 26-ago-2026): coronar al
CONJUNTO de fragmentos que cumplen los dos criterios —pisa su área y es
el último hombre de ese lado— y sumar su presencia en vez de medirla por
separado. Si cuatro trozos son el portero, los cuatro son el portero.

Lo que hay que demostrar, en este orden:

1. Que el conjunto encuentra al portero A LAS DOS LONGITUDES (60 s y 5
   min) y que lo que se corona es LA MISMA PERSONA del GT.
2. Que el umbral del último hombre sale de una MESETA común a las dos
   patas, no de un número que suene bien.
3. Que el caso negativo sigue pasando: borrando al portero, no se corona
   a nadie.

⚠️ Nada se reimplementa: la tabla de candidatas se le pide a la propia
regla (`censar_candidatas` / `puntuar_candidatas`) interceptando la
llamada que hace el pipeline de producción. Una tabla reimplementada en
un script mide otra cosa que la que corre en producción.

Uso:
    python scripts/portero_escala.py                       # benjamín 60 s
    python scripts/portero_escala.py --piloto5min          # benjamín 5 min
    python scripts/portero_escala.py --config configs/processor_villa_v4_cache.yaml \
        --gt data/annotations/ground_truth_tracking/annotations.xml --offset 7500
"""

import argparse
import logging
import sys
import warnings
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from fugas_en_el_campo import casar_con_gt  # noqa: E402
from portero_identidades import cargar_todo, porteros_del_gt  # noqa: E402
from src.team_classification import porteros as mod_porteros  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("portero_escala")

# Rejilla del barrido del último hombre. Arranca en 0 (= sin criterio de
# último hombre, solo el área) para que se vea qué aporta cada señal.
REJILLA = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]


def estado_antes_del_portero(cfg_eq, cache, colores, datos, cfg_tr):
    """Lo que ve la regla del portero cuando el pipeline la llama.

    Se intercepta la llamada real en vez de reconstruirla: así el censo
    incluye el mismo `equipos` a medio cocinar (catálogo arbitral sí,
    staff todavía no) que ve producción, que es justo el matiz que ya
    causó un fallo (docs/portero.md).
    """
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
    capturado = {}
    original = mod_porteros.aplicar_regla_portero_ultimo_hombre

    def espia(equipos, identidades, modelo, lados, params):
        capturado["equipos"] = dict(equipos)
        capturado["identidades"] = identidades
        capturado["modelo"] = modelo
        capturado["lados"] = dict(lados)
        capturado["params"] = params
        return original(equipos, identidades, modelo, lados, params)

    mod_porteros.aplicar_regla_portero_ultimo_hombre = espia
    try:
        import src.team_classification.pipeline_equipos as pe

        pe_original = pe.aplicar_regla_portero_ultimo_hombre
        pe.aplicar_regla_portero_ultimo_hombre = espia
        try:
            clasificar_identidades(ids, colores, clf, cfg_eq)
        finally:
            pe.aplicar_regla_portero_ultimo_hombre = pe_original
    finally:
        mod_porteros.aplicar_regla_portero_ultimo_hombre = original
    if not capturado:
        raise SystemExit(
            "La regla por ÚLTIMO HOMBRE no llegó a llamarse: revisa que "
            "porteros.activo y porteros.metodo: ultimo_hombre estén puestos."
        )
    return capturado


def duenos_de_identidad(identidades, cache, gt_px):
    """{id del sistema: (obj_id del GT, nº de observaciones casadas)}.

    Por POSICIÓN Y TIEMPO, nunca por el id del sistema, que caduca al
    cambiar de detector o de tramo (lección en CLAUDE.md).
    """
    por_frame = {e["frame_idx"]: e for e in cache}
    casados = {}
    for f in sorted(set(por_frame) & set(gt_px)):
        casado, _ = casar_con_gt(por_frame[f]["dets"], gt_px[f])
        for det_idx, obj in casado.items():
            casados[(f, det_idx)] = obj["id"]
    salida = {}
    for k, ident in enumerate(identidades, start=1):
        votos = Counter()
        for tracklet in ident:
            for par in tracklet.det_idxs:
                if par in casados:
                    votos[casados[par]] += 1
        if votos:
            salida[k] = votos.most_common(1)[0]
    return salida


def conjunto(filas, min_pisa, min_ultimo, frames_de=None):
    """Fragmentos que cumplen LOS DOS criterios, y su presencia conjunta.

    ⚠️ La presencia del conjunto es la de la UNIÓN de sus frames, no la
    suma. Sumar da números por encima de 1,0 —medido: 2,27 en el lado B
    del piloto— porque dos fragmentos pueden coexistir en el mismo frame,
    y entonces "fracción del tramo" deja de querer decir nada. La unión
    es lo que la regla quería medir desde el principio: en qué parte del
    tramo hay ALGÚN trozo del portero.
    """
    dentro = [
        f for f in filas if f["pisa"] >= min_pisa and f["ultimo_hombre"] >= min_ultimo
    ]
    if frames_de is None:
        return dentro, sum(f["presencia"] for f in dentro)
    union = set()
    for f in dentro:
        union |= frames_de[f["id"]]
    return dentro, len(union)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    p.add_argument("--piloto5min", action="store_true")
    p.add_argument("--cache", default=None, help="caché de detecciones alternativo")
    p.add_argument("--colores", default=None, help="caché de colores alternativo")
    p.add_argument(
        "--equipos",
        default=None,
        help="config de equipos alternativo (si el processor no lo trae)",
    )
    p.add_argument("--etiqueta", default=None)
    p.add_argument(
        "--caso-negativo",
        action="store_true",
        help="borra a cada portero del GT y comprueba que la regla NO corona a nadie",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")

    cfg, cfg_tr, cfg_eq, datos, cache, colores, gt_m, gt_px = cargar_todo(
        args.config,
        args.gt,
        args.offset,
        args.paso,
        recortar=False,
        sin_porteros=False,
        ruta_eq=args.equipos,
    )
    ruta_cache, ruta_col = args.cache, args.colores
    if args.piloto5min:
        base = Path(cfg["rutas"]["cache"]).parent
        ruta_cache = str(base / "cache_detecciones_benja_piloto5min.pkl")
        ruta_col = str(base / "cache_colores_benja_piloto5min.pkl")
    if ruta_cache:
        import pickle

        from src.tracking.cache_io import cargar_cache
        from src.tracking.filtro_confianza import filtrar_por_confianza

        datos = cargar_cache(ruta_cache)
        with open(ruta_col, "rb") as f:
            colores = pickle.load(f)
        cache, colores = filtrar_por_confianza(
            datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
        )

    etiqueta = args.etiqueta or ("5 min" if args.piloto5min else "60 s")
    dur = cache[-1]["t"] - cache[0]["t"]
    print(f"\n{'='*70}\n{etiqueta}: {len(cache)} frames, {dur:.0f} s\n{'='*70}")

    if args.caso_negativo:
        # ⚠️ AQUÍ EL CACHÉ SE RECORTA AL RANGO DEL GT. Sin esto el caso
        # negativo no prueba nada: fuera de los frames anotados no se
        # sabe dónde está el portero, así que no se le borra, y el
        # "impostor" que la regla corona es él mismo. Ya pasó una vez
        # (portero_identidades.py) y vuelve a pasar si se olvida: sin
        # recortar, la regla corona al portero_B con x=58,9 justo después
        # de haberlo borrado.
        cfg, cfg_tr, cfg_eq, datos, cache, colores, gt_m, gt_px = cargar_todo(
            args.config,
            args.gt,
            args.offset,
            args.paso,
            recortar=True,
            sin_porteros=False,
            ruta_eq=args.equipos,
        )
        print(
            f"\nCASO NEGATIVO (caché recortado al GT: {len(cache)} frames, "
            f"{min(gt_m)}-{max(gt_m)}): ¿sabe abstenerse?"
        )
        caso_negativo(cfg_eq, cache, colores, datos, cfg_tr, gt_m, gt_px)
        return

    est = estado_antes_del_portero(cfg_eq, cache, colores, datos, cfg_tr)
    censo = mod_porteros.censar_candidatas(
        est["identidades"], est["equipos"], est["modelo"]
    )
    areas = est["modelo"].areas_porteria(margen=est["params"].margen_area_m)
    duenos = duenos_de_identidad(est["identidades"], cache, gt_px)
    porteros_gt = porteros_del_gt(gt_m)
    print(f"porteros anotados en el GT: {porteros_gt}")
    print(f"lados deducidos: {est['lados']}")

    for equipo, lado in est["lados"].items():
        filas = mod_porteros.puntuar_candidatas(est["identidades"], censo, areas, lado)
        print(f"\n── lado de {equipo} (x{'0' if lado == -1 else ' largo'}) ──")
        print(
            f"  {'id':>4} {'ult.hombre':>11} {'pisa':>6} {'presencia':>10}"
            f"  {'vista':>6} {'mediana (x,y)':>16}  dueño en el GT"
        )
        for f in filas[:8]:
            dueno = duenos.get(f["id"])
            marca = ""
            if dueno and dueno[0] in porteros_gt:
                marca = f"  ← PORTERO_{porteros_gt[dueno[0]]}"
            txt = f"obj {dueno[0]} ({dueno[1]} obs)" if dueno else "—"
            import numpy as np

            pos = np.array(
                [q for tr in est["identidades"][f["id"] - 1] for q in tr.pos]
            )
            mx, my = np.median(pos, axis=0)
            print(
                f"  {f['id']:>4} {f['ultimo_hombre']:>11.3f} {f['pisa']:>6.2f}"
                f" {f['presencia']:>10.2f} {f['vista']:>6}"
                f" {f'({mx:5.1f},{my:5.1f})':>16}  {txt}{marca}"
            )

        print(
            f"\n  barrido del umbral de último hombre (pisa ≥ "
            f"{est['params'].min_pisa_area:.2f}):"
        )
        print(f"  {'umbral':>7} {'nº':>3} {'unión':>7} {'suma':>7}  ids")
        n_frames = censo[3]
        for u in REJILLA:
            dentro, n_union = conjunto(filas, est["params"].min_pisa_area, u, censo[2])
            suma = sum(f["presencia"] for f in dentro)
            ids = ",".join(str(f["id"]) for f in dentro[:6])
            gt_ok = any(duenos.get(f["id"], (None,))[0] in porteros_gt for f in dentro)
            print(
                f"  {u:>7.2f} {len(dentro):>3} {n_union / n_frames:>7.2f}"
                f" {suma:>7.2f}  {ids}{'  ✓GT' if gt_ok else ''}"
            )


def caso_negativo(cfg_eq, cache, colores, datos, cfg_tr, gt_m, gt_px):
    """Borrado el portero del caché, ¿la regla se abstiene en SU lado?

    Se ejecuta la regla DE PRODUCCIÓN (vía `clasificar_identidades`), no
    una copia: el caso negativo solo vale si prueba lo que se despliega.
    El lado se identifica por POSICIÓN —dónde estaba el portero borrado—
    y nunca por la etiqueta de equipo, que es arbitraria entre corridas.
    """
    from portero_identidades import borrar_persona
    from src.team_classification.pipeline_equipos import clasificar_identidades

    porteros_gt = porteros_del_gt(gt_m)
    total = sum(len(e["dets"]) for e in cache)
    for oid in sorted(porteros_gt):
        cache2, colores2, borradas = borrar_persona(cache, colores, gt_m, oid)
        # Dónde vivía: el lado que se queda huérfano.
        xs = [float(o.pos[0]) for obs in gt_m.values() for o in obs if o.obj_id == oid]
        x_medio = sum(xs) / len(xs)
        print(
            f"\n  ── borrado el portero obj {oid} (x medio {x_medio:.1f} m): "
            f"{borradas} de {total} detecciones ({borradas/total:.1%}) ──"
        )
        est = estado_antes_del_portero(cfg_eq, cache2, colores2, datos, cfg_tr)
        censo = mod_porteros.censar_candidatas(
            est["identidades"], est["equipos"], est["modelo"]
        )
        clf2 = entrenar_clasificador(colores2, cfg_eq, cache2)
        eq2 = clasificar_identidades(est["identidades"], colores2, clf2, cfg_eq)
        import numpy as np

        coronados = {}
        for k, v in eq2.items():
            if not str(v).startswith("portero_"):
                continue
            pos = np.array([q for tr in est["identidades"][k - 1] for q in tr.pos])
            coronados[k] = (str(v), float(np.median(pos[:, 0])))
        largo = est["modelo"].largo
        huerfano = "bajo" if x_medio < largo / 2 else "alto"
        en_ese_lado = [
            k
            for k, (_v, mx) in coronados.items()
            if (mx < largo / 2) == (huerfano == "bajo")
        ]
        print(f"     coronados: {coronados if coronados else 'ninguno'}")
        if en_ese_lado:
            print(
                f"     → MAL: corona a {en_ese_lado} en el lado {huerfano}, "
                "que se ha quedado sin portero."
            )
        else:
            print(f"     → BIEN: se abstiene en el lado {huerfano}.")
        assert censo is not None


if __name__ == "__main__":
    main()
