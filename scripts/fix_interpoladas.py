#!/usr/bin/env python
"""Etiqueta de las filas interpoladas desde la fila real vecina.

Criterios en `docs/fix_interpoladas.md`.

Uso:
    python scripts/fix_interpoladas.py correr  --modulos <dir>   # desde_cache: CSV antes y después
    python scripts/fix_interpoladas.py medir   --modulos <dir>   # medida previa + criterios
    python scripts/fix_interpoladas.py pizarra --modulos <dir>   # la pizarra con histéresis de 1 s

`--modulos` es la carpeta con los scripts de medida de ramas sin fusionar (`fichas_pizarra.py`,
`etiqueta_por_trozos.py`): se cargan como si estuvieran en `scripts/`, sin copiarlos al repo.
"""

import argparse
import hashlib
import json
import pickle
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import linear_sum_assignment

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
SALIDA = R / "outputs/fix_interpoladas"
CONFIG_BENJA = R / "configs/processor_benja_parte_entera.yaml"
CONFIG_VILLA = R / "configs/processor.yaml"
CAPTURA = R / "outputs/diagnostico_26oct_b/captura_main.pkl"
CSV_MAIN = R / "outputs/diagnostico_26oct_b/posiciones_main.csv"
CSV_PARTE = R / "data/tracking_benja/posiciones_benja_p1.csv"
HOMOGRAFIA = R / "data/calibracion_benja/homografia_benja.npy"
CAMPO = R / "configs/campo_benja.yaml"
TRAMO = (840.0, 930.0)
RADIO_CASADO_M = 2.0
MODULOS: Path | None = None


def _mod(nombre):
    """Un script de `scripts/`, o de `--modulos` con `__file__` dentro de `scripts/`."""
    ruta = R / f"scripts/{nombre}.py"
    fuente = ruta if ruta.exists() else MODULOS / f"{nombre}.py"
    m = types.ModuleType(nombre)
    m.__file__ = str(ruta)
    exec(compile(fuente.read_text(), str(fuente), "exec"), m.__dict__)
    m._mod = _mod
    return m


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── correr: una pasada de desde_cache, el escritor llamado con los dos modos ─────────────────


def _pasada(config: Path, salidas: dict) -> None:
    import src.tracking_data.processor as proc

    cfg = yaml.safe_load(open(config))
    cfg["modo"] = "desde_cache"
    original = proc.exportar_posiciones

    def espia(*args, **kwargs):
        cfg_export = args[3]
        for modo, ruta in salidas.items():
            c = dict(cfg_export)
            c["rutas"] = dict(cfg_export["rutas"])
            c["rutas"]["salida_csv"] = str(ruta)
            c["rutas"]["salida_meta"] = str(ruta.with_name(ruta.stem + "_meta.json"))
            c["exportacion"] = {"etiqueta_interpoladas": modo}
            original(*args[:3], c, *args[4:], **kwargs)
        return None

    proc.exportar_posiciones = espia
    try:
        proc.procesar_desde_cache(cfg)
    finally:
        proc.exportar_posiciones = original


def correr() -> dict:
    SALIDA.mkdir(parents=True, exist_ok=True)
    datos = {p.name: _sha(p) for p in (CSV_MAIN, CSV_PARTE)}
    _pasada(
        CONFIG_BENJA,
        {
            "identidad": SALIDA / "benja_antes.csv",
            "vecina_real": SALIDA / "benja_despues.csv",
        },
    )
    _pasada(
        CONFIG_VILLA,
        {
            "identidad": SALIDA / "villa_antes.csv",
            "vecina_real": SALIDA / "villa_despues.csv",
        },
    )
    res = {
        "benja_antes_igual_a_posiciones_main": _sha(SALIDA / "benja_antes.csv")
        == _sha(CSV_MAIN),
        "villa_identico_byte_a_byte": _sha(SALIDA / "villa_antes.csv")
        == _sha(SALIDA / "villa_despues.csv"),
        "csv_de_datos_intactos": datos
        == {p.name: _sha(p) for p in (CSV_MAIN, CSV_PARTE)},
    }
    json.dump(res, open(SALIDA / "correr.json", "w"), indent=1)
    return res


# ── medida ───────────────────────────────────────────────────────────────────────────────────


def control_solo_etiqueta(antes: pd.DataFrame, despues: pd.DataFrame) -> dict:
    """Mismas filas y orden; solo cambian `etiqueta` y `equipo` de las filas interpoladas."""
    if len(antes) != len(despues):
        return {"mismas_filas": False}
    fijas = ["frame", "tiempo_s", "id_jugador", "x_m", "y_m", "es_real"]
    iguales = {c: bool((antes[c].values == despues[c].values).all()) for c in fijas}
    reales = antes.es_real.values == 1
    cambia = (antes.etiqueta.values != despues.etiqueta.values) | (
        antes.equipo.values != despues.equipo.values
    )
    return {
        "mismas_filas": True,
        "columnas_fijas_identicas": iguales,
        "filas_reales_que_cambian": int((cambia & reales).sum()),
        "filas_interpoladas_que_cambian": int((cambia & ~reales).sum()),
    }


