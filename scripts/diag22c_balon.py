#!/usr/bin/env python
"""Diagnóstico 22-oct (c), bloque 1: corte duro del balón (`balon.descartar_fuera_m`).

Criterio en `docs/diagnostico_22oct_c.md`. Compara la pizarra (CSV de `procesar_balon.py`)
y el vídeo (`generar_video_detecciones.balon_activo`) con el flag apagado (= main) y encendido.

Uso:
    python scripts/diag22c_balon.py --base-main outputs/diagnostico_22oct_b/balon_base_main.csv \\
        --csv-off X.csv --csv-on Y.csv --campo-on Z.yaml --salida outputs/diagnostico_22oct_c
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
CSV_JUGADORES = R / "outputs/arbitro_obs/posiciones.csv"
CAMPO = R / "configs/campo_benja.yaml"
PANELES = R / "outputs/diagnostico_22oct/bloque1.json"
CAMPO_DE_AL_LADO = [9306, 9306, 9360, 9738, 10166, 10472, 10474]  # 7 paneles, 6 frames
FPS = 29.97002997002997
DESFASE_REPRODUCTOR_S = 93  # el reproductor de Alex va +1:33


def relojes(frame: int) -> str:
    t = frame / FPS
    r = t + DESFASE_REPRODUCTOR_S
    return f"{int(t // 60)}:{t % 60:04.1f} archivo / {int(r // 60)}:{r % 60:04.1f} reproductor"


def fuera_m(x: float, y: float) -> float:
    from src.balon.tracking_balon import _fuera_del_campo_m

    return _fuera_del_campo_m(x, y, (62.0, 40.0))


def filas_balon(csv: Path) -> pd.DataFrame:
    d = pd.read_csv(csv)
    b = d[d.etiqueta.astype(str).str.startswith("balon")].copy()
    b["fuera"] = [fuera_m(x, y) for x, y in zip(b.x_m, b.y_m)]
    return b


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-main", required=True)
    ap.add_argument("--csv-off", required=True)
    ap.add_argument("--csv-on", required=True)
    ap.add_argument("--campo-on", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()

    spec = importlib.util.spec_from_file_location(
        "gv", R / "scripts/generar_video_detecciones.py"
    )
    gv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gv)
    video_off = gv.balon_activo(CACHE_BALON, CSV_JUGADORES, CAMPO)
    video_on = gv.balon_activo(CACHE_BALON, CSV_JUGADORES, args.campo_on)

    res = {}
    # flag apagado = main
    res["off_identico_a_main_bytes"] = (
        Path(args.csv_off).read_bytes() == Path(args.base_main).read_bytes()
    )

    # cuántos se descartan y la zona ambigua (3-6 m), sobre la selección SIN corte (el vídeo)
    dist_sel = {f: fuera_m(d[0], d[1]) for f, (d, _a) in video_off.items()}
    descartados = sorted(set(video_off) - set(video_on))
    res["seleccion_frames_off_on"] = [len(video_off), len(video_on)]
    res["descartados"] = len(descartados)
    res["descartados_todos_a_mas_de_3m"] = all(dist_sel[f] > 3.0 for f in descartados)
    res["entre_3_y_6_m"] = sum(3.0 < v <= 6.0 for v in dist_sel.values())
    res["a_mas_de_6_m"] = sum(v > 6.0 for v in dist_sel.values())
    res["entre_0_y_3_m"] = sum(0.0 < v <= 3.0 for v in dist_sel.values())
    res["video_on_es_subconjunto_de_off_y_mismas_detecciones"] = set(video_on) <= set(
        video_off
    ) and all(video_on[f][0] == video_off[f][0] for f in video_on)

    # pizarra
    base, on = filas_balon(Path(args.base_main)), filas_balon(Path(args.csv_on))
    res["pizarra_filas_balon_main_on"] = [len(base), len(on)]
    res["pizarra_filas_en_frames_descartados"] = int(on.frame.isin(descartados).sum())
    reales_on = set(on[on.es_real == 1].frame)
    res["pizarra_reales_on_fuera_del_video_on"] = len(reales_on - set(video_on))
    res["pizarra_filas_a_mas_de_3m_main_on"] = [
        int((base.fuera > 3).sum()),
        int((on.fuera > 3).sum()),
    ]
    nuevas = on.merge(
        base[["frame"]].drop_duplicates(), on="frame", how="left", indicator=True
    )
    res["pizarra_frames_nuevos_con_balon_a_mas_de_3m"] = int(
        ((nuevas._merge == "left_only") & (nuevas.fuera > 3)).sum()
    )

    # (3) saques de banda: filas de main a 0-3 m fuera, idénticas fila a fila
    cols = ["frame", "etiqueta", "x_m", "y_m", "es_real"]
    banda = base[(base.fuera > 0) & (base.fuera <= 3)][cols + ["id_jugador"]]
    junt = banda.merge(
        on[cols + ["id_jugador"]],
        on=["frame", "etiqueta"],
        how="left",
        suffixes=("", "_on"),
    )
    iguales = (
        (junt.x_m == junt.x_m_on)
        & (junt.y_m == junt.y_m_on)
        & (junt.es_real == junt.es_real_on)
    )
    res["banda_0_3m_filas_main"] = int(len(banda))
    res["banda_0_3m_identicas"] = int(iguales.sum())
    res["banda_0_3m_cambia_solo_el_id_de_tramo"] = int(
        (iguales & (junt.id_jugador != junt.id_jugador_on)).sum()
    )
    distintas = junt[~iguales]
    res["banda_0_3m_distintas_ejemplos"] = [
        {
            **{
                k: (None if pd.isna(v) else float(v))
                for k, v in r.items()
                if k != "etiqueta"
            },
            "etiqueta": r["etiqueta"],
            "relojes": relojes(int(r["frame"])),
        }
        for r in distintas.head(10).to_dict("records")
    ]

    # paneles
    paneles = json.load(open(PANELES))["1e_paneles"]
    filas = []
    for p in paneles:
        f = p["frame"]

        def estado(video, piz):
            v = video.get(f)
            pv = None if v is None else round(fuera_m(v[0][0], v[0][1]), 1)
            pp = piz[piz.frame == f]
            return pv, [round(x, 1) for x in pp.fuera]

        v_off, p_off = estado(video_off, base)
        v_on, p_on = estado(video_on, on)
        filas.append(
            {
                "panel": p["panel"],
                "frame": f,
                "relojes": relojes(f),
                "campo_de_al_lado": f in CAMPO_DE_AL_LADO,
                "video_fuera_m_main_on": [v_off, v_on],
                "pizarra_fuera_m_main_on": [p_off, p_on],
            }
        )
    res["paneles"] = filas

    def mal(fl):
        v_on, p_on = fl["video_fuera_m_main_on"][1], fl["pizarra_fuera_m_main_on"][1]
        return (v_on is not None and v_on > 3) or any(x > 3 for x in p_on)

    def pierde(fl):
        v_off, v_on = fl["video_fuera_m_main_on"]
        p_off, p_on = fl["pizarra_fuera_m_main_on"]
        return (v_off is not None and v_on is None) or (bool(p_off) and not p_on)

    por_frame = {fl["frame"]: fl for fl in filas}
    res["criterio"] = {
        # los 7 paneles (f9306 cuenta dos veces: salió en dos estratos)
        "1_campo_de_al_lado_que_siguen_mal_(de_7)": sum(
            mal(por_frame[f]) for f in CAMPO_DE_AL_LADO
        ),
        "2_otros_paneles_que_pierden_el_balon": [
            fl["panel"] for fl in filas if not fl["campo_de_al_lado"] and pierde(fl)
        ],
        "3_banda_identica_fila_a_fila": res["banda_0_3m_identicas"]
        == res["banda_0_3m_filas_main"],
    }
    c = res["criterio"]
    c["cumple"] = (
        c["1_campo_de_al_lado_que_siguen_mal_(de_7)"] <= 1
        and not c["2_otros_paneles_que_pierden_el_balon"]
        and c["3_banda_identica_fila_a_fila"]
    )
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "bloque1.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(
        json.dumps(
            {k: v for k, v in res.items() if k != "paneles"},
            indent=1,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
