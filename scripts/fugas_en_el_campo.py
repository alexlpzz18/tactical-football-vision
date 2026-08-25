#!/usr/bin/env python
"""¿Quién se cuela como jugador dentro del campo, y por qué?

Dos bugs que Alex vio mirando los 5 frames de `mirar_recortes_sueltos.py`:

1. A veces se detecta como jugador una **línea del campo** o la **media
   blanca** de un jugador de naranja, y sale clasificado de blanco.
2. El **árbitro** cae en uno de los dos equipos en varios frames: el
   catálogo arbitral lo caza a veces y otras no.

Los dos comparten población: detecciones que están DENTRO del rectángulo
del campo (así que la regla de staff no las toca), que no son ninguna de
las 14 personas del GT, y que ninguna regla saca. Esas salen con equipo.

Qué mide, en tres bloques:

**A. Las fugas, una a una.** Hoja de contactos con el recorte, para
poder clasificarlas a ojo: línea, media, árbitro, público o persona real
que el casado con el GT no pilló. Sin la imagen no se puede decidir si
son falsos positivos del detector o cajas mal ajustadas.

**B. El barrido de confianza.** Si son del detector, subir el umbral
debería quitarlas. Se mide a la vez lo que CUESTA: cuántas de las 14
personas del GT se dejan de detectar. El caché se generó a 0,3, así que
solo se puede subir; si el barrido pidiera bajar, haría falta otra pasada
de Colab.

**C. El árbitro.** Cuántas de sus observaciones acaban bien etiquetadas
y, en las que fallan, por qué: si el arquetipo no dispara, si otra regla
lo pisa, o si la identidad es demasiado corta para que el catálogo la
mire (min_observaciones = 25).

Uso:
    python scripts/fugas_en_el_campo.py
"""

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from mirar_recortes_sueltos import (  # noqa: E402
    FRAC_TOLERANCIA,
    regla_de_la_observacion,
    texto,
)
from src.evaluation.gt_parser import parsear_cvat  # noqa: E402
from src.team_classification.arbitro import (  # noqa: E402
    arquetipos_activos,
    tono_dominante,
)
from src.team_classification.feature_v2 import brillo_medio  # noqa: E402
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    cargar_config_equipos,
    clasificar_identidades,
    entrenar_clasificador,
)
from src.team_classification.porteros import (  # noqa: E402
    ReglaPorteros,
    deducir_lados,
)
from src.team_classification.staff import ReglaStaff  # noqa: E402
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402
from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("fugas")
BLANCO = (255, 255, 255)
GRIS = (150, 150, 150)


