#!/usr/bin/env python
"""Diagnóstico 23-oct (f), bloque 2: la máscara de zona de juego del balón (`balon.mascara_zona`).

Criterio en `docs/diagnostico_23oct_f.md`. Mide el polígono que Alex marca con
`scripts/marcar_mascara_zona.py` (NO se ajusta aquí) y su control desplazado 100 px.

Uso:
    python scripts/diag23f_mascara.py --salida outputs/diagnostico_23oct_f
    # el polígono sale de data/calibracion_benja/mascara_zona_benja.json (o --poligono a.json)
"""

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
CSV_JUGADORES = R / "outputs/arbitro_obs/posiciones.csv"  # el de los paneles del 22-oct
CAMPO = R / "configs/campo_benja.yaml"
POLIGONO = R / "data/calibracion_benja/mascara_zona_benja.json"
PANELES = R / "outputs/diagnostico_22oct/bloque1.json"
CAMPO_DE_AL_LADO = [9306, 9306, 9360, 9738, 10166, 10472, 10474]  # 7 paneles, 6 frames
ETIQUETAS = R / "docs/etiquetas_balon_23oct_e.json"
HOJAS = R / "outputs/diagnostico_23oct_e"
TRAMOS = {
    "minuto_5": ["tramo", "tramo_b"],
    "minutos_14_16": ["control", "control_regla"],
}
SAQUES_SOBRE_LA_CABEZA = [("control_regla", "C09"), ("control_regla", "C25")]
DESPLAZAMIENTO_CONTROL_PX = 100


def campo_con_mascara(poligono) -> Path:
    """Copia temporal del config del campo con `balon.mascara_zona` puesta."""
    cfg = yaml.safe_load(open(CAMPO))
    cfg["balon"]["mascara_zona"] = poligono
    tmp = Path(tempfile.mkdtemp()) / "campo_mascara.yaml"
    # las rutas del config son relativas a la raíz del repo: se dejan absolutas
    cfg["rutas"] = {k: str(R / v) for k, v in cfg["rutas"].items()}
    tmp.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    return tmp


def video(campo: Path) -> dict:
    spec = importlib.util.spec_from_file_location(
        "gv", R / "scripts/generar_video_detecciones.py"
    )
    gv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gv)
    return gv.balon_activo(CACHE_BALON, CSV_JUGADORES, campo)


def etiquetadas() -> pd.DataFrame:
    E = json.loads(ETIQUETAS.read_text())
    partes = []
    for tramo, hojas in TRAMOS.items():
        for h in hojas:
            c = pd.DataFrame(
                json.loads((HOJAS / f"hoja_{h}/candidatas.json").read_text())
            )
            c["clase"], c["hoja"], c["tramo"] = c.id.map(E[h]), h, tramo
            partes.append(c[c.clase.notna()])
    return pd.concat(partes)


def medir_poligono(poligono, base: dict, cand: pd.DataFrame) -> dict:
    from src.balon.tracking_balon import dentro_del_poligono

    sel = video(campo_con_mascara(poligono))
    paneles = json.loads(PANELES.read_text())["1e_paneles"]
    otros = [p["frame"] for p in paneles if p["frame"] not in CAMPO_DE_AL_LADO]

    def misma(f):
        a, b = base.get(f), sel.get(f)
        return (a is None and b is None) or (
            a is not None and b is not None and tuple(a[0]) == tuple(b[0])
        )

    # un panel del campo de al lado sigue MAL si se sigue eligiendo la misma candidata (la de fuera)
    siguen_mal = [f for f in CAMPO_DE_AL_LADO if base.get(f) is not None and misma(f)]
    cambian = sorted({f for f in otros if not misma(f)})
    cand = cand.assign(
        dentro=[dentro_del_poligono(x, y, poligono) for x, y in zip(cand.cx, cand.cy)]
    )
    por_tramo = {}
    for t, g in cand.groupby("tramo"):
        al, re = g[g.clase == "campo_al_lado"], g[g.clase == "balon_real"]
        por_tramo[t] = {
            "campo_al_lado_fuera_pct": round(100 * float((~al.dentro).mean()), 1),
            "balon_real_dentro_pct": round(100 * float(re.dentro.mean()), 1),
            "n_al_lado_real": [len(al), len(re)],
        }
    saques = {
        f"{h}/{i}": bool(cand[(cand.hoja == h) & (cand.id == i)].dentro.iloc[0])
        for h, i in SAQUES_SOBRE_LA_CABEZA
    }
    return {
        "1_campo_de_al_lado_que_siguen_mal_(de_7)": len(siguen_mal),
        "2_otros_23_paneles_con_otra_deteccion": cambian,
        "3_por_tramo": por_tramo,
        "3_saques_sobre_la_cabeza_dentro": saques,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--poligono", default=str(POLIGONO))
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    ruta = Path(args.poligono)
    if not ruta.exists():
        sys.exit(
            f"No hay polígono en {ruta}: márcalo con "
            "`python scripts/marcar_mascara_zona.py marcar` (bloque 2 NO MEDIDO)."
        )
    poligono = json.loads(ruta.read_text())["poligono"]
    base = video(CAMPO)  # flag apagado: la selección de siempre
    cand = etiquetadas()
    real = medir_poligono(poligono, base, cand)
    desplazado = [[x, y + DESPLAZAMIENTO_CONTROL_PX] for x, y in poligono]
    control = medir_poligono(desplazado, base, cand)

    def cumple(m):
        return (
            m["1_campo_de_al_lado_que_siguen_mal_(de_7)"] <= 2
            and not m["2_otros_23_paneles_con_otra_deteccion"]
            and all(t["balon_real_dentro_pct"] >= 95 for t in m["3_por_tramo"].values())
            and all(m["3_saques_sobre_la_cabeza_dentro"].values())
        )

    def peor(m, ref):
        return any(
            m["3_por_tramo"][t]["campo_al_lado_fuera_pct"]
            < ref["3_por_tramo"][t]["campo_al_lado_fuera_pct"]
            or m["3_por_tramo"][t]["balon_real_dentro_pct"]
            < ref["3_por_tramo"][t]["balon_real_dentro_pct"]
            for t in TRAMOS
        )

    res = {
        "poligono": poligono,
        "con_el_poligono": real,
        "control_desplazado_100px": control,
        "criterio": {
            "cumple_1_2_3": cumple(real),
            "4_el_control_empeora_algo": peor(control, real),
        },
    }
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / "bloque2_mascara.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
