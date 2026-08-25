#!/usr/bin/env python
"""¿Acierta el clasificador de color cuando mira recortes SUELTOS?

Todas las mediciones de esta línea dicen que etiquetar POR OBSERVACIÓN
gana a votar sobre la identidad (+6,2 puntos incluso en identidades
PURAS, donde no había contaminación que arreglar). Pero eso son tablas.
Este script produce la comprobación VISUAL: 5 frames elegidos al azar
con semilla fija, todas las detecciones marcadas, y la etiqueta de cada
caja decidida ÚNICAMENTE con el color de ese recorte concreto — sin voto
por identidad, sin propagar desde otra observación, sin ventana temporal.

Qué se dibuja, por frame:

  1. `..._SIN_REGLAS.png`  — solo color. Cada caja pintada con el color
     REAL del equipo que le tocó (el que sale del prototipo aprendido) y
     encima las tres distancias a los prototipos A / B / otro, para ver
     no solo qué decidió sino CUÁNTO dudaba.
  2. `..._CON_REGLAS.png`  — encima, las reglas posicionales (área de
     portero, staff fuera del campo, catálogo arbitral). Las cajas que
     decidió una regla van con borde DISCONTINUO y una etiqueta [P]/[S]/
     [R], para que se vea de un vistazo qué señal decidió cada caja.
  3. `..._RECORTES.png`   — la hoja de contactos: el mismo recorte que
     vio el clasificador, ampliado, con su decisión y sus distancias.

⚠️ TRANSPOSICIÓN DE LAS REGLAS, que no es gratis y hay que decirlo: las
reglas del producto son POR IDENTIDAD (mediana de la identidad, mínimo
de observaciones, y en porteros exclusividad un-portero-por-área). Aquí,
por construcción del experimento, no hay identidad, así que se aplica el
criterio geométrico/cromático a la observación suelta. Consecuencia
directa y esperada: sin exclusividad, CUALQUIER detección dentro del
área sale como portero. Es exactamente lo que la auditoría pendiente de
las reglas del F7 quiere ver de cerca, así que se cuenta aparte.

El casado con el GT se hace en PÍXELES (pie de la caja GT contra pie de
la detección, tolerancia 0,5 × alto de caja, casado uno-a-uno por
cercanía), no en metros: así el número que sale es el mismo que se puede
verificar mirando la imagen, y no arrastra el error de la homografía.
La tolerancia sale de la distribución real (p50 5,8 px, p90 27,3 px
sobre 814 cajas), no de un número que suene razonable.

⚠️ El GT del benjamín tiene a las 14 PERSONAS del partido (12 jugadores
de campo + 2 porteros) y NO tiene árbitro ni banquillos. Las detecciones
que no casan con ninguna de las 14 no se pueden juzgar: se cuentan
aparte como "sin GT", no como aciertos ni como fallos.

Uso:
    python scripts/mirar_recortes_sueltos.py
    python scripts/mirar_recortes_sueltos.py --semilla 7 --n-frames 5
"""

import argparse
import logging
import pickle
import random
import sys
import warnings
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from src.evaluation.gt_parser import parsear_cvat  # noqa: E402
from src.team_classification.arbitro import (  # noqa: E402
    arquetipos_activos,
    tono_dominante,
)
from src.team_classification.color_classifier import (  # noqa: E402
    _solo_hs,
    color_dominante,
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
    _en_area,
    deducir_lados,
)
from src.team_classification.staff import (  # noqa: E402
    ReglaStaff,
    _distancia_fuera,
)
from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa: E402
from src.tracking.perfiles import correr_perfil  # noqa: E402
from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("recortes")

ESCALA = 2  # el vídeo es 1920x1080 y los jugadores miden 15-40 px
GRIS = (150, 150, 150)
BLANCO = (255, 255, 255)
NEGRO = (0, 0, 0)
AMARILLO = (0, 220, 255)
# Tolerancia del casado GT↔detección, en fracción del alto de la caja.
FRAC_TOLERANCIA = 0.5


# ───────────────────────── dibujo ──────────────────────────────────────


def rect_discontinuo(img, p1, p2, color, grosor=2, guion=8):
    """Rectángulo de línea discontinua (marca 'lo decidió una regla')."""
    x1, y1 = p1
    x2, y2 = p2
    for x in range(x1, x2, guion * 2):
        cv2.line(img, (x, y1), (min(x + guion, x2), y1), color, grosor)
        cv2.line(img, (x, y2), (min(x + guion, x2), y2), color, grosor)
    for y in range(y1, y2, guion * 2):
        cv2.line(img, (x1, y), (x1, min(y + guion, y2)), color, grosor)
        cv2.line(img, (x2, y), (x2, min(y + guion, y2)), color, grosor)


_ASCII = str.maketrans(
    {
        "—": "-",
        "–": "-",
        "·": "|",
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
        "¿": "",
        "¡": "",
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "⚠": "!",
        "→": "->",
        "º": "o",
    }
)


