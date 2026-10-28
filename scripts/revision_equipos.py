#!/usr/bin/env python
"""Hoja de revisión del equipo: plantilla, lector con validación y herramienta HTML de marcado.

Para que Alex marque rápido qué caja tiene el equipo mal en la hoja de `hoja_revision_equipos.py`
(docs/plan_causas_equipo_equivocado.md) y para que sus marcas se lean sin sorpresas.

Uso:
    python scripts/revision_equipos.py plantilla   # crea revision.csv SOLO si no existe
    python scripts/revision_equipos.py validar     # lee revision.csv y avisa de valores raros
    python scripts/revision_equipos.py html --ventana azar   # herramienta de marcado autocontenida
"""

import argparse
import base64
import csv
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
HOJA = R / "outputs/hoja_equipos"
CABECERA = ["ventana", "imagen", "caja", "equipo_correcto", "causa", "nota"]
# `otro_v3`: recortes de las filas que la feature v3 manda a `otro` (docs/diagnostico_22oct_d.md,
# bloque 1b). Sus cajas viven en `cajas_otro_v3.csv`, con la identidad y la etiqueta OCULTAS.
# `tope_cardinalidad`: filas cuya etiqueta cambia con el tope (docs/diagnostico_22oct_e.md).
# `arbitro_viterbi` / `viterbi_a_otro`: la pista del árbitro y lo que saca de los equipos
# (23-oct c).
VENTANAS = [
    "gt",
    "minuto_malo",
    "azar",
    "otro_v3",
    "tope_cardinalidad",
    "tope_trozo",
    "arbitro_viterbi",
    "viterbi_a_otro",
    "equipo_por_obs_20min",  # docs/diagnostico_26oct_b.md
]
EQUIPOS = [
    "A",
    "B",
    "portero_A",
    "portero_B",
    "arbitro",
    "staff",
    "jugador",  # para `otro_v3`: jugador de campo sin decir de qué equipo
    "no_es_persona",
    "dudoso",
]
CAUSAS = [
    "caja_dos_personas",
    "arbitro",
    "portero",
    "staff",
    "color_limpio",
    "otra",
    "no_se",
]


def crear_plantilla(ruta: Path) -> bool:
    """Escribe la cabecera SOLO si el fichero no existe. Devuelve True si lo ha creado."""
    if ruta.exists():
        return False
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="") as fh:
        csv.writer(fh).writerow(CABECERA)
    return True


def validar(filas: list[dict], cajas: dict[tuple[str, str], set]) -> list[str]:
    """Avisos (vacío = todo bien). `cajas`: {(ventana, imagen): {números de caja}}."""
    avisos, vistas = [], set()
    for i, f in enumerate(filas, start=2):  # la fila 1 es la cabecera
        pref = f"fila {i}"
        if f.get("ventana") not in VENTANAS:
            avisos.append(
                f"{pref}: ventana «{f.get('ventana')}» no es ninguna de {VENTANAS}"
            )
        if f.get("equipo_correcto") not in EQUIPOS:
            avisos.append(
                f"{pref}: equipo_correcto «{f.get('equipo_correcto')}» fuera de la lista"
            )
        if f.get("causa") not in CAUSAS:
            avisos.append(f"{pref}: causa «{f.get('causa')}» fuera de la lista")
        clave = (f.get("ventana"), f.get("imagen"))
        try:
            caja = int(f.get("caja", ""))
        except ValueError:
            avisos.append(f"{pref}: caja «{f.get('caja')}» no es un número")
            continue
        if clave not in cajas:
            avisos.append(
                f"{pref}: la imagen «{f.get('imagen')}» no está en la ventana"
            )
        elif caja not in cajas[clave]:
            avisos.append(f"{pref}: la imagen {f.get('imagen')} no tiene caja {caja}")
        if (clave, caja) in vistas:
            avisos.append(
                f"{pref}: la caja {caja} de {f.get('imagen')} ya estaba marcada"
            )
        vistas.add((clave, caja))
    return avisos


def cajas_de_la_hoja(ruta_cajas: Path):
    """`cajas.csv` más los `cajas_<ventana>.csv` de las ventanas que llevan fichero propio."""
    import pandas as pd

    partes = [pd.read_csv(ruta_cajas)] if ruta_cajas.exists() else []
    partes += [pd.read_csv(p) for p in sorted(ruta_cajas.parent.glob("cajas_*.csv"))]
    return pd.concat(partes, ignore_index=True)


def leer(ruta_revision: Path, ruta_cajas: Path) -> tuple[list[dict], list[str]]:
    c = cajas_de_la_hoja(ruta_cajas)
    cajas = {k: set(g.caja) for k, g in c.groupby(["ventana", "imagen"])}
    with open(ruta_revision, newline="") as fh:
        lector = csv.DictReader(fh)
        if lector.fieldnames != CABECERA:
            return [], [
                f"cabecera inesperada: {lector.fieldnames} (se esperaba {CABECERA})"
            ]
        filas = [{k: (v or "").strip() for k, v in f.items()} for f in lector]
    return filas, validar(filas, cajas)


PLANTILLA_HTML = (
    Path(__file__).resolve().parent / "plantillas" / "revision_equipos.html"
)


def generar_html(ventana: str, salida: Path) -> Path:
    import pandas as pd

    c = cajas_de_la_hoja(HOJA / "cajas.csv")
    c = c[c.ventana == ventana]
    imagenes, cajas = [], {}
    for nombre, g in c.groupby("imagen", sort=True):
        b64 = base64.b64encode((HOJA / ventana / nombre).read_bytes()).decode()
        imagenes.append(
            {
                "nombre": nombre,
                "archivo": g.reloj_archivo.iloc[0],
                "reproductor": g.reloj_reproductor.iloc[0],
                "b64": b64,
            }
        )
        cajas[nombre] = [
            {
                "caja": int(r.caja),
                "etiqueta": r.etiqueta,
                "id": "" if pd.isna(r.id_jugador) else int(r.id_jugador),
                "x1": int(r.x1),
                "y1": int(r.y1),
                "x2": int(r.x2),
                "y2": int(r.y2),
            }
            for r in g.sort_values("caja").itertuples()
        ]
    html = (
        PLANTILLA_HTML.read_text(encoding="utf-8")
        .replace("__VENTANA__", json.dumps(ventana))
        .replace("__IMAGENES__", json.dumps(imagenes))
        .replace("__CAJAS__", json.dumps(cajas))
        .replace("__EQUIPOS__", json.dumps(EQUIPOS))
        .replace("__CAUSAS__", json.dumps(CAUSAS))
    )
    salida.write_text(html, encoding="utf-8")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plantilla")
    v = sub.add_parser("validar")
    v.add_argument("--revision", default=str(HOJA / "revision.csv"))
    h = sub.add_parser("html")
    h.add_argument("--ventana", default="azar", choices=VENTANAS)
    args = ap.parse_args()
    if args.cmd == "plantilla":
        creado = crear_plantilla(HOJA / "revision.csv")
        print("✓ creado" if creado else "ya existía: no se toca")
    elif args.cmd == "validar":
        filas, avisos = leer(Path(args.revision), HOJA / "cajas.csv")
        print(f"{len(filas)} filas")
        for a in avisos:
            print("⚠", a)
        sys.exit(1 if avisos else 0)
    else:
        ruta = generar_html(args.ventana, HOJA / f"revision_{args.ventana}.html")
        print(f"✓ {ruta} ({ruta.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
