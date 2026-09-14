#!/usr/bin/env python
"""Genera el caché de BALÓN de un tramo (necesita GPU: Colab).

Independiente del de jugadores a propósito: el balón se muestrea MUCHO
más denso. Un jugador entre dos muestras se interpola sin drama —se mueve
despacio y en línea recta—, pero el balón puede recibir un toque y
cambiar de dirección entre una muestra y la siguiente, y ese contacto se
pierde para siempre. Por eso `sample_every` es propio de este modelo.

Además compara ESQUEMAS de detección (`--comparar-sahi`) donde tienen que
ganar: en los huecos de balón del FONDO del campo, no en los primeros
frames del tramo. Medido, el frame entero con imgsz 1280 cierra 0 de 47
huecos del fondo y SAHI 3x5 los cierra los 47 — el balón de allí entra en
la red a 7,0 px y el detector nunca ha encontrado uno de menos de 7,1
(`docs/sahi_balon.md`).

⚠️ El "~10x de inferencia" que decía aquí antes era una suposición, no una
medida. El comparador da el coste real y proyecta la pasada entera.

Uso (Colab):
    python scripts/detectar_balon.py --config configs/processor_benja_balon.yaml
    python scripts/detectar_balon.py --config ... --comparar-sahi
    python scripts/detectar_balon.py --config ... --comparar-sahi \
        --esquemas "frame entero" "MIXTO franja"
"""

import argparse
import logging
import os
import pickle
import tempfile
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.balon.franja_lejana import banda_a_trocear  # noqa: E402
from src.tracking_data.processor import (  # noqa: E402
    _build_camera_matrix,
    _rango_de_frames,
    posicionar_en_frame,
    project_point,
)

logger = logging.getLogger("balon")


def iter_frames(cap, frame_ini, frame_fin, sample, total=0):
    """Genera (frame_idx, frame) del tramo, con posicionamiento VERIFICADO.

    El salto se comprueba LEYENDO, no preguntando. `cap.set` puede
    informar de que aterrizó donde se le pidió y dejar el lector
    inservible: entonces el primer `read()` devuelve False, el bucle sale
    a la primera y el script acaba procesando 0 frames sin decir por qué.
    Es lo que pasó en Colab con este mismo vídeo, que en local se lee sin
    problema — o sea, el fallo depende del build de OpenCV.

    Por eso, si el primer fotograma no llega, se rebobina y se avanza
    decodificando (`grab()` es barato). Cuesta unos segundos y elimina
    toda una familia de fallos que dependen del entorno.
    """
    posicionar_en_frame(cap, frame_ini)
    ok, frame = cap.read()
    if not ok:
        logger.warning(
            "El salto al frame %d dejó el vídeo ilegible (read() falló pese a "
            "que el seek se dio por bueno): se rebobina y se decodifica.",
            frame_ini,
        )
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        pos = 0
        while pos < frame_ini and cap.grab():
            pos += 1
        ok, frame = cap.read()
        if not ok:
            raise SystemExit(
                f"\nERROR: no se puede leer el frame {frame_ini} ni saltando "
                f"ni decodificando desde el principio.\n"
                f"  El vídeo declara {total} frames. Si el tramo cae dentro, "
                f"el archivo puede estar truncado o mal copiado a Drive."
            )

    frame_idx = frame_ini
    while True:
        if frame_fin is not None and frame_idx >= frame_fin:
            return
        if frame_idx % sample == 0:
            yield frame_idx, frame
        frame_idx += 1
        ok, frame = cap.read()
        if not ok:
            return


def _detectar_frame_entero(modelo, frame, conf, imgsz):
    r = modelo.predict(frame, conf=conf, imgsz=imgsz, verbose=False)[0]
    return [(*map(float, b.xyxy[0].tolist()), float(b.conf[0])) for b in r.boxes]


def _detectar_sahi(modelo_sahi, frame, cfg_sahi, w, h):
    from sahi.predict import get_sliced_prediction

    r = get_sliced_prediction(
        frame,
        modelo_sahi,
        slice_height=h // cfg_sahi["filas"],
        slice_width=w // cfg_sahi["columnas"],
        overlap_height_ratio=cfg_sahi["solape"],
        overlap_width_ratio=cfg_sahi["solape"],
        verbose=0,
    )
    return [
        (p.bbox.minx, p.bbox.miny, p.bbox.maxx, p.bbox.maxy, p.score.value)
        for p in r.object_prediction_list
    ]