def texto(img, s, org, color=BLANCO, escala=0.42, grosor=1):
    """Texto con contorno negro, legible sobre césped y sobre camiseta.

    cv2.putText solo sabe pintar ASCII: cualquier acento o guion largo
    sale como '???' en la imagen. Se translitera aquí y no en cada
    llamada, que es donde se olvida.
    """
    s = str(s).translate(_ASCII)
    cv2.putText(
        img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, NEGRO, grosor + 2, cv2.LINE_AA
    )
    cv2.putText(
        img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, color, grosor, cv2.LINE_AA
    )


def _solapa(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def colocar(ocupados, x, y, ancho, alto):
    """Sube la etiqueta hasta que no pise a otra ya colocada."""
    for _ in range(14):
        caja = (x, y - alto, x + ancho, y)
        if not any(_solapa(caja, o) for o in ocupados):
            ocupados.append(caja)
            return y
        y -= alto + 2
    ocupados.append((x, y - alto, x + ancho, y))
    return y


def _regla_staff(cfg_eq: dict, modelo) -> ReglaStaff:
    """ReglaStaff construida DESDE EL CONFIG, con todas sus claves.

    Enumerar claves a mano (`tolerancia_m=..., min_observaciones=...`)
    parece inofensivo y no lo es: cuando la regla gana un parámetro nuevo,
    el banco se queda midiendo el sistema VIEJO **sin fallar**, que es la
    peor forma de romperse. Pasó con la rama de "fuera de la línea y
    lento".
    """
    opciones = {k: v for k, v in cfg_eq.get("staff", {}).items() if k != "activo"}
    opciones.setdefault("largo", modelo.largo)
    opciones.setdefault("ancho", modelo.ancho)
    return ReglaStaff.desde_dict(opciones)


# ────────────────── reglas transpuestas a la observación ───────────────


def regla_de_la_observacion(mx, my, feat, regla_p, regla_s, activos):
    """Qué regla posicional (si alguna) decide esta detección suelta.

    ⚠️ Las reglas se aplican EN CASCADA, cada una SOBRESCRIBIENDO a la
    anterior, que es exactamente lo que hace `clasificar_identidades`:
    catálogo arbitral, luego porteros, luego staff. NO es "la primera que
    casa gana". La primera versión de esta función devolvía en cuanto
    casaba el arquetipo arbitral, y eso invertía la precedencia real: el
    portero del benjamín viste azul eléctrico, cae en un arquetipo, y con
    "primera que gana" salía como árbitro en vez de como portero. Lo
    delataron dos fallos idénticos, los dos porteros_A del área cercana.
    En el producto el orden está puesto a propósito y comentado: "un
    portero con equipación llamativa cae en un arquetipo, y quien manda
    sobre él es su POSICIÓN, no su color".

    Returns:
        (etiqueta, marca) o (None, None) si no manda ninguna regla.
    """
    etiqueta, marca = None, None
    # 1. Catálogo arbitral, sobre el color de ESTE recorte
    tono = tono_dominante(feat)
    if tono is not None:
        brillo = brillo_medio(np.asarray(feat))
        for arq in activos:
            if arq.contiene(tono[0], tono[1], brillo):
                etiqueta, marca = "otro", f"R:{arq.nombre[:4]}"
                break
    # 2. Área de portería (SIN exclusividad: aquí no hay identidad, así
    #    que CUALQUIER detección dentro del área sale portero — es justo
    #    lo que la auditoría de las reglas del F7 quiere mirar de cerca)
    lado = _en_area(mx, my, regla_p)
    if lado is not None:
        equipo = regla_p.equipo_mx_bajo if lado == "bajo" else regla_p.equipo_mx_alto
        etiqueta, marca = f"portero_{equipo}", "P"
    # 3. Staff: fuera del rectángulo del campo (la última palabra)
    fuera = _distancia_fuera(mx, my, regla_s.largo, regla_s.ancho)
    if fuera > regla_s.tolerancia_m:
        etiqueta, marca = "staff", f"S:{fuera:.0f}m"
    return etiqueta, marca


# ──────────────────────────── main ─────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/processor_benja_v4_ajustado.yaml")
    p.add_argument("--gt", default="data/annotations/gt_benja/annotations.xml")
    p.add_argument("--salida", default="outputs/recortes_sueltos")
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--n-frames", type=int, default=5)
    p.add_argument(
        "--sin-control",
        dest="control",
        action="store_false",
        help="salta los controles sobre los 60 frames del GT",
    )
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    cfg = yaml.safe_load(open(args.config))
    cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
    cfg_eq = cargar_config_equipos(cfg["config_equipos"])
    datos = cargar_cache(cfg["rutas"]["cache"])
    with open(cfg["rutas"]["cache_colores"], "rb") as f:
        colores = pickle.load(f)
    conf = float(cfg_tr.get("confianza_min", 0) or 0)
    cache, colores = filtrar_por_confianza(datos["cache"], colores, conf)

    # El clasificador se entrena EXACTAMENTE igual que en producción
    clf = entrenar_clasificador(colores, cfg_eq, cache)
    proto_a, proto_b = clf._prototipos.a, clf._prototipos.b
    proto_o = clf._prototipos.otro
    sep_ab = float(np.linalg.norm(proto_a - proto_b))
    col_eq = {}
    for et, proto in (("A", proto_a), ("B", proto_b)):
        r, g, b = color_dominante(proto, clf.params)
        col_eq[et] = (b, g, r)  # BGR para cv2
    col_eq["otro"] = GRIS
    col_eq["staff"] = (200, 120, 255)
    print(
        f"\nColores REALES de equipo aprendidos: A=BGR{col_eq['A']}  "
        f"B=BGR{col_eq['B']}  ·  separación d(A,B) = {sep_ab:.3f}"
    )
    # Dato que cambia cómo se leen las imágenes: si el fit NO produjo un
    # tercer meta-grupo, el prototipo 'otro' no existe y el color no puede
    # decir "otro" NUNCA — todo recorte cae forzosamente en A o en B.
    if proto_o is None:
        print(
            "⚠️  El fit NO produjo prototipo 'otro': el color solo puede "
            "elegir entre A y B (no hay tercer cajón donde caer)."
        )
    else:
        print(
            f"   Prototipo 'otro' presente (d a A {np.linalg.norm(proto_o-proto_a):.2f}, "
            f"a B {np.linalg.norm(proto_o-proto_b):.2f})."
        )

    modelo, profundidad = _profundidad_configurada(cfg_eq)

    # ── Lados de portería: es la ÚNICA cosa que no se puede decidir por
    # observación (qué equipo defiende cada portería es una propiedad del
    # tramo). Se deduce igual que en producción, con las identidades.
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
    provisional = ReglaPorteros.desde_modelo(modelo, margen=margen)
    solo_color = {k: v for k, v in eq_ident.items() if v in ("A", "B")}
    lados = deducir_lados(
        solo_color, ids, modelo.largo, regla=provisional, ancho=modelo.ancho
    )
    bajo, alto = lados if lados else (cfg_p["equipo_mx_bajo"], cfg_p["equipo_mx_alto"])
    regla_p = ReglaPorteros.desde_modelo(
        modelo, margen=margen, equipo_mx_bajo=bajo, equipo_mx_alto=alto
    )
    # ⚠️ Del CONFIG, no a mano. Construir ReglaStaff enumerando claves
    # deja fuera las que se añadan después —pasó con la rama de "fuera de
    # la línea y lento"— y entonces el banco mide un sistema que ya no es
    # el que corre en producción, sin fallar.
    regla_s = _regla_staff(cfg_eq, modelo)
    activos = arquetipos_activos([proto_a, proto_b])
    print(
        f"Campo {modelo.largo:.1f} x {modelo.ancho:.1f} m · "
        f"área bajo mx {regla_p.area_mx_bajo} · alto mx {regla_p.area_mx_alto} "
        f"· my {regla_p.area_my}"
    )
    print(
        f"Lados deducidos: {bajo} defiende x=0 (cámara), {alto} defiende x={modelo.largo:.0f}"
    )
    print(f"Arquetipos arbitrales activos: {[a.nombre for a in activos] or 'ninguno'}")
    print(f"Staff: fuera del rectángulo por más de {regla_s.tolerancia_m:.1f} m")

    # ── GT en píxeles ─────────────────────────────────────────────────
    tracks = parsear_cvat(args.gt)
    gt_frames: dict[int, list] = {}
    for t in tracks:
        for c in t.cajas:
            g = 9750 + 15 * c.frame_local
            gt_frames.setdefault(g, []).append(
                {
                    "id": t.track_id,
                    "pie": ((c.xtl + c.xbr) / 2.0, c.ybr),
                    "team": (c.team or t.team or "?"),
                    "caja": (c.xtl, c.ytl, c.xbr, c.ybr),
                }
            )

    por_frame = {e["frame_idx"]: e for e in cache}
    comunes = sorted(set(por_frame) & set(gt_frames))
    print(
        f"\nFrames con caché Y ground truth: {len(comunes)} "
        f"(de {comunes[0]} a {comunes[-1]})"
    )

    elegidos = sorted(random.Random(args.semilla).sample(comunes, args.n_frames))
    print(f"Frames elegidos al azar (semilla {args.semilla}): {elegidos}")

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(cfg["rutas"]["video"])
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir {cfg['rutas']['video']}")
    # ⚠️ `cap.set(POS_FRAMES, n)` NO vale: pedir el 9855 dejaba el vídeo en
    # el 10186 (331 frames, 11 s de desfase) y los recortes salían de
    # CÉSPED con la etiqueta de un jugador. Es la misma trampa que ya
    # documenta `posicionar_en_frame` en el procesador —cajas correctas
    # sobre el fotograma equivocado, sin romper nada— y por eso se usa esa
    # función y luego se avanza decodificando, sin volver a saltar.
    frames = {}
    pos = posicionar_en_frame(cap, elegidos[0])
    for objetivo in elegidos:
        while pos < objetivo:
            if not cap.grab():
                break
            pos += 1
        ok, img = cap.read()
        if not ok:
            print(f"  ⚠️ no se pudo leer el frame {objetivo}")
            continue
        frames[objetivo] = img
        pos += 1
    cap.release()

    # Contadores globales
    cnt = {
        "color_ok": 0,
        "color_mal": 0,
        "regla_ok": 0,
        "regla_mal": 0,
        "sin_gt_color": 0,
        "sin_gt_regla": 0,
        "gt_sin_det": 0,
        "total_det": 0,
    }
    cnt_sin_reglas = {"ok": 0, "mal": 0}
    cnt_forzado = {"ok": 0, "mal": 0}
    fallos = []
    detalle_reglas = {"P": [0, 0], "S": [0, 0], "R": [0, 0]}
    singt_por_regla = {"P": 0, "S": 0, "R": 0, "—": 0}

    for frame_idx in elegidos:
        frame = frames.get(frame_idx)
        if frame is None:
            continue
        entrada = por_frame[frame_idx]
        dets = entrada["dets"]

        # ── decisión por recorte suelto ───────────────────────────────
        filas = []
        for i, det in enumerate(dets):
            mx, my, x1, y1, x2, y2, conf_d = det
            feat = colores.get((frame_idx, i))
            if feat is None:
                filas.append(None)
                continue
            v = _solo_hs(feat)
            d_a = float(np.linalg.norm(v - proto_a))
            d_b = float(np.linalg.norm(v - proto_b))
            d_o = float(np.linalg.norm(v - proto_o)) if proto_o is not None else np.nan
            solo_color_et = clf.predict_color(feat)
            forzado = clf.predict_color(feat, solo_equipos=True)
            et_regla, marca = regla_de_la_observacion(
                mx, my, feat, regla_p, regla_s, activos
            )
            filas.append(
                {
                    "i": i,
                    "caja": (x1, y1, x2, y2),
                    "conf": conf_d,
                    "pos": (mx, my),
                    "d": (d_a, d_b, d_o),
                    "color": solo_color_et,
                    "forzado": forzado,
                    "regla": et_regla,
                    "marca": marca,
                    "final": et_regla if et_regla else solo_color_et,
                    "quien": "regla" if et_regla else "color",
                }
            )

        # ── casado con el GT, en píxeles, uno a uno por cercanía ──────
        obs_gt = gt_frames[frame_idx]
        pares = []
        for k, o in enumerate(obs_gt):
            for f in filas:
                if f is None:
                    continue
                x1, y1, x2, y2 = f["caja"]
                pie = ((x1 + x2) / 2.0, y2)
                dd = float(np.hypot(pie[0] - o["pie"][0], pie[1] - o["pie"][1]))
                if dd <= FRAC_TOLERANCIA * (y2 - y1):
                    pares.append((dd, k, f["i"]))
        pares.sort()
        usados_gt, usados_det = set(), set()
        casado = {}
        for dd, k, i in pares:
            if k in usados_gt or i in usados_det:
                continue
            usados_gt.add(k)
            usados_det.add(i)
            casado[i] = obs_gt[k]

        # ── contar ────────────────────────────────────────────────────
        n_ok = n_mal = n_singt = 0
        for f in filas:
            if f is None:
                continue
            cnt["total_det"] += 1
            g = casado.get(f["i"])
            if g is None:
                n_singt += 1
                cnt["sin_gt_color" if f["quien"] == "color" else "sin_gt_regla"] += 1
                singt_por_regla[f["marca"][0] if f["marca"] else "—"] += 1
                continue
            real = g["team"].replace("portero_", "")
            acierto = f["final"].replace("portero_", "") == real
            n_ok += acierto
            n_mal += not acierto
            clave = "regla" if f["quien"] == "regla" else "color"
            cnt[f"{clave}_{'ok' if acierto else 'mal'}"] += 1
            if f["quien"] == "regla":
                tipo = f["marca"][0]
                detalle_reglas[tipo][0] += acierto
                detalle_reglas[tipo][1] += 1
            # controles: solo color, y color forzado a A/B
            ok_sc = f["color"].replace("portero_", "") == real
            cnt_sin_reglas["ok" if ok_sc else "mal"] += 1
            ok_fz = f["forzado"] == real
            cnt_forzado["ok" if ok_fz else "mal"] += 1
            if not acierto:
                fallos.append(
                    {
                        "frame": frame_idx,
                        "i": f["i"],
                        "gt": g["team"],
                        "dio": f["final"],
                        "quien": f["quien"],
                        "marca": f["marca"],
                        "d": f["d"],
                        "pos": f["pos"],
                    }
                )
        cnt["gt_sin_det"] += len(obs_gt) - len(usados_gt)
        print(
            f"\n  frame {frame_idx}: {len(dets)} detecciones · "
            f"{len(obs_gt)} personas en el GT · {len(usados_gt)} casadas · "
            f"{n_ok} bien / {n_mal} mal / {n_singt} sin GT"
        )

        # ── imágenes ──────────────────────────────────────────────────
        for con_reglas in (False, True):
            lienzo = cv2.resize(
                frame, None, fx=ESCALA, fy=ESCALA, interpolation=cv2.INTER_CUBIC
            )
            ocupados = []
            for f in sorted(
                [x for x in filas if x], key=lambda z: z["caja"][3], reverse=True
            ):
                x1, y1, x2, y2 = [int(v * ESCALA) for v in f["caja"]]
                et = f["final"] if con_reglas else f["color"]
                por_regla = con_reglas and f["quien"] == "regla"
                base = et.replace("portero_", "")
                color = col_eq.get(base if base in col_eq else et, GRIS)
                if por_regla:
                    rect_discontinuo(lienzo, (x1, y1), (x2, y2), color, 2)
                    cv2.rectangle(
                        lienzo, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), AMARILLO, 1
                    )
                else:
                    cv2.rectangle(lienzo, (x1, y1), (x2, y2), color, 2)
                d_a, d_b, d_o = f["d"]
                etiqueta = et if not por_regla else f"{et} [{f['marca']}]"
                nums = (
                    f"{d_a:.2f}|{d_b:.2f}"
                    if np.isnan(d_o)
                    else f"{d_a:.2f}|{d_b:.2f}|{d_o:.2f}"
                )
                anchura = int(9 * max(len(etiqueta), len(nums)))
                yy = colocar(ocupados, x1, y1 - 4, anchura, 34)
                texto(lienzo, etiqueta, (x1, yy - 18), color, 0.46, 1)
                texto(lienzo, nums, (x1, yy - 3), BLANCO, 0.36, 1)
                g = casado.get(f["i"])
                if g is not None:
                    real = g["team"].replace("portero_", "")
                    bien = et.replace("portero_", "") == real
                    cv2.circle(
                        lienzo,
                        (int(g["pie"][0] * ESCALA), int(g["pie"][1] * ESCALA)),
                        5,
                        (0, 200, 0) if bien else (0, 0, 255),
                        -1,
                    )
                    if not bien:
                        texto(lienzo, f"GT:{real}", (x2 + 4, y2), (0, 0, 255), 0.46, 1)
            cab = (
                f"frame {frame_idx}  |  SIN REGLAS: solo el color de cada recorte"
                if not con_reglas
                else f"frame {frame_idx}  |  CON REGLAS posicionales "
                f"(borde discontinuo + [P]ortero / [S]taff / a[R]bitro)"
            )
            cv2.rectangle(lienzo, (0, 0), (lienzo.shape[1], 92), NEGRO, -1)
            texto(lienzo, cab, (14, 34), BLANCO, 0.72, 2)
            texto(
                lienzo,
                "numeros = distancia a los prototipos  A|B|otro   "
                f"(d(A,B) = {sep_ab:.2f})    punto verde/rojo = acierto/fallo "
                "segun el GT (14 personas; el arbitro NO esta en el GT)",
                (14, 70),
                (200, 200, 200),
                0.55,
                1,
            )
            nombre = f"f{frame_idx}_{'CON' if con_reglas else 'SIN'}_REGLAS.png"
            cv2.imwrite(str(salida / nombre), lienzo)

        # ── hoja de contactos ─────────────────────────────────────────
        hoja_recortes(frame, filas, casado, salida, frame_idx, col_eq)

    # ── el número ─────────────────────────────────────────────────────
    tot_ok = cnt["color_ok"] + cnt["regla_ok"]
    tot_mal = cnt["color_mal"] + cnt["regla_mal"]
    tot = tot_ok + tot_mal
    print("\n" + "=" * 74)
    print(f"EL NÚMERO — {args.n_frames} frames al azar (semilla {args.semilla})")
    print("=" * 74)
    print(f"  detecciones totales en los {args.n_frames} frames : {cnt['total_det']}")
    print(f"  casadas con una persona del GT            : {tot}")
    print(
        f"  sin GT (árbitro, banquillo, público, FP)  : "
        f"{cnt['sin_gt_color'] + cnt['sin_gt_regla']} "
        f"({cnt['sin_gt_color']} las dejó el color, "
        f"{cnt['sin_gt_regla']} las cazó una regla)"
    )
    print(f"  personas del GT que el detector no vio    : {cnt['gt_sin_det']}")
    nombres_regla = {
        "P": "área de portero",
        "S": "staff (fuera del campo)",
        "R": "catálogo arbitral",
        "—": "NINGUNA: salió como jugador",
    }
    print("     de esas, quién las cazó:")
    for tipo, n in singt_por_regla.items():
        if n:
            print(f"       {nombres_regla[tipo]:<32}{n:>4}")
    print()
    cabecera = (
        f"  {'quién decidió':<26}{'bien':>7}{'mal':>7}{'total':>8}{'acierto':>10}"
    )
    print(cabecera)
    print("  " + "-" * (len(cabecera) - 2))
    for nombre, ok, mal in (
        ("EL COLOR (recorte suelto)", cnt["color_ok"], cnt["color_mal"]),
        ("UNA REGLA posicional", cnt["regla_ok"], cnt["regla_mal"]),
    ):
        n = ok + mal
        print(f"  {nombre:<26}{ok:>7}{mal:>7}{n:>8}{ok/max(n,1):>9.1%}")
    print("  " + "-" * (len(cabecera) - 2))
    print(f"  {'TOTAL':<26}{tot_ok:>7}{tot_mal:>7}{tot:>8}{tot_ok/max(tot,1):>9.1%}")
    print()
    print("  Desglose de las reglas (P=área de portero, S=staff, R=árbitro):")
    for tipo, (ok, n) in detalle_reglas.items():
        if n:
            print(f"    [{tipo}] {ok}/{n} bien  ({ok/n:.1%})")
    print()
    print("  CONTROLES sobre las mismas detecciones casadas:")
    n1 = cnt_sin_reglas["ok"] + cnt_sin_reglas["mal"]
    n2 = cnt_forzado["ok"] + cnt_forzado["mal"]
    print(
        f"    solo color (sin ninguna regla) : {cnt_sin_reglas['ok']}/{n1} "
        f"= {cnt_sin_reglas['ok']/max(n1,1):.1%}"
    )
    print(
        f"    solo color, forzado a A o B    : {cnt_forzado['ok']}/{n2} "
        f"= {cnt_forzado['ok']/max(n2,1):.1%}"
    )

    if fallos:
        print(f"\n  Los {len(fallos)} fallos, uno a uno:")
        print(
            f"    {'frame':>7}{'det':>5}  {'GT':<10}{'dio':<12}{'quién':<8}"
            f"{'dA|dB|dO':<20}{'pos (m)':<14}"
        )
        for f in fallos:
            d = "|".join(f"{x:.2f}" for x in f["d"])
            marca = f["quien"] if not f["marca"] else f"{f['quien']}"
            print(
                f"    {f['frame']:>7}{f['i']:>5}  {f['gt']:<10}{f['dio']:<12}"
                f"{marca:<8}{d:<20}({f['pos'][0]:.1f}, {f['pos'][1]:.1f})"
            )

    print(f"\n  Imágenes en {salida}/")

    if args.control:
        control(
            comunes,
            por_frame,
            gt_frames,
            colores,
            clf,
            regla_p,
            regla_s,
            activos,
            ids,
            eq_ident,
            modelo,
            profundidad,
            elegidos,
        )