def casar_con_gt(dets, obs_gt):
    """{det_idx: observación GT} por cercanía del pie, en píxeles."""
    pares = []
    for k, o in enumerate(obs_gt):
        for i, d in enumerate(dets):
            x1, y1, x2, y2 = d[2], d[3], d[4], d[5]
            dd = float(np.hypot((x1 + x2) / 2 - o["pie"][0], y2 - o["pie"][1]))
            if dd <= FRAC_TOLERANCIA * (y2 - y1):
                pares.append((dd, k, i))
    pares.sort()
    ugt, udet, casado = set(), set(), {}
    for dd, k, i in pares:
        if k in ugt or i in udet:
            continue
        ugt.add(k)
        udet.add(i)
        casado[i] = obs_gt[k]
    return casado, len(ugt)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--salida", default="outputs/fugas")
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores_crudos = pickle.load(f)
    conf_prod = float(cfg_tr.get("confianza_min", 0) or 0)
    cache, colores = filtrar_por_confianza(datos["cache"], colores_crudos, conf_prod)
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    modelo, profundidad = _profundidad_configurada(cfg_eq)
    activos = arquetipos_activos([clf._prototipos.a, clf._prototipos.b])

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
    eq_ident = clasificar_identidades(ids, colores, clf, cfg_eq)
    cfg_p = cfg_eq.get("porteros", {})
    margen = cfg_p.get("margen_m", 2.0)
    lados = deducir_lados(
        {k: v for k, v in eq_ident.items() if v in ("A", "B")},
        ids,
        modelo.largo,
        regla=ReglaPorteros.desde_modelo(modelo, margen=margen),
        ancho=modelo.ancho,
    )
    bajo, alto = lados if lados else (cfg_p["equipo_mx_bajo"], cfg_p["equipo_mx_alto"])
    regla_p = ReglaPorteros.desde_modelo(
        modelo, margen=margen, equipo_mx_bajo=bajo, equipo_mx_alto=alto
    )
    cfg_s = cfg_eq.get("staff", {})
    regla_s = ReglaStaff(
        largo=modelo.largo,
        ancho=modelo.ancho,
        tolerancia_m=cfg_s.get("tolerancia_m", 2.0),
        min_observaciones=cfg_s.get("min_observaciones", 5),
    )

    tracks = parsear_cvat(args.gt)
    gt_frames = {}
    for t in tracks:
        for c in t.cajas:
            gt_frames.setdefault(9750 + 15 * c.frame_local, []).append(
                {
                    "id": t.track_id,
                    "pie": ((c.xtl + c.xbr) / 2.0, c.ybr),
                    "team": (c.team or t.team or "?"),
                }
            )
    por_frame = {e["frame_idx"]: e for e in cache}
    comunes = sorted(set(por_frame) & set(gt_frames))

    # ── A. Las fugas: dentro del campo, sin GT, sin regla ─────────────
    fugas = []
    for f in comunes:
        entrada = por_frame[f]
        casado, _ = casar_con_gt(entrada["dets"], gt_frames[f])
        for i, d in enumerate(entrada["dets"]):
            if i in casado:
                continue
            mx, my = float(d[0]), float(d[1])
            feat = colores.get((f, i))
            if feat is None:
                continue
            et_r, _m = regla_de_la_observacion(mx, my, feat, regla_p, regla_s, activos)
            if et_r is not None:
                continue  # una regla la saca: no es fuga
            fugas.append(
                {
                    "frame": f,
                    "i": i,
                    "caja": (d[2], d[3], d[4], d[5]),
                    "conf": float(d[6]),
                    "pos": (mx, my),
                    "color": clf.predict_color(feat),
                    "alto": float(d[5] - d[3]),
                    "ancho": float(d[4] - d[2]),
                    "prof": profundidad.de((mx, my), modelo),
                }
            )

    print("\n" + "=" * 74)
    print("A. FUGAS: dentro del campo, no son de las 14, sin regla que las saque")
    print("=" * 74)
    print(
        f"  {len(fugas)} en los {len(comunes)} frames del GT "
        f"({len(fugas)/len(comunes):.1f} por frame)"
    )
    if fugas:
        anchos = np.array([f["ancho"] for f in fugas])
        altos = np.array([f["alto"] for f in fugas])
        confs = np.array([f["conf"] for f in fugas])
        rel = anchos / np.maximum(altos, 1)
        print(
            f"  caja: alto {np.median(altos):.0f} px (p10 {np.percentile(altos,10):.0f}, "
            f"p90 {np.percentile(altos,90):.0f}) · "
            f"relación ancho/alto {np.median(rel):.2f}"
        )
        print(
            f"  confianza: mediana {np.median(confs):.2f} · "
            f"p10 {np.percentile(confs,10):.2f} · p90 {np.percentile(confs,90):.2f}"
        )
        etq = {}
        for f in fugas:
            etq[f["color"]] = etq.get(f["color"], 0) + 1
        print(f"  equipo que les asigna el color: {etq}")
        # Comparación con las cajas de personas REALES, que es lo que
        # decide si la confianza puede separarlas
        reales = []
        for f in comunes:
            entrada = por_frame[f]
            casado, _ = casar_con_gt(entrada["dets"], gt_frames[f])
            for i in casado:
                reales.append(float(entrada["dets"][i][6]))
        reales = np.array(reales)
        print(
            f"\n  Para comparar, las {len(reales)} detecciones que SÍ son "
            f"una de las 14:"
        )
        print(
            f"    confianza: mediana {np.median(reales):.2f} · "
            f"p10 {np.percentile(reales,10):.2f} · p90 {np.percentile(reales,90):.2f}"
        )

    # ── B. Barrido de confianza ───────────────────────────────────────
    print("\n" + "=" * 74)
    print("B. ¿Las quita subir la confianza? (el caché se generó a 0,30: solo se sube)")
    print("=" * 74)
    cab = (
        f"  {'confianza':>10}{'fugas':>8}{'personas del GT vistas':>25}"
        f"{'detecciones':>14}"
    )
    print(cab)
    print("  " + "-" * (len(cab) - 2))
    for umbral in (0.30, 0.45, 0.50, 0.60, 0.70, 0.80):
        c_u, col_u = filtrar_por_confianza(datos["cache"], colores_crudos, umbral)
        pf_u = {e["frame_idx"]: e for e in c_u}
        n_fugas = n_vistas = n_gt = n_dets = 0
        for f in comunes:
            entrada = pf_u.get(f)
            if entrada is None:
                continue
            n_dets += len(entrada["dets"])
            casado, n_cas = casar_con_gt(entrada["dets"], gt_frames[f])
            n_vistas += n_cas
            n_gt += len(gt_frames[f])
            for i, d in enumerate(entrada["dets"]):
                if i in casado:
                    continue
                feat = col_u.get((f, i))
                if feat is None:
                    continue
                et_r, _m = regla_de_la_observacion(
                    float(d[0]), float(d[1]), feat, regla_p, regla_s, activos
                )
                if et_r is None:
                    n_fugas += 1
        marca = "  <- hoy" if abs(umbral - conf_prod) < 1e-6 else ""
        print(
            f"  {umbral:>10.2f}{n_fugas:>8}"
            f"{f'{n_vistas}/{n_gt} = {n_vistas/max(n_gt,1):.1%}':>25}"
            f"{n_dets:>14}{marca}"
        )

    # ── C. El árbitro ─────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print("C. EL ÁRBITRO: ¿en cuántas observaciones está bien etiquetado?")
    print("=" * 74)
    # ⚠️ Hay que medirlo a DOS niveles y no confundirlos, porque dan
    # respuestas distintas y solo uno es lo que Alex ve en el replay:
    #   - SISTEMA: la etiqueta sale del voto por identidad. Es lo que
    #     produce el replay hoy.
    #   - POR OBSERVACIÓN: cada recorte decide solo. Es lo que se pintó
    #     en las imágenes de mirar_recortes_sueltos.py, y por eso allí el
    #     árbitro salía de naranja.
    et_sistema = {}
    for k, ident in enumerate(ids, start=1):
        for tr in ident:
            for par in tr.det_idxs:
                et_sistema[tuple(par)] = str(eq_ident.get(k, "otro"))
    id_de = {}
    for k, ident in enumerate(ids, start=1):
        for tr in ident:
            for par in tr.det_idxs:
                id_de[tuple(par)] = k
    n_no14 = n_cuela_sis = n_cuela_obs = 0
    culpables, quien = {}, {}
    for f in comunes:
        entrada = por_frame[f]
        casado, _ = casar_con_gt(entrada["dets"], gt_frames[f])
        for i, d in enumerate(entrada["dets"]):
            if i in casado:
                continue
            feat = colores.get((f, i))
            if feat is None:
                continue
            n_no14 += 1
            sis = et_sistema.get((f, i))
            if sis in ("A", "B"):
                n_cuela_sis += 1
                culpables[sis] = culpables.get(sis, 0) + 1
                quien[id_de.get((f, i), 0)] = quien.get(id_de.get((f, i), 0), 0) + 1
            et_r, _m = regla_de_la_observacion(
                float(d[0]), float(d[1]), feat, regla_p, regla_s, activos
            )
            if et_r is None:
                n_cuela_obs += 1
    print(f"  Detecciones de los 60 frames que NO son ninguna de las 14: {n_no14}")
    print(
        f"    se cuelan como jugador con el SISTEMA (voto por identidad): "
        f"{n_cuela_sis} = {n_cuela_sis/max(n_no14,1):.1%}  {culpables}"
    )
    print(
        f"    se cuelan etiquetando POR OBSERVACIÓN:                      "
        f"{n_cuela_obs} = {n_cuela_obs/max(n_no14,1):.1%}"
    )
    print("\n  Qué identidades meten esas 'personas' que no existen:")
    for k, n in sorted(quien.items(), key=lambda x: -x[1])[:10]:
        pos = np.array([p for tr in ids[k - 1] for p in tr.pos])
        n_obs = sum(len(tr.det_idxs) for tr in ids[k - 1])
        print(
            f"    id {k:<4} {n:>3} fugas de sus {n_obs:>4} obs  ->"
            f" '{eq_ident.get(k)}'  mediana ({np.median(pos[:, 0]):.1f},"
            f" {np.median(pos[:, 1]):.1f}) m"
        )
    print()
    # Quién es el árbitro, SIN usar el catálogo (sería circular): las
    # identidades cuyas observaciones no casan con ninguna de las 14 pero
    # viven DENTRO del campo y persisten en el tramo.
    duenos = {}
    for f in comunes:
        casado, _ = casar_con_gt(por_frame[f]["dets"], gt_frames[f])
        for i, o in casado.items():
            duenos[(f, i)] = o["id"]
    candidatos = []
    for k, ident in enumerate(ids, start=1):
        pares = [tuple(par) for tr in ident for par in tr.det_idxs]
        pos = np.array([p for tr in ident for p in tr.pos])
        en_gt = [duenos.get(par) for par in pares if par[0] in gt_frames]
        n_juzgables = sum(1 for x in en_gt if x is not None) + sum(
            1 for x in en_gt if x is None
        )
        n_casan = sum(1 for x in en_gt if x is not None)
        mx, my = float(np.median(pos[:, 0])), float(np.median(pos[:, 1]))
        dentro = 0 <= mx <= modelo.largo and 0 <= my <= modelo.ancho
        if len(pares) >= 25 and dentro and n_juzgables and n_casan / n_juzgables < 0.2:
            candidatos.append((k, ident, pares, mx, my, n_casan, n_juzgables))

    cab2 = (
        f"  {'id':>5}{'obs':>7}{'mediana (m)':>16}{'casa GT':>11}"
        f"{'etiqueta del sistema':>23}"
    )
    print(cab2)
    print("  " + "-" * (len(cab2) - 2))
    for k, ident, pares, mx, my, n_casan, n_juz in sorted(
        candidatos, key=lambda c: -len(c[2])
    ):
        print(
            f"  {k:>5}{len(pares):>7}{f'({mx:.1f}, {my:.1f})':>16}"
            f"{f'{n_casan}/{n_juz}':>11}{str(eq_ident.get(k)):>23}"
        )

    print("\n  Por qué falla cuando falla (identidad a identidad):")
    total_obs = bien = 0
    for k, ident, pares, mx, my, _nc, _nj in sorted(
        candidatos, key=lambda c: -len(c[2])
    ):
        feats = [colores[par] for par in pares if par in colores]
        if not feats:
            continue
        media = np.mean(feats, axis=0)
        tm = tono_dominante(media)
        casa = [
            a.nombre
            for a in activos
            if tm and a.contiene(tm[0], tm[1], brillo_medio(media))
        ]
        etiqueta = str(eq_ident.get(k))
        total_obs += len(pares)
        bien += len(pares) if etiqueta not in ("A", "B") else 0
        if etiqueta in ("A", "B"):
            if len(feats) < cfg_eq["arbitro"].get("min_observaciones", 25):
                causa = f"identidad corta ({len(feats)} < 25): el catálogo ni la mira"
            elif not casa:
                causa = (
                    f"el tono medio (H {tm[0]:.0f}, S {tm[1]:.0f}) no cae en "
                    f"ningún arquetipo"
                )
            else:
                causa = f"casaba '{casa[0]}' pero otra regla la sobrescribió"
            print(f"    id {k:<4} {len(pares):>4} obs -> '{etiqueta}'  ·  {causa}")
    print(f"\n  Observaciones de no-jugador dentro del campo: {total_obs}")
    print(
        f"    bien sacadas del cómputo de equipos: {bien} "
        f"({bien/max(total_obs,1):.1%})"
    )
    print(
        f"    coladas como jugador de un equipo  : {total_obs - bien} "
        f"({(total_obs-bien)/max(total_obs,1):.1%})"
    )

    # ── hoja de contactos de las fugas ────────────────────────────────
    if fugas:
        hoja_fugas(cfg["rutas"]["video"], fugas, Path(args.salida))