def _volcar(ruta, objeto) -> None:
    """Escribe el caché de forma ATÓMICA (temporal único + rename).

    Con un `.tmp` de nombre fijo dos procesos abrirían el mismo fichero e
    intercalarían bytes (medido en el procesador de jugadores: 1 de cada
    12 intentos con 4 procesos). Y si el volcado falla, el caché bueno
    anterior sigue en su sitio.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp = tempfile.mkstemp(dir=str(ruta.parent), suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as f:
            pickle.dump(objeto, f)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _reanudar_balon(ruta, firma):
    """Recupera un checkpoint compatible, o None."""
    ruta = Path(ruta)
    if not ruta.exists():
        return None
    try:
        with open(ruta, "rb") as f:
            previo = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError) as err:
        logger.warning("No se pudo leer el caché de balón previo (%s); se rehace.", err)
        return None
    if previo.get("firma") != firma:
        logger.warning(
            "Hay un caché de balón hecho con OTRA configuración: se SOBRESCRIBE."
        )
        return None
    if previo.get("completo") or not previo.get("cache"):
        return None
    return previo["cache"]


def _modelo_campo(cfg):
    """Modelo de campo para el filtro de plausibilidad.

    Aquí solo se usan largo y ancho —el filtro comprueba que el balón
    proyecte DENTRO del campo—, así que las marcas del reglamento dan
    igual; la base se elige por el tamaño.
    """
    from src.campo_modelo import MODELO_F7, MODELO_F11

    largo = float(cfg["campo_m"]["largo"])
    ancho = float(cfg["campo_m"]["ancho"])
    base = MODELO_F11 if largo > 80 else MODELO_F7
    return base.con_dimensiones(largo, ancho)


def _huecos_del_fondo(datos, modelo, zona_min, dt_min=1.0, dt_max=8.0):
    """Huecos de balón en el FONDO del campo: donde SAHI tiene que ganar.

    Un hueco es un par de muestras consecutivas CON balón separadas por
    más de `dt_min` segundos. Se filtra por zona porque está medido que
    los dos extremos del campo fallan por motivos DISTINTOS
    (`docs/huecos_de_balon_gt.md`): cerca el balón se sale del plano —75 %
    de esos huecos empiezan a menos de 30 px del borde, y eso SAHI no lo
    arregla—, mientras que en el fondo **0 de 47 tocan el borde**: el
    balón está en la imagen y el detector no llega. Medir SAHI sobre los
    huecos de cerca lo condenaría por un fallo que no es suyo.
    """
    from src.balon.tracking_balon import filtrar_balon_plausible

    dets = filtrar_balon_plausible(
        {e["frame_idx"]: e["dets"] for e in datos["cache"] if e["dets"]}, modelo
    )
    tiempos = {e["frame_idx"]: e["t"] for e in datos["cache"]}
    vistos = sorted(dets)
    huecos = []
    for a, b in zip(vistos, vistos[1:]):
        if dt_min < tiempos[b] - tiempos[a] < dt_max and dets[a][0][0] >= zona_min:
            huecos.append((a, b))
    return huecos, dets


def _plausibles(crudas, conf_min, homografia, modelo, idx):
    """Detecciones que pasan la confianza Y proyectan dentro del campo."""
    from src.balon.tracking_balon import filtrar_balon_plausible

    dets = []
    for x1, y1, x2, y2, conf in crudas:
        if conf < conf_min:
            continue
        mx, my = project_point((x1 + x2) / 2.0, y2, homografia)
        dets.append((mx, my, x1, y1, x2, y2, conf))
    if not dets:
        return []
    return filtrar_balon_plausible({idx: dets}, modelo).get(idx, [])


def _esquema_de_config(cb):
    """El esquema de detección que pide el config, validado.

    ⚠️ UN SOLO INTERRUPTOR. Antes esto lo decidía `balon.sahi.activo`, y
    dejar los dos conviviendo sería repetir el fallo canónico del
    proyecto: `cota_plantilla.activa` llevaba semanas sin que nadie la
    leyera, dando una falsa sensación de control. Así que `sahi.activo`
    ya no existe y un config que todavía lo traiga PARA el script en vez
    de ignorarlo en silencio.
    """
    if "activo" in cb.get("sahi", {}):
        raise SystemExit(
            "\nERROR: `balon.sahi.activo` ya no se usa y se estaba "
            "ignorando.\n"
            "  Ponlo como `balon.esquema`, que es el único interruptor:\n"
            "    esquema: mixto    # adoptado: frame entero + tiles en la franja\n"
            "    esquema: sahi     # trocear la imagen ENTERA (pierde detecciones\n"
            "                      # buenas por el postproceso IOS, ver docs/)\n"
            "    esquema: entero   # solo frame entero (cierra 0 de 47 huecos)"
        )
    nombre = cb.get("esquema", "entero")
    esquemas = {
        "entero": {"modo": "entero"},
        "sahi": {
            "modo": "sahi",
            "filas": cb.get("sahi", {}).get("filas", 3),
            "columnas": cb.get("sahi", {}).get("columnas", 5),
            "solape": cb.get("sahi", {}).get("solape", 0.15),
        },
        "mixto": {
            "modo": "mixto",
            "columnas": cb.get("sahi", {}).get("columnas", 5),
            "solape": cb.get("sahi", {}).get("solape", 0.15),
        },
    }
    if nombre not in esquemas:
        raise SystemExit(
            f"\nERROR: balon.esquema = {nombre!r} no existe.\n"
            f"  Usa uno de: {', '.join(sorted(esquemas))}"
        )
    return nombre, esquemas[nombre]


def _centro(det):
    """Centro en píxeles de una detección (mx, my, x1, y1, x2, y2, conf)."""
    return (det[2] + det[4]) / 2.0, (det[3] + det[5]) / 2.0


# ── ESQUEMAS DE DETECCIÓN ────────────────────────────────────────────
#
# La franja del esquema mixto ya NO es un par de números fijos: la deriva
# `src.balon.franja_lejana.banda_a_trocear` de la homografía y de las
# medidas del campo, porque 540-720 solo valía para la cámara del
# benjamín y ese fallo habría sido silencioso en cualquier otro partido.
ESQUEMAS = [
    ("frame entero", {"modo": "entero"}),
    ("SAHI 3x5", {"modo": "sahi", "filas": 3, "columnas": 5, "solape": 0.15}),
    ("SAHI 2x3", {"modo": "sahi", "filas": 2, "columnas": 3, "solape": 0.15}),
    ("SAHI 4x6", {"modo": "sahi", "filas": 4, "columnas": 6, "solape": 0.15}),
    ("MIXTO franja", {"modo": "mixto", "columnas": 5, "solape": 0.15}),
]


def _solapan(a, b, umbral=0.3):
    """IoU por encima del umbral: son la misma caja."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return False
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return union > 0 and inter / union > umbral