def control(
    comunes,
    por_frame,
    gt_frames,
    colores,
    clf,
    regla_p,
    regla_s,
    activos,
    ids,
    eq_ident,
    modelo,
    profundidad,
    elegidos,
):
    """Los controles obligatorios: ¿es real el número, o suerte de 5 frames?

    Cuatro preguntas que hay que responder antes de creerse un 96 %:

    1. **¿Suerte del muestreo?** Se repite sobre los 60 frames del GT.
    2. **¿Qué daría no hacer nada?** Línea base de la clase mayoritaria:
       si el 60 % de las observaciones son del equipo A, decir siempre
       "A" ya acierta el 60 %. Sin esta comparación un 96 % no significa
       nada.
    3. **¿Está el acierto donde no duele?** Desglose por profundidad: si
       las que se juzgan son las cercanas y las lejanas se quedan sin
       casar, el número está inflado por construcción.
    4. **La comparación que importa**: sobre EXACTAMENTE las mismas
       detecciones, ¿qué acierta el sistema real, que vota por identidad?
    """
    # Etiqueta que el SISTEMA REAL le da a cada detección (voto por identidad)
    et_sistema = {}
    for k, ident in enumerate(ids, start=1):
        for tr in ident:
            for par in tr.det_idxs:
                et_sistema[tuple(par)] = str(eq_ident.get(k, "otro"))

    franjas = [
        ("<20 m", 0, 20),
        ("20-30 m", 20, 30),
        ("30-40 m", 30, 40),
        (">40 m", 40, 1e9),
    ]
    acc = {"color": [0, 0], "regla": [0, 0], "solo_color": [0, 0], "sistema": [0, 0]}
    # Desglose por TIPO de regla y, para cada una, qué habría dicho el
    # color en las mismas cajas: sin ese contraste no se sabe si la regla
    # aporta o estorba.
    por_regla = {"P": [0, 0, 0], "S": [0, 0, 0], "R": [0, 0, 0]}
    singt_regla = {"P": 0, "S": 0, "R": 0, "—": 0}
    por_franja = {n: {"obs": [0, 0], "sist": [0, 0]} for n, _a, _b in franjas}
    clases = {"A": 0, "B": 0}
    n_det = n_singt = n_sindet = 0

    for frame_idx in comunes:
        entrada = por_frame[frame_idx]
        obs_gt = gt_frames[frame_idx]
        filas = []
        for i, det in enumerate(entrada["dets"]):
            mx, my, x1, y1, x2, y2, _c = det
            feat = colores.get((frame_idx, i))
            if feat is None:
                continue
            sc = clf.predict_color(feat)
            et_r, marca = regla_de_la_observacion(
                mx, my, feat, regla_p, regla_s, activos
            )
            filas.append(
                {
                    "i": i,
                    "caja": (x1, y1, x2, y2),
                    "color": sc,
                    "final": et_r or sc,
                    "quien": "regla" if et_r else "color",
                    "marca": marca,
                    "prof": profundidad.de((mx, my), modelo),
                }
            )
        n_det += len(filas)
        pares = []
        for k, o in enumerate(obs_gt):
            for f in filas:
                x1, y1, x2, y2 = f["caja"]
                dd = float(np.hypot((x1 + x2) / 2 - o["pie"][0], y2 - o["pie"][1]))
                if dd <= FRAC_TOLERANCIA * (y2 - y1):
                    pares.append((dd, k, f["i"]))
        pares.sort()
        ugt, udet, casado = set(), set(), {}
        for dd, k, i in pares:
            if k in ugt or i in udet:
                continue
            ugt.add(k)
            udet.add(i)
            casado[i] = obs_gt[k]
        n_sindet += len(obs_gt) - len(ugt)
        for f in filas:
            g = casado.get(f["i"])
            if g is None:
                n_singt += 1
                singt_regla[f["marca"][0] if f["marca"] else "—"] += 1
                continue
            real = g["team"].replace("portero_", "")
            clases[real] = clases.get(real, 0) + 1
            ok = f["final"].replace("portero_", "") == real
            acc[f["quien"]][0] += ok
            acc[f["quien"]][1] += 1
            ok_sc = f["color"].replace("portero_", "") == real
            acc["solo_color"][0] += ok_sc
            acc["solo_color"][1] += 1
            if f["marca"]:
                t = f["marca"][0]
                por_regla[t][0] += ok
                por_regla[t][1] += 1
                por_regla[t][2] += ok_sc
            sis = et_sistema.get((frame_idx, f["i"]))
            if sis is not None:
                ok_s = sis.replace("portero_", "") == real
                acc["sistema"][0] += ok_s
                acc["sistema"][1] += 1
            for n, lo, hi in franjas:
                if lo <= f["prof"] < hi:
                    por_franja[n]["obs"][0] += ok
                    por_franja[n]["obs"][1] += 1
                    if sis is not None:
                        por_franja[n]["sist"][0] += ok_s
                        por_franja[n]["sist"][1] += 1

    print("\n" + "=" * 74)
    print("CONTROLES — los mismos 60 frames del GT, no solo los 5 sorteados")
    print("=" * 74)
    print(
        f"  detecciones {n_det} · casadas con el GT "
        f"{acc['color'][1] + acc['regla'][1]} · sin GT {n_singt} · "
        f"personas no detectadas {n_sindet}"
    )
    total_ok = acc["color"][0] + acc["regla"][0]
    total_n = acc["color"][1] + acc["regla"][1]
    mayoritaria = max(clases.values()) / max(sum(clases.values()), 1)
    cab = f"  {'variante':<40}{'bien':>7}{'total':>8}{'acierto':>10}"
    print("\n" + cab)
    print("  " + "-" * (len(cab) - 2))
    print(
        f"  {'LÍNEA BASE: decir siempre la clase mayor':<40}"
        f"{'':>7}{sum(clases.values()):>8}{mayoritaria:>9.1%}"
    )
    print(
        f"  {'SISTEMA REAL (voto por identidad)':<40}"
        f"{acc['sistema'][0]:>7}{acc['sistema'][1]:>8}"
        f"{acc['sistema'][0]/max(acc['sistema'][1],1):>9.1%}"
    )
    print(
        f"  {'recorte suelto, solo color':<40}"
        f"{acc['solo_color'][0]:>7}{acc['solo_color'][1]:>8}"
        f"{acc['solo_color'][0]/max(acc['solo_color'][1],1):>9.1%}"
    )
    print(
        f"  {'recorte suelto + reglas posicionales':<40}"
        f"{total_ok:>7}{total_n:>8}{total_ok/max(total_n,1):>9.1%}"
    )
    print("  " + "-" * (len(cab) - 2))
    print(
        f"    de esas: las decidió el color {acc['color'][1]} "
        f"({acc['color'][0]/max(acc['color'][1],1):.1%} bien) · "
        f"una regla {acc['regla'][1]} "
        f"({acc['regla'][0]/max(acc['regla'][1],1):.1%} bien)"
    )
    print(f"    reparto real de clases: A {clases.get('A',0)} · B {clases.get('B',0)}")

    nombres = {
        "P": "área de portero",
        "S": "staff (fuera del campo)",
        "R": "catálogo arbitral",
    }
    print("\n  ¿Aporta o estorba cada regla? Mismas cajas, la regla contra el color:")
    cab3 = (
        f"  {'regla':<26}{'n':>5}{'acierta la regla':>19}"
        f"{'habría acertado el color':>27}"
    )
    print(cab3)
    print("  " + "-" * (len(cab3) - 2))
    for t, (ok, n, ok_c) in por_regla.items():
        if n:
            print(f"  {nombres[t]:<26}{n:>5}{ok/n:>18.1%}{ok_c/n:>26.1%}")
    print(
        f"  (además, sin casar con el GT: área {singt_regla['P']}, "
        f"staff {singt_regla['S']}, árbitro {singt_regla['R']}, "
        f"ninguna regla {singt_regla['—']})"
    )

    # ── El precio de mirar recortes sueltos: quien NO está en el GT ──
    # El catálogo arbitral compara el TONO DOMINANTE con una franja de
    # color, y ese tono se calcula sobre la media de la identidad. Sobre
    # un recorte suelto es otra cosa muy distinta, y aquí se mide cuánto.
    from src.team_classification.arbitro import tono_dominante as _tono
    from src.team_classification.feature_v2 import brillo_medio as _brillo

    print(
        "\n  ¿Qué pasa con quien NO es jugador? (el catálogo arbitral "
        "necesita la MEDIA de la identidad)"
    )
    cab4 = (
        f"  {'identidad':<12}{'obs':>6}{'la media casa':>16}"
        f"{'recortes sueltos que casan':>29}{'color del recorte':>20}"
    )
    print(cab4)
    print("  " + "-" * (len(cab4) - 2))
    for k, ident in enumerate(ids, start=1):
        pares = [par for tr in ident for par in tr.det_idxs if par in colores]
        if len(pares) < 100:
            continue
        feats = [colores[par] for par in pares]
        media = np.mean(feats, axis=0)
        tm = _tono(media)
        casa_media = [
            a.nombre for a in activos if tm and a.contiene(tm[0], tm[1], _brillo(media))
        ]
        if not casa_media:
            continue
        n_casan = 0
        for f in feats:
            t = _tono(f)
            if t and any(
                a.contiene(t[0], t[1], _brillo(np.asarray(f))) for a in activos
            ):
                n_casan += 1
        etiquetas = {}
        for f in feats:
            e = clf.predict_color(f)
            etiquetas[e] = etiquetas.get(e, 0) + 1
        dominante = max(etiquetas, key=etiquetas.get)
        print(
            f"  id {k:<9}{len(pares):>6}{casa_media[0]:>16}"
            f"{f'{n_casan}/{len(pares)} = {n_casan/len(pares):.0%}':>29}"
            f"{f'{dominante} en {etiquetas[dominante]/len(pares):.0%}':>20}"
        )

    print(
        "\n  ¿Está el acierto solo donde es fácil? Por profundidad "
        f"(eje {profundidad.eje}, cámara en x=0):"
    )
    cab2 = f"  {'franja':<12}{'n':>6}{'recorte suelto':>17}{'sistema real':>15}"
    print(cab2)
    print("  " + "-" * (len(cab2) - 2))
    for n, _lo, _hi in franjas:
        o, s_ = por_franja[n]["obs"], por_franja[n]["sist"]
        if not o[1]:
            continue
        print(
            f"  {n:<12}{o[1]:>6}{o[0]/o[1]:>16.1%}"
            f"{(s_[0]/s_[1] if s_[1] else float('nan')):>15.1%}"
        )


