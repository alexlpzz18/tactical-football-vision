#!/usr/bin/env python
"""El examen que decide: el criterio del portero con NUESTRAS identidades.

Contra el GT el criterio del último hombre es limpísimo (0,94 / 0,82 /
0,96 / 0,96 con 78-96 puntos de margen, ver `docs/portero.md`). Pero eso
es con identidad perfecta, y nuestras identidades están repartidas en una
mediana de **6 fragmentos por jugador**. "La identidad que más veces es
último hombre" no es lo mismo que "la persona que más veces lo es".

Y hay una pregunta que importa más que el acierto: **¿sabe la regla decir
que NO hay portero?** Una regla que siempre corona a alguien es
peligrosa: en un partido donde el portero no se vea coronaría a un
central, y ese central se saldría del cómputo de su equipo.

Por eso se miden los dos casos:

- **POSITIVO**: ¿corona al portero real? ¿con qué margen?
- **NEGATIVO**: se le quitan al caché las observaciones del portero y se
  vuelve a correr. Si sigue coronando a alguien con la misma confianza,
  la regla no sirve tal cual.

Y si hace falta abstención, se miden las tres salvaguardas propuestas:

1. **pisa el área** de su portería alguna vez,
2. **presencia mínima sostenida** en el tramo,
3. **su color está lejos de los dos prototipos** del partido — un portero
   viste distinto por reglamento, y eso es independiente de la posición.

⚠️ La regla de porteros por ÁREA se desactiva a propósito: lo que se está
midiendo es un candidato a sustituirla, así que dejarla puesta sería
darle la respuesta hecha. Staff y catálogo arbitral se quedan, porque son
independientes del portero.

Uso:
    python scripts/portero_identidades.py
    python scripts/portero_identidades.py --config configs/processor_villa_v4_cache.yaml \
        --gt data/annotations/ground_truth_tracking/annotations.xml --offset 7500
"""

import argparse
import logging
import pickle
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from fugas_en_el_campo import casar_con_gt  # noqa: E402
from portero import puntuacion  # noqa: E402
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.team_classification.color_classifier import _solo_hs  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402

logger = logging.getLogger("portero_ids")

# Radio con el que se borra al portero del caché, en metros. Se comprueba
# en el propio script cuántas detecciones se lleva: si se llevara muchas
# más que las del portero, el caso negativo estaría amañado.
RADIO_BORRADO_M = 2.5


def cargar_todo(ruta_cfg, ruta_gt, offset, paso, recortar=True, sin_porteros=True):
    cfg = yaml.safe_load(open(ruta_cfg))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    cache, colores = filtrar_por_confianza(
        datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
    )
    H = np.load(cfg["rutas"]["homografia"])
    tracks = parsear_cvat(ruta_gt)
    gt_m = gt_a_por_frame(tracks, H, frame_offset=offset, paso_gt=paso)
    gt_px = {}
    for t in tracks:
        for c in t.cajas:
            gt_px.setdefault(offset + paso * c.frame_local, []).append(
                {
                    "id": t.track_id,
                    "pie": ((c.xtl + c.xbr) / 2.0, c.ybr),
                    "team": ("referee" if t.label == "referee" else (c.team or t.team)),
                }
            )
    # La regla de portero se apaga POR DEFECTO: este módulo nació para
    # medir un candidato a sustituirla, y dejarla puesta sería darle la
    # respuesta hecha. Quien quiera el pipeline de producción entero
    # —como el censo del tercer grupo— pasa `sin_porteros=False`.
    if sin_porteros:
        cfg_eq = {
            **cfg_eq,
            "porteros": {**cfg_eq.get("porteros", {}), "activo": False},
        }

    # ⚠️ EL CACHÉ SE RECORTA AL RANGO DEL GT, y sin esto el caso negativo
    # no prueba nada. El caché del benjamín va del frame 8991 al 10788 y
    # el GT solo del 9750 al 10635: fuera de ahí no se puede saber dónde
    # está el portero, así que no se le borra, y el "fantasma" que la
    # regla coronaba en el caso negativo era el propio portero en los
    # frames sin anotar. Medido: de sus 524 observaciones sobrevivían 343
    # al borrado.
    if not recortar:
        return cfg, cfg_tr, cfg_eq, datos, cache, colores, gt_m, gt_px
    f0, f1 = min(gt_m), max(gt_m)
    recortado, colores_r = [], {}
    for entrada in cache:
        f = entrada["frame_idx"]
        if not (f0 <= f <= f1):
            continue
        recortado.append(entrada)
        for i in range(len(entrada["dets"])):
            if (f, i) in colores:
                colores_r[(f, i)] = colores[(f, i)]
    logger.info(
        "Caché recortado al rango del GT (%d-%d): %d de %d frames",
        f0,
        f1,
        len(recortado),
        len(cache),
    )
    return cfg, cfg_tr, cfg_eq, datos, recortado, colores_r, gt_m, gt_px