def origen_interpoladas(df: pd.DataFrame, voto: dict) -> dict:
    """De dónde sale la etiqueta de cada fila interpolada: voto, vecinas reales, ninguna."""
    n = {
        "filas": len(df),
        "interpoladas": 0,
        "igual_al_voto": 0,
        "igual_a_las_dos_vecinas": 0,
        "igual_a_una_vecina": 0,
        "distinta_de_las_dos_vecinas": 0,
        "sin_dos_vecinas_reales": 0,
        "islas": 0,
    }
    for i, g in df.sort_values("frame").groupby("id_jugador"):
        e = g.etiqueta.astype(str).to_numpy()
        r = g.es_real.to_numpy() == 1
        v = voto.get(int(i), "otro")
        idx_reales = np.where(r)[0]
        en_isla = False
        for k in np.where(~r)[0]:
            n["interpoladas"] += 1
            n["igual_al_voto"] += int(e[k] == v)
            a = idx_reales[idx_reales < k]
            b = idx_reales[idx_reales > k]
            if not len(a) or not len(b):
                n["sin_dos_vecinas_reales"] += 1
                continue
            iguales = int(e[k] == e[a[-1]]) + int(e[k] == e[b[0]])
            clave = [
                "distinta_de_las_dos_vecinas",
                "igual_a_una_vecina",
                "igual_a_las_dos_vecinas",
            ][iguales]
            n[clave] += 1
            # una isla = racha de interpoladas con alguna fila distinta de las dos vecinas
            nueva = iguales == 0 and not (en_isla and k - 1 >= 0 and not r[k - 1])
            n["islas"] += int(nueva)
            en_isla = iguales == 0
    n["interpoladas_pct"] = round(100 * n["interpoladas"] / n["filas"], 2)
    return n


def islas_en_la_pizarra(csv: Path) -> dict:
    """Islas en el CSV que pinta la pizarra (corte ± 5 s y SUS filtros), dentro del tramo."""
    from src.campo_modelo import cargar_modelo
    from src.report.replay_tactico import _filtrar_creible, _filtrar_fuera_del_campo

    t0, t1 = TRAMO
    modelo = cargar_modelo(config=str(CAMPO))
    df = pd.read_csv(csv)
    df = df[(df.tiempo_s >= t0 - 5) & (df.tiempo_s <= t1 + 5)]
    df = _filtrar_fuera_del_campo(df, modelo.largo, modelo.ancho)
    df = _filtrar_creible(df, 0.6, 2.0)
    islas, cambios, con_interp = 0, 0, 0
    for _i, g in df.sort_values("tiempo_s").groupby("id_jugador"):
        g = g[(g.tiempo_s >= t0 - 0.1) & (g.tiempo_s < t1)]
        e = g.etiqueta.astype(str).to_numpy()
        r = g.es_real.to_numpy() == 1
        for k in np.where(e[1:] != e[:-1])[0]:
            cambios += 1
            con_interp += int(not (r[k] and r[k + 1]))
        k = 0
        while k < len(e):
            if r[k]:
                k += 1
                continue
            j = k
            while j < len(e) and not r[j]:
                j += 1
            if k > 0 and j < len(e):
                if any(e[m] != e[k - 1] and e[m] != e[j] for m in range(k, j)):
                    islas += 1
            k = j
    return {
        "islas": islas,
        "cambios_entre_filas_seguidas": cambios,
        "de_ellos_con_alguna_interpolada": con_interp,
    }


def gt_con_todas_las_filas(csv: Path) -> dict:
    """Casado 1-a-1 a 2 m con TODAS las filas: error de equipo de interpoladas frente a reales."""
    from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat

    ce = _mod("comparar_escalas")
    gt = gt_a_por_frame(
        parsear_cvat(R / "data/annotations/gt_benja/annotations.xml"),
        np.load(HOMOGRAFIA),
        9750,
        15,
    )
    df = pd.read_csv(csv)
    pf = {f: g for f, g in df.groupby("frame")}
    c = {"real": [0, 0], "interpolada": [0, 0]}  # [casadas, mal]
    for f in sorted(gt):
        gente = [o for o in gt[f] if ce.equipo_gt(o) in ("A", "B")]
        if f not in pf or not gente:
            continue
        sub = pf[f]
        xy = sub[["x_m", "y_m"]].to_numpy()
        et = sub.etiqueta.astype(str).to_numpy()
        real = sub.es_real.to_numpy() == 1
        d = np.hypot(
            xy[None, :, 0] - np.array([o.pos[0] for o in gente])[:, None],
            xy[None, :, 1] - np.array([o.pos[1] for o in gente])[:, None],
        )
        d = np.where(d > RADIO_CASADO_M, 1e6, d)
        for a, b in zip(*linear_sum_assignment(d)):
            if d[a, b] >= 1e6:
                continue
            tipo = "real" if real[b] else "interpolada"
            c[tipo][0] += 1
            s = et[b].replace("portero_", "")
            c[tipo][1] += int(s in ("A", "B") and s != ce.equipo_gt(gente[a]))
    return {
        k: {
            "casadas": v[0],
            "mal": v[1],
            "pct": round(100 * v[1] / v[0], 2) if v[0] else None,
        }
        for k, v in c.items()
    }


