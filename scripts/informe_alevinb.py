#!/usr/bin/env python
"""Informe de UNA página del alevín B (F2 de la segunda opinión, borrador para diciembre).

Envuelve el motor de forma por tramos (`informe_forma.py`: largo, anchura, altura de la defensa y
distancias entre líneas por tramos de 10 s, mediana sobre los fotogramas) y lo junta en una página:
1. los dos equipos lado a lado (cifras de todo el tramo analizado y su forma media dibujada);
2. la evolución por bloques de 5 minutos;
3. la ocupación del campo (tercios × carriles);
4. «3 cosas a entrenar» del equipo elegido, por reglas (ningún modelo de lenguaje);
5. momentos: los clips con superposición (los de `demo_alevinb.py`) con sus cifras.

⚠️ Sin la posesión todavía, las reglas se evalúan sobre TODOS los tramos (sin separar con y sin
balón) y la página lo dice. Cuando el CSV traiga la columna `posesion`, el motor ya las separa.

Uso:
    python scripts/informe_alevinb.py \\
        --csv outputs/f11_staff_dentro/alevinb/posiciones_staff_on.csv \\
        --clips 180:210,600:630,1255:1285 --clips-dir outputs/demo_alevinb \\
        --salida outputs/informe_alevinb/index.html
"""

import argparse
import html
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "scripts"))

from informe_forma import evaluar_reglas, por_tramos, svg_forma  # noqa: E402

LARGO, ANCHO = 100.0, 64.0
PLANTILLA = R / "scripts/plantillas/informe_alevinb.html"
COLOR = {"A": "#2563eb", "B": "#dc2626"}
METRICAS = [
    ("largo_m", "Largo del bloque"),
    ("ancho_m", "Anchura"),
    ("altura_def_m", "Altura de la defensa"),
    ("def_med_m", "Defensa–medio"),
    ("med_ata_m", "Medio–ataque"),
]


