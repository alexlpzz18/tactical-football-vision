#!/usr/bin/env python
"""Suavizado por TIEMPO real (V1) y sin cruzar saltos (V2): el experimento del plan.

Plan y criterio aprobados, sin cambios: `docs/plan_suavizado_por_tiempo.md`. Producción NO se
toca: las variantes viven aquí y sustituyen a `suavizar_trayectorias` solo durante cada pasada
(como los espías de `diagnostico_filas_movidas.py`).

- **B0**: producción (la función original, tal cual).
- **B1**: sin suavizado (`suavizado.activo: false`).
- **V1**: la ventana de cada muestra son las muestras reales a ±h·paso FRAMES de ella (h = la
  media ventana que usa hoy esa trayectoria), con el mismo relleno de bordes. Sin huecos, da
  exactamente B0.
- **V2**: la trayectoria se parte donde un paso supera el umbral LOCAL
  v_umbral = 8,5 + 3 · 3,5 px · (m/píxel en el punto medio) / Δt real, y se suaviza cada tramo
  con la regla de hoy.
- **V3**: V1 dentro de los tramos de V2.

Uso:
    python scripts/suavizado_por_tiempo.py correr --trabajo DIR [--pata benja|villa|ambas]
    python scripts/suavizado_por_tiempo.py medir --trabajo DIR
"""

import argparse
import copy
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

# ── Del plan (docs/plan_suavizado_por_tiempo.md), sin tocar ────────────────────
V2 = {"v_max": 8.5, "sigma_paso_px": 3.5, "z": 3.0}
CRITERIO = {
    "bloque_s": 5.0,  # remuestreo de bloques de 5 s (el método del +0,066)
    "n_boot": 2000,
    "semilla": 0,
    "lejos_de_deteccion_m": 1.0,
    "radio_casado_m": 2.0,
    "radio_traza_m": 5.0,
    # franjas: x en el benjamín (la cámara está detrás de x = 0); en Villaviciosa la profundidad
    # no es x (cámara en la grada), así que se usan los m/píxel equivalentes a esas x del benjamín
    "franjas_temblor_x": [(0, 20), (20, 40), (40, 1e9)],
    "franjas_temblor_mpp": [(0, 0.09), (0.09, 0.24), (0.24, 1e9)],
    "franjas_cortes_x": [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 1e9)],
    "franjas_cortes_mpp": [(0, 0.045), (0.045, 0.09), (0.09, 0.16), (0.16, 0.24), (0.24, 0.35),
                           (0.35, 1e9)],  # fmt: skip
    "cortes_fondo_max_factor": 2.0,
}
VARIANTES = ("B0", "B1", "V1", "V2", "V3")
PATAS = {
    "benja": {
        "config": "configs/processor_benja_parte_entera.yaml",
        "gt": "data/annotations/gt_benja/annotations.xml",
        "offset": 9750,
        "paso_gt": 15,
        "franjas_por": "x",
    },
    "villa": {
        "config": "configs/processor.yaml",
        "gt": "data/annotations/ground_truth_tracking/annotations.xml",
        "offset": 7500,
        "paso_gt": 15,
        "franjas_por": "mpp",
    },
}


