#!/usr/bin/env python
"""Prueba #4 (segunda opinión): ¿un indicador barato de posesión llega al 80 % en el alevín B?

Plan y criterios, fijados ANTES de ver las etiquetas: `docs/plan_posesion_prueba.md`.

Entrada:
- las marcas de Alex (`posesion_alevinb_3m00_6m00.csv` de la página `outputs/etiquetado_posesion/`):
  instante de inicio de cada fase y su etiqueta (verde / blanco / disputa / parado);
- el CSV de posiciones del alevín B con SigLIP (rama `alevinb-preparacion`), donde A = blanco y
  B = verde (mini-GT a ojo: 45 de 45 blancos con fila A son A);
- las candidatas en bruto del balón (`cache_alevinb_p1_balon.pkl`, 12,5 fps, conf ≥ 0,3, dentro
  del campo; la de más confianza por fotograma).

Indicadores (todos con parámetros fijados antes, ninguno ajustado a las etiquetas):
- T1 «siempre el equipo mayoritario» (el que más tiempo vivo tiene en las etiquetas);
- T2 «el equipo con más jugadores en la mitad del balón» (última posición conocida del balón);
- I1 voto del equipo más cercano al balón a ≤ 2,5 m; ventana sin votos ⇒ se mantiene la anterior;
- I2 HMM de 2 estados (verde / blanco), Viterbi con coste de cambio;
- I3 HMM de 3 estados (verde / blanco / muerto): I2 + evidencia de balón muerto (jugadores
  parados, balón fuera, balón perdido mucho rato);
- I4 = I3 + señal colectiva sin balón: el equipo que empuja hacia la portería rival.
La idea del decodificador de 3 estados y de las pistas de balón muerto viene del repositorio
público 404-Possession-Not-Found (sin licencia: se reimplementa, no se copia código).

Uso:
    python scripts/posesion_prueba.py --marcas ~/Downloads/posesion_alevinb_3m00_6m00.csv \\
        --salida outputs/posesion_prueba
"""

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
CSV = R / "outputs/alevinb_siglip/alevinb/posiciones_siglip.csv"
BALON = R / "data/tracking_alevinb/cache_alevinb_p1_balon.pkl"
INICIO, FIN, LARGO, ANCHO = 180.0, 360.0, 100.0, 64.0
EQUIPO_DE = {"A": "blanco", "portero_A": "blanco", "B": "verde", "portero_B": "verde"}

# ── parámetros fijados ANTES de ver las etiquetas (docs/plan_posesion_prueba.md) ──
P = {
    "radio_voto_m": 2.5,
    "radio_cerca_m": 4.0,  # entre 2,5 y 4 m: evidencia débil (×0,3)
    "ganancia_por_m": 1.0,  # log-razón por metro de ventaja del más cercano
    "tope_llr": 3.0,
    "conf_balon": 0.3,
    "quieta_px": 3.0,
    "quieta_s": 10.0,
    "quieta_n": 25,
    # costes en nats a 12,5 muestras/s: los del repositorio de referencia (12 y 48 a 25 fps, modo
    # reglas) a la mitad, porque con la mitad de muestras la evidencia por segundo es la mitad
    "coste_cambio": 6.0,
    "coste_muerto": 24.0,
    "previa_muerto": -1.5,
    "lentos_ms": 1.0,
    "rapidos_ms": 2.0,
    "ganancia_empuje": 0.5,  # log-razón por m/s de diferencia de empuje entre equipos
}


def fases_por_instante(marcas: pd.DataFrame, t: np.ndarray) -> np.ndarray:
    """Etiqueta verdadera en cada instante t (la de la última marca anterior)."""
    m = marcas.sort_values("t_archivo_s")
    i = np.searchsorted(m.t_archivo_s.to_numpy(), t, side="right") - 1
    return np.where(i >= 0, m.etiqueta.to_numpy()[np.clip(i, 0, None)], "sin_marca")


def quietas(cache: list) -> set:
    """(t, j) de las candidatas QUIETAS: ≥ `quieta_n` veces a ± `quieta_px` px en ± `quieta_s` s.

    La cámara tiembla 0,22 px (docs/segunda_opinion_26nov.md), así que algo que repite píxel durante
    segundos es un objeto parado (un balón junto a la banda), no el balón del partido. Medido antes
    de ver las etiquetas: el 49 % de las candidatas de 3:00-6:00 son quietas, todas fuera del campo.
    """
    pts = [
        (e["t"], j, (d[2] + d[4]) / 2, (d[3] + d[5]) / 2)
        for e in cache
        for j, d in enumerate(e["dets"])
        if d[6] >= P["conf_balon"]
    ]
    if not pts:
        return set()
    a = np.array([(t, u, v) for t, _j, u, v in pts])
    salida = set()
    for t, j, u, v in pts:
        cerca = (
            (np.abs(a[:, 0] - t) <= P["quieta_s"])
            & (np.abs(a[:, 1] - u) <= P["quieta_px"])
            & (np.abs(a[:, 2] - v) <= P["quieta_px"])
        )
        if cerca.sum() >= P["quieta_n"]:
            salida.add((t, j))
    return salida