def informe_por_etiqueta(antes: pd.DataFrame, despues: pd.DataFrame) -> dict:
    """Lo que lee el informe (todas las filas): filas por etiqueta, antes y después."""
    a = antes.etiqueta.astype(str).value_counts()
    d = despues.etiqueta.astype(str).value_counts()
    return {
        e: {"antes": int(a.get(e, 0)), "despues": int(d.get(e, 0))}
        for e in sorted(set(a.index) | set(d.index))
    }


def medir() -> dict:
    ept = _mod("etiqueta_por_trozos")
    cap = pickle.load(open(CAPTURA, "rb"))
    voto = {int(i): str(e) for i, e in cap["voto"].items()}
    antes_csv, despues_csv = SALIDA / "benja_antes.csv", SALIDA / "benja_despues.csv"
    antes, despues = pd.read_csv(antes_csv), pd.read_csv(despues_csv)
    rel = "14:00-15:30 (archivo) · 15:33-17:03 (reproductor)"
    res = {
        "control": control_solo_etiqueta(antes, despues),
        "origen_20min": {
            "antes": origen_interpoladas(antes, voto),
            "despues": origen_interpoladas(despues, voto),
        },
        "informe_filas_por_etiqueta": informe_por_etiqueta(antes, despues),
        "gt_todas_las_filas": {
            "antes": gt_con_todas_las_filas(antes_csv),
            "despues": gt_con_todas_las_filas(despues_csv),
        },
    }
    for nombre, csv_ in (("antes", antes_csv), ("despues", despues_csv)):
        res[nombre] = {
            "islas_pizarra": islas_en_la_pizarra(csv_),
            "pizarra": ept.cambios_pizarra(
                csv_,
                SALIDA / f"pizarra_{nombre}_sin_histeresis.html",
                f"{'main' if nombre == 'antes' else 'arreglo interpoladas'} · {rel}",
            ),
            "gt": ept.errores_gt(csv_),
            "hoja_120": ept.errores_hoja(csv_, cap),
        }
    a, d = res["antes"], res["despues"]
    cpm = d["pizarra"]["cambios_de_color_por_minuto"]
    res["criterio"] = {
        "islas_0": d["islas_pizarra"]["islas"] == 0,
        "cambios_por_min_<=_52.4": cpm <= 0.6 * 87.3,
        "bajada_pct_frente_a_87.3": round(100 * (1 - cpm / 87.3), 1),
        "gt_no_sube": d["gt"]["errores"] <= a["gt"]["errores"],
        "hoja_no_sube": d["hoja_120"]["errores"] <= a["hoja_120"]["errores"],
        "solo_cambia_la_etiqueta": res["control"].get("mismas_filas", False)
        and all(res["control"]["columnas_fijas_identicas"].values())
        and res["control"]["filas_reales_que_cambian"] == 0,
    }
    res["criterio"]["cumple"] = all(
        v for k, v in res["criterio"].items() if k != "bajada_pct_frente_a_87.3"
    )
    json.dump(res, open(SALIDA / "medida.json", "w"), indent=1, ensure_ascii=False)
    return res


def pizarra() -> str:
    fp = _mod("fichas_pizarra")
    html = SALIDA / "pizarra_arreglo_histeresis_1s.html"
    fp.pizarra(
        SALIDA / "benja_despues.csv",
        fp.TRAMO,
        html,
        "arreglo interpoladas + color estable ≥ 1 s · 14:00-15:30 (archivo) · "
        "15:33-17:03 (reproductor)",
        ["--histeresis-visual-s", "1"],
    )
    m = fp.metricas(html, fp.TRAMO, np.linalg.inv(np.load(HOMOGRAFIA)))
    out = {
        "html": str(html),
        "cambios_de_color_por_minuto": m["cambios_de_color_por_minuto"],
    }
    json.dump(out, open(SALIDA / "pizarra.json", "w"), indent=1)
    return json.dumps(out)


def main() -> None:
    global MODULOS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["correr", "medir", "pizarra"])
    ap.add_argument("--modulos", type=Path, required=True)
    args = ap.parse_args()
    MODULOS = args.modulos
    out = {"correr": correr, "medir": medir, "pizarra": pizarra}[args.accion]()
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str)[:6000])


if __name__ == "__main__":
    main()