def porteros_del_gt(gt_m):
    """{obj_id: equipo} de los porteros anotados."""
    salida = {}
    for _f, obs in gt_m.items():
        for o in obs:
            if str(o.team).startswith("portero"):
                salida[o.obj_id] = str(o.team).replace("portero_", "")
    return salida


def trayectoria_gt(gt_m, obj_id):
    """[(t_frame, x, y)] de una persona del GT, ordenada."""
    puntos = []
    for f, obs in gt_m.items():
        for o in obs:
            if o.obj_id == obj_id:
                puntos.append((f, float(o.pos[0]), float(o.pos[1])))
    return sorted(puntos)


def borrar_persona(cache, colores, gt_m, obj_id, radio=RADIO_BORRADO_M):
    """Caché sin las detecciones que caen encima de esa persona.

    El GT solo tiene 1 de cada 15 frames y el caché 1 de cada 3, así que
    no basta con borrar en los frames anotados: hay que INTERPOLAR la
    posición de la persona a todos los frames del caché y borrar lo que
    caiga cerca. Si no, el portero seguiría estando en 4 de cada 5
    frames y el caso negativo no probaría nada.
    """
    tray = trayectoria_gt(gt_m, obj_id)
    if len(tray) < 2:
        return cache, colores, 0
    fs = np.array([p[0] for p in tray], dtype=float)
    xs = np.array([p[1] for p in tray])
    ys = np.array([p[2] for p in tray])
    nuevo, nuevos_colores, borradas = [], {}, 0
    for entrada in cache:
        f = entrada["frame_idx"]
        if f < fs[0] or f > fs[-1]:
            cx = cy = None
        else:
            cx = float(np.interp(f, fs, xs))
            cy = float(np.interp(f, fs, ys))
        dets = []
        for i, det in enumerate(entrada["dets"]):
            if cx is not None and np.hypot(det[0] - cx, det[1] - cy) <= radio:
                borradas += 1
                continue
            j = len(dets)
            dets.append(det)
            if (f, i) in colores:
                nuevos_colores[(f, j)] = colores[(f, i)]
        nuevo.append({**entrada, "dets": dets})
    return nuevo, nuevos_colores, borradas


def lados_por_equipo(identidades, equipos, modelo):
    """{equipo: -1 defiende x=0, +1 defiende x=largo}, de las posiciones."""
    areas = modelo.areas_porteria(margen=2.0)
    medias = defaultdict(list)
    for k, ident in enumerate(identidades, start=1):
        eq = str(equipos.get(k, "otro"))
        if eq not in ("A", "B"):
            continue
        pos = np.array([p for tr in ident for p in tr.pos])
        mx, my = float(np.median(pos[:, 0])), float(np.median(pos[:, 1]))
        if any(
            r[0][0] <= mx <= r[0][1] and r[1][0] <= my <= r[1][1]
            for r in areas.values()
        ):
            continue
        medias[eq].append(mx)
    if len(medias) < 2:
        return {}
    bajo = "A" if np.mean(medias["A"]) < np.mean(medias["B"]) else "B"
    return {bajo: -1, ("B" if bajo == "A" else "A"): +1}