def hoja_recortes(frame, filas, casado, salida, frame_idx, col_eq):
    """Hoja de contactos: el recorte que vio el clasificador, ampliado."""
    validas = [f for f in filas if f]
    if not validas:
        return
    ALTO_CROP, COLS, PIE = 150, 7, 74
    celda_w = 130
    filas_n = (len(validas) + COLS - 1) // COLS
    W = COLS * celda_w + 20
    H = filas_n * (ALTO_CROP + PIE) + 70
    hoja = np.full((H, W, 3), 28, np.uint8)
    texto(
        hoja,
        f"frame {frame_idx} — el recorte que ve el clasificador, "
        f"su decision SOLO por color y sus distancias A|B|otro",
        (12, 34),
        BLANCO,
        0.6,
        1,
    )
    texto(
        hoja,
        "borde = decision por COLOR · texto [regla] = lo que la regla "
        "posicional habria dicho · GT verde/rojo",
        (12, 56),
        (190, 190, 190),
        0.45,
        1,
    )
    for n, f in enumerate(validas):
        r, c = divmod(n, COLS)
        x0 = 10 + c * celda_w
        y0 = 70 + r * (ALTO_CROP + PIE)
        x1, y1, x2, y2 = [int(v) for v in f["caja"]]
        x1, y1 = max(x1, 0), max(y1, 0)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        esc = ALTO_CROP / crop.shape[0]
        nw = max(int(crop.shape[1] * esc), 8)
        crop = cv2.resize(
            crop, (min(nw, celda_w - 16), ALTO_CROP), interpolation=cv2.INTER_NEAREST
        )
        y_fin, x_fin = y0 + ALTO_CROP, x0 + crop.shape[1]
        hoja[y0:y_fin, x0:x_fin] = crop
        base = f["color"].replace("portero_", "")
        col = col_eq.get(base, GRIS)
        cv2.rectangle(
            hoja, (x0 - 2, y0 - 2), (x0 + crop.shape[1] + 1, y0 + ALTO_CROP + 1), col, 2
        )
        d_a, d_b, d_o = f["d"]
        texto(hoja, f"#{f['i']} {f['color']}", (x0, y0 + ALTO_CROP + 16), col, 0.44, 1)
        nums = (
            f"{d_a:.2f}|{d_b:.2f}"
            if np.isnan(d_o)
            else f"{d_a:.2f}|{d_b:.2f}|{d_o:.2f}"
        )
        texto(hoja, nums, (x0, y0 + ALTO_CROP + 32), BLANCO, 0.36, 1)
        if f["regla"]:
            texto(
                hoja,
                f"[{f['marca']}]->{f['regla']}",
                (x0, y0 + ALTO_CROP + 48),
                AMARILLO,
                0.36,
                1,
            )
        g = casado.get(f["i"])
        if g is None:
            texto(hoja, "GT: —", (x0, y0 + ALTO_CROP + 64), (140, 140, 140), 0.38, 1)
        else:
            real = g["team"].replace("portero_", "")
            bien = f["final"].replace("portero_", "") == real
            texto(
                hoja,
                f"GT: {g['team']} {'OK' if bien else 'MAL'}",
                (x0, y0 + ALTO_CROP + 64),
                (0, 220, 0) if bien else (0, 80, 255),
                0.38,
                1,
            )
    cv2.imwrite(str(salida / f"f{frame_idx}_RECORTES.png"), hoja)


if __name__ == "__main__":
    main()
