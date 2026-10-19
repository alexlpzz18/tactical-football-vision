#!/usr/bin/env python
"""Mide el criterio YA COMMITEADO de `docs/plan_arbitro_tono_brillo.md` (no cambia ningún umbral).

1. Calibración: píxeles del centro del torso (el recorte de la puerta) de chaleco (filas del proxy),
   césped (cajas vacías) y portero de B, 20 frames por minuto, SIN los minutos 16 y 17 (la ventana
   `azar`). Umbrales con `arbitro_tono_brillo.derivar_umbrales`.
2. Validación: solo contra las marcas de Alex en las imágenes REVISADAS de `azar`, sobre los frames
   ORIGINALES del vídeo (no los JPG pintados), con las cajas de `outputs/hoja_equipos/cajas.csv`.

Uso:
    python scripts/medir_arbitro_tono_brillo.py --pasada outputs/arbitro_obs \\
        --revisadas 0-30
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
HOJA = R / "outputs/hoja_equipos"
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
FPS = 29.97002997002997


def _modulo(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verdad_de_caja(etiqueta: str, marca: dict | None, dentro: bool) -> str | None:
    """'arbitro', 'jugador' o None (fuera de las dos cuentas), según el plan.

    - árbitro: marcada `arbitro`, o `otro` dentro del campo sin marcar;
    - jugador: marcada A/B/portero_*, o sin marcar con etiqueta A/B/portero_*;
    - fuera: staff, no_es_persona, dudoso, marcas sin equipo y todo lo demás.
    """
    jugador = {"A", "B", "portero_A", "portero_B"}
    if marca is not None:
        eq = marca.get("equipo_correcto") or ""
        if eq == "arbitro":
            return "arbitro"
        if eq in jugador:
            return "jugador"
        return None
    if etiqueta == "otro" and dentro:
        return "arbitro"
    if etiqueta in jugador:
        return "jugador"
    return None


def main() -> None:
    import cv2
    import pandas as pd
    import yaml

    from src.campo_modelo import cargar_modelo
    from src.tracking.cache_io import cargar_cache
    from src.tracking_data.processor import posicionar_en_frame

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pasada", required=True)
    ap.add_argument(
        "--revisadas", default="0-30", help="índices de imagen de azar, p. ej. 0-30"
    )
    args = ap.parse_args()
    pasada = Path(args.pasada)
    atb, pu = _modulo("arbitro_tono_brillo"), _modulo("puerta_chaleco_cesped")
    C = atb.CRITERIO
    cfg = yaml.safe_load(open(CONFIG))
    rng = np.random.default_rng(0)

    # ── verdad: imágenes revisadas de azar ──
    a0, a1 = (int(x) for x in args.revisadas.split("-"))
    cajas = pd.read_csv(HOJA / "cajas.csv")
    cajas = cajas[cajas.ventana == "azar"]
    imagenes = sorted(cajas.imagen.unique())[a0 : a1 + 1]  # noqa: E203
    cajas = cajas[cajas.imagen.isin(imagenes)].copy()
    rev = pd.read_csv(HOJA / "revision.csv").fillna("")
    rev = rev[rev.ventana == "azar"]
    marcas = {(r.imagen, int(r.caja)): r._asdict() for r in rev.itertuples()}
    cajas["dentro"] = cajas.x_m.between(0, 62) & cajas.y_m.between(0, 40)
    cajas["verdad"] = [
        verdad_de_caja(e, marcas.get((im, int(k))), d)
        for e, im, k, d in zip(cajas.etiqueta, cajas.imagen, cajas.caja, cajas.dentro)
    ]
    area_b = cargar_modelo(config=R / "configs/campo_benja.yaml").areas_porteria(
        margen=C["margen_area_portero_b_m"]
    )["alto"]
    en_area_b = cajas.x_m.between(*area_b[0]) & cajas.y_m.between(*area_b[1])
    cajas["elegible"] = cajas.dentro & (cajas.etiqueta != "staff") & ~en_area_b

    # ── calibración: las tres clases, sin los minutos de azar ──
    filas = pd.read_csv(pasada / "posiciones.csv")
    reales = filas[filas.es_real == 1]
    capt = pickle.load(open(pasada / "cajas.pkl", "rb"))
    am = _modulo("arbitro_medicion")
    crudo = {
        e["frame_idx"]: e["dets"]
        for e in cargar_cache(R / cfg["rutas"]["cache"])["cache"]
    }
    W = am.masa_de_ventana(
        reales, crudo, pickle.load(open(R / cfg["rutas"]["cache_colores"], "rb"))
    )
    zb = (W.x_m >= am.ZONA_PORTERO_B_X) & ((W.y_m - 20.0).abs() <= am.ZONA_PORTERO_B_DY)
    W["proxy"] = (W.masa >= am.UMBRAL_MASA) & ~zb & (W.etiqueta != "portero_B")
    proxy = set(zip(W[W.proxy].frame, W[W.proxy].id_jugador))
    H = np.load(R / cfg["rutas"]["homografia"])
    fr_cache = np.array(sorted(capt["cache_filtrado"]))
    calib = {}
    for m in pu.CRITERIO["minutos"]:
        if m in C["minutos_excluidos_de_calibracion"]:
            continue
        for k in range(pu.CRITERIO["frames_por_minuto"]):
            t = m * 60 + k * 60 / pu.CRITERIO["frames_por_minuto"]
            calib[int(fr_cache[np.argmin(np.abs(fr_cache - t * FPS))])] = m
    validar = {int(f): g for f, g in cajas.groupby("frame")}
    porf = {f: g for f, g in reales.groupby("frame")}
    cajas_calib = {
        "chaleco": [],
        "cesped": [],
        "portero_B": [],
    }  # una matriz HSV por caja

    def a_metros(u, v):
        p = H @ np.array([u, v, 1.0])
        return p[0] / p[2], p[1] / p[2]

    def recorte(img, caja):
        px = pu.recorte_centro(img, [int(round(v)) for v in caja])
        if len(px) > pu.CRITERIO["max_px_por_caja"]:
            px = px[rng.choice(len(px), pu.CRITERIO["max_px_por_caja"], replace=False)]
        return px

    pixeles_validacion = {}
    cap = cv2.VideoCapture(str(R / cfg["rutas"]["video"]))
    actual = posicionar_en_frame(cap, 0)
    for f in sorted(set(calib) | set(validar)):
        while actual < f:
            cap.grab()
            actual += 1
        ok, img = cap.read()
        actual += 1
        if not ok:
            raise RuntimeError(f"no se pudo leer el frame {f}")
        if f in validar:
            for r in validar[f].itertuples():
                pixeles_validacion[(r.imagen, int(r.caja))] = pu.recorte_centro(
                    img, [r.x1, r.y1, r.x2, r.y2]
                )
        if f not in calib:
            continue
        dets = [tuple(d[2:6]) for d in capt["cache_filtrado"].get(f, [])]
        g = porf.get(f)
        if g is not None:
            for r in g.itertuples():
                d = capt["obs"].get((int(r.id_jugador), f))
                if d is None:
                    continue
                if (f, int(r.id_jugador)) in proxy:
                    cajas_calib["chaleco"].append(recorte(img, dets[d]))
                elif r.etiqueta == "portero_B":
                    cajas_calib["portero_B"].append(recorte(img, dets[d]))
        for x1, y1, x2, y2 in dets[:3]:
            an = x2 - x1
            for dx in pu.CRITERIO["desplazamientos_caja_vacia"]:
                c = (x1 + dx * an, y1, x2 + dx * an, y2)
                if (
                    c[0] < 0
                    or c[2] >= img.shape[1]
                    or any(pu._solapan(c, b) for b in dets)
                ):
                    continue
                xm, ym = a_metros((c[0] + c[2]) / 2, c[3])
                if 0 <= xm <= 62 and 0 <= ym <= 40:
                    cajas_calib["cesped"].append(recorte(img, c))
    cap.release()

    def junta(lista):
        lista = [x for x in lista if len(x)]
        return np.vstack(lista).astype(float) if lista else np.zeros((0, 3))

    u = atb.derivar_umbrales(
        junta(cajas_calib["chaleco"]),
        junta(cajas_calib["cesped"]),
        junta(cajas_calib["portero_B"]),
        None,
        None,
    )

    def fraccion(px):
        return (
            float(atb.es_pixel_chaleco(px.astype(float), u).mean()) if len(px) else 0.0
        )

    u = atb.derivar_umbrales(
        junta(cajas_calib["chaleco"]),
        junta(cajas_calib["cesped"]),
        junta(cajas_calib["portero_B"]),
        [fraccion(p) for p in cajas_calib["cesped"]],
        [fraccion(p) for p in cajas_calib["portero_B"]],
    )

    # ── validación ──
    cajas["frac"] = [
        fraccion(pixeles_validacion.get((im, int(k)), np.zeros((0, 3))))
        for im, k in zip(cajas.imagen, cajas.caja)
    ]
    cajas["dispara"] = cajas.elegible & (cajas.frac >= u["frac_min"])
    arb, jug = cajas[cajas.verdad == "arbitro"], cajas[cajas.verdad == "jugador"]
    fp = jug[jug.dispara]
    no_arb = (
        cajas[cajas.verdad != "arbitro"]
        .sort_values("frac", ascending=False)
        .head(C["n_lista"])
    )
    jugador_en_top = bool(
        ((no_arb.verdad == "jugador") & (no_arb.frac >= u["frac_min"])).any()
    )
    veredicto = atb.veredicto(len(arb), int(arb.dispara.sum()), len(fp), jugador_en_top)
    cols = [
        "imagen",
        "reloj_archivo",
        "reloj_reproductor",
        "caja",
        "id_jugador",
        "etiqueta",
        "verdad",
        "elegible",
        "frac",
        "dispara",
    ]
    res = {
        "imagenes_revisadas": [imagenes[0], imagenes[-1], len(imagenes)],
        "umbrales": u,
        "cajas_calibracion": {k: len(v) for k, v in cajas_calib.items()},
        "verdad": {
            "arbitro": int(len(arb)),
            "otro_sin_marcar_como_arbitro": int(
                sum(
                    1 for r in arb.itertuples() if (r.imagen, int(r.caja)) not in marcas
                )
            ),
            "jugador": int(len(jug)),
            "fuera_de_las_cuentas": int(cajas.verdad.isna().sum()),
        },
        "arbitro_recuperado": int(arb.dispara.sum()),
        "arbitro_no_elegible": int((~arb.elegible).sum()),
        "recuperacion": float(arb.dispara.mean()) if len(arb) else None,
        "falsos_positivos": int(len(fp)),
        "falsos_positivos_detalle": fp[cols].to_dict("records"),
        "top20_no_arbitro": no_arb[cols].to_dict("records"),
        "jugador_en_top20_sobre_umbral": jugador_en_top,
        "veredicto": veredicto,
    }
    salida = pasada / "tono_brillo.json"
    salida.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    cajas.to_csv(pasada / "tono_brillo_cajas.csv", index=False)
    print(json.dumps(res, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
