#!/usr/bin/env python3
"""Monta un HTML autocontenido sustituyendo <script src="x.js"> por su contenido.

El resultado no hace ni una sola petición externa, que es como tiene que
viajar esta landing (igual que la actual).
"""
import re
import sys
from pathlib import Path

AQUI = Path(__file__).parent


def montar(entrada: Path) -> str:
    html = entrada.read_text()

    def sustituir(m):
        nombre = m.group(1)
        ruta = AQUI / nombre
        if not ruta.exists():
            raise SystemExit(f"falta {ruta}")
        return "<script>\n" + ruta.read_text() + "\n</script>"

    html = re.sub(r'<script src="([^"]+)"></script>', sustituir, html)
    if 'script src=' in html:
        raise SystemExit("queda algún script externo sin inlinear")
    return html


if __name__ == "__main__":
    entrada = AQUI / (sys.argv[1] if len(sys.argv) > 1 else "test-env.html")
    salida = AQUI / (sys.argv[2] if len(sys.argv) > 2 else "build.html")
    salida.write_text(montar(entrada))
    print(f"{salida.name}: {salida.stat().st_size:,} bytes")
