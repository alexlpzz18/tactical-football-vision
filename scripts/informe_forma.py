#!/usr/bin/env python
"""Motor del informe de FORMA del equipo, por tramos de ≥ 10 s (tarea 5 de la noche).

Lee NUESTRO formato de CSV de posiciones (frame, tiempo_s, id_jugador, etiqueta, x_m, y_m, …), así
que sirve igual para un partido de SkillCorner convertido (`skillcorner_a_csv.py`) que para los
nuestros. Si el CSV trae la columna `posesion` (A/B), separa con y sin balón; si no, todo junto.

Por tramo y equipo (jugadores de campo, sin porteros), la MEDIANA sobre los fotogramas del tramo de:
- **largo del bloque**: del jugador más retrasado al más adelantado, en profundidad;
- **anchura**: de banda a banda;
- **altura de la defensa**: distancia de su línea de defensa a su propia portería;
- **distancia entre líneas** (defensa-medio y medio-ataque): las tres líneas son el corte 1D
  óptimo de las profundidades (`superposicion_tactica.cortes_1d`);
- **ocupación de zonas**: % de jugador-fotogramas en cada tercio (propio, medio, rival) × carril.
Qué portería defiende cada equipo se deduce en CADA tramo de dónde está su portero (vale tras el
descanso).

Las «3 cosas a entrenar» salen de reglas sobre esos números (umbrales relativos al tamaño del campo,
dichos en el propio informe): no se usa ningún modelo de lenguaje.

Uso:
    python scripts/informe_forma.py --csv outputs/literatura/skillcorner/1874553.csv \\
        --largo 105 --ancho 68 --equipo A --salida outputs/literatura/informe/1874553.html
"""

import argparse
import html
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "scripts"))

from superposicion_tactica import cortes_1d  # noqa: E402

# Reglas: (clave, métrica, fase, sentido, umbral relativo, a qué medida del campo, texto)
REGLAS = [
    ("largo", "largo_m", "sin", ">", 0.35, "largo",
     "Juntar líneas al defender",
     "Sin balón, el bloque mide de punta a punta más de un tercio del campo. Trabajar la "
     "basculación y el repliegue juntos, con distancias de referencia entre líneas."),
    ("def_med", "def_med_m", "sin", ">", 0.13, "largo",
     "Acercar la línea de medios a la defensa",
     "Sin balón queda demasiado espacio entre defensa y medios: es el pasillo por el que el rival "
     "recibe entre líneas. Ejercicios de bloque medio con dos líneas pegadas."),
    ("ancho_sin", "ancho_m", "sin", ">", 0.65, "ancho",
     "Cerrar por dentro al defender",
     "Sin balón el equipo ocupa casi todo el ancho: el carril central queda abierto. Trabajar las "
     "ayudas y la basculación hacia el lado del balón."),
    ("ancho_con", "ancho_m", "con", "<", 0.55, "ancho",
     "Abrir el campo con balón",
     "Con balón el equipo ocupa poco ancho y el rival defiende en poco espacio. Trabajar la "
     "amplitud: extremos o laterales pegados a la banda."),
    ("altura", "altura_def_m", "sin", "<", 0.20, "largo",
     "Defender más arriba, saliendo juntos",
     "Sin balón la defensa vive muy cerca de su portería. Trabajar la salida coordinada de la "
     "línea tras despejes y pases atrás del rival."),
]  # fmt: skip


def metricas_frame(
    xy: np.ndarray, defiende_x0: bool, largo: float, ancho: float
) -> dict | None:
    """Métricas de forma de un equipo en un fotograma (jugadores de campo)."""
    if len(xy) < 4:
        return None
    prof = xy[:, 0] if defiende_x0 else largo - xy[:, 0]
    grupos = cortes_1d(prof, 3)
    lineas = [float(g.mean()) for g in grupos]
    tercio = np.minimum((prof / largo * 3).astype(int), 2)
    carril = np.minimum((xy[:, 1] / ancho * 3).astype(int), 2)
    return {
        "largo_m": float(prof.max() - prof.min()),
        "ancho_m": float(xy[:, 1].max() - xy[:, 1].min()),
        "altura_def_m": lineas[0],
        "def_med_m": lineas[1] - lineas[0],
        "med_ata_m": lineas[2] - lineas[1],
        **{f"zona_{t}{c}": float(np.mean((tercio == t) & (carril == c))) for t in range(3)
           for c in range(3)},
    }  # fmt: skip