def _detectar_con_esquema(esquema, modelo, modelo_sahi, frame, cb, w, h, banda):
    """Detecta con uno de los esquemas y devuelve cajas (x1,y1,x2,y2,conf).

    El esquema `mixto` es idea de Alex: frame entero donde el balón es
    grande y tiles SOLO donde es pequeño. Aquí la franja no es la mitad
    izquierda ni la derecha —medido, un corte VERTICAL no separa nada: el
    fondo ocupa el 60 % del ancho— sino una franja HORIZONTAL, porque con
    la cámara elevada la distancia se traduce en altura en la imagen.
    """
    modo = esquema["modo"]
    if modo == "entero":
        return _detectar_frame_entero(modelo, frame, cb["confianza"], cb["imgsz"])
    if modo == "sahi":
        cfg_s = {
            "filas": esquema["filas"],
            "columnas": esquema["columnas"],
            "solape": esquema["solape"],
        }
        return _detectar_sahi(modelo_sahi, frame, cfg_s, w, h)

    # mixto: el frame entero manda, y la franja se trocea aparte
    y0, y1 = max(0, banda[0]), min(h, banda[1])
    cajas = _detectar_frame_entero(modelo, frame, cb["confianza"], cb["imgsz"])
    franja = frame[y0:y1]
    cfg_s = {"filas": 1, "columnas": esquema["columnas"], "solape": esquema["solape"]}
    for bx1, by1, bx2, by2, conf in _detectar_sahi(
        modelo_sahi, franja, cfg_s, w, y1 - y0
    ):
        caja = (bx1, by1 + y0, bx2, by2 + y0, conf)
        # Sin esta comprobación el mismo balón contaría dos veces y el
        # recuento de candidatos por frame mentiría justo en la métrica
        # que Alex quiere vigilar.
        if not any(_solapan(caja[:4], c[:4]) for c in cajas):
            cajas.append(caja)
    return cajas