def hoja_fugas(ruta_video, fugas, salida, max_celdas=56):
    """Hoja de contactos de las fugas: sin verlas no se pueden clasificar."""
    salida.mkdir(parents=True, exist_ok=True)
    # Muestra repartida por el tramo, no las primeras (serían todas del
    # mismo instante y no representarían nada)
    paso = max(1, len(fugas) // max_celdas)
    muestra = fugas[::paso][:max_celdas]
    quiere = sorted({f["frame"] for f in muestra})
    cap = cv2.VideoCapture(str(ruta_video))
    frames = {}
    pos = posicionar_en_frame(cap, quiere[0])
    for objetivo in quiere:
        while pos < objetivo and cap.grab():
            pos += 1
        ok, img = cap.read()
        if ok:
            frames[objetivo] = img
            pos += 1
    cap.release()

    ALTO, COLS, PIE, CELDA = 130, 8, 58, 118
    filas_n = (len(muestra) + COLS - 1) // COLS
    hoja = np.full((filas_n * (ALTO + PIE) + 62, COLS * CELDA + 20, 3), 28, np.uint8)
    texto(
        hoja,
        "FUGAS: detecciones DENTRO del campo que no son ninguna de las "
        "14 personas y que ninguna regla saca",
        (12, 30),
        BLANCO,
        0.58,
        1,
    )
    texto(
        hoja,
        "cada celda: #frame/det, equipo que le pone el color, confianza, "
        "tamano de caja",
        (12, 50),
        (190, 190, 190),
        0.44,
        1,
    )
    for n, f in enumerate(muestra):
        r, c = divmod(n, COLS)
        x0, y0 = 10 + c * CELDA, 62 + r * (ALTO + PIE)
        img = frames.get(f["frame"])
        if img is None:
            continue
        x1, y1, x2, y2 = [max(int(v), 0) for v in f["caja"]]
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        nw = max(int(crop.shape[1] * ALTO / crop.shape[0]), 8)
        crop = cv2.resize(
            crop, (min(nw, CELDA - 14), ALTO), interpolation=cv2.INTER_NEAREST
        )
        y_fin, x_fin = y0 + ALTO, x0 + crop.shape[1]
        hoja[y0:y_fin, x0:x_fin] = crop
        cv2.rectangle(
            hoja, (x0 - 2, y0 - 2), (x0 + crop.shape[1] + 1, y0 + ALTO + 1), GRIS, 1
        )
        texto(hoja, f"{f['frame']}/{f['i']}", (x0, y0 + ALTO + 15), BLANCO, 0.38, 1)
        texto(
            hoja,
            f"{f['color']}  c={f['conf']:.2f}",
            (x0, y0 + ALTO + 31),
            (0, 200, 255),
            0.38,
            1,
        )
        texto(
            hoja,
            f"{f['ancho']:.0f}x{f['alto']:.0f}px {f['prof']:.0f}m",
            (x0, y0 + ALTO + 47),
            (180, 180, 180),
            0.36,
            1,
        )
    cv2.imwrite(str(salida / "FUGAS.png"), hoja)
    print(
        f"\n  Hoja de contactos de {len(muestra)} fugas (de {len(fugas)}) "
        f"en {salida}/FUGAS.png"
    )


if __name__ == "__main__":
    main()
