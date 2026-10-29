#!/usr/bin/env python
"""Conciliar los cambios de color de la pizarra con los de los datos, y una pizarra SIN identidades.
Criterios en `docs/pizarra_sin_identidades.md`. SOLO mide y dibuja; los CSV de datos no se tocan.

Uso:
    python scripts/pizarra_sin_identidades.py conciliar
    python scripts/pizarra_sin_identidades.py pizarra
"""

import argparse
import hashlib
import importlib.util
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/pizarra_sin_identidades"
BASE_HTML = R / "outputs/etiqueta_por_trozos_intento1/base.html"
BASE_CSV = R / "outputs/etiqueta_por_trozos_intento1/base.csv"
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
CSV_MAIN = R / "outputs/diagnostico_26oct_b/posiciones_main.csv"
CSV_PARTE = R / "data/tracking_benja/posiciones_benja_p1.csv"
CAMPO = R / "configs/campo_benja.yaml"
META = R / "outputs/diagnostico_26oct_b/posiciones_main_meta.json"
FPS = 29.97002997002997
TRAMO = (840.0, 930.0)
CASADO_M = 1.0
ESTELA_S = 0.4


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def categoria(a: str, b: str) -> str:
    par = {str(a), str(b)}
    if "staff" in par:
        return "con staff"
    if "otro" in par:
        return "con otro"
    if any(p.startswith("portero") for p in par):
        return "con portero"
    return "A <-> B"


# ── 1. conciliar ─────────────────────────────────────────────────────────────────────────────


def conciliar() -> dict:
    from src.campo_modelo import cargar_modelo
    from src.report.replay_tactico import _filtrar_creible, _filtrar_fuera_del_campo

    fp = _mod("fichas_pizarra")
    t0, t1 = TRAMO
    # (a) el simulador sobre la pizarra base
    datos, cat = fp.leer_pizarra(BASE_HTML)
    Ts = np.arange(t0, t1, fp.PASO_S)
    F = [
        f
        for f in fp.simular(datos, cat, Ts)
        if not str(f["col"][0]).startswith("balon")
    ]
    sim = sum(
        int((f["vis"][1:] & f["vis"][:-1] & (f["col"][1:] != f["col"][:-1])).sum())
        for f in F
    )
    # (b) el CSV que usa la pizarra, con SUS filtros (parámetros por defecto de generar_replay)
    modelo = cargar_modelo(config=str(CAMPO))
    df = pd.read_csv(BASE_CSV)
    n0 = len(df)
    df = _filtrar_fuera_del_campo(df, modelo.largo, modelo.ancho)
    df = _filtrar_creible(df, 0.6, 2.0)
    cap = pickle.load(open(CAPTURA, "rb"))
    voto = {int(i): str(e) for i, e in cap["voto"].items()}
    filas = Counter()
    por_tipo = Counter()
    por_cat = Counter()
    por_ident = Counter()
    for i, g in df.sort_values("tiempo_s").groupby("id_jugador"):
        g = g[(g.tiempo_s >= t0 - 0.1) & (g.tiempo_s < t1)]
        e = g.etiqueta.astype(str).to_numpy()
        r = g.es_real.to_numpy() == 1
        for k in np.where(e[1:] != e[:-1])[0]:
            filas["cambios"] += 1
            por_tipo["real -> real" if r[k] and r[k + 1] else "con interpolada"] += 1
            por_cat[categoria(e[k], e[k + 1])] += 1
            por_ident[
                (
                    "identidad A/B"
                    if voto.get(int(i)) in ("A", "B")
                    else f"identidad {voto.get(int(i))}"
                )
            ] += 1
    # (c) el 51: A <-> B, real -> real, identidades A/B
    cruz = Counter()
    for i, g in df.sort_values("tiempo_s").groupby("id_jugador"):
        g = g[(g.tiempo_s >= t0 - 0.1) & (g.tiempo_s < t1)]
        e = g.etiqueta.astype(str).to_numpy()
        r = g.es_real.to_numpy() == 1
        ab = voto.get(int(i)) in ("A", "B")
        for k in np.where(e[1:] != e[:-1])[0]:
            real = r[k] and r[k + 1]
            c = categoria(e[k], e[k + 1])
            if not real:
                cruz["1 interpolación (alguna fila interpolada)"] += 1
            elif not ab:
                cruz["2 identidad portero/staff/otro (real -> real)"] += 1
            elif c != "A <-> B":
                cruz[f"3 identidad A/B, real -> real, {c}"] += 1
            else:
                cruz["4 identidad A/B, real -> real, A <-> B (el 51)"] += 1
    # (d) las filas reales que la pizarra QUITA (fuera del campo o efímeras) y el cambio de datos
    datos_reales = 0
    d0 = pd.read_csv(CSV_MAIN)
    d0 = d0[(d0.es_real == 1) & (d0.tiempo_s >= t0) & (d0.tiempo_s < t1)]
    for i, g in d0.sort_values("frame").groupby("id_jugador"):
        if voto.get(int(i)) not in ("A", "B"):
            continue
        e = g.etiqueta.astype(str).to_numpy()
        for k in np.where(e[1:] != e[:-1])[0]:
            if categoria(e[k], e[k + 1]) == "A <-> B":
                datos_reales += 1
    ids_unicos = all(
        len(set(d["id"] if isinstance(d["id"], list) else [d["id"]])) == 1
        for d in datos
    )
    return {
        "simulador_cambios_en_el_tramo": sim,
        "simulador_por_minuto": round(sim / 1.5, 1),
        "csv_de_la_pizarra_tras_sus_filtros": {
            "filas_antes": n0,
            "filas_despues": len(df),
        },
        "cambios_entre_filas_seguidas_del_csv_pintado": filas["cambios"],
        "por_tipo_de_fila": dict(por_tipo),
        "por_categoria": dict(por_cat),
        "por_identidad": dict(por_ident),
        "puente": dict(sorted(cruz.items())),
        "A_B_real_real_identidades_AB_en_el_CSV_de_datos_sin_filtros": datos_reales,
        "ficha_que_pasa_a_otra_fila": 0 if ids_unicos else "revisar",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["conciliar", "pizarra"])
    args = ap.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)
    antes = {p.name: _sha(p) for p in (CSV_MAIN, CSV_PARTE)}
    res = {"conciliar": conciliar, "pizarra": pizarra}[args.accion]()
    res["csv_de_datos_identicos"] = antes == {
        p.name: _sha(p) for p in (CSV_MAIN, CSV_PARTE)
    }
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=float)
    (SALIDA / f"{args.accion}.json").write_text(texto)
    print(texto)