def _comparar_en_huecos(args, cfg, cb, modelo, modelo_sahi, homografia, w, h, sample):
    """Compara varios esquemas de detección DONDE tienen que ganar.

    ⚠️ POR QUÉ NO VALE LA COMPARACIÓN ORIGINAL. Cogía los N primeros
    frames del tramo en orden y comparaba DETECCIONES TOTALES. Dos fallos,
    los dos vistos por Alex: si en esos segundos el balón está cerca de la
    cámara, SAHI no puede demostrar nada porque ahí no falla nadie; y "más
    detecciones" no es la mejora, porque SAHI también inventa falsos
    positivos que empeoran la elección del balón activo.

    Lo que mide esta: **cuántos de los huecos del fondo se CIERRAN**, un
    grupo de control de frames donde el balón ya se detectaba —y CUÁLES se
    pierden, no solo cuántos, porque un recuento no deja diagnosticar— y
    el coste. El vídeo se decodifica UNA vez para todos los esquemas.
    """
    import random

    modelo_campo = _modelo_campo(cfg)
    with open(cfg["rutas"]["cache_balon"], "rb") as f:
        datos = pickle.load(f)
    huecos, dets = _huecos_del_fondo(datos, modelo_campo, args.zona_min)
    if not huecos:
        raise SystemExit(
            f"\nERROR: no hay ni un hueco de balón con x >= {args.zona_min} m en\n"
            f"  {cfg['rutas']['cache_balon']}\n"
            f"  Baja --zona-min o comprueba que el caché es el que crees."
        )

    prueba = {}
    for a, b in huecos:
        interior = list(range(a + sample, b, sample))
        if not interior:
            continue
        paso = max(len(interior) // args.por_hueco, 1)
        for f_idx in interior[::paso][: args.por_hueco]:
            prueba[f_idx] = (a, b)

    candidatos = [f for f in dets if dets[f][0][0] >= args.zona_min and f not in prueba]
    random.Random(0).shuffle(candidatos)
    control = sorted(candidatos[: args.control])

    banda = banda_a_trocear(
        homografia,
        float(cfg["campo_m"]["largo"]),
        float(cfg["campo_m"]["ancho"]),
        args.zona_min,
        h,
        w,
        cb.get("margen_campo_m", 20.0),
        cb.get("altura_aerea_m", 3.0),
    )
    esquemas = [e for e in ESQUEMAS if not args.esquemas or e[0] in args.esquemas]
    if not esquemas:
        raise SystemExit(
            f"\nERROR: ningún esquema se llama así.\n"
            f"  Hay: {', '.join(repr(n) for n, _ in ESQUEMAS)}"
        )
    objetivo = sorted(set(prueba) | set(control))
    logger.info(
        "%d huecos del fondo · %d frames en huecos + %d de control · %d esquemas",
        len(huecos),
        len(prueba),
        len(control),
        len(esquemas),
    )

    marcador = {
        nombre: {
            "cerrados": set(),
            "conservados": 0,
            "perdidos": [],
            "candidatos": 0,
            "distractores": 0,
            "desplaz": [],
            "t": 0.0,
        }
        for nombre, _ in esquemas
    }

    cap = cv2.VideoCapture(cfg["rutas"]["video"])
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sin_dist = cfg["distorsion"]["k1"] == 0 and cfg["distorsion"]["k2"] == 0
    K = _build_camera_matrix(w, h)
    dist = np.array(
        [cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], dtype=np.float64
    )

    pendientes = set(objetivo)
    idx, hechos = 0, 0
    while pendientes:
        ok, frame = cap.read()
        if not ok:
            break
        if idx in pendientes:
            pendientes.discard(idx)
            if not sin_dist:
                frame = cv2.undistort(frame, K, dist)
            for nombre, esquema in esquemas:
                m = marcador[nombre]
                t0 = time.time()
                crudas = _detectar_con_esquema(
                    esquema, modelo, modelo_sahi, frame, cb, w, h, banda
                )
                m["t"] += time.time() - t0
                plaus = _plausibles(
                    crudas, cb["confianza"], homografia, modelo_campo, idx
                )
                m["candidatos"] += len(plaus)
                if idx in prueba:
                    if plaus:
                        m["cerrados"].add(prueba[idx])
                    continue
                # Control: el balón bueno es el que ya tenía el caché.
                cx, cy = _centro(dets[idx][0])
                cerca = [
                    d
                    for d in plaus
                    if np.hypot(_centro(d)[0] - cx, _centro(d)[1] - cy) < args.radio_ok
                ]
                m["distractores"] += len(plaus) - len(cerca)
                if cerca:
                    m["conservados"] += 1
                    mx, my = _centro(cerca[0])
                    m["desplaz"].append(float(np.hypot(mx - cx, my - cy)))
                else:
                    m["perdidos"].append(idx)
            hechos += 1
            if hechos % 25 == 0:
                logger.info("  %d de %d frames", hechos, len(objetivo))
        idx += 1
    cap.release()

    if not hechos:
        raise SystemExit("\nERROR: no se procesó ningún frame; ¿es el vídeo correcto?")

    _informe_esquemas(
        marcador, esquemas, huecos, control, dets, hechos, total, cb, args
    )


def _informe_esquemas(
    marcador, esquemas, huecos, control, dets, hechos, total, cb, args
):
    """Imprime la comparación. Dice QUÉ se pierde, no solo cuánto."""
    n_h, n_c = len(huecos), len(control)
    n_pasada = max(total, 1) // cb["sample_every"]
    linea = "=" * 78
    print(f"\n{linea}")
    print(
        f"ESQUEMAS DE DETECCIÓN · {n_h} huecos del fondo (x >= {args.zona_min:.0f} m)"
    )
    print(linea)
    print(
        f"{'esquema':<15} {'huecos':>10} {'control':>10} {'distr.':>8} "
        f"{'cand/frame':>11} {'ms/frame':>9} {'pasada':>9}"
    )
    for nombre, _e in esquemas:
        m = marcador[nombre]
        ms = 1000 * m["t"] / hechos
        print(
            f"{nombre:<15} {len(m['cerrados']):>4}/{n_h:<5} "
            f"{m['conservados']:>4}/{n_c:<5} {m['distractores']:>8} "
            f"{m['candidatos'] / hechos:>11.2f} {ms:>9.0f} "
            f"{n_pasada * ms / 1000 / 60:>7.0f} m"
        )

    print("\n  huecos  = de los del fondo, cuántos cierra  ← el número que decide")
    print("  control = frames donde el balón YA se detectaba y sigue saliendo")
    print(
        f"  distr.  = candidatos plausibles a más de {args.radio_ok:.0f} px del balón"
    )
    print("            bueno, sumados sobre los frames de control: son los que")
    print("            pueden despistar al selector de balón activo")

    for nombre, _e in esquemas:
        m = marcador[nombre]
        if not m["perdidos"]:
            continue
        print(f"\n  ── {nombre}: pierde {len(m['perdidos'])} del control ──")
        print(f"     {'frame':>7} {'conf':>6} {'lado px':>8} {'y px':>6} {'x_m':>6}")
        for f in m["perdidos"][:12]:
            d = dets[f][0]
            lado = max(d[4] - d[2], d[5] - d[3])
            print(
                f"     {f:>7} {d[6]:>6.2f} {lado:>8.1f} "
                f"{(d[3] + d[5]) / 2:>6.0f} {d[0]:>6.1f}"
            )
        if len(m["perdidos"]) > 12:
            print(f"     ... y {len(m['perdidos']) - 12} más")
        print(
            "     ⚠️  compara esas conf con la mediana del control: si son las\n"
            "        más flojas, no es la rejilla, es que estaban en el filo."
        )
    confs = [dets[f][0][6] for f in control]
    print(
        f"\n  confianza del control (frame entero): mediana {np.median(confs):.2f}, "
        f"p10 {np.percentile(confs, 10):.2f}, mínima {min(confs):.2f}"
    )
    print(f"\n{linea}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--comparar-sahi",
        action="store_true",
        help="Mide SAHI vs frame entero en unos frames y sale (no cachea)",
    )
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument(
        "--frames-seguidos",
        action="store_true",
        help="Comparación VIEJA: los N primeros frames del tramo. Solo sirve "
        "cuando todavía no hay caché de balón; mide donde nadie falla.",
    )
    parser.add_argument(
        "--zona-min",
        type=float,
        default=45.0,
        help="Metros desde los que un hueco cuenta como 'del fondo'",
    )
    parser.add_argument(
        "--por-hueco", type=int, default=4, help="Frames a probar dentro de cada hueco"
    )
    parser.add_argument(
        "--control", type=int, default=60, help="Frames del fondo CON balón, de control"
    )
    parser.add_argument(
        "--esquemas",
        nargs="*",
        default=None,
        help="Solo estos esquemas (por defecto, todos). Ver ESQUEMAS.",
    )
    parser.add_argument(
        "--radio-ok",
        type=float,
        default=40.0,
        help="Px hasta los que un candidato cuenta como EL balón, no un distractor",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    cb = cfg["balon"]
    H = np.load(cfg["rutas"]["homografia"])

    # Validación de rutas ANTES de cargar nada: un fallo de config debe
    # verse como tal y no después de gastar medio minuto de GPU.
    ruta_video = Path(cfg["rutas"]["video"])
    if not ruta_video.exists():
        candidatos = sorted(x.name for x in ruta_video.parent.glob("*.mp4")) or [
            "(ninguno)"
        ]
        raise SystemExit(
            f"\nERROR: no existe el vídeo {ruta_video}\n"
            f"  Lo pide {args.config} (rutas.video).\n"
            f"  En {ruta_video.parent} hay: {', '.join(candidatos)}\n"
            f"  Haz que el enlace y el config usen el MISMO nombre."
        )
    if not Path(cb["modelo"]).exists():
        raise SystemExit(f"\nERROR: no existe el modelo {cb['modelo']}")

    from ultralytics import YOLO

    modelo = YOLO(cb["modelo"])
    nombre_esquema, esquema = _esquema_de_config(cb)
    logger.info("Esquema de detección de balón: %s", nombre_esquema)
    modelo_sahi = None
    if esquema["modo"] != "entero" or args.comparar_sahi:
        from sahi import AutoDetectionModel

        modelo_sahi = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=cb["modelo"],
            confidence_threshold=cb["confianza"],
            device=cfg["deteccion"]["device"],
        )

    # Comprobaciones ANTES de tocar la GPU. Sin ellas, una ruta que no
    # existe hacía que VideoCapture fallara callando, read() devolviera
    # False a la primera y el script acabara dividiendo por cero tras
    # "Comparación sobre 0 frames" — un mensaje que no dice nada de la
    # causa real. Un fallo de configuración debe verse como tal.
    ruta_video = Path(cfg["rutas"]["video"])
    if not ruta_video.exists():
        candidatos = sorted(x.name for x in ruta_video.parent.glob("*.mp4")) or [
            "(ninguno)"
        ]
        raise SystemExit(
            f"\nERROR: no existe el vídeo {ruta_video}\n"
            f"  El config {args.config} apunta ahí (rutas.video).\n"
            f"  En {ruta_video.parent} hay: {', '.join(candidatos)}\n"
            f"  Arregla el enlace o la ruta del config para que coincidan."
        )
    cap = cv2.VideoCapture(str(ruta_video))
    if not cap.isOpened():
        raise SystemExit(
            f"\nERROR: {ruta_video} existe pero OpenCV no puede abrirlo.\n"
            f"  ¿Está completo? ¿Es un enlace roto (ls -l) o un códec no "
            f"soportado por este build de OpenCV?"
        )

    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample = cb["sample_every"]
    frame_ini, frame_fin = _rango_de_frames(cfg["muestreo"], fps)

    # ── COMPARACIÓN DE SAHI ──────────────────────────────────────────
    #
    # Por defecto se mide EN LOS HUECOS DEL FONDO, no en los primeros N
    # frames del tramo. El motivo está en `_comparar_en_huecos`: los
    # primeros frames caen donde caigan, y si el balón está cerca de la
    # cámara SAHI no puede demostrar nada porque ahí no falla nadie.
    # La vía vieja sigue disponible con --frames-seguidos, porque cuando
    # todavía NO hay caché de balón es la única posible.
    if args.comparar_sahi and not args.frames_seguidos:
        if not Path(cfg["rutas"]["cache_balon"]).exists():
            raise SystemExit(
                f"\nERROR: la comparación en huecos necesita un caché de balón "
                f"previo y no existe:\n  {cfg['rutas']['cache_balon']}\n"
                f"  Haz primero una pasada normal, o usa --frames-seguidos "
                f"(que mide donde caiga, y es lo que ya sabemos que engaña)."
            )
        cap.release()
        _comparar_en_huecos(args, cfg, cb, modelo, modelo_sahi, H, w, h, sample)
        return

    # ── CHECKPOINT Y REANUDACIÓN ─────────────────────────────────────
    #
    # Este script ya nos dio dos sustos: procesar 0 frames en silencio y
    # un "✓ Caché de balón" sobre un archivo vacío. La guarda de abajo
    # arregló el segundo, pero quedaba el peor: el `pickle.dump` está al
    # final, así que una caída de sesión en el minuto 35 de 40 lo pierde
    # todo. Sobre la parte entera son ~18.000 frames de GPU.
    #
    # Mismo diseño que `procesar_full`: volcado atómico cada N frames,
    # las detecciones (que anclan la reanudación) SIEMPRE al final, y una
    # firma que impide reanudar sobre otra configuración de detección.
    cfg_ck = cfg.get("checkpoint") or {}
    cada = int(cfg_ck.get("cada_frames", 500) or 0)
    # La franja del esquema mixto, derivada de la homografía. Se calcula
    # aunque el esquema no la use, para que entre en la firma: así un
    # cambio de banda invalida el checkpoint en vez de mezclar.
    banda_produccion = (
        banda_a_trocear(
            H,
            float(cfg["campo_m"]["largo"]),
            float(cfg["campo_m"]["ancho"]),
            float(cb.get("zona_min_m", 45.0)),
            h,
            w,
            float(cb.get("margen_campo_m", 20.0)),
            float(cb.get("altura_aerea_m", 3.0)),
        )
        if esquema["modo"] == "mixto"
        else None
    )

    firma_balon = {
        "video": str(cfg["rutas"]["video"]),
        "modelo": cb["modelo"],
        "confianza": cb["confianza"],
        "imgsz": cb["imgsz"],
        "sample_every": sample,
        "sahi": dict(cb.get("sahi") or {}),
        # Sin esto, reanudar un caché empezado con otro esquema mezclaría
        # dos detectores distintos dentro del mismo fichero, y el caché
        # resultante no sería el de ninguno de los dos.
        "esquema": nombre_esquema,
        "banda": banda_produccion,
        "k1": cfg["distorsion"]["k1"],
        "k2": cfg["distorsion"]["k2"],
        "tramo": dict(cfg["muestreo"].get("tramo") or {}),
    }
    ruta_ck = Path(cfg["rutas"]["cache_balon"])

    def _guardar(cache_actual, completo):
        _volcar(
            ruta_ck,
            {
                "cache": cache_actual,
                "fps": fps,
                "sample": sample,
                "wh": (w, h),
                "modelo": cb["modelo"],
                "confianza": cb["confianza"],
                "completo": completo,
                "firma": firma_balon,
            },
        )

    logger.info(
        "Vídeo %s: %dx%d, %.2f fps, %d frames (%.1f min). Tramo [%d, %s), "
        "1 de cada %d",
        ruta_video.name,
        w,
        h,
        fps,
        total,
        total / fps / 60 if fps else 0,
        frame_ini,
        frame_fin if frame_fin is not None else "fin",
        sample,
    )
    if total > 0 and frame_ini >= total:
        raise SystemExit(
            f"\nERROR: el tramo empieza en el frame {frame_ini} "
            f"({frame_ini / fps / 60:.1f} min) y el vídeo solo tiene {total} "
            f"({total / fps / 60:.1f} min).\n"
            f"  Revisa muestreo.tramo en {args.config}."
        )
    posicionar_en_frame(cap, frame_ini)

    K = _build_camera_matrix(w, h)
    dist = np.array(
        [cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], dtype=np.float64
    )
    sin_dist = cfg["distorsion"]["k1"] == 0 and cfg["distorsion"]["k2"] == 0

    cache, n_con = [], 0
    if cada and not args.comparar_sahi and cfg_ck.get("reanudar", True):
        previo = _reanudar_balon(ruta_ck, firma_balon)
        if previo:
            cache = previo
            n_con = sum(1 for e in cache if e["dets"])
            frame_ini = cache[-1]["frame_idx"] + 1
            logger.info(
                "REANUDANDO el balón: %d frames ya cacheados, se sigue desde "
                "el %d (t=%.1f s)",
                len(cache),
                frame_ini,
                frame_ini / fps,
            )
    t_entero = t_sahi = 0.0
    n_entero = n_sahi = 0
    hechos = 0
    for frame_idx, frame in iter_frames(cap, frame_ini, frame_fin, sample, total):
        if args.comparar_sahi and len(cache) >= args.frames:
            break
        if not sin_dist:
            frame = cv2.undistort(frame, K, dist)

        if args.comparar_sahi:
            t0 = time.time()
            d1 = _detectar_frame_entero(modelo, frame, cb["confianza"], cb["imgsz"])
            t_entero += time.time() - t0
            n_entero += len(d1)
            t0 = time.time()
            d2 = _detectar_sahi(modelo_sahi, frame, cb["sahi"], w, h)
            t_sahi += time.time() - t0
            n_sahi += len(d2)
            cache.append(1)
            continue

        crudas = _detectar_con_esquema(
            esquema, modelo, modelo_sahi, frame, cb, w, h, banda_produccion
        )

        dets = []
        for x1, y1, x2, y2, conf in crudas:
            if conf < cb["confianza"]:
                continue
            mx, my = project_point((x1 + x2) / 2.0, y2, H)
            dets.append((mx, my, x1, y1, x2, y2, conf))
        cache.append({"frame_idx": frame_idx, "t": frame_idx / fps, "dets": dets})
        if dets:
            n_con += 1
        hechos += 1
        if cada and hechos % cada == 0:
            _guardar(cache, False)
            logger.info(
                "  %d frames (%d con balón) · checkpoint guardado", len(cache), n_con
            )
        elif len(cache) % 200 == 0:
            logger.info("  %d frames (%d con balón)", len(cache), n_con)
    cap.release()

    # Validar ANTES de escribir. Antes se guardaba el caché, se imprimía
    # un "✓ Caché de balón" y solo después reventaba el resumen: un ✓
    # sobre un archivo vacío es peor que un error, porque se cree.
    if not cache:
        raise SystemExit(
            f"\nERROR: no se procesó NINGÚN frame.\n"
            f"  vídeo   : {ruta_video} ({total} frames)\n"
            f"  tramo   : del {frame_ini} al "
            f"{frame_fin if frame_fin is not None else 'fin'}\n"
            f"  muestreo: 1 de cada {sample}\n"
            f"  No se ha escrito ningún caché."
        )

    if args.comparar_sahi:
        n = len(cache)
        print(f"\nComparación sobre {n} frames:")
        print(
            f"  frame entero (imgsz {cb['imgsz']}): {n_entero} detecciones, "
            f"{1000 * t_entero / n:.0f} ms/frame"
        )
        print(
            f"  SAHI {cb['sahi']['filas']}x{cb['sahi']['columnas']}: "
            f"{n_sahi} detecciones, {1000 * t_sahi / n:.0f} ms/frame"
        )
        print(
            f"  SAHI cuesta {t_sahi / max(t_entero, 1e-9):.1f}x y encuentra "
            f"{n_sahi - n_entero:+d} detecciones"
        )
        print(
            "\n  Si SAHI no encuentra bastantes más, no compensa: pon "
            "balon.sahi.activo: false"
        )
        return

    salida = Path(cfg["rutas"]["cache_balon"])
    _guardar(cache, True)

    # ⚠️ SE RELEE EL FICHERO ANTES DE DAR EL ✓. Contar lo que se envió al
    # disco no prueba que esté en el disco: ya nos pasó con el vídeo, donde
    # OpenCV reventaba al final y el proceso salía con estado 0.
    with open(salida, "rb") as f:
        releido = pickle.load(f)
    if len(releido.get("cache", [])) != len(cache):
        raise SystemExit(
            f"\nERROR: el caché salió INCOMPLETO. Se procesaron {len(cache)} "
            f"frames y en {salida} hay {len(releido.get('cache', []))}."
        )
    print(f"\n✓ Caché de balón en {salida} ({len(releido['cache'])} releídos)")
    print(
        f"  {len(cache)} frames, {n_con} con balón ({100 * n_con / len(cache):.0f} %)"
    )


if __name__ == "__main__":
    main()