def por_tramos(
    df: pd.DataFrame, largo: float, ancho: float, tramo_s: float, cada: int
) -> pd.DataFrame:
    df = df[df.x_m.between(0, largo) & df.y_m.between(0, ancho)]
    hay_posesion = "posesion" in df.columns
    filas = []
    for k, tr in df.groupby((df.tiempo_s // tramo_s).astype(int)):
        frames = sorted(tr.frame.unique())[::cada]
        tr = tr[tr.frame.isin(frames)]
        for e in ("A", "B"):
            p = tr[tr.etiqueta == f"portero_{e}"]
            if p.empty:
                continue
            defiende_x0 = bool(p.x_m.median() < largo / 2)
            campo = tr[tr.etiqueta == e]
            ms = [
                m
                for _f, g in campo.groupby("frame")
                if (
                    m := metricas_frame(
                        g[["x_m", "y_m"]].to_numpy(), defiende_x0, largo, ancho
                    )
                )
            ]
            if not ms:
                continue
            fila = {"tramo": int(k), "t0": k * tramo_s, "equipo": e}
            fila |= {c: float(np.median([m[c] for m in ms])) for c in ms[0]}
            if hay_posesion:
                pos = tr.drop_duplicates("frame").posesion.fillna("")
                propia = float((pos == e).mean())
                rival = float(((pos != e) & (pos != "")).mean())
                fila["fase"] = (
                    "con" if propia >= 0.7 else ("sin" if rival >= 0.7 else "mixta")
                )
            else:
                fila["fase"] = "todo"
            filas.append(fila)
    return pd.DataFrame(filas)


def evaluar_reglas(t: pd.DataFrame, largo: float, ancho: float) -> list[dict]:
    salida = []
    for clave, met, fase, sentido, rel, ref, titulo, texto in REGLAS:
        sub = t[t.fase == fase] if (t.fase != "todo").any() else t
        if sub.empty:
            continue
        umbral = rel * (largo if ref == "largo" else ancho)
        incumple = sub[met] > umbral if sentido == ">" else sub[met] < umbral
        salida.append(
            {
                "clave": clave,
                "titulo": titulo,
                "texto": texto,
                "pct": float(100 * incumple.mean()),
                "mediana": float(sub[met].median()),
                "umbral": umbral,
                "sentido": sentido,
                "tramos": len(sub),
                "fase": fase,
            }
        )
    return sorted(salida, key=lambda r: -r["pct"])


def svg_forma(t: pd.DataFrame, largo: float, ancho: float, color: str) -> str:
    """Campo con las tres líneas medias del equipo (sin balón si hay fases), atacando a derecha."""
    sub = t[t.fase == "sin"] if (t.fase == "sin").any() else t
    esc = 4.0
    w, h = largo * esc, ancho * esc
    d0 = sub.altura_def_m.median()
    d1 = d0 + sub.def_med_m.median()
    d2 = d1 + sub.med_ata_m.median()
    an = sub.ancho_m.median()
    y0, y1 = (ancho - an) / 2 * esc, (ancho + an) / 2 * esc
    lineas = "".join(
        f'<line x1="{x * esc:.0f}" y1="{y0:.0f}" x2="{x * esc:.0f}" y2="{y1:.0f}" '
        f'stroke="{color}" stroke-width="5" stroke-linecap="round"/>'
        f'<text x="{x * esc + 6:.0f}" y="{y0 - 6:.0f}" class="et">{n}</text>'
        for x, n in ((d0, "defensa"), (d1, "medio"), (d2, "ataque"))
    )
    return f"""<svg viewBox="-10 -24 {w + 20:.0f} {h + 34:.0f}" role="img"
aria-label="Forma media del equipo" class="campo">
<rect x="0" y="0" width="{w:.0f}" height="{h:.0f}" class="cesped"/>
<line x1="{w / 2:.0f}" y1="0" x2="{w / 2:.0f}" y2="{h:.0f}" class="raya"/>
<circle cx="{w / 2:.0f}" cy="{h / 2:.0f}" r="{9.15 * esc:.0f}" class="raya" fill="none"/>
<rect x="0" y="{(ancho - 40.3) / 2 * esc:.0f}" width="{16.5 * esc:.0f}" height="{40.3 * esc:.0f}"
 class="raya" fill="none"/>
<rect x="{w - 16.5 * esc:.0f}" y="{(ancho - 40.3) / 2 * esc:.0f}" width="{16.5 * esc:.0f}"
 height="{40.3 * esc:.0f}" class="raya" fill="none"/>
<rect x="{d0 * esc:.0f}" y="{y0:.0f}" width="{(d2 - d0) * esc:.0f}" height="{y1 - y0:.0f}"
 fill="{color}" opacity="0.12"/>{lineas}
<text x="{w - 4:.0f}" y="{h + 8:.0f}" class="et" text-anchor="end">ataca →</text></svg>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--largo", type=float, required=True)
    ap.add_argument("--ancho", type=float, required=True)
    ap.add_argument("--equipo", default="A", choices=["A", "B"])
    ap.add_argument("--tramo-s", type=float, default=10.0)
    ap.add_argument(
        "--cada", type=int, default=5, help="1 de cada N fotogramas del tramo"
    )
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    if a.tramo_s < 10:
        raise SystemExit(
            "Los tramos tienen que ser de 10 s o más (a menos, la forma es ruido)"
        )
    df = pd.read_csv(a.csv)
    meta_ruta = a.csv.with_suffix(".json")
    meta = json.loads(meta_ruta.read_text()) if meta_ruta.exists() else {}
    t = por_tramos(df, a.largo, a.ancho, a.tramo_s, a.cada)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(a.salida.with_suffix(".csv"), index=False)
    mio = t[t.equipo == a.equipo]
    reglas = evaluar_reglas(mio, a.largo, a.ancho)
    nombre = meta.get(a.equipo, f"Equipo {a.equipo}")
    rival = meta.get("B" if a.equipo == "A" else "A", "rival")

    def fila(fase: str, etiqueta: str) -> str:
        s = mio[mio.fase == fase] if fase != "todas" else mio
        if s.empty:
            return ""
        return (
            f"<tr><th>{etiqueta}</th><td>{len(s)}</td>"
            f"<td>{s.largo_m.median():.0f} m</td><td>{s.ancho_m.median():.0f} m</td>"
            f"<td>{s.altura_def_m.median():.0f} m</td><td>{s.def_med_m.median():.0f} m</td>"
            f"<td>{s.med_ata_m.median():.0f} m</td></tr>"
        )

    filas = (
        fila("sin", "Sin balón")
        + fila("con", "Con balón")
        + fila("todas", "Todo el partido")
    )
    tres = "".join(
        f"<li><b>{html.escape(r['titulo'])}.</b> {html.escape(r['texto'])} "
        f"<span class='dato'>Pasa en el {r['pct']:.0f} % de los tramos {r['fase']} balón "
        f"(mediana {r['mediana']:.0f} m; referencia {'≤' if r['sentido'] == '>' else '≥'} "
        f"{r['umbral']:.0f} m).</span></li>"
        for r in reglas[:3]
    )
    zonas_sin = mio[mio.fase == "sin"] if (mio.fase == "sin").any() else mio
    rejilla = "".join(
        "<tr>"
        + "".join(
            f"<td style='--o:{zonas_sin[f'zona_{tt}{c}'].mean():.2f}'>"
            f"{100 * zonas_sin[f'zona_{tt}{c}'].mean():.0f} %</td>"
            for tt in range(3)
        )
        + "</tr>"
        for c in (2, 1, 0)
    )
    color = "#2563eb"
    pagina = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Informe de forma</title><style>
:root {{ --fondo:#f7f7f5; --texto:#1c1f24; --tenue:#5f6670; --linea:#d9dcd6; --acento:{color}; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --fondo:#14171b;
  --texto:#e9ebee; --tenue:#a2a9b1; --linea:#2e343b; }} }}
body {{ margin:0; background:var(--fondo); color:var(--texto);
  font:15px/1.45 system-ui,-apple-system,sans-serif; }}
main {{ max-width:860px; margin:0 auto; padding:20px 16px; }}
h1 {{ font-size:22px; margin:0 0 2px; }} h2 {{ font-size:16px; margin:22px 0 8px; }}
.tenue {{ color:var(--tenue); font-size:13px; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:6px 8px; border-bottom:1px solid var(--linea); text-align:right; }}
th:first-child {{ text-align:left; }}
.rejilla td {{ text-align:center; background:color-mix(in srgb, var(--acento)
  calc(var(--o) * 260%), transparent); border:1px solid var(--linea); }}
.campo {{ width:100%; max-width:520px; }} .cesped {{ fill:#2f7d4a; }}
.raya {{ stroke:#ffffffaa; stroke-width:2; }} .et {{ font-size:13px; fill:#fff; }}
ol li {{ margin-bottom:8px; }} .dato {{ color:var(--tenue); font-size:13px; }}
.dos {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; align-items:start; }}
@media (max-width:640px) {{ .dos {{ grid-template-columns:1fr; }} }}
</style></head><body><main>
<h1>Forma de {html.escape(nombre)}</h1>
<div class="tenue">{html.escape(meta.get('partido', ''))} {html.escape(meta.get('marcador', ''))} ·
contra {html.escape(rival)} · {len(mio)} tramos de {a.tramo_s:.0f} s</div>
<h2>Tres cosas a entrenar</h2><ol>{tres}</ol>
<h2>Cómo se coloca el equipo (medianas por tramo)</h2>
<table><tr><th></th><th>tramos</th><th>largo del bloque</th><th>anchura</th>
<th>altura de la defensa</th><th>defensa-medio</th><th>medio-ataque</th></tr>{filas}</table>
<div class="dos"><div><h2>Forma media sin balón</h2>{svg_forma(mio, a.largo, a.ancho, color)}</div>
<div><h2>Dónde está el equipo sin balón</h2><p class="tenue">% del tiempo de los jugadores de
campo en cada zona (izquierda: su campo; arriba: banda izquierda al atacar).</p>
<table class="rejilla"><tr><th>propio</th><th>medio</th><th>rival</th></tr>{rejilla}</table>
</div></div>
<p class="tenue">Cómo se calcula: cada número es la mediana de un tramo de {a.tramo_s:.0f} s, con
los jugadores de campo (sin porteros). Las tres líneas salen de partir a los jugadores por
profundidad en tres grupos. Las referencias de las «cosas a entrenar» son proporciones del campo
(largo del bloque ≤ 35 % del largo, defensa-medio ≤ 13 %, anchura sin balón ≤ 65 % del ancho, con
balón ≥ 55 %, altura de la defensa ≥ 20 % del largo): son de partida y hay que calibrarlas con
partidos de la categoría. Datos: {html.escape(meta.get('fuente', a.csv.name))}.</p>
</main></body></html>"""
    a.salida.write_text(pagina)
    print(f"✓ {a.salida} · {len(t)} filas en {a.salida.with_suffix('.csv').name}")
    for r in reglas:
        print(
            f"  {r['pct']:5.1f} %  {r['titulo']}  "
            f"(mediana {r['mediana']:.1f}, umbral {r['umbral']:.1f})"
        )


if __name__ == "__main__":
    main()
