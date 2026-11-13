#!/usr/bin/env python
"""Línea base de la misión (docs/registro_mision.md): lo que VE la pizarra, y de dónde sale.

Mide sobre un CSV de posiciones lo mismo que dibuja `replay_tactico` (sus filtros y su regla de
interpolación, simulada a 10 Hz), SIN histéresis visual: tiene que ser estable el dato, no el
dibujo.

Criterios de presentación de la misión (los de exactitud necesitan verdad de referencia):
1. cambios de color A↔B por minuto;
2. saltos de una ficha > 3 m en 0,2 s y p99 de la velocidad de las fichas;
3. apariciones/desapariciones por minuto dentro de la zona visible, y fichas simultáneas por equipo.

Y la CONCILIACIÓN: cada cambio de color y cada salto, clasificado por su origen en los DATOS (filas
reales o interpoladas, hueco entre filas, categoría de etiqueta).

«Zona visible»: sin modelo de cámara aquí, es el interior del campo a ≥ `--margen-visible` m de las
líneas (una ficha que nace o muere pegada a la línea puede ser una entrada o salida real del plano).
Es un PROXY: en el F7 del benjamín la cámara no ve la franja cercana, y ahí sobrecuenta.

Uso:
    python scripts/linea_base_mision.py --csv data/tracking_alevinb/posiciones_alevinb_p1.csv \\
        --largo 100 --ancho 64 --por-equipo 11 --desde 600 --hasta 900
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.report.replay_tactico import (  # noqa: E402
    _filtrar_creible,
    _filtrar_fuera_del_campo,
)

PASO_S = 0.1  # la pizarra se muestrea a 10 Hz
MAX_HUECO_S = 3.0  # `max_hueco_s` por defecto de generar_replay
COLA_S = 0.25  # una ficha se ve hasta 0,25 s después de su última muestra
EQUIPO = {"A": "A", "portero_A": "A", "B": "B", "portero_B": "B"}


def lo_que_pinta(csv: Path, largo: float, ancho: float, desde, hasta) -> pd.DataFrame:
    """Las filas que la pizarra usa de verdad: sus dos filtros, con sus valores por defecto."""
    df = pd.read_csv(csv)
    df = df[df.etiqueta != "balon"] if "etiqueta" in df else df
    df = _filtrar_fuera_del_campo(df, largo, ancho)
    df = _filtrar_creible(df, 0.6, 2.0)
    if desde is not None:
        df = df[(df.tiempo_s >= desde - 5) & (df.tiempo_s <= hasta + 5)]
    return df.sort_values(["id_jugador", "tiempo_s"]).reset_index(drop=True)


def simular(df: pd.DataFrame, desde: float, hasta: float) -> dict:
    """{id: (visible[T], x[T], y[T], etiqueta[T], hueco_s[T])} en la rejilla de 10 Hz."""
    rejilla = np.arange(desde, hasta, PASO_S)
    fichas = {}
    for ident, g in df.groupby("id_jugador"):
        t = g.tiempo_s.to_numpy()
        x, y = g.x_m.to_numpy(), g.y_m.to_numpy()
        et = g.etiqueta.to_numpy()
        i = np.searchsorted(t, rejilla, side="right") - 1
        con = i >= 0
        i0 = np.clip(i, 0, len(t) - 1)
        i1 = np.clip(i0 + 1, 0, len(t) - 1)
        ultimo = i0 == len(t) - 1
        dt = t[i1] - t[i0]
        visible = con & np.where(ultimo, rejilla - t[i0] <= COLA_S, dt <= MAX_HUECO_S)
        if not visible.any():
            continue
        f = np.where(
            ultimo | (dt <= 0), 0.0, (rejilla - t[i0]) / np.where(dt > 0, dt, 1)
        )
        fichas[ident] = (
            visible,
            x[i0] + f * (x[i1] - x[i0]),
            y[i0] + f * (y[i1] - y[i0]),
            et[i0],
            np.where(ultimo, 0.0, dt),
        )
    return {"rejilla": rejilla, "fichas": fichas}


def medir(sim: dict, largo, ancho, por_equipo: int, margen_visible: float) -> dict:
    rejilla, fichas = sim["rejilla"], sim["fichas"]
    minutos = (rejilla[-1] - rejilla[0] + PASO_S) / 60.0
    cambios_ab = cambios_color = 0
    saltos = saltos_en_hueco = eventos = 0
    velocidades = []
    simult = {"A": np.zeros(len(rejilla), int), "B": np.zeros(len(rejilla), int)}
    distintas = {"A": 0, "B": 0}
    for vis, x, y, et, hueco in fichas.values():
        eq = np.array([EQUIPO.get(e, "") for e in et])
        for e in ("A", "B"):
            m = vis & (eq == e)
            simult[e] += m
            distintas[e] += bool(m.any())
        seguidas = vis[1:] & vis[:-1]
        cambios_color += int((seguidas & (et[1:] != et[:-1])).sum())
        cambios_ab += int(
            (seguidas & (eq[1:] != eq[:-1]) & (eq[1:] != "") & (eq[:-1] != "")).sum()
        )
        paso = np.hypot(np.diff(x), np.diff(y))
        velocidades.append(paso[seguidas] / PASO_S)
        # salto: > 3 m en 0,2 s (dos pasos de rejilla), episodios seguidos contados una vez
        d2 = np.hypot(x[2:] - x[:-2], y[2:] - y[:-2])
        es_salto = (d2 > 3.0) & vis[2:] & vis[1:-1] & vis[:-2]
        inicio = es_salto & ~np.r_[False, es_salto[:-1]]
        saltos += int(inicio.sum())
        saltos_en_hueco += int((inicio & (hueco[1:-1] > 0.25)).sum())
        # aparición / desaparición dentro de la zona visible (sin los bordes de la ventana)
        cambia = np.flatnonzero(vis[1:] != vis[:-1])
        for k in cambia:
            j = k + 1 if vis[k + 1] else k  # la muestra visible del lado del evento
            if (
                margen_visible <= x[j] <= largo - margen_visible
                and margen_visible <= y[j] <= ancho - margen_visible
            ):
                eventos += 1
    v = np.concatenate(velocidades) if velocidades else np.zeros(1)
    return {
        "minutos": round(minutos, 2),
        "fichas": len(fichas),
        "cambios_AB_por_min": round(cambios_ab / minutos, 1),
        "cambios_de_color_por_min": round(cambios_color / minutos, 1),
        "saltos_3m_en_02s_por_min": round(saltos / minutos, 2),
        "saltos_dentro_de_un_hueco_pct": round(
            100 * saltos_en_hueco / max(saltos, 1), 1
        ),
        "velocidad_p50_p95_p99_ms": [
            round(float(np.percentile(v, q)), 1) for q in (50, 95, 99)
        ],
        "eventos_por_min": round(eventos / minutos, 1),
        "fichas_distintas_A_B": [distintas["A"], distintas["B"]],
        "simultaneas": {
            e: {
                "p50": int(np.percentile(s, 50)),
                "p95": int(np.percentile(s, 95)),
                "max": int(s.max()),
                f"pct_mas_de_{por_equipo}": round(
                    100 * float((s > por_equipo).mean()), 1
                ),
            }
            for e, s in simult.items()
        },
    }


def conciliar(df: pd.DataFrame, desde: float, hasta: float) -> dict:
    """De dónde sale cada cambio de color y cada salto, en las FILAS que la pizarra usa."""
    d = df[(df.tiempo_s >= desde) & (df.tiempo_s < hasta)]
    mismo = d.id_jugador.to_numpy()[1:] == d.id_jugador.to_numpy()[:-1]
    et = d.etiqueta.to_numpy()
    real = d.es_real.to_numpy()
    t = d.tiempo_s.to_numpy()
    paso_m = np.hypot(np.diff(d.x_m.to_numpy()), np.diff(d.y_m.to_numpy()))
    dt = np.diff(t)
    minutos = (hasta - desde) / 60.0
    cambia = mismo & (et[1:] != et[:-1])
    eq0 = np.array([EQUIPO.get(e, "") for e in et[:-1]])
    eq1 = np.array([EQUIPO.get(e, "") for e in et[1:]])
    ab = cambia & (eq0 != eq1) & (eq0 != "") & (eq1 != "")
    rr = (real[1:] == 1) & (real[:-1] == 1)
    seguidas = dt <= np.nanmedian(dt[mismo]) * 1.5
    rapido = mismo & (dt > 0) & (paso_m / np.where(dt > 0, dt, 1) > 15.0)
    vida = d.groupby("id_jugador").tiempo_s.agg(lambda s: s.max() - s.min())
    por_frame = d[d.es_real == 1].groupby("frame").size()
    return {
        "filas": len(d),
        "filas_interpoladas_pct": round(100 * float((d.es_real == 0).mean()), 1),
        "cambios_de_etiqueta_por_min": round(float(cambia.sum()) / minutos, 1),
        "cambios_AB_por_min": {
            "total": round(float(ab.sum()) / minutos, 1),
            "real_a_real": round(float((ab & rr).sum()) / minutos, 1),
            "con_fila_interpolada": round(float((ab & ~rr).sum()) / minutos, 1),
        },
        "cambios_con_portero_otro_staff_por_min": round(
            float((cambia & ~ab).sum()) / minutos, 1
        ),
        "pasos_a_mas_de_15ms_por_min": {
            "total": round(float(rapido.sum()) / minutos, 1),
            "entre_filas_seguidas": round(
                float((rapido & seguidas).sum()) / minutos, 1
            ),
            "a_traves_de_un_hueco": round(
                float((rapido & ~seguidas).sum()) / minutos, 1
            ),
            "entre_dos_reales": round(float((rapido & rr).sum()) / minutos, 1),
        },
        "identidades": int(d.id_jugador.nunique()),
        "identidades_por_min": round(d.id_jugador.nunique() / minutos, 1),
        "vida_identidad_s_p25_p50_p75": [
            round(float(vida.quantile(q)), 1) for q in (0.25, 0.5, 0.75)
        ],
        "filas_reales_por_frame_p10_p50_p90": [
            int(por_frame.quantile(q)) for q in (0.1, 0.5, 0.9)
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--largo", type=float, required=True)
    ap.add_argument("--ancho", type=float, required=True)
    ap.add_argument("--por-equipo", type=int, required=True, help="11 en F11, 7 en F7")
    ap.add_argument("--desde", type=float, default=None)
    ap.add_argument("--hasta", type=float, default=None)
    ap.add_argument("--margen-visible", type=float, default=2.0)
    ap.add_argument("--salida", type=Path, default=None)
    a = ap.parse_args()
    import logging

    logging.basicConfig(level=logging.ERROR)
    df = lo_que_pinta(a.csv, a.largo, a.ancho, a.desde, a.hasta)
    desde = a.desde if a.desde is not None else float(df.tiempo_s.min())
    hasta = a.hasta if a.hasta is not None else float(df.tiempo_s.max())
    res = {
        "csv": str(a.csv),
        "tramo_s": [desde, hasta],
        "pizarra": medir(
            simular(df, desde, hasta), a.largo, a.ancho, a.por_equipo, a.margen_visible
        ),
        "datos": conciliar(df, desde, hasta),
    }
    texto = json.dumps(res, indent=1, ensure_ascii=False)
    if a.salida:
        a.salida.parent.mkdir(parents=True, exist_ok=True)
        a.salida.write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
