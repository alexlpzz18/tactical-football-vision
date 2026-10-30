#!/usr/bin/env python
"""Staff que entra en el campo, etiquetado por observación. Criterios en
`docs/staff_dentro_del_campo.md`.

Uso:
    python scripts/staff_dentro.py correr
    python scripts/staff_dentro.py medir --modulos <dir>

`--modulos`: carpeta con `etiqueta_por_trozos.py` (GT de 30 s y hoja de 120, rama sin fusionar).
"""

import argparse
import hashlib
import json
import pickle
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/staff_dentro"
CONFIG_BENJA = R / "configs/processor_benja_parte_entera.yaml"
CONFIG_VILLA = R / "configs/processor.yaml"
CSV_MAIN_ARREGLO = R / "outputs/fix_interpoladas/benja_despues.csv"  # main de hoy
VILLA_MAIN = R / "outputs/fix_interpoladas/villa_despues.csv"
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
VIDEO = R / "data/raw/benja_gredos_p1_20min.mp4"
FPS = 29.97002997002997
LARGO, ANCHO, MARGEN_M = 62.0, 40.0, 1.0
LATERAL_ID, LATERAL_VENTANA = 590, (785.0, 808.31)
MODULOS: Path | None = None


def _mod(nombre):
    ruta = R / f"scripts/{nombre}.py"
    fuente = ruta if ruta.exists() else MODULOS / f"{nombre}.py"
    m = types.ModuleType(nombre)
    m.__file__ = str(ruta)
    exec(compile(fuente.read_text(), str(fuente), "exec"), m.__dict__)
    m._mod = _mod
    return m


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def relojes(t: float) -> str:
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} archivo · {int(r // 60)}:{r % 60:04.1f} reproductor"


def _pasada(config: Path, salida: Path, staff_dentro: bool | None) -> None:
    """desde_cache con el flag puesto o quitado (None = el YAML tal cual)."""
    from src.tracking_data.processor import procesar_desde_cache

    cfg = yaml.safe_load(open(config))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(salida)
    cfg["rutas"]["salida_meta"] = str(salida.with_name(salida.stem + "_meta.json"))
    if staff_dentro is not None:
        eq = yaml.safe_load(open(R / cfg["config_equipos"]))
        eq["agregacion"]["por_observacion"]["staff_dentro_del_campo"][
            "activo"
        ] = staff_dentro
        tmp = Path(tempfile.mkdtemp()) / "equipos.yaml"
        yaml.safe_dump(eq, open(tmp, "w"), allow_unicode=True)
        cfg["config_equipos"] = str(tmp)
    procesar_desde_cache(cfg)


def correr() -> dict:
    SALIDA.mkdir(parents=True, exist_ok=True)
    _pasada(CONFIG_BENJA, SALIDA / "benja_antes.csv", False)
    _pasada(CONFIG_BENJA, SALIDA / "benja_despues.csv", True)
    _pasada(CONFIG_VILLA, SALIDA / "villa.csv", None)
    res = {
        "flag_apagado_igual_a_main": _sha(SALIDA / "benja_antes.csv")
        == _sha(CSV_MAIN_ARREGLO),
        "villa_identico_a_main": _sha(SALIDA / "villa.csv") == _sha(VILLA_MAIN),
    }
    json.dump(res, open(SALIDA / "correr.json", "w"), indent=1)
    return res


def rachas_cambiadas(antes: pd.DataFrame, despues: pd.DataFrame) -> pd.DataFrame:
    """Rachas (identidad, filas seguidas) cuya etiqueta cambia, con su primera fila real."""
    cambia = antes.etiqueta.values != despues.etiqueta.values
    d = despues[cambia].assign(antes=antes.etiqueta.values[cambia])
    filas = []
    for i, g in d.sort_values("frame").groupby("id_jugador"):
        corte = np.where(np.diff(g.tiempo_s.to_numpy()) > 1.0)[0] + 1
        for trozo in np.split(np.arange(len(g)), corte):
            s = g.iloc[trozo]
            reales = s[s.es_real == 1]
            ref = reales.iloc[len(reales) // 2] if len(reales) else s.iloc[0]
            filas.append(
                {
                    "id": int(i),
                    "t0": float(s.tiempo_s.min()),
                    "t1": float(s.tiempo_s.max()),
                    "filas": len(s),
                    "de": "/".join(sorted(set(s.antes))),
                    "a": "/".join(sorted(set(s.etiqueta.astype(str)))),
                    "frame_ref": int(ref.frame),
                    "x": float(ref.x_m),
                    "y": float(ref.y_m),
                }
            )
    return pd.DataFrame(filas)


def miniaturas(rachas: pd.DataFrame) -> Path:
    """Una imagen por racha, con la caja de la PROPIA detección de la fila (no la más cercana)."""
    cap = pickle.load(open(CAPTURA, "rb"))
    dets = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    dueno = {}
    for i, ident in enumerate(cap["identidades"], start=1):
        for f, k in ident:
            dueno[(i, int(f))] = int(k)
    import base64

    tarjetas = []
    for n, r in rachas.iterrows():
        k = dueno.get((r.id, r.frame_ref))
        caja = dets[r.frame_ref][k][2:6] if k is not None else None
        jpg = SALIDA / f"racha_{n}.jpg"
        filtro = "scale=960:-2"
        if caja is not None:
            x1, y1, x2, y2 = (float(v) for v in caja)
            filtro = (
                f"drawbox=x={x1 - 3:.0f}:y={y1 - 3:.0f}:w={x2 - x1 + 6:.0f}:h={y2 - y1 + 6:.0f}"
                ":color=yellow:t=3," + filtro
            )
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{r.frame_ref / FPS:.3f}",
             "-i", str(VIDEO), "-frames:v", "1", "-vf", filtro, str(jpg)],
            check=True,
        )  # fmt: skip
        b64 = base64.b64encode(jpg.read_bytes()).decode()
        tarjetas.append(
            f'<div><img src="data:image/jpeg;base64,{b64}"><p><b>id {r.id}</b> · '
            f"{relojes(r.t0)} → {r.t1 - r.t0:.1f} s · {r.filas} filas · {r.de} → {r.a} · "
            f"pie ({r.x:.1f}, {r.y:.1f}) m · caja {'de su detección' if caja else 'SIN caja'}"
            "</p></div>"
        )
    html = SALIDA / "rachas.html"
    html.write_text(
        "<!doctype html><meta charset=utf-8><title>Staff dentro del campo</title>"
        "<style>body{background:#111;color:#eee;font:14px system-ui;margin:16px}"
        "img{width:100%;max-width:960px}div{margin-bottom:18px}</style>"
        "<h1>Rachas que pasan de staff a jugador</h1>" + "".join(tarjetas)
    )
    return html


def medir() -> dict:
    ept = _mod("etiqueta_por_trozos")
    antes = pd.read_csv(SALIDA / "benja_antes.csv")
    despues = pd.read_csv(SALIDA / "benja_despues.csv")
    assert len(antes) == len(despues)
    cambia = antes.etiqueta.values != despues.etiqueta.values
    ids_staff = set(antes[antes.etiqueta == "staff"].id_jugador)
    fijas = ["frame", "tiempo_s", "id_jugador", "x_m", "y_m", "es_real"]
    # 1. el lateral
    g = despues[
        (despues.id_jugador == LATERAL_ID)
        & despues.tiempo_s.between(*LATERAL_VENTANA)
        & despues.x_m.between(MARGEN_M, LARGO - MARGEN_M)
        & despues.y_m.between(MARGEN_M, ANCHO - MARGEN_M)
    ]
    lateral = g.etiqueta.astype(str).value_counts().to_dict()
    pct_a = 100 * (g.etiqueta == "A").mean() if len(g) else 0.0
    rachas = rachas_cambiadas(antes, despues)
    rachas.to_csv(SALIDA / "rachas.csv", index=False)
    cap = pickle.load(open(CAPTURA, "rb"))
    res = {
        "lateral_590": {
            "filas_dentro": len(g),
            "etiquetas": lateral,
            "pct_A": round(pct_a, 1),
        },
        "filas_que_cambian": int(cambia.sum()),
        "solo_identidades_de_staff": bool(set(antes.id_jugador[cambia]) <= ids_staff),
        "columnas_fijas_identicas": all(
            (antes[c].values == despues[c].values).all() for c in fijas
        ),
        "rachas": rachas.to_dict("records"),
        "miniaturas": str(miniaturas(rachas)),
        "gt": {
            "antes": ept.errores_gt(SALIDA / "benja_antes.csv")["errores"],
            "despues": ept.errores_gt(SALIDA / "benja_despues.csv")["errores"],
        },
        "hoja_120": {
            "antes": ept.errores_hoja(SALIDA / "benja_antes.csv", cap)["errores"],
            "despues": ept.errores_hoja(SALIDA / "benja_despues.csv", cap)["errores"],
        },
    }
    res["criterio"] = {
        "1_lateral_A_>=_90": pct_a >= 90,
        "3_gt_no_sube": res["gt"]["despues"] <= 9,
        "3_hoja_no_sube": res["hoja_120"]["despues"] <= 2,
        "3_solo_staff": res["solo_identidades_de_staff"]
        and res["columnas_fijas_identicas"],
        "2_miniaturas": "a ojo (rachas.html)",
    }
    json.dump(
        res,
        open(SALIDA / "medida.json", "w"),
        indent=1,
        ensure_ascii=False,
        default=str,
    )
    return res


def main() -> None:
    global MODULOS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["correr", "medir"])
    ap.add_argument("--modulos", type=Path, default=None)
    args = ap.parse_args()
    MODULOS = args.modulos
    out = correr() if args.accion == "correr" else medir()
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
