#!/usr/bin/env python
"""La pizarra, solo el dibujo: histéresis de color y persistencia. Criterios en
`docs/pizarra_dibujo.md`. SOLO mide; los CSV de datos no se tocan.

Uso:
    python scripts/pizarra_dibujo.py --persistencia 1.0
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
SALIDA = R / "outputs/pizarra_dibujo"
RELEVO_M, RELEVO_S = 2.0, 0.2
SOSTENIDO_S = 1.0
HISTERESIS = (0.5, 1.0, 2.0)


def _fp():
    spec = importlib.util.spec_from_file_location("fp", R / "scripts/fichas_pizarra.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def medir(fp, html: Path, base_html: Path, Hinv) -> dict:
    """Las métricas del simulador + eventos con la regla del RELEVO, sostenidos y lo escondido."""
    t0, t1 = fp.TRAMO
    Ts = np.arange(t0, t1, fp.PASO_S)
    minutos = (t1 - t0) / 60
    m = fp.metricas(html, fp.TRAMO, Hinv)
    datos, cat = fp.leer_pizarra(html)
    fichas = [
        f
        for f in fp.simular(datos, cat, Ts)
        if not str(f["col"][0]).startswith("balon")
    ]
    # eventos con su tipo, para la regla del relevo
    ev = []
    for f in fichas:
        vis = f["vis"]
        for k in np.where(vis[1:] != vis[:-1])[0]:
            j = k + 1 if vis[k + 1] else k
            x, y = f["x"][j], f["y"][j]
            dentro = 0 <= x <= fp.LARGO and 0 <= y <= fp.ANCHO
            if dentro and fp.en_camara(np.array([x]), np.array([y]), Hinv)[0]:
                ev.append(
                    (
                        Ts[k + 1],
                        "nace" if vis[k + 1] else "muere",
                        fp.equipo(f["col"][j]),
                        x,
                        y,
                    )
                )
    usados, relevos = set(), 0
    for i, a in enumerate(ev):
        if a[1] != "muere" or i in usados:
            continue
        for j, b in enumerate(ev):
            if (
                j not in usados
                and b[1] == "nace"
                and b[2] is not None
                and b[2] == a[2]
                and abs(b[0] - a[0]) <= RELEVO_S
                and np.hypot(b[3] - a[3], b[4] - a[4]) < RELEVO_M
            ):
                usados |= {i, j}
                relevos += 1
                break
    m["eventos_por_minuto_sin_relevos"] = round((len(ev) - 2 * relevos) / minutos, 1)
    m["relevos_por_minuto"] = round(relevos / minutos, 1)
    # cambios de color que quedan: ¿el color nuevo dura > 1 s?
    sost = tot = 0
    for f in fichas:
        vis, col = f["vis"], f["col"]
        for k in np.where(vis[1:] & vis[:-1] & (col[1:] != col[:-1]))[0]:
            tot += 1
            j = k + 1
            while j < len(col) and vis[j] and col[j] == col[k + 1]:
                j += 1
            sost += (j - (k + 1)) * fp.PASO_S > SOSTENIDO_S
    m["cambios_sostenidos_>1s_pct"] = round(100 * sost / max(tot, 1), 1)
    # lo que se esconde, contra la base (mismas identidades)
    db, cb = fp.leer_pizarra(base_html)
    base = {f["id"]: f for f in fp.simular(db, cb, Ts)}
    distinto = visibles = 0
    for f in fichas:
        b = base.get(f["id"])
        if b is None:
            continue
        v = f["vis"] & b["vis"]
        visibles += int(v.sum())
        distinto += int((v & (f["col"] != b["col"])).sum())
    m["tiempo_ficha_con_color_distinto_del_dato_pct"] = round(
        100 * distinto / max(visibles, 1), 1
    )
    return m


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persistencia", type=float, required=True)
    args = ap.parse_args()
    fp = _fp()
    SALIDA.mkdir(parents=True, exist_ok=True)
    antes = {p.name: _sha(p) for p in (fp.CSV_MAIN, fp.CSV_PARTE)}
    Hinv = np.linalg.inv(np.load(fp.HOMOGRAFIA))
    zona = SALIDA / "zona_no_visible.json"
    zona.write_text(json.dumps(fp.zona_no_visible(Hinv)))
    rel = "14:00-15:30 (archivo) · 15:33-17:03 (reproductor)"
    base = fp.pizarra(fp.CSV_MAIN, fp.TRAMO, SALIDA / "base.html", f"main · {rel}")
    res = {"base": medir(fp, base, base, Hinv)}
    for x in HISTERESIS:
        h = fp.pizarra(
            fp.CSV_MAIN,
            fp.TRAMO,
            SALIDA / f"histeresis_{x:g}s.html",
            f"color estable ≥ {x:g} s (SOLO DIBUJO) · {rel}",
            ["--histeresis-visual-s", str(x)],
        )
        res[f"histeresis_{x:g}s"] = medir(fp, h, base, Hinv)
    p = args.persistencia
    pers = fp.pizarra(
        fp.CSV_MAIN,
        fp.TRAMO,
        SALIDA / f"persistencia_{p:g}s.html",
        f"fichas en espera {p:g} s (SOLO DIBUJO) · {rel}",
        ["--persistencia-s", str(p), "--zona-no-visible", str(zona)],
    )
    res[f"persistencia_{p:g}s"] = medir(fp, pers, base, Hinv)
    b = res["base"]
    cambios_b = b["cambios_de_color_por_minuto"]
    cumple_h = {
        k: v["cambios_de_color_por_minuto"] <= 0.2 * cambios_b
        for k, v in res.items()
        if k.startswith("histeresis")
    }
    mejor = next(
        (f"histeresis_{x:g}s" for x in HISTERESIS if cumple_h[f"histeresis_{x:g}s"]),
        None,
    )
    ps = res[f"persistencia_{p:g}s"]
    res["criterio"] = {
        "histeresis_1s_>=80%": cumple_h["histeresis_1s"],
        "mejor_compromiso": mejor,
        "persistencia_eventos_-50%_(con_relevos)": ps["eventos_por_minuto_sin_relevos"]
        <= 0.5 * b["eventos_por_minuto_sin_relevos"],
        "persistencia_mas_de_7_no_sube": all(
            ps["simultaneas_por_equipo"][e]["pct_tiempo_mas_de_7"]
            <= b["simultaneas_por_equipo"][e]["pct_tiempo_mas_de_7"]
            for e in ("A", "B")
        ),
    }
    if mejor:
        x = float(mejor.split("_")[1][:-1])
        fp.pizarra(
            fp.CSV_MAIN,
            fp.TRAMO,
            SALIDA / "para_alex.html",
            f"color estable ≥ {x:g} s + fichas en espera {p:g} s (SOLO DIBUJO) · {rel}",
            [
                "--histeresis-visual-s",
                str(x),
                "--persistencia-s",
                str(p),
                "--zona-no-visible",
                str(zona),
            ],
        )
    res["csv_de_datos_identicos"] = antes == {
        q.name: _sha(q) for q in (fp.CSV_MAIN, fp.CSV_PARTE)
    }
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=float)
    (SALIDA / f"resultado_persistencia_{p:g}s.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
