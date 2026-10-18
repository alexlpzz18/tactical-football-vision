#!/usr/bin/env python
"""Pool de etiquetado del balón PEGADO AL PIE, con el split train/test hecho de entrada.

Para reentrenar el detector de balón (docs/plan_reentreno_balon.md): lo que el
modelo pierde es el balón pegado al pie, tapado a medias o en conducción, a
resolución completa (docs/balon_en_vuelo.md). El umbral bajo no lo arregla
(docs/colab_balon_umbral_bajo.md): hace falta enseñárselo.

Candidatos: frames SIN balón elegido dentro de un hueco corto (≤ 1 s) de la
pista de producción, con el balón a ≤ 2 m de un jugador antes Y después del
hueco y casi quieto entre medias (≤ 3 m): el balón sigue en el pie de alguien y
el detector no lo da. Más los 30 del etiquetado dirigido de los 6 casos del GT.

⚠️ Tres reglas que deciden si la medida después vale algo:

1. **El test se separa por MINUTOS enteros**, no por frames: dos frames vecinos
   son casi la misma imagen y mezclarlos inflaría el resultado. Un minuto de
   cada bloque de 5 (semilla fija): ~20 % de los frames.
2. **Ningún frame de ENTRENAMIENTO a ±3 s del banco de medida** (los 38 del GT
   de desempates, los 25 del GT de vuelo) ni dentro de los dos tramos
   etiquetados a ojo (365-378 s y 990-1005 s): si no, "no empeora" se mediría
   sobre imágenes que el modelo ya ha visto.
3. Repartido por el partido: un frame por hueco, por rondas entre minutos, ≥ 3 s
   entre dos elegidos, y los
   tres tercios del campo representados (el cercano tiene pocos candidatos: el
   balón ahí es grande y casi siempre se detecta).

Cada imagen lleva una caja PRE-PUESTA (YOLO y COCO): en los nuevos, en el punto
medio entre la última y la siguiente posición medida del balón; en los 30
viejos, donde dijo Alex. Del tamaño de un balón ahí según la homografía. Es un
punto de partida: se ajusta, o se borra si el balón no se ve.

Salida (outputs/, no se versiona): train/ y test/ con images/, labels/ y
preanotaciones_coco.json; manifiesto.csv; hoja_train.jpg / hoja_test.jpg; LEEME.txt

Uso:
    python scripts/preparar_pool_balon_pegado.py
"""

import argparse
import contextlib
import io
import json
import random
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import preparar_etiquetado_balon_dirigido as dirigido  # noqa: E402
from src.balon.carga import cargar_detecciones_limpias  # noqa: E402
from src.balon.carga import contexto_del_selector  # noqa: E402
from src.balon.carga import jugadores_por_frame_de_balon  # noqa: E402
from src.balon.tracking_balon import ParametrosBalon  # noqa: E402
from src.balon.tracking_balon import seleccionar_balon_activo  # noqa: E402
from src.campo_modelo import cargar_modelo  # noqa: E402

SEMILLA = 20261003
HUECO_MAX_S = 1.5
DIST_JUGADOR_M = 2.5
MOVIMIENTO_MAX_M = 3.0
SEPARACION_S = 1.5
N_TRAIN_NUEVOS = 115  # + los 30 dirigidos
N_TEST = 36  # ~20 % del pool
EXCLUSION_BANCO_S = 3.0
TRAMOS_ETIQUETADOS = ((365.0, 378.0), (990.0, 1005.0))
OFFSET_REPRODUCTOR_S = 93.0  # el reproductor de Alex va 1:33 por delante del archivo


def zona(x_m: float) -> int:
    """Tercio del campo por la x: 0 cerca de la cámara, 2 al fondo."""
    return 0 if x_m < 20 else 1 if x_m < 40 else 2


def minutos_de_test(n_minutos: int, rng: random.Random, bloque: int = 5) -> set[int]:
    """Un minuto al azar de cada bloque de `bloque` minutos."""
    return {
        rng.randrange(b, min(b + bloque, n_minutos))
        for b in range(0, n_minutos, bloque)
    }