def votar_ultimo_hombre(identidades, equipos, lados, incluir_otro=True):
    """{id_identidad: (veces último hombre, frames presente)} por equipo.

    ⚠️ `incluir_otro` NO es un adorno, es la corrección que salió de medir.
    Con solo las identidades A/B, el criterio **no puede encontrar al
    portero cercano del benjamín**: viste azul eléctrico, el catálogo
    arbitral lo etiqueta 'otro' y queda fuera de la votación. Y es
    circular pedirle otra cosa — el portero es precisamente aquel cuyo
    color NO es fiable, que es la razón de buscarlo por comportamiento.

    Así que una identidad 'otro' compite en la votación de LOS DOS
    equipos: no sabemos su equipo, pero si es el último hombre de un
    lado, el lado dice de qué equipo es. Es la misma lógica que la regla
    de área de producción, que asigna `portero_{equipo del lado}`.
    """
    por_frame = defaultdict(list)
    for k, ident in enumerate(identidades, start=1):
        eq = str(equipos.get(k, "otro"))
        if eq == "staff":
            continue  # vive fuera del campo: no juega
        # ⚠️ TODAS compiten en los DOS lados, no solo las 'otro'. Medido:
        # al borrar un portero, el fit cambia y el clasificador metió al
        # OTRO portero en el equipo contrario; como su voto solo contaba
        # en el lado de su etiqueta, sacó 0 de 494 y la regla se abstuvo
        # teniéndolo delante. La premisa de todo esto es que el color de
        # un portero NO es fiable, así que dejar que su etiqueta decida en
        # qué lado compite es contradecirse. El LADO dice el equipo, igual
        # que en la regla de área de producción.
        destinos = ["A", "B"] if incluir_otro else [eq]
        for tr in ident:
            for pos, par in zip(tr.pos, tr.det_idxs):
                for destino in destinos:
                    por_frame[(par[0], destino)].append((k, float(pos[0])))
    # ⚠️ Las cuentas van por (identidad, EQUIPO), no por identidad. Una
    # identidad 'otro' compite en las dos votaciones, así que contando
    # global su presencia se duplicaba y su ratio se partía por dos: el
    # portero cercano salía 523/1048 = 0,47 y perdía contra un fragmento
    # de 50/51. Es un fallo de diseño mío, no del criterio.
    veces, presente = Counter(), Counter()
    for (_f, eq), gente in por_frame.items():
        lado = lados.get(eq)
        if lado is None:
            continue
        # cada identidad cuenta UNA vez por frame aunque tenga dos cajas
        mejor = {}
        for k, x in gente:
            if k not in mejor or -lado * x < -lado * mejor[k]:
                mejor[k] = x
        for k in mejor:
            presente[(k, eq)] += 1
        veces[(min(mejor, key=lambda k: -lado * mejor[k]), eq)] += 1
    return veces, presente


def candidatos_de(presente, equipos, equipo):
    """Identidades que compiten por ser el portero de ese equipo.

    Incluye las etiquetadas 'otro' a propósito: el portero cercano del
    benjamín viste azul eléctrico y el catálogo arbitral lo manda ahí, así
    que un ranking de solo A/B no puede encontrarlo. Y pedirle al color
    que acierte con el portero es circular: su color no es fiable, que es
    la razón de buscarlo por comportamiento.
    """
    return [
        k
        for (k, eq) in presente
        if eq == equipo and str(equipos.get(k, "otro")) != "staff"
    ]