def cargar_balon() -> pd.DataFrame:
    cache = [
        e
        for e in pickle.load(open(BALON, "rb"))["cache"]
        if INICIO - 15 <= e["t"] < FIN + 15
    ]
    fijas = quietas(cache)
    filas = []
    for e in cache:
        if not (INICIO - 5 <= e["t"] < FIN + 5):
            continue
        validas = [
            d
            for j, d in enumerate(e["dets"])
            if d[6] >= P["conf_balon"] and (e["t"], j) not in fijas
        ]
        dentro = [d for d in validas if 0 <= d[0] <= LARGO and 0 <= d[1] <= ANCHO]
        fuera = [d for d in validas if d not in dentro]
        mejor = max(dentro, key=lambda d: d[6]) if dentro else None
        filas.append(
            (
                e["t"],
                mejor[0] if mejor else np.nan,
                mejor[1] if mejor else np.nan,
                bool(fuera) and not dentro,
            )
        )
    return pd.DataFrame(filas, columns=["t", "bx", "by", "solo_fuera"])


def senales(pos: pd.DataFrame, balon: pd.DataFrame) -> pd.DataFrame:
    """Por cada muestra del balón: distancias del más cercano de cada equipo, velocidad media de
    los jugadores, empuje de cada equipo y recuento por mitad."""
    pos = pos[pos.etiqueta.isin(EQUIPO_DE)].copy()
    pos["equipo_color"] = pos.etiqueta.map(EQUIPO_DE)
    pos = pos.sort_values(["id_jugador", "tiempo_s"])
    dt = pos.groupby("id_jugador").tiempo_s.diff()
    pos["vx"] = pos.groupby("id_jugador").x_m.diff() / dt
    pos["v"] = np.hypot(pos.vx, pos.groupby("id_jugador").y_m.diff() / dt)
    pos.loc[pos.v > 12, ["vx", "v"]] = np.nan  # saltos de identidad, no carreras
    # dirección de ataque: verde (portero en x ≈ 12) ataca hacia x creciente; blanco, al revés
    signo = {"verde": 1.0, "blanco": -1.0}
    tiempos = np.sort(pos.tiempo_s.unique())
    por_t = {t: g for t, g in pos.groupby("tiempo_s")}
    filas, ultima = [], (np.nan, np.nan)
    for b in balon.itertuples():
        g = por_t[tiempos[np.argmin(np.abs(tiempos - b.t))]]
        visto = not np.isnan(b.bx)
        if visto:
            ultima = (b.bx, b.by)
        d = {}
        for e in ("verde", "blanco"):
            ge = g[g.equipo_color == e]
            d[e] = (
                float(np.min(np.hypot(ge.x_m - b.bx, ge.y_m - b.by)))
                if visto and len(ge)
                else np.nan
            )
            d[f"empuje_{e}"] = (
                float(np.nanmean(ge.vx * signo[e])) if len(ge) else np.nan
            )
            mitad = (
                (ge.x_m < LARGO / 2) == (ultima[0] < LARGO / 2)
                if not np.isnan(ultima[0])
                else []
            )
            d[f"mitad_{e}"] = int(np.sum(mitad)) if len(ge) else 0
        filas.append(
            {"t": b.t, "visto": visto, "solo_fuera": b.solo_fuera, "d_verde": d["verde"],
             "d_blanco": d["blanco"], "v_media": float(np.nanmean(g.v)) if len(g) else np.nan,
             **{k: v for k, v in d.items() if k not in ("verde", "blanco")}}
        )  # fmt: skip
    return pd.DataFrame(filas)


def viterbi(em: np.ndarray, trans: np.ndarray) -> np.ndarray:
    n, k = em.shape
    atras = np.zeros((n, k), dtype=int)
    s = em[0].copy()
    for i in range(1, n):
        c = s[:, None] + trans
        atras[i] = c.argmax(axis=0)
        s = c.max(axis=0) + em[i]
    camino = np.empty(n, dtype=int)
    camino[-1] = int(s.argmax())
    for i in range(n - 1, 0, -1):
        camino[i - 1] = atras[i, camino[i]]
    return camino


def log_sig(z):
    return -np.logaddexp(0.0, -z)


def llr_equipo(s: pd.DataFrame) -> np.ndarray:
    """Log-razón verde frente a blanco por la ventaja del más cercano (positivo = verde)."""
    dv, db = s.d_verde.fillna(99).to_numpy(), s.d_blanco.fillna(99).to_numpy()
    cerca = np.minimum(dv, db)
    ventaja = np.clip(P["ganancia_por_m"] * (db - dv), -P["tope_llr"], P["tope_llr"])
    llr = np.zeros(len(s))
    llr[cerca <= P["radio_voto_m"]] = ventaja[cerca <= P["radio_voto_m"]]
    debil = (cerca > P["radio_voto_m"]) & (cerca <= P["radio_cerca_m"])
    llr[debil] = 0.3 * ventaja[debil]
    return llr