def minutos_de_validacion(
    por_minuto: dict, rng: random.Random, min_n=15, max_n=20
) -> set:
    """Minutos ENTEROS para validar la parada temprana, sumando min_n-max_n imágenes.

    Sin esto `best.pt` saldría de las primeras épocas (la validación del dataset
    original no ve lo nuevo) y el reentreno no aprendería el balón pegado al pie.
    Por minutos, igual que el test: frames vecinos son casi la misma imagen.
    """
    minutos = sorted(por_minuto)
    rng.shuffle(minutos)
    elegidos, n = set(), 0
    for m in minutos:
        if n >= min_n:
            break
        if n + por_minuto[m] <= max_n:
            elegidos.add(m)
            n += por_minuto[m]
    return elegidos


def excluido_de_entrenamiento(
    t: float, tiempos_banco, tramos=TRAMOS_ETIQUETADOS
) -> bool:
    if any(a <= t <= b for a, b in tramos):
        return True
    return any(abs(t - tb) <= EXCLUSION_BANCO_S for tb in tiempos_banco)


def candidatos_pegados(sel, tiempos, jugadores):
    """[(frame, t, punto_m, punto_px)] de los huecos cortos con el balón en el pie."""

    def d_jug(f, p):
        return min(
            (np.hypot(j[0] - p[0], j[1] - p[1]) for j in jugadores.get(f, [])),
            default=99,
        )

    fs, todos, salida = sorted(sel), sorted(tiempos), []
    for a, b in zip(fs, fs[1:]):
        dt = tiempos[b] - tiempos[a]
        pa, pb = np.array(sel[a][:2]), np.array(sel[b][:2])
        if not (0.1 < dt <= HUECO_MAX_S) or np.linalg.norm(pb - pa) > MOVIMIENTO_MAX_M:
            continue
        if not (0 <= pa[0] <= 62 and 0 <= pa[1] <= 40):
            continue
        if d_jug(a, pa) > DIST_JUGADOR_M or d_jug(b, pb) > DIST_JUGADOR_M:
            continue
        ca = np.array(((sel[a][2] + sel[a][4]) / 2, (sel[a][3] + sel[a][5]) / 2))
        cb = np.array(((sel[b][2] + sel[b][4]) / 2, (sel[b][3] + sel[b][5]) / 2))
        for f in todos:
            if a < f < b:
                w = (tiempos[f] - tiempos[a]) / dt  # interpolación lineal por tiempo
                salida.append(
                    (f, tiempos[f], (1 - w) * pa + w * pb, (1 - w) * ca + w * cb)
                )
    return salida


