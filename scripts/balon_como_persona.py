#!/usr/bin/env python
"""¿Una regla de FORMA quita el balón que el detector de personas coge? (BACKLOG 16)

Solo medición, local, sin tocar producción. Plan y criterio en `docs/balon_como_persona.md`;
el CRITERIO de abajo se commitea ANTES de ver ningún número.

La regla: una detección de persona es un balón si es BAJA (altura implícita < una fracción de
la mediana del partido) Y CUADRADA (ancho/alto alto). Cada señal sola cuesta personas
(`docs/reglas_fisicas.md`); juntas, una persona agachada falla la segunda y una tumbada la
primera.

Uso:
    python scripts/balon_como_persona.py medir --trabajo DIR [--csv-prod DIR/posiciones.csv]
    python scripts/balon_como_persona.py hoja --trabajo DIR      # recortes para mirar a ojo
    python scripts/balon_como_persona.py veredicto --trabajo DIR --personas-a-ojo N
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

# ── Fijado ANTES de medir (commit aparte) ─────────────────────────────────────
CRITERIO = {
    # la regla
    "alto_max_frac": 0.40,  # altura implícita < 0,40 × la mediana del partido (≈ 0,6 m)
    "aspecto_min": 0.70,  # Y ancho/alto ≥ 0,70 (balón ≈ 1; persona mediana 0,39)
    # adopción
    "personas_gt_perdidas_max": 0,
    "personas_a_ojo_max": 0,
    "balon_quitado_min": 1,
    # revisión a ojo
    "muestra_sin_balon": 60,  # si hay más, 60 al azar
    "muestra_con_balon": 20,  # control: ¿de verdad son balones?
    "semilla": 0,
    # coincidencia con el caché de balón: un balón dentro de la caja, en f o f±1
    "margen_px": 4,
    "frames_vecinos": 1,
}

CONFIG = R / "configs/processor_benja_parte_entera.yaml"
GT = R / "data/annotations/gt_benja/annotations.xml"
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
CAMPO = R / "configs/campo_benja.yaml"
OFFSET_GT, PASO_GT = 9750, 15
DESFASE_REPRODUCTOR_S = 93  # el reproductor de Alex va +1:33


def forma_de_balon(
    alto_m: float, ancho_m: float, ref: float, crit: dict = CRITERIO
) -> bool:
    """True si la caja es BAJA y CUADRADA a la vez (las dos condiciones)."""
    if alto_m is None or alto_m <= 0 or ref <= 0:
        return False
    return (
        alto_m < crit["alto_max_frac"] * ref and ancho_m / alto_m >= crit["aspecto_min"]
    )


def balon_dentro(det, balones, margen: float) -> bool:
    """¿Alguna detección de balón (su centro) cae dentro de la caja de persona?"""
    x1, y1, x2, y2 = det[2] - margen, det[3] - margen, det[4] + margen, det[5] + margen
    for b in balones:
        u, v = (b[2] + b[4]) / 2.0, (b[3] + b[5]) / 2.0
        if x1 <= u <= x2 and y1 <= v <= y2:
            return True
    return False


def es_persona_gt(det, cajas_gt) -> bool:
    """Unión de dos casados (protege más): centro del GT dentro de la caja, o pies cerca."""
    x1, y1, x2, y2 = det[2], det[3], det[4], det[5]
    alto = max(y2 - y1, 1.0)
    for c in cajas_gt:
        cu, cv = (c.xtl + c.xbr) / 2.0, (c.ytl + c.ybr) / 2.0
        if x1 <= cu <= x2 and y1 <= cv <= y2:
            return True
        if np.hypot((x1 + x2) / 2.0 - cu, y2 - c.ybr) <= 0.5 * alto:
            return True
    return False


def veredicto(perdidas_gt: int, perdidas_a_ojo: int | None, balon_quitado: int) -> str:
    c = CRITERIO
    if perdidas_gt > c["personas_gt_perdidas_max"]:
        return "NO SE ADOPTA (pierde personas del GT)"
    if balon_quitado < c["balon_quitado_min"]:
        return "NO SE ADOPTA (no quita ningún balón)"
    if perdidas_a_ojo is None:
        return "PENDIENTE de la revisión a ojo"
    if perdidas_a_ojo > c["personas_a_ojo_max"]:
        return "NO SE ADOPTA (pierde jugadores reales en el partido)"
    return "PASA (no se activa sin el OK de Alex)"


def _relojes(f: int, fps: float) -> str:
    t = f / fps
    r = t + DESFASE_REPRODUCTOR_S
    return f"{int(t // 60)}:{t % 60:04.1f} / {int(r // 60)}:{r % 60:04.1f}"


def _cache_produccion():
    """El caché de personas con los filtros que ya pasa producción, antes del tracking."""
    import yaml

    from src.tracking.cache_io import cargar_cache
    from src.tracking.filtro_confianza import filtrar_por_confianza
    from src.tracking.plausibilidad_fisica import filtrar_por_plausibilidad

    cfg = yaml.safe_load(open(CONFIG))
    cfg_tr = yaml.safe_load(open(R / cfg["config_tracking"]))
    datos = cargar_cache(R / cfg["rutas"]["cache"])
    cache = datos["cache"]
    conf = float(cfg_tr.get("confianza_min", 0) or 0)
    if conf > 0:
        cache, _ = filtrar_por_confianza(cache, None, conf)
    H = np.load(R / cfg["rutas"]["homografia"])
    fis = cfg_tr.get("plausibilidad_fisica", {}) or {}
    if fis.get("activo", False):
        cache, _, _ = filtrar_por_plausibilidad(
            cache, None, H, **{k: v for k, v in fis.items() if k != "activo"}
        )
    return cache, H, datos.get("fps", 29.97)


def medir(args) -> None:
    from src.balon.carga import cargar_detecciones_limpias
    from src.campo_modelo import cargar_modelo
    from src.evaluation.gt_parser import parsear_cvat
    from src.tracking.plausibilidad_fisica import (
        medidas_implicadas,
        referencia_del_partido,
    )

    trabajo = Path(args.trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    cache, H, fps = _cache_produccion()
    med = medidas_implicadas(cache, H)
    ref = referencia_del_partido(med)
    balones, _t, _m = cargar_detecciones_limpias(
        CACHE_BALON, cargar_modelo(config=CAMPO)
    )

    def balones_cerca(f):
        out = []
        for d in range(-CRITERIO["frames_vecinos"], CRITERIO["frames_vecinos"] + 1):
            out.extend(balones.get(f + d, []))
        return out

    quitadas = []  # (frame, det_idx, alto_m, ancho_m, con_balon)
    total = 0
    for e in cache:
        f = e["frame_idx"]
        for i, det in enumerate(e["dets"]):
            total += 1
            alto, ancho = med.get((f, i), (None, None))
            if alto is None or not forma_de_balon(alto, ancho, ref):
                continue
            cb = balon_dentro(det, balones_cerca(f), CRITERIO["margen_px"])
            quitadas.append((f, i, alto, ancho, bool(cb)))

    # 1. GT de 14
    cajas_por_frame = {}
    for t in parsear_cvat(GT):
        for c in t.cajas:
            cajas_por_frame.setdefault(OFFSET_GT + PASO_GT * c.frame_local, []).append(
                c
            )
    por_frame = {e["frame_idx"]: e for e in cache}
    dets_gt = perdidas_gt = 0
    aspecto_gt, alto_gt = [], []
    for f, cajas in cajas_por_frame.items():
        if f not in por_frame:
            continue
        for i, det in enumerate(por_frame[f]["dets"]):
            if not es_persona_gt(det, cajas):
                continue
            dets_gt += 1
            alto, ancho = med.get((f, i), (None, None))
            if alto:
                alto_gt.append(alto / ref)
                aspecto_gt.append(ancho / alto)
            if alto is not None and forma_de_balon(alto, ancho, ref):
                perdidas_gt += 1

    # 3. CSV de producción: filas que salen de una detección con forma de balón
    filas = {}
    if args.csv_prod and Path(args.csv_prod).exists():
        import pandas as pd

        csv = pd.read_csv(args.csv_prod)
        reales = csv[csv.es_real == 1] if "es_real" in csv else csv
        # Cada fila real se casa con la detección MÁS CERCANA de su frame (a < 1 m): la
        # posición está suavizada (0,5 s) y no coincide al centímetro con la detección.
        marcadas = {(f, i): cb for f, i, *_r, cb in quitadas}
        por_id = {}
        for r in reales.itertuples():
            dets = por_frame.get(r.frame, {"dets": []})["dets"]
            forma, cb = False, False
            if dets:
                dist = [np.hypot(d[0] - r.x_m, d[1] - r.y_m) for d in dets]
                i = int(np.argmin(dist))
                if dist[i] < 1.0 and (r.frame, i) in marcadas:
                    forma, cb = True, marcadas[(r.frame, i)]
            n = por_id.setdefault(int(r.id_jugador), [0, 0, 0, r.etiqueta])
            n[0] += 1
            n[1] += forma
            n[2] += cb
        mayoria = {k: v for k, v in por_id.items() if v[1] > 0.5 * v[0]}
        filas = {
            "filas_reales": int(len(reales)),
            "filas_forma_balon": int(sum(v[1] for v in por_id.values())),
            "filas_forma_y_balon": int(sum(v[2] for v in por_id.values())),
            "ids_con_alguna": int(sum(1 for v in por_id.values() if v[1])),
            "ids_mayoria_forma_balon": {
                str(k): {
                    "filas": v[0],
                    "forma": v[1],
                    "con_balon": v[2],
                    "etiqueta": v[3],
                }
                for k, v in sorted(mayoria.items())
            },
            "etiquetas_de_las_filas": {},
        }
        for k, v in por_id.items():
            if v[1]:
                filas["etiquetas_de_las_filas"][v[3]] = (
                    filas["etiquetas_de_las_filas"].get(v[3], 0) + v[1]
                )

    con = [q for q in quitadas if q[4]]
    sin = [q for q in quitadas if not q[4]]
    res = {
        "criterio": CRITERIO,
        "referencia_m": ref,
        "detecciones_total": total,
        "quitadas": len(quitadas),
        "quitadas_con_balon": len(con),
        "quitadas_sin_balon": len(sin),
        "gt": {
            "detecciones_persona": dets_gt,
            "perdidas": perdidas_gt,
            "alto_frac_p1": float(np.percentile(alto_gt, 1)),
            "aspecto_p99": float(np.percentile(aspecto_gt, 99)),
            "aspecto_max": float(np.max(aspecto_gt)),
            "bajas_y_cuadradas_mas_cercanas": sorted(
                (round(a, 2), round(h, 2))
                for a, h in zip(aspecto_gt, alto_gt)
                if a >= 0.55
            )[:10],
        },
        "csv_produccion": filas,
        "veredicto_parcial": veredicto(perdidas_gt, None, len(con)),
    }
    (trabajo / "quitadas.json").write_text(json.dumps(quitadas))
    (trabajo / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"fps {fps:.2f}")


def hoja(args) -> None:
    """Recortes de las quitadas, para mirarlas a ojo (con posicionar_en_frame, no cap.set)."""
    import cv2

    from src.tracking_data.processor import posicionar_en_frame

    trabajo = Path(args.trabajo)
    quitadas = json.loads((trabajo / "quitadas.json").read_text())
    cache, _H, fps = _cache_produccion()
    por_frame = {e["frame_idx"]: e for e in cache}
    rng = np.random.default_rng(CRITERIO["semilla"])
    sin = [q for q in quitadas if not q[4]]
    con = [q for q in quitadas if q[4]]
    if len(sin) > CRITERIO["muestra_sin_balon"]:
        sin = [
            sin[k] for k in rng.choice(len(sin), CRITERIO["muestra_sin_balon"], False)
        ]
    if len(con) > CRITERIO["muestra_con_balon"]:
        con = [
            con[k] for k in rng.choice(len(con), CRITERIO["muestra_con_balon"], False)
        ]

    import yaml

    video = R / yaml.safe_load(open(CONFIG))["rutas"]["video"]
    cap = cv2.VideoCapture(str(video))
    lado, cols = 160, 10
    for nombre, grupo in (("sin_balon", sin), ("con_balon", con)):
        grupo = sorted(grupo)
        tiles, indice = [], []
        actual = None  # frame que devolvería el próximo read()
        for k, (f, i, alto, ancho, _cb) in enumerate(grupo):
            # Se posiciona UNA vez con posicionar_en_frame (nunca cap.set) y luego se
            # avanza decodificando: los frames van ordenados y buscar cada uno desde
            # su fotograma clave era lentísimo.
            if actual is None or f < actual:
                actual = posicionar_en_frame(cap, f)
            while actual < f:
                cap.grab()
                actual += 1
            ok, img = cap.read()
            actual += 1
            if not ok:
                continue
            x1, y1, x2, y2 = (int(round(v)) for v in por_frame[f]["dets"][i][2:6])
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            r = max(40, y2 - y1, x2 - x1)
            ox, oy = max(cx - r, 0), max(cy - r, 0)
            filas_rec = slice(oy, cy + r)
            cols_rec = slice(ox, cx + r)
            rec = img[filas_rec, cols_rec].copy()
            cv2.rectangle(rec, (x1 - ox, y1 - oy), (x2 - ox, y2 - oy), (0, 255, 255), 1)
            rec = cv2.resize(rec, (lado, lado), interpolation=cv2.INTER_NEAREST)
            cv2.putText(
                rec, str(k), (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1
            )
            tiles.append(rec)
            indice.append(
                {
                    "n": k,
                    "frame": f,
                    "relojes": _relojes(f, fps),
                    "alto_m": alto,
                    "ancho_m": ancho,
                }
            )
        if not tiles:
            continue
        while len(tiles) % cols:
            tiles.append(np.zeros((lado, lado, 3), np.uint8))
        filas_img = [np.hstack(tiles[j:][:cols]) for j in range(0, len(tiles), cols)]
        cv2.imwrite(str(trabajo / f"hoja_{nombre}.jpg"), np.vstack(filas_img))
        (trabajo / f"hoja_{nombre}.json").write_text(json.dumps(indice, indent=1))
        print(f"✓ hoja_{nombre}.jpg ({len(indice)} recortes)")
    cap.release()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("medir")
    m.add_argument("--trabajo", required=True)
    m.add_argument("--csv-prod", default=None)
    h = sub.add_parser("hoja")
    h.add_argument("--trabajo", required=True)
    v = sub.add_parser("veredicto")
    v.add_argument("--trabajo", required=True)
    v.add_argument("--personas-a-ojo", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "medir":
        medir(args)
    elif args.cmd == "hoja":
        hoja(args)
    else:
        res = json.loads((Path(args.trabajo) / "resultado.json").read_text())
        print(
            veredicto(
                res["gt"]["perdidas"], args.personas_a_ojo, res["quitadas_con_balon"]
            )
        )


if __name__ == "__main__":
    main()