def logit_muerto(s: pd.DataFrame) -> np.ndarray:
    z = np.full(len(s), P["previa_muerto"])
    v = s.v_media.fillna(P["rapidos_ms"]).to_numpy()
    z[v < P["lentos_ms"]] += 2.0
    z[(v >= P["lentos_ms"]) & (v < 1.4)] += 1.0
    z[v > P["rapidos_ms"]] -= 1.0
    z[s.solo_fuera.to_numpy()] += 4.0
    # ⚠️ La pista «balón sin ver más de 2 s» del repositorio de referencia NO se usa: allí faltaba
    # el balón el 41 % del tiempo; aquí el 83 %, así que salta casi siempre y no informa (quitada
    # antes de ver las etiquetas: con ella el modelo marcaba «parado» el 53 % del tramo).
    return z


def decodificar(llr: np.ndarray, muerto: np.ndarray | None) -> np.ndarray:
    c, m = P["coste_cambio"], P["coste_muerto"]
    if muerto is None:
        em = np.stack([log_sig(llr), log_sig(-llr)], axis=1)
        trans = np.array([[0.0, -c], [-c, 0.0]])
        return np.array(["verde", "blanco"])[viterbi(em, trans)]
    vivo = log_sig(-muerto)
    em = np.stack([vivo + log_sig(llr), vivo + log_sig(-llr), log_sig(muerto)], axis=1)
    trans = np.array([[0.0, -c, -m], [-c, 0.0, -m], [-m, -m, 0.0]])
    return np.array(["verde", "blanco", "parado"])[viterbi(em, trans)]


def por_ventana(t: np.ndarray, etiquetas: np.ndarray, ancho: float) -> list:
    """La etiqueta mayoritaria de cada ventana [INICIO + k·ancho, ...)."""
    salida = []
    for a in np.arange(INICIO, FIN - 1e-6, ancho):
        sel = etiquetas[(t >= a) & (t < a + ancho)]
        sel = sel[sel != ""]
        salida.append(pd.Series(sel).mode().iloc[0] if len(sel) else "")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--marcas", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    marcas = pd.read_csv(a.marcas)
    pos = pd.read_csv(CSV)
    pos = pos[(pos.tiempo_s >= INICIO - 5) & (pos.tiempo_s < FIN + 5)]
    s = senales(pos, cargar_balon())
    s = s[(s.t >= INICIO) & (s.t < FIN)].reset_index(drop=True)
    t = s.t.to_numpy()
    verdad = fases_por_instante(marcas, t)

    llr = llr_equipo(s)
    voto = np.where(
        np.minimum(s.d_verde.fillna(99), s.d_blanco.fillna(99)) <= P["radio_voto_m"],
        np.where(s.d_verde.fillna(99) < s.d_blanco.fillna(99), "verde", "blanco"),
        "",
    )
    mitad = np.where(s.mitad_verde > s.mitad_blanco, "verde",
                     np.where(s.mitad_blanco > s.mitad_verde, "blanco", ""))  # fmt: skip
    empuje = (s.empuje_verde - s.empuje_blanco).fillna(0).to_numpy()
    llr4 = llr + np.where(llr == 0, P["ganancia_empuje"] * empuje, 0.0)
    indicadores = {
        "T2_mitad_del_balon": mitad,
        "I1_voto_2.5m": voto,
        "I2_hmm_2_estados": decodificar(llr, None),
        "I3_hmm_3_estados": decodificar(llr, logit_muerto(s)),
        "I4_hmm_3_estados_mas_empuje": decodificar(llr4, logit_muerto(s)),
    }
    res = {
        "parametros": P,
        "muestras": len(s),
        "balon_visto_pct": round(100 * s.visto.mean(), 1),
    }
    for ancho in (4.0, 6.0):
        v = por_ventana(t, verdad, ancho)
        vivas = [i for i, x in enumerate(v) if x in ("verde", "blanco")]
        vivo_total = [i for i, x in enumerate(v) if x in ("verde", "blanco", "disputa")]
        mayoritario = pd.Series([v[i] for i in vivas]).mode().iloc[0] if vivas else ""
        r = {"ventanas": len(v), "con_posesion": len(vivas), "disputa": v.count("disputa"),
             "parado": v.count("parado"), "mayoritario": mayoritario}  # fmt: skip
        preds = {"T1_siempre_mayoritario": [mayoritario] * len(v)}
        for k, e in indicadores.items():
            p = por_ventana(t, e, ancho)
            if k == "I1_voto_2.5m":  # ventana sin votos: se mantiene la anterior
                for i in range(1, len(p)):
                    p[i] = p[i] or p[i - 1]
            preds[k] = p
        for k, p in preds.items():
            r[k] = {
                "acierto_con_posesion_pct": round(
                    100 * np.mean([p[i] == v[i] for i in vivas]), 1
                ) if vivas else None,
                "acierto_juego_vivo_con_disputa_pct": round(
                    100 * np.mean([p[i] == v[i] for i in vivo_total]), 1
                ) if vivo_total else None,
                "parado_detectado_pct": round(
                    100 * np.mean([p[i] == "parado" for i, x in enumerate(v) if x == "parado"]), 1
                ) if "parado" in v else None,
            }  # fmt: skip
        res[f"ventana_{ancho:g}s"] = r
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "resultado.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False)
    )
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