# ─────────────────────────── las variantes (piezas puras, con tests) ──────────
def ventana_de_hoy(puntos, base, resolucion, escalar) -> int | None:
    """La ventana (muestras) que usa hoy `suavizar_trayectorias`, o None si no suaviza."""
    ventana = base
    if resolucion is not None and escalar > 0:
        paso = max(1, len(puntos) // 10)
        factor = float(np.mean([resolucion.factor(p) for p in puntos[::paso]]))
        ventana = int(round(base * (1 + escalar * np.log1p(factor))))
        ventana = max(base, min(ventana, len(puntos) // 2 * 2 - 1, 61))
        if ventana % 2 == 0:
            ventana -= 1
    if ventana < 3 or len(puntos) < ventana:
        return None
    return ventana


def media_movil(puntos: np.ndarray, ventana: int) -> np.ndarray:
    """La media móvil de hoy (relleno 'edge' + convolución), eje a eje."""
    suave = puntos.copy()
    for eje in (0, 1):
        nucleo = np.ones(ventana) / ventana
        relleno = np.pad(puntos[:, eje], ventana // 2, mode="edge")
        suave[:, eje] = np.convolve(relleno, nucleo, mode="valid")
    return suave


def media_por_tiempo(puntos: np.ndarray, frames: np.ndarray, ventana: int, paso: int):
    """V1: media de las muestras a ±h·paso frames, con el mismo relleno de bordes que hoy.

    Donde la ventana en tiempo coincide con la de hoy (sin hueco dentro), devuelve EXACTAMENTE
    el valor de hoy (no una suma en otro orden): así el control «sin huecos = B0» es byte a byte.
    """
    n, h = len(puntos), ventana // 2
    hoy = media_movil(puntos, ventana)
    salida = hoy.copy()
    lo = np.searchsorted(frames, frames - h * paso, side="left")
    hi = np.searchsorted(frames, frames + h * paso, side="right")
    acum = np.vstack([np.zeros((1, 2)), np.cumsum(puntos, axis=0)])
    for i in range(n):
        pad_ini = max(0, -(-(frames[0] - (frames[i] - h * paso)) // paso))
        pad_fin = max(0, -(-((frames[i] + h * paso) - frames[-1]) // paso))
        igual_que_hoy = (
            lo[i] == max(0, i - h)
            and hi[i] == min(n, i + h + 1)
            and pad_ini == max(0, h - i)
            and pad_fin == max(0, i + h - (n - 1))
        )
        if igual_que_hoy:
            continue
        suma = acum[hi[i]] - acum[lo[i]] + pad_ini * puntos[0] + pad_fin * puntos[-1]
        salida[i] = suma / (hi[i] - lo[i] + pad_ini + pad_fin)
    return salida


def umbral_local(pos, dt_s: float, resolucion) -> float:
    """v_umbral del plan: 8,5 m/s + 3 · 3,5 px · (m/píxel en pos) / Δt."""
    mpp = resolucion.metros_por_pixel(pos)
    return V2["v_max"] + V2["z"] * V2["sigma_paso_px"] * mpp / dt_s


def cortes_v2(puntos: np.ndarray, frames: np.ndarray, fps: float, resolucion):
    """Índices k tales que el paso k→k+1 supera su umbral local, y la lista de pasos evaluados.

    Cada paso: (x del punto medio, m/píxel del punto medio, ¿corta?).
    """
    pasos, cortes = [], []
    for k in range(len(puntos) - 1):
        dt_s = (frames[k + 1] - frames[k]) / fps
        medio = (puntos[k] + puntos[k + 1]) / 2.0
        v = float(np.linalg.norm(puntos[k + 1] - puntos[k])) / dt_s
        corta = v > umbral_local(medio, dt_s, resolucion)
        pasos.append((float(medio[0]), resolucion.metros_por_pixel(medio), bool(corta)))
        if corta:
            cortes.append(k)
    return cortes, pasos


def suavizar_tramo(puntos, frames, ventana, paso, por_tiempo: bool):
    """Un tramo con la regla de hoy (o la de V1), con la ventana recortada a su longitud."""
    v = min(ventana, len(puntos) // 2 * 2 - 1)
    if v % 2 == 0:
        v -= 1
    if v < 3:
        return puntos.copy()
    if por_tiempo:
        return media_por_tiempo(puntos, frames, v, paso)
    return media_movil(puntos, v)


def suavizar_variante(trayectorias, params, resolucion, dt, variante, fps, registro):
    """Sustituto de `suavizar_trayectorias` para V1, V2 y V3 (mismas entradas y salidas)."""
    if params.metodo != "media":
        raise ValueError(
            "el experimento solo replica el método 'media' (el de las dos patas)"
        )
    if not params.activo or dt <= 0:
        return trayectorias
    paso = int(round(dt * fps))
    base = max(3, int(round(params.ventana_s / dt)))
    base += base % 2 == 0
    resultado = []
    for tray in trayectorias:
        indices = [i for i, (_f, _p, real) in enumerate(tray) if real]
        if len(indices) < base:
            resultado.append(tray)
            continue
        puntos = np.array([tray[i][1] for i in indices], dtype=float)
        frames = np.array([tray[i][0] for i in indices])
        ventana = ventana_de_hoy(
            puntos, base, resolucion, params.escalar_con_resolucion
        )
        if ventana is None:
            resultado.append(tray)
            continue
        if variante == "V1":
            suave = media_por_tiempo(puntos, frames, ventana, paso)
        else:  # V2 y V3: por tramos
            cortes, pasos = cortes_v2(puntos, frames, fps, resolucion)
            registro.extend(pasos)
            suave = np.empty_like(puntos)
            limites = [0] + [k + 1 for k in cortes] + [len(puntos)]
            for a, b in zip(limites[:-1], limites[1:]):
                suave[a:b] = suavizar_tramo(
                    puntos[a:b],
                    frames[a:b],
                    ventana,
                    paso,
                    por_tiempo=(variante == "V3"),
                )
        nueva = list(tray)
        for k, i in enumerate(indices):
            frame, _pos, real = tray[i]
            nueva[i] = (frame, suave[k], real)
        resultado.append(nueva)
    return resultado


def huella(trayectorias) -> str:
    """Hash de la ENTRADA al suavizado: tiene que ser idéntica en todas las variantes."""
    h = hashlib.sha256()
    for tray in trayectorias:
        for f, p, real in tray:
            h.update(
                f"{f},{float(p[0]):.9f},{float(p[1]):.9f},{int(bool(real))};".encode()
            )
        h.update(b"|")
    return h.hexdigest()


# ─────────────────────────────── las pasadas ──────────────────────────────────
def pasada(pata: str, variante: str, trabajo: Path) -> dict:
    import yaml

    import src.tracking.suavizado as sv
    from src.tracking_data.processor import procesar_desde_cache

    cfg_p = PATAS[pata]
    cfg = yaml.safe_load(open(R / cfg_p["config"]))
    cfg["modo"] = "desde_cache"
    d = trabajo / pata / variante
    d.mkdir(parents=True, exist_ok=True)
    cfg["rutas"]["salida_csv"] = str(d / "posiciones.csv")
    cfg["rutas"]["salida_meta"] = str(d / "meta.json")
    cfg_tr = yaml.safe_load(open(R / cfg["config_tracking"]))
    if variante == "B1":
        cfg_tr = copy.deepcopy(cfg_tr)
        cfg_tr["suavizado"]["activo"] = False
        yaml.safe_dump(cfg_tr, open(d / "tracking.yaml", "w"), allow_unicode=True)
        cfg["config_tracking"] = str(d / "tracking.yaml")
    fps = float(pickle.load(open(R / cfg["rutas"]["cache"], "rb"))["fps"])

    original, info, registro = sv.suavizar_trayectorias, {}, []

    def sustituto(trayectorias, params=None, resolucion=None, dt=0.12):
        info["entrada"] = huella(trayectorias)
        info["filas_por_id_entrada"] = [len(t) for t in trayectorias]
        if variante == "B0":
            return original(trayectorias, params, resolucion=resolucion, dt=dt)
        return suavizar_variante(
            trayectorias, params, resolucion, dt, variante, fps, registro
        )

    sv.suavizar_trayectorias = sustituto
    try:
        procesar_desde_cache(cfg)
    finally:
        sv.suavizar_trayectorias = original
    pickle.dump({"info": info, "pasos_v2": registro}, open(d / "control.pkl", "wb"))
    return info


def correr(args) -> None:
    trabajo = Path(args.trabajo)
    patas = list(PATAS) if args.pata == "ambas" else [args.pata]
    for pata in patas:
        for variante in VARIANTES:
            pasada(pata, variante, trabajo)
            print(f"✓ {pata} {variante}", flush=True)


# ─────────────────────────────── la medición ──────────────────────────────────
def _ic(dif_por_bloque: dict, pesos: dict, rng) -> tuple[float, float, float]:
    """Diferencia media ponderada y su IC 95 % por remuestreo de bloques."""
    claves = sorted(dif_por_bloque)
    d = np.array([dif_por_bloque[k] for k in claves])
    w = np.array([pesos[k] for k in claves], dtype=float)
    punto = float((d * w).sum() / w.sum())
    boots = []
    for _ in range(CRITERIO["n_boot"]):
        idx = rng.integers(0, len(claves), len(claves))
        boots.append(float((d[idx] * w[idx]).sum() / w[idx].sum()))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return punto, float(lo), float(hi)


def _franja(valor, franjas):
    for k, (a, b) in enumerate(franjas):
        if a <= valor < b:
            return k
    return None


def medir_pata(pata: str, trabajo: Path) -> dict:
    import pandas as pd
    import yaml

    from src.evaluation.desglose_error import (
        casar_frame,
        conjunto_del_equipo,
        conjunto_gt,
        equipo_de_etiqueta,
        error_de_conjunto,
    )
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat
    from src.tracking.cache_io import cargar_cache
    from src.tracking.resolucion import ResolucionCampo

    rng = np.random.default_rng(CRITERIO["semilla"])
    cp = PATAS[pata]
    cfg = yaml.safe_load(open(R / cp["config"]))
    H = np.load(R / cfg["rutas"]["homografia"])
    datos = cargar_cache(R / cfg["rutas"]["cache"])
    fps = float(datos["fps"])
    dets = {
        e["frame_idx"]: np.array([(d[0], d[1]) for d in e["dets"]])
        for e in datos["cache"]
    }
    res = ResolucionCampo(H, cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"])
    gt = gt_a_por_frame(parsear_cvat(R / cp["gt"]), H, cp["offset"], cp["paso_gt"])
    bloque = lambda f: int(f // (CRITERIO["bloque_s"] * fps))  # noqa: E731
    por_x = cp["franjas_por"] == "x"
    fr_t = CRITERIO["franjas_temblor_x" if por_x else "franjas_temblor_mpp"]
    fr_c = CRITERIO["franjas_cortes_x" if por_x else "franjas_cortes_mpp"]

    csv = {v: pd.read_csv(trabajo / pata / v / "posiciones.csv") for v in VARIANTES}
    ctl = {
        v: pickle.load(open(trabajo / pata / v / "control.pkl", "rb"))
        for v in VARIANTES
    }

    # ── controles exactos ──
    filas_id = {v: csv[v].groupby("id_jugador").size().to_dict() for v in VARIANTES}
    huellas = {v: ctl[v]["info"].get("entrada") for v in VARIANTES if v != "B1"}
    controles = {
        "filas_por_id_igual_que_B0": {
            v: filas_id[v] == filas_id["B0"] for v in VARIANTES
        },
        "entrada_al_suavizado_identica": len(set(huellas.values())) == 1,
    }

    def lejos(df):
        reales = df[df.es_real == 1]
        dist = []
        for r in reales.itertuples():
            D = dets.get(r.frame)
            dist.append(np.inf if D is None or not len(D) else
                        float(np.min(np.hypot(D[:, 0] - r.x_m, D[:, 1] - r.y_m))))  # fmt: skip
        out = reales[["frame", "id_jugador", "x_m", "y_m"]].copy()
        out["lejos"] = np.array(dist) > CRITERIO["lejos_de_deteccion_m"]
        out["franja"] = [
            _franja(x if por_x else res.metros_por_pixel((x, y)), fr_t)
            for x, y in zip(out.x_m, out.y_m)
        ]
        return out.set_index(["frame", "id_jugador"])

    def centroides(df):
        reales = df[df.es_real == 1]
        porf = {f: g for f, g in reales.groupby("frame")}
        out = {}
        for f in sorted(gt):
            g = porf.get(f)
            if g is None:
                continue
            personas = [(equipo_de_etiqueta(o.team), o.pos[0], o.pos[1]) for o in gt[f]
                        if equipo_de_etiqueta(o.team) in ("A", "B")]  # fmt: skip
            fc = casar_frame(f, personas, g.x_m.to_numpy(), g.y_m.to_numpy(),
                             g.etiqueta.to_numpy(), CRITERIO["radio_casado_m"])  # fmt: skip
            for eq in ("A", "B"):
                P, V = conjunto_del_equipo(fc, eq), conjunto_gt(fc, eq)
                if len(P) and len(V):
                    out[(f, eq)] = error_de_conjunto(P, V)
        return out

    def temblor(df):
        """σ ≈ MAD(Δ²)/√6 por identidad y franja (el estimador de scripts/temblor.py)."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "temblor", R / "scripts/temblor.py"
        )
        tb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tb)
        RAIZ6, sigma_robusta = tb.RAIZ6, tb.sigma_robusta

        out = {}
        reales = df[df.es_real == 1].sort_values("frame")
        for ident, g in reales.groupby("id_jugador"):
            P = g[["x_m", "y_m"]].to_numpy()
            if len(P) < 5:
                continue
            d2 = P[2:] - 2 * P[1:-1] + P[:-2]
            fr = [_franja(x if por_x else res.metros_por_pixel((x, y)), fr_t)
                  for x, y in P[1:-1]]  # fmt: skip
            fr = np.array([-1 if f is None else f for f in fr])
            for k in range(len(fr_t)):
                sel = fr == k
                if sel.sum() >= 4:
                    sx = sigma_robusta(d2[sel, 0]) / RAIZ6
                    sy = sigma_robusta(d2[sel, 1]) / RAIZ6
                    out[(ident, k)] = float(np.hypot(sx, sy))
        return out

    def pasos_imposibles(df):
        """Por fila pintada (real o interpolada): ¿el paso desde la anterior supera v_umbral?"""
        out = {}
        for ident, g in df.sort_values("frame").groupby("id_jugador"):
            P, F = g[["x_m", "y_m"]].to_numpy(), g.frame.to_numpy()
            for k in range(1, len(P)):
                dt_s = (F[k] - F[k - 1]) / fps
                if dt_s <= 0:
                    continue
                v = float(np.linalg.norm(P[k] - P[k - 1])) / dt_s
                out[(F[k], ident)] = v > umbral_local((P[k] + P[k - 1]) / 2, dt_s, res)
        return out

    base = {
        "lejos": lejos(csv["B0"]),
        "cent": centroides(csv["B0"]),
        "temb": temblor(csv["B0"]),
        "pasos": pasos_imposibles(csv["B0"]),
    }
    resultado = {"controles": controles, "variantes": {}}
    for v in VARIANTES[1:]:
        m = {}
        L = lejos(csv[v])
        # 1. filas reales a > 1 m de toda detección (todas y por franja), pareadas por fila
        for nombre, sel in [("todas", None)] + [
            (f"franja{k}", k) for k in range(len(fr_t))
        ]:
            a = (
                base["lejos"]
                if sel is None
                else base["lejos"][base["lejos"].franja == sel]
            )
            b = L.reindex(a.index)
            dif = (b.lejos.astype(float) - a.lejos.astype(float)).groupby(
                [bloque(f) for f in a.index.get_level_values(0)]
            )
            m[f"1_lejos_{nombre}"] = {
                "B0": float(a.lejos.mean()),
                "V": float(b.lejos.mean()),
                "dif_IC": _ic(dif.mean().to_dict(), dif.size().to_dict(), rng),
            }
        # 3 y 6. centroide, anchura y profundidad contra el GT, por (frame, equipo)
        C = centroides(csv[v])
        comunes = sorted(set(C) & set(base["cent"]))
        for clave in ("centroide", "ancho", "prof"):
            difb, pes = {}, {}
            for f, eq in comunes:
                b_ = bloque(f)
                difb.setdefault(b_, []).append(
                    C[(f, eq)][clave] - base["cent"][(f, eq)][clave]
                )
            dmed = {k: float(np.mean(x)) for k, x in difb.items()}
            pes = {k: len(x) for k, x in difb.items()}
            m[f"3_6_{clave}"] = {
                "B0": float(np.mean([base["cent"][c][clave] for c in comunes])),
                "V": float(np.mean([C[c][clave] for c in comunes])),
                "dif_IC": _ic(dmed, pes, rng),
            }
        # 4. temblor por franja, pareado por identidad, remuestreo por identidades
        T = temblor(csv[v])
        for k in range(len(fr_t)):
            claves = [c for c in base["temb"] if c[1] == k and c in T]
            dif = {c[0]: T[c] - base["temb"][c] for c in claves}
            m[f"4_temblor_franja{k}"] = {
                "B0": (
                    float(np.median([base["temb"][c] for c in claves]))
                    if claves
                    else None
                ),
                "V": float(np.median([T[c] for c in claves])) if claves else None,
                "dif_IC": _ic(dif, {c: 1 for c in dif}, rng) if dif else None,
            }
        # 5. pasos por encima de su umbral local en lo pintado
        Pv = pasos_imposibles(csv[v])
        comunes_p = [c for c in base["pasos"] if c in Pv]
        difb = {}
        for f, ident in comunes_p:
            difb.setdefault(bloque(f), []).append(
                float(Pv[(f, ident)]) - base["pasos"][(f, ident)]
            )
        m["5_pasos_sobre_umbral"] = {
            "B0": float(np.mean([base["pasos"][c] for c in comunes_p])),
            "V": float(np.mean([Pv[c] for c in comunes_p])),
            "dif_IC": _ic({k: float(np.mean(x)) for k, x in difb.items()},
                          {k: len(x) for k, x in difb.items()}, rng),  # fmt: skip
        }
        # tasa de cortes de V2/V3 por franja (el control de «¿corta temblor?»)
        if v in ("V2", "V3"):
            pasos = ctl[v]["pasos_v2"]
            tasas = []
            for k, (a, b) in enumerate(fr_c):
                sel = [p for p in pasos if a <= (p[0] if por_x else p[1]) < b]
                tasas.append((len(sel), sum(p[2] for p in sel)))
            m["cortes_por_franja"] = [
                {
                    "franja": list(fr_c[k]),
                    "pasos": n,
                    "cortes": c,
                    "tasa": c / n if n else None,
                }
                for k, (n, c) in enumerate(tasas)
            ]
            t1, tf = (
                m["cortes_por_franja"][1]["tasa"],
                m["cortes_por_franja"][-1]["tasa"],
            )
            m["corta_ruido"] = bool(
                t1 is not None and tf is not None
                and tf > CRITERIO["cortes_fondo_max_factor"] * t1
            )  # fmt: skip
        # 2. (benjamín) pérdidas de la etapa e de la traza a 5 m: las etapas a-d no dependen del
        # suavizado, así que se reutilizan las de B0 (scripts/traza_por_etapas.py pasada)
        if pata == "benja" and (trabajo / "benja" / "traza" / "etapas.pkl").exists():
            m["2_perdidas_etapa_e"] = _perdidas_e(
                trabajo, csv["B0"], csv[v], gt, bloque, rng
            )
        # 7. (Villaviciosa) IDF1 y AssA del banco, IC por jackknife de bloques de 5 s
        if pata == "villa":
            m["7_idf1_assa"] = _idf1_assa(csv["B0"], csv[v], gt, bloque)
        resultado["variantes"][v] = m
    return resultado


def _perdidas_e(trabajo, csv_b0, csv_v, gt, bloque, rng):
    """Personas casadas en la etapa d que el CSV no cubre a ≤ 5 m (la etapa e de la traza)."""
    import importlib.util

    from src.evaluation.desglose_error import casar_frame

    spec = importlib.util.spec_from_file_location(
        "traza", R / "scripts/traza_por_etapas.py"
    )
    tz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tz)
    capt = pickle.load(open(trabajo / "benja" / "traza" / "etapas.pkl", "rb"))
    crudas = capt.get("crudas", {})

    def perdidas(csv):
        out = {}
        for f in sorted(gt):
            gtf = [("X", o.pos[0], o.pos[1]) for o in gt[f]]
            pts = tz._puntos_por_etapa(capt, crudas, csv, f)
            vivo = {}
            for etapa in ("d_etiqueta", "e_csv"):
                x, y = pts[etapa]
                fc = casar_frame(
                    f, gtf, x, y, np.array(["A"] * len(x)), CRITERIO["radio_traza_m"]
                )
                vivo[etapa] = [p.fila is not None for p in fc.personas]
            out[f] = sum(
                1 for d, e in zip(vivo["d_etiqueta"], vivo["e_csv"]) if d and not e
            )
        return out

    a, b = perdidas(csv_b0), perdidas(csv_v)
    difb = {}
    for f in a:
        difb.setdefault(bloque(f), []).append(b[f] - a[f])
    return {
        "B0": int(sum(a.values())),
        "V": int(sum(b.values())),
        "dif_IC_por_frame": _ic({k: float(np.mean(x)) for k, x in difb.items()},
                                {k: len(x) for k, x in difb.items()}, rng),  # fmt: skip
    }


def _idf1_assa(csv_b0, csv_v, gt, bloque):
    """IDF1 (propio, 2 m) y AssA/IDF1 de TrackEval; Δ con IC 95 % por jackknife de bloques."""
    import tempfile

    from src.evaluation.metricas import calcular_metricas_tracking
    from src.evaluation.modelo import Observacion
    from src.evaluation.trackeval_runner import evaluar_con_trackeval

    def pred_de(csv):
        porf = {f: g for f, g in csv.groupby("frame")}
        return {
            f: [
                Observacion(
                    int(r.id_jugador), np.array([r.x_m, r.y_m]), str(r.etiqueta)
                )
                for r in porf.get(f, csv.iloc[0:0]).itertuples()
            ]  # fmt: skip
            for f in gt
        }

    def metricas(pred, frames):
        propias = calcular_metricas_tracking(
            gt, pred, frames, CRITERIO["radio_casado_m"]
        )
        with tempfile.TemporaryDirectory(prefix="trackeval_") as tmp:
            te = evaluar_con_trackeval(gt, pred, frames, tmp, 2.0)
        return {"IDF1_propio": propias.idf1, "IDF1": te["IDF1"], "AssA": te["AssA"]}

    pa, pb = pred_de(csv_b0), pred_de(csv_v)
    frames = sorted(gt)
    total_a, total_b = metricas(pa, frames), metricas(pb, frames)
    bloques = sorted({bloque(f) for f in frames})
    jk = {k: [] for k in total_a}
    for bq in bloques:
        sub = [f for f in frames if bloque(f) != bq]
        ma, mb = metricas(pa, sub), metricas(pb, sub)
        for k in jk:
            jk[k].append(mb[k] - ma[k])
    out = {}
    n = len(bloques)
    for k in total_a:
        d = total_b[k] - total_a[k]
        se = float(
            np.sqrt((n - 1) / n * np.sum((np.array(jk[k]) - np.mean(jk[k])) ** 2))
        )
        out[k] = {
            "B0": total_a[k],
            "V": total_b[k],
            "dif_IC": (d, d - 1.96 * se, d + 1.96 * se),
        }
    return out


def medir(args) -> None:
    trabajo = Path(args.trabajo)
    out = {p: medir_pata(p, trabajo) for p in PATAS if (trabajo / p / "B0").exists()}
    (trabajo / "resultado.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False)
    )
    print(json.dumps(out, indent=1, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("correr")
    c.add_argument("--trabajo", required=True)
    c.add_argument("--pata", default="ambas", choices=["benja", "villa", "ambas"])
    m = sub.add_parser("medir")
    m.add_argument("--trabajo", required=True)
    args = ap.parse_args()
    correr(args) if args.cmd == "correr" else medir(args)


if __name__ == "__main__":
    main()