def puntos_del_tramo() -> tuple[list, int]:
    """[(frame, [(x, y, etiqueta), ...]), ...] de las detecciones asignadas, y las no asignadas."""
    cap = pickle.load(open(CAPTURA, "rb"))
    cache = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    t0, t1 = TRAMO
    por_frame, asignadas = {}, set()
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            f, k = int(f), int(k)
            if not (t0 * FPS <= f < t1 * FPS):
                continue
            d = cache[f][k]
            et = str(cap["final"].get((i, f)) or cap["voto"].get(i, "otro"))
            por_frame.setdefault(f, []).append((float(d[0]), float(d[1]), et))
            asignadas.add((f, k))
    sin_asignar = sum(
        1
        for f, dets in cache.items()
        if t0 * FPS <= f < t1 * FPS
        for k in range(len(dets))
        if (f, k) not in asignadas
    )
    return sorted(por_frame.items()), sin_asignar


def cambios_visibles(frames: list) -> dict:
    """Un punto que cambia de color respecto al más cercano del frame anterior a < 1 m."""
    cambios = nuevos = vecino_equivocado = total = 0
    for (_f0, ant), (_f1, act) in zip(frames[:-1], frames[1:]):
        A = np.array([(x, y) for x, y, _e in ant])
        ea = [e for _x, _y, e in ant]
        for x, y, e in act:
            total += 1
            d = np.hypot(A[:, 0] - x, A[:, 1] - y)
            j = int(np.argmin(d))
            if d[j] >= CASADO_M:
                nuevos += 1
                continue
            if ea[j] != e:
                cambios += 1
                # ¿había a < 1 m un punto de SU color, y se casó con el vecino equivocado?
                if any(ea[k] == e and d[k] < CASADO_M for k in range(len(ea))):
                    vecino_equivocado += 1
    minutos = (TRAMO[1] - TRAMO[0]) / 60
    return {
        "cambios_visibles": cambios,
        "cambios_visibles_por_minuto": round(cambios / minutos, 1),
        "de_ellos_con_un_punto_de_su_color_a_<1m": vecino_equivocado,
        "puntos_sin_pareja_a_<1m_por_minuto": round(nuevos / minutos, 1),
        "puntos": total,
        "criterio_<=17_por_minuto": cambios / minutos <= 17,
    }


PLANTILLA = R / "scripts/plantilla_sin_identidades.html"  # el HTML, aparte del código


def pizarra() -> dict:
    from src.campo_modelo import cargar_modelo
    from src.report.replay_tactico import colores_con_equipos

    frames, sin_asignar = puntos_del_tramo()
    res = cambios_visibles(frames)
    res["detecciones_sin_identidad_(no_se_pintan)"] = sin_asignar
    modelo = cargar_modelo(config=str(CAMPO))
    paleta = colores_con_equipos(json.loads(META.read_text()).get("colores_equipo"))
    colores = {k: v[0] for k, v in paleta.items() if not k.startswith("balon")}
    html = (
        PLANTILLA.read_text()
        .replace(
            "__FRAMES__",
            json.dumps(
                [
                    [f, [[round(a, 2), round(b, 2), e] for a, b, e in p]]
                    for f, p in frames
                ]
            ),
        )
        .replace("__COLORES__", json.dumps(colores))
        .replace("__CAMPO__", json.dumps(modelo.geometria_dibujo()))
        .replace("__LARGO__", str(modelo.largo))
        .replace("__ANCHO__", str(modelo.ancho))
        .replace("__FPS__", str(FPS))
        .replace(
            "__TITULO__",
            "Pizarra SIN identidades · 14:00-15:30 (archivo) · 15:33-17:03 (reproductor)",
        )
    )
    ruta = SALIDA / "pizarra_sin_identidades.html"
    ruta.write_text(html)
    res["html"] = str(ruta)
    return res


if __name__ == "__main__":
    main()