def ganador(veces, presente, identidades, equipos, equipo):
    """(id, puntuación, puntuación del segundo) del equipo."""
    gente = candidatos_de(presente, equipos, equipo)
    if not gente:
        return None, 0.0, 0.0
    orden = sorted(
        gente, key=lambda k: -puntuacion(veces[(k, equipo)], presente[(k, equipo)])
    )
    p1 = puntuacion(veces[(orden[0], equipo)], presente[(orden[0], equipo)])
    p2 = (
        puntuacion(veces[(orden[1], equipo)], presente[(orden[1], equipo)])
        if len(orden) > 1
        else 0.0
    )
    return orden[0], p1, p2


def dueno_mayoritario(identidad, duenos):
    """A qué persona del GT pertenece mayoritariamente una identidad."""
    gs = [duenos.get(tuple(par)) for tr in identidad for par in tr.det_idxs]
    gs = [g for g in gs if g is not None]
    return Counter(gs).most_common(1)[0][0] if gs else None


def salvaguardas(identidad, equipos_k, modelo, lados, colores, clf, n_frames):
    """Las tres salvaguardas propuestas, medidas sobre una identidad."""
    pos = np.array([p for tr in identidad for p in tr.pos])
    areas = modelo.areas_porteria(margen=2.0)
    lado = lados.get(equipos_k)
    clave = "bajo" if lado == -1 else "alto"
    rx, ry = areas[clave]
    dentro = int(sum(1 for x, y in pos if rx[0] <= x <= rx[1] and ry[0] <= y <= ry[1]))
    n_obs = len(pos)
    frames = {par[0] for tr in identidad for par in tr.det_idxs}
    feats = [
        _solo_hs(colores[tuple(par)])
        for tr in identidad
        for par in tr.det_idxs
        if tuple(par) in colores
    ]
    if feats and clf._prototipos is not None:
        media = np.mean(feats, axis=0)
        a, b = clf._prototipos.a, clf._prototipos.b
        sep = float(np.linalg.norm(a - b)) or 1.0
        d_color = (
            min(float(np.linalg.norm(media - a)), float(np.linalg.norm(media - b)))
            / sep
        )
    else:
        d_color = float("nan")
    return {
        "pisa_area": dentro / max(n_obs, 1),
        "presencia": len(frames) / max(n_frames, 1),
        "color_lejos": d_color,
    }


def correr(nombre, cache, colores, datos, cfg_tr, cfg_eq, gt_m, gt_px, quitar=None):
    """Corre el pipeline y devuelve todo lo necesario para juzgar."""
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    modelo, _prof = _profundidad_configurada(cfg_eq)
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
    lados = lados_por_equipo(ids, equipos, modelo)
    veces, presente = votar_ultimo_hombre(ids, equipos, lados)
    por_frame = {e["frame_idx"]: e for e in cache}
    duenos = {}
    for f in sorted(set(por_frame) & set(gt_px)):
        casado, _ = casar_con_gt(por_frame[f]["dets"], gt_px[f])
        for i, o in casado.items():
            duenos[(f, i)] = o["id"]
    n_frames = len(cache)
    return dict(
        nombre=nombre,
        ids=ids,
        equipos=equipos,
        lados=lados,
        veces=veces,
        presente=presente,
        duenos=duenos,
        clf=clf,
        modelo=modelo,
        colores=colores,
        n_frames=n_frames,
    )


# LAS DOS SALVAGUARDAS, y hacen falta las dos. Los umbrales salen de la
# separación medida, no de números que suenen bien. Sobre los 8 casos de
# las dos patas (4 porteros presentes, 4 borrados):
#
#   porteros de verdad : área 99-100 %  ·  presencia  99-100 %
#   impostores         : área  0-100 %  ·  presencia   7- 99 %
#
# Ninguna de las dos separa sola: un impostor vive dentro del área el
# 100 % del tiempo (un fragmento de 21 frames detrás de la portería) y
# otro tiene el 99 % de presencia (un defensa). Pero **cada impostor
# falla al menos una**, así que exigiendo las dos salen 8 de 8. Los
# huecos son anchos (27-98 % y 22-98 %), así que 0,50 no es un filo.
MIN_PISA_AREA = 0.50
MIN_PRESENCIA = 0.50