def mmss(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def m(v) -> str:
    """Metros redondeados, o «–» si no hay dato (p. ej. un tramo sin portero visible)."""
    return "–" if v is None or v != v else f"{v:.0f} m"


def cifras(t: pd.DataFrame) -> dict:
    return {k: float(t[k].median()) for k, _ in METRICAS} if len(t) else {}


def tabla_equipos(t: pd.DataFrame, nombres: dict) -> str:
    c = {e: cifras(t[t.equipo == e]) for e in ("A", "B")}
    filas = "".join(
        f"<tr><th>{et}</th>"
        + "".join(f"<td>{m(c[e].get(clave))}</td>" for e in ("A", "B"))
        + "</tr>"
        for clave, et in METRICAS
    )
    cab = "".join(
        f"<th style='color:{COLOR[e]}'>{html.escape(nombres[e])}</th>" for e in "AB"
    )
    return f"<table><tr><th></th>{cab}</tr>{filas}</table>"


def tabla_evolucion(t: pd.DataFrame, nombres: dict, bloque_s: float = 300.0) -> str:
    t = t.assign(bloque=(t.t0 // bloque_s).astype(int))
    bloques = sorted(t.bloque.unique())
    cab = "".join(f"<th>{mmss(b * bloque_s)}</th>" for b in bloques)
    filas = ""
    for e in ("A", "B"):
        for clave, et in METRICAS[:3]:
            vals = t[t.equipo == e].groupby("bloque")[clave].median()
            filas += (
                f"<tr><th><span style='color:{COLOR[e]}'>●</span> {et}</th>"
                + "".join(
                    f"<td>{vals[b]:.0f}</td>" if b in vals.index else "<td>–</td>"
                    for b in bloques
                )
                + "</tr>"
            )
    return f"<table class='evol'><tr><th>m, por bloques de 5 min</th>{cab}</tr>{filas}</table>"


def rejilla(t: pd.DataFrame, e: str) -> str:
    s = t[t.equipo == e]
    celdas = "".join(
        "<tr>"
        + "".join(
            f"<td style='--o:{s[f'zona_{tt}{c}'].mean():.2f};--c:{COLOR[e]}'>"
            f"{100 * s[f'zona_{tt}{c}'].mean():.0f} %</td>"
            for tt in range(3)
        )
        + "</tr>"
        for c in (2, 1, 0)
    )
    return f"<table class='zonas'>{celdas}</table>"


def momentos(
    df: pd.DataFrame, clips: list, clips_dir: Path | None, salida: Path, nombres
) -> str:
    out = []
    for i, (a, b) in enumerate(clips):
        sub = df[(df.tiempo_s >= a) & (df.tiempo_s < b)]
        t = por_tramos(sub, LARGO, ANCHO, 10.0, 3)
        c = (
            {e: cifras(t[t.equipo == e]) for e in "AB"}
            if len(t)
            else {"A": {}, "B": {}}
        )
        enlace = ""
        if clips_dir is not None and (clips_dir / f"clip_{i}.mp4").exists():
            rel = Path("..") / clips_dir.name / f"clip_{i}.mp4"
            try:
                rel = (
                    (clips_dir / f"clip_{i}.mp4")
                    .resolve()
                    .relative_to(salida.parent.resolve())
                )
            except ValueError:
                pass
            enlace = f" · <a href='{rel}'>vídeo con superposición</a>"
        datos = " · ".join(
            f"<span style='color:{COLOR[e]}'>{html.escape(nombres[e])}</span>: largo "
            f"{m(c[e].get('largo_m'))}, ancho {m(c[e].get('ancho_m'))}"
            for e in "AB"
        )
        out.append(f"<li><b>{mmss(a)}–{mmss(b)}</b>{enlace}<br>{datos}</li>")
    return "<ul class='momentos'>" + "".join(out) + "</ul>"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument(
        "--equipo", default="B", choices=["A", "B"], help="el equipo del informe"
    )
    ap.add_argument("--nombres", default="Blancos,Verdes", help="nombre de A y de B")
    ap.add_argument("--titulo", default="Alevín B · primera parte")
    ap.add_argument(
        "--clips", default="", help="desde:hasta (s del archivo), por comas"
    )
    ap.add_argument("--clips-dir", type=Path, default=None)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    nombres = dict(zip("AB", a.nombres.split(",")))
    df = pd.read_csv(a.csv)
    meta_ruta = a.csv.with_name(
        a.csv.name.replace("posiciones_", "meta_").replace(".csv", ".json")
    )
    meta = json.loads(meta_ruta.read_text()) if meta_ruta.exists() else {}
    t = por_tramos(df, LARGO, ANCHO, 10.0, 5)
    mio = t[t.equipo == a.equipo]
    reglas = evaluar_reglas(mio, LARGO, ANCHO)
    tres = "".join(
        f"<li><span class='tenue'>[regla de «{r['fase']} balón»]</span> "
        f"<b>{html.escape(r['titulo'])}.</b> {html.escape(r['texto'])} "
        f"<span class='tenue'>Pasa en el {r['pct']:.0f} % de los tramos "
        f"(mediana {r['mediana']:.0f} m; referencia "
        f"{'≤' if r['sentido'] == '>' else '≥'} {r['umbral']:.0f} m).</span></li>"
        for r in reglas[:3]
    )
    clips = [tuple(float(x) for x in c.split(":")) for c in a.clips.split(",") if c]
    dur = df.tiempo_s.max() - df.tiempo_s.min()
    sig = ((meta.get("seleccion_feature") or {}).get("siglip") or {}).get("usa_siglip")
    equipos = {True: "SigLIP", False: "histograma de color"}.get(sig, "¿?")
    calidad = (
        f"{mmss(dur)} analizados · {t.tramo.nunique()} tramos de 10 s · equipos por {equipos} · "
        f"fantasmas quitados: {meta.get('fantasmas_quitados', '–')}"
    )
    # la página (HTML + CSS) vive aparte para que el formateador no la toque
    valores = {
        "__TITULO__": html.escape(a.titulo),
        "__CALIDAD__": calidad,
        "__FECHA__": f"{date.today():%d-%m-%Y}",
        "__TABLA__": tabla_equipos(t, nombres),
        "__COLOR_EQ__": COLOR[a.equipo],
        "__NOMBRE_EQ__": html.escape(nombres[a.equipo]),
        "__SVG__": svg_forma(mio, LARGO, ANCHO, COLOR[a.equipo]),
        "__EVOL__": tabla_evolucion(t, nombres),
        "__COLOR_A__": COLOR["A"],
        "__NOMBRE_A__": html.escape(nombres["A"]),
        "__REJ_A__": rejilla(t, "A"),
        "__COLOR_B__": COLOR["B"],
        "__NOMBRE_B__": html.escape(nombres["B"]),
        "__REJ_B__": rejilla(t, "B"),
        "__TRES__": tres,
        "__MOMENTOS__": momentos(df, clips, a.clips_dir, a.salida, nombres),
    }
    pagina = PLANTILLA.read_text()
    for clave, valor in valores.items():
        pagina = pagina.replace(clave, valor)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(pagina)
    t.to_csv(a.salida.with_name("tramos.csv"), index=False)
    print(f"✓ {a.salida} · {t.tramo.nunique()} tramos")


if __name__ == "__main__":
    main()