def huecos_de(candidatos):
    """Agrupa los candidatos en HUECOS (rachas seguidas) y se queda con el frame central.

    Un hueco dura ≤ 1 s: sus frames son casi la misma imagen. Un frame por hueco
    da variedad (momentos de juego distintos) en vez de repetidos.
    """
    huecos, previo = [], None
    for c in sorted(candidatos, key=lambda c: c[1]):
        if previo is None or c[1] - previo > 0.2:
            huecos.append([])
        huecos[-1].append(c)
        previo = c[1]
    return [h[len(h) // 2] for h in huecos]


def elegir(candidatos, ya_elegidos_t, n_objetivo, rng):
    """Hasta n_objetivo, por RONDAS entre minutos y equilibrando los tercios del campo.

    Cada ronda toma, de cada minuto, el candidato del tercio menos cubierto hasta
    ahora; ≥ SEPARACION_S entre dos elegidos (también contra `ya_elegidos_t`).
    """
    por_minuto = {}
    for c in candidatos:
        por_minuto.setdefault(int(c[1] // 60), []).append(c)
    for lista in por_minuto.values():
        rng.shuffle(lista)
    elegidos, usados = [], list(ya_elegidos_t)
    cuenta_zona = {0: 0, 1: 0, 2: 0}

    def libre(c):
        return all(abs(c[1] - t) >= SEPARACION_S for t in usados)

    while len(elegidos) < n_objetivo and any(por_minuto.values()):
        for minuto in sorted(por_minuto):
            lista = por_minuto[minuto]
            lista[:] = [c for c in lista if libre(c)]
            if not lista or len(elegidos) >= n_objetivo:
                continue
            # orden estable: dentro de cada tercio sigue siendo aleatorio
            lista.sort(key=lambda c: cuenta_zona[zona(c[2][0])])
            c = lista.pop(0)
            elegidos.append(c)
            usados.append(c[1])
            cuenta_zona[zona(c[2][0])] += 1
    return elegidos


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache-balon", default="data/tracking_benja/cache_balon_p1.pkl")
    p.add_argument(
        "--csv-jugadores", default="data/tracking_benja/posiciones_benja_p1_v3.csv"
    )
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    p.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument(
        "--gt-desempates", default="data/tracking_benja/gt_desempates_balon.csv"
    )
    p.add_argument("--gt-vuelo", default="outputs/gt_balon_en_vuelo/metadatos.json")
    p.add_argument("--salida", default="outputs/pool_balon_pegado")
    args = p.parse_args()
    rng = random.Random(SEMILLA)

    modelo = cargar_modelo(config=args.campo)
    with contextlib.redirect_stdout(io.StringIO()):
        dets, tiempos, meta = cargar_detecciones_limpias(args.cache_balon, modelo)
    jug, ctx = contexto_del_selector(
        args.csv_jugadores, tiempos, dets, args.campo, modelo, meta["fuera_de_campo"]
    )
    pos = {f: [(j[0], j[1]) for j in jug.get(f, [])] for f in dets}
    sel = seleccionar_balon_activo(dets, pos, ParametrosBalon(), **ctx)
    jugadores = jugadores_por_frame_de_balon(
        args.csv_jugadores, tiempos, sorted(tiempos)
    )
    H = np.load(args.homografia)

    # Banco de medida: lo que el ENTRENAMIENTO no puede tocar
    gt_des = pd.read_csv(args.gt_desempates)
    meta_vuelo = json.loads(Path(args.gt_vuelo).read_text())
    tiempos_banco = sorted(
        set(gt_des.t.round(2)) | {v["t_archivo"] for v in meta_vuelo.values()}
    )

    n_minutos = int(np.ceil(max(tiempos.values()) / 60))
    test_min = minutos_de_test(n_minutos, rng)

    # Los 30 del etiquetado dirigido (6 casos × 5 frames)
    viejos = []
    for caso, (frame, celdas, ancla) in dirigido.CASOS.items():
        punto = dirigido.punto_del_caso(celdas, ancla, meta_vuelo[caso])
        for k in dirigido.VECINOS:
            f = frame + 2 * k
            viejos.append(
                (f, tiempos[f], None, np.array(punto), f"dirigido_{caso}{k:+d}")
            )

    cands = huecos_de(candidatos_pegados(sel, tiempos, jugadores))
    frames_viejos = {v[0] for v in viejos}
    cands = [c for c in cands if c[0] not in frames_viejos]
    de_test = [c for c in cands if int(c[1] // 60) in test_min]
    de_train = [
        c
        for c in cands
        if int(c[1] // 60) not in test_min
        and not excluido_de_entrenamiento(c[1], tiempos_banco)
    ]
    nuevos = elegir(de_train, [v[1] for v in viejos], N_TRAIN_NUEVOS, rng)
    nuevos += elegir(de_test, [], N_TEST, rng)

    filas = []
    for f, t, pm, ppx, origen in viejos:
        filas.append((f, t, ppx, origen, None))
    for f, t, pm, ppx in nuevos:
        filas.append((f, t, ppx, "pegado", zona(pm[0])))
    filas.sort()

    salida = Path(args.salida)
    manifiesto, por_split = [], {"train": [], "test": []}
    for f, t, ppx, origen, z in filas:
        minuto = int(t // 60)
        split = "test" if minuto in test_min else "train"
        # Los 30 dirigidos SÍ entran a entrenar aunque sean frames del GT de vuelo:
        # son justo los ejemplos que el modelo no sabe (lo pidió Alex). Esos 6
        # casos dejan de valer para medir el beneficio (docs/plan_reentreno_balon.md).
        if (
            split == "train"
            and not origen.startswith("dirigido")
            and excluido_de_entrenamiento(t, tiempos_banco)
        ):
            split = "descartado_banco"
        manifiesto.append(
            {
                "frame": f,
                "t_archivo": round(t, 3),
                "t_reproductor": round(t + OFFSET_REPRODUCTOR_S, 3),
                "minuto": minuto,
                "zona": "" if z is None else z,
                "origen": origen,
                "split": split,
                "pre_x": round(float(ppx[0]), 1),
                "pre_y": round(float(ppx[1]), 1),
            }
        )

    # Validación: minutos enteros de TRAIN sin dirigidos (esos son lo que tiene que
    # aprender), con un generador APARTE para no mover ninguna elección anterior.
    con_dirigidos = {
        r["minuto"] for r in manifiesto if r["origen"].startswith("dirigido")
    }
    por_minuto = {}
    for r in manifiesto:
        if r["split"] == "train" and r["minuto"] not in con_dirigidos:
            por_minuto[r["minuto"]] = por_minuto.get(r["minuto"], 0) + 1
    val_min = minutos_de_validacion(por_minuto, random.Random(SEMILLA + 1))
    for r in manifiesto:
        if r["split"] == "train" and r["minuto"] in val_min:
            r["split"] = "val"
    # Dos tareas de CVAT: train (lleva dentro la validación) y test.
    por_frame = {f: (ppx, origen) for f, _t, ppx, origen, _z in filas}
    for r in manifiesto:
        tarea = {"train": "train", "val": "train", "test": "test"}.get(r["split"])
        if tarea:
            ppx, origen = por_frame[r["frame"]]
            por_split[tarea].append((r["frame"], ppx, origen))

    cap = cv2.VideoCapture(args.video)
    ancho, alto = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )
    pedidos = {
        f: (split, ppx, origen)
        for split, lista in por_split.items()
        for f, ppx, origen in lista
    }
    miniaturas = {"train": [], "test": []}
    coco = {
        s: {"images": [], "annotations": [], "categories": [{"id": 1, "name": "balon"}]}
        for s in por_split
    }
    for s in por_split:
        (salida / s / "images").mkdir(parents=True, exist_ok=True)
        (salida / s / "labels").mkdir(parents=True, exist_ok=True)
    pos_video = 0
    for f in sorted(pedidos):
        while pos_video < f:  # lectura SECUENCIAL: el frame exacto (nunca cap.set)
            cap.grab()
            pos_video += 1
        ok, img = cap.read()
        pos_video += 1
        if not ok:
            raise RuntimeError(f"No se pudo leer el frame {f}")
        s, ppx, origen = pedidos[f]
        nombre = f"f{f:06d}"
        cv2.imwrite(str(salida / s / "images" / f"{nombre}.png"), img)
        caja = dirigido.caja_preanotada(float(ppx[0]), float(ppx[1]), H, ancho, alto)
        (salida / s / "labels" / f"{nombre}.txt").write_text(
            dirigido.a_yolo(caja, ancho, alto) + "\n"
        )
        i = len(coco[s]["images"]) + 1
        coco[s]["images"].append(
            {"id": i, "file_name": f"{nombre}.png", "width": ancho, "height": alto}
        )
        x1, y1, x2, y2 = caja
        coco[s]["annotations"].append(
            {
                "id": i,
                "image_id": i,
                "category_id": 1,
                "bbox": [
                    round(x1, 1),
                    round(y1, 1),
                    round(x2 - x1, 1),
                    round(y2 - y1, 1),
                ],
                "area": round((x2 - x1) * (y2 - y1), 1),
                "iscrowd": 0,
            }
        )
        vis = img.copy()
        cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 1)
        x0 = int(np.clip(ppx[0] - 100, 0, ancho - 200))
        y0 = int(np.clip(ppx[1] - 75, 0, alto - 150))
        x1r, y1r = x0 + 200, y0 + 150
        mini = cv2.resize(
            vis[y0:y1r, x0:x1r], (240, 180), interpolation=cv2.INTER_NEAREST
        )
        cv2.putText(
            mini, nombre, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 2
        )
        miniaturas[s].append(mini)

    for s in por_split:
        (salida / s / "preanotaciones_coco.json").write_text(
            json.dumps(coco[s], indent=1)
        )
        tiles = miniaturas[s] + [np.zeros_like(miniaturas[s][0])] * (
            -len(miniaturas[s]) % 10
        )
        filas_img = [
            np.hstack(tiles[i:j])
            for i, j in zip(range(0, len(tiles), 10), range(10, len(tiles) + 10, 10))
        ]
        cv2.imwrite(str(salida / f"hoja_{s}.jpg"), np.vstack(filas_img))
    pd.DataFrame(manifiesto).to_csv(salida / "manifiesto.csv", index=False)
    # Para CVAT: la preanotación en COCO 1.0 (Acciones → Subir anotaciones). Las
    # imágenes se suben DIRECTAMENTE desde <tarea>/images: un zip las duplicaría
    # (~400 MB de PNG) y el disco de este Mac va justo.
    for s in por_split:
        with zipfile.ZipFile(salida / f"cvat_{s}_preanotaciones_coco.zip", "w") as z:
            z.write(
                salida / s / "preanotaciones_coco.json",
                "annotations/instances_default.json",
            )
    n_val = sum(r["split"] == "val" for r in manifiesto)
    (salida / "LEEME.txt").write_text(
        "Pool de etiquetado del balón pegado al pie (NO entrenar sin el OK de Alex).\n"
        f"Tarea train: {len(por_split['train'])} imágenes ({n_val} de ellas son la VALIDACIÓN,\n"
        f"minutos {sorted(val_min)}, se etiquetan igual). Tarea test: {len(por_split['test'])} "
        f"(minutos {sorted(test_min)}). El test NO se mira hasta medir.\n\n"
        "EN CVAT, una tarea por carpeta (train y test, por separado):\n"
        "1. Crear tarea con UNA etiqueta: balon (rectángulo). Subir todas las imágenes de\n"
        "   <tarea>/images/ (arrastrarlas: no hace falta zip).\n"
        "2. Acciones → Subir anotaciones → formato COCO 1.0 →\n"
        "   cvat_<tarea>_preanotaciones_coco.zip\n"
        "   (trae una caja pre-puesta por imagen donde el sistema cree que está el balón).\n"
        "3. En cada imagen:\n"
        "   - ajusta la caja al balón visible (aunque esté medio tapado: cubre lo que se VE);\n"
        "   - si ves el balón en otro sitio, mueve la caja allí;\n"
        "   - si el balón NO se ve, BORRA la caja (queda como ejemplo sin balón).\n"
        "4. Acciones → Exportar dataset de la tarea → YOLO 1.1, SIN imágenes.\n"
        "   Deja los dos zips (train y test) en outputs/pool_balon_pegado/etiquetado/.\n\n"
        "manifiesto.csv: frame, tiempo de archivo y de tu reproductor (+1:33), minuto,\n"
        "tercio del campo, origen (pegado / dirigido_Vxx) y split (train/val/test).\n"
    )
    cuenta = pd.DataFrame(manifiesto).groupby("split").size().to_dict()
    print(
        f"minutos de test: {sorted(test_min)} · de validación: {sorted(val_min)} · {cuenta}"
        f" · candidatos {len(cands)}"
    )


if __name__ == "__main__":
    main()