def informar(r, porteros_gt, quitado=None):
    print(f"\n  lados deducidos: {r['lados']} · {len(r['ids'])} identidades")
    cab = (
        f"    {'lado':<17}{'gana':>5}{'punt.':>7}{'2º':>7}"
        f"{'del GT':>9}{'¿portero?':>11}{'pisa área':>10}"
        f"{'presencia':>10}{'color':>7}{'DECISIÓN':>14}"
    )
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    veredicto = {}
    # ⚠️ Se reporta por LADO, no por etiqueta de equipo. Las etiquetas A/B
    # del clasificador son ARBITRARIAS —salen del fit— y se intercambian
    # entre corridas: al borrar al portero de un lado, el "equipo A" de la
    # corrida nueva resultó ser el equipo B de la vieja, y la tabla parecía
    # decir un disparate. El lado (defiende x=0 / x=largo) es invariante.
    por_lado = {v: k for k, v in r["lados"].items()}
    for lado_val, nombre_lado in ((-1, "defiende x=0"), (+1, "defiende x=largo")):
        equipo = por_lado.get(lado_val)
        if equipo is None:
            continue
        k, p1, p2 = ganador(r["veces"], r["presente"], r["ids"], r["equipos"], equipo)
        if k is None:
            print(f"    {nombre_lado:<8}{'—':>6}")
            continue
        dueno = dueno_mayoritario(r["ids"][k - 1], r["duenos"])
        es_portero = dueno in porteros_gt
        sv = salvaguardas(
            r["ids"][k - 1],
            equipo,
            r["modelo"],
            r["lados"],
            r["colores"],
            r["clf"],
            r["n_frames"],
        )
        etiqueta = "SÍ" if es_portero else ("(borrado)" if quitado else "NO")
        acepta = (
            "corona"
            if sv["pisa_area"] >= MIN_PISA_AREA and sv["presencia"] >= MIN_PRESENCIA
            else "SE ABSTIENE"
        )
        print(
            f"    {nombre_lado:<17}{k:>5}{p1:>7.2f}{p2:>7.2f}"
            f"{str(dueno):>9}{etiqueta:>11}{sv['pisa_area']:>10.0%}"
            f"{sv['presencia']:>10.0%}{sv['color_lejos']:>7.2f}{acepta:>14}"
        )
        veredicto[nombre_lado] = (k, p1, p1 - p2, es_portero, sv, acepta)

    # Los cinco primeros de cada equipo con TODO: sin esto no se puede
    # diseñar la abstención, solo constatar que hace falta.
    print("\n    Los 5 primeros candidatos de cada equipo:")
    cab2 = (
        f"      {'eq':<4}{'id':>5}{'punt.':>7}{'ult/pres':>11}{'mediana (m)':>16}"
        f"{'obs':>6}{'pisa área':>11}{'presencia':>11}{'color':>8}{'GT':>6}"
    )
    print(cab2)
    print("      " + "-" * (len(cab2) - 6))
    for lado_val, nombre_lado in ((-1, "x=0"), (+1, "x=largo")):
        equipo = por_lado.get(lado_val)
        if equipo is None:
            continue
        gente = candidatos_de(r["presente"], r["equipos"], equipo)
        for k in sorted(
            gente,
            key=lambda k: -puntuacion(
                r["veces"][(k, equipo)], r["presente"][(k, equipo)]
            ),
        )[:5]:
            ident = r["ids"][k - 1]
            pos = np.array([p for tr in ident for p in tr.pos])
            n_obs = sum(len(tr.det_idxs) for tr in ident)
            sv = salvaguardas(
                ident,
                equipo,
                r["modelo"],
                r["lados"],
                r["colores"],
                r["clf"],
                r["n_frames"],
            )
            d = dueno_mayoritario(ident, r["duenos"])
            marca = "PORT" if d in porteros_gt else (str(d) if d is not None else "—")
            ratio = f"{r['veces'][(k, equipo)]}/{r['presente'][(k, equipo)]}"
            print(
                f"      {equipo:<4}{k:>5}"
                f"{puntuacion(r['veces'][(k, equipo)], r['presente'][(k, equipo)]):>7.2f}"
                f"{ratio:>11}"
                f"{f'({np.median(pos[:,0]):.1f},{np.median(pos[:,1]):.1f})':>16}"
                f"{n_obs:>6}{sv['pisa_area']:>10.0%}{sv['presencia']:>10.0%}"
                f"{sv['color_lejos']:>8.2f}{marca:>6}"
            )
    return veredicto


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--offset", type=int, default=9750)
    p.add_argument("--paso", type=int, default=15)
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg, cfg_tr, cfg_eq, datos, cache, colores, gt_m, gt_px = cargar_todo(
        args.config, args.gt, args.offset, args.paso
    )
    porteros_gt = porteros_del_gt(gt_m)
    print(f"\n{args.config}")
    print(f"  porteros del GT: {porteros_gt}")
    print(
        f"  caché recortado al rango del GT: {len(cache)} frames "
        f"({min(gt_m)}-{max(gt_m)}), {sum(len(e['dets']) for e in cache)} detecciones"
    )
    print("  ⚠️ regla de área DESACTIVADA (es lo que este criterio sustituye)")

    print("\n" + "=" * 96)
    print("CASO POSITIVO: ¿corona al portero real con NUESTRAS identidades?")
    print("=" * 96)
    r0 = correr("positivo", cache, colores, datos, cfg_tr, cfg_eq, gt_m, gt_px)
    v0 = informar(r0, porteros_gt)

    print("\n" + "=" * 96)
    print("CASO NEGATIVO: sin el portero en el caché, ¿sabe abstenerse?")
    print("=" * 96)
    for oid, equipo in sorted(porteros_gt.items()):
        cache2, colores2, borradas = borrar_persona(cache, colores, gt_m, oid)
        total = sum(len(e["dets"]) for e in cache)
        print(
            f"\n  ── borrado el portero {oid} (equipo {equipo}): "
            f"{borradas} detecciones de {total} = {borradas/total:.1%} ──"
        )
        r1 = correr("negativo", cache2, colores2, datos, cfg_tr, cfg_eq, gt_m, gt_px)
        v1 = informar(r1, porteros_gt, quitado=oid)
        # ¿Qué LADO se ha quedado sin portero? El del portero borrado, y
        # se localiza mirando qué lado coronaba a ESA persona en el caso
        # positivo. No se puede usar la etiqueta de equipo: es arbitraria
        # y cambia entre corridas.
        lado_borrado = None
        for nombre_lado, dat in v0.items():
            if dueno_mayoritario(r0["ids"][dat[0] - 1], r0["duenos"]) == oid:
                lado_borrado = nombre_lado
        if lado_borrado and lado_borrado in v1:
            a, b = v0[lado_borrado], v1[lado_borrado]
            print(f"\n    EL NÚMERO QUE DECIDE ({lado_borrado}):")
            print(
                f"      con portero : puntuación {a[1]:.2f} · "
                f"pisa área {a[4]['pisa_area']:.0%} · {a[5]}"
            )
            print(
                f"      sin portero : puntuación {b[1]:.2f} · "
                f"pisa área {b[4]['pisa_area']:.0%} · {b[5]}"
            )
            if b[5] == "SE ABSTIENE":
                print("      → BIEN: las salvaguardas descartan al impostor.")
            else:
                print("      → MAL: corona a un impostor. Hace falta más.")


if __name__ == "__main__":
    main()
