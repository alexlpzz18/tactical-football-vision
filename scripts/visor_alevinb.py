#!/usr/bin/env python
"""Visor del Alevín B: 5 minutos de VÍDEO sincronizados con la PIZARRA (jugadores + balón).

docs/alevinb_visor.md. Solo DIBUJO: lee el CSV del tracking y el caché de balón; no escribe en
`data/` salvo su carpeta de salida.

- Jugadores: el CSV de `gpu_colab.py seguimiento` (imagen original + lente), con su clasificación.
- Balón PROVISIONAL (no es el `tracking_balon` de producción, que mide el balón con una homografía
  y aquí hay lente): por fotograma, la candidata de más confianza que NO sea fija, llevada a metros
  con la lente. «Fija» = una celda de 8 px con candidatas en `FIJA_SEGUNDOS` segundos distintos o
  más de la parte (marcas, conos: no se mueven como un balón). Donde no se detecta, no se pinta.
- Vídeo: el tramo recodificado a 1280 px (H.264) para que pese poco; la pizarra sigue al vídeo.

Uso:
    python scripts/visor_alevinb.py --desde 600 --hasta 900
"""

import argparse
import json
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.campo_modelo import cargar_modelo  # noqa: E402
from src.report.replay_tactico import generar_replay  # noqa: E402

DATOS = R / "data/tracking_alevinb"
VIDEO = R / "data/raw/alevinb_p1.mp4"
CAMARA = R / "data/calibracion_alevinb/camara_alevinb.npz"
SALIDA = R / "outputs/visor_alevinb"
# Aviso por defecto sobre los colores de equipo (el del CSV de producción, sin selección automática)
AVISO_EQUIPOS = """<b>⚠️ Colores de equipo NO fiables en este partido:</b> una equipación es clara
  (blanca/celeste) y la otra oscura, y la feature de color de producción (tono y saturación, sin
  brillo) no separa el negro de la sombra. Sale ~4 de A y ~15 de B por fotograma, cuando deberían
  ser ~10 y ~10. Las POSICIONES sí valen; el color de cada ficha, no todavía."""
INICIO_IMPRESO_S = 9 * 3600 + 25 * 60 + 1  # archivo 0:00 = 09:25:01 del reloj impreso
INICIO_CORTE_ARCHIVO_S = (
    300.0  # la p1 empieza en el fotograma clave de 300,0 s del archivo
)
CELDA_PX = 8
# «fija» = celda con candidatas en al menos 20 SEGUNDOS DISTINTOS de la parte (p99 de las celdas;
# la mediana es 1 s y las marcas llegan a 80-152). Medir el TRAMO de tiempo, como al principio,
# mataba el balón real que vuelve a la misma zona: 532 celdas fijas y 111 frames pintados de 3.750.
FIJA_SEGUNDOS = 20
MARGEN_CAMPO_M = 2.0
# La pizarra solo une dos detecciones de balón a < 3 s y tras la última lo quita a los 0,25 s: con
# balón en el 6,7 % de los frames era un parpadeo invisible. Tras cada detección se MANTIENE
# este tiempo en su sitio, ATENUADO (ayuda visual: la leyenda lo dice; el dato no cambia).
MANTENER_BALON_S = 1.5
MAX_HUECO_PIZARRA_S = 3.0  # el `max_hueco_s` por defecto de generar_replay
LARGO, ANCHO = 100.0, 64.0


def _lente():
    import importlib.util

    spec = importlib.util.spec_from_file_location("lc", R / "scripts/lente_camara.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def celdas_fijas(
    cache: list, celda: int = CELDA_PX, minimo: int = FIJA_SEGUNDOS
) -> set:
    """Celdas de píxeles con candidatas en `minimo` segundos distintos o más (marcas, conos).

    Una marca está ahí todo el partido; el balón pasa unos fotogramas cada vez. Por eso se cuentan
    SEGUNDOS DISTINTOS, no cuánto tiempo hay entre la primera y la última aparición.
    """
    segundos: dict[tuple, set] = {}
    for e in cache:
        for d in e["dets"]:
            cx, cy = (d[2] + d[4]) / 2, (d[3] + d[5]) / 2
            segundos.setdefault((int(cx // celda), int(cy // celda)), set()).add(
                int(e["t"])
            )
    return {c for c, ss in segundos.items() if len(ss) >= minimo}


def balon_provisional(
    cache: list, fijas: set, cam, celda: int = CELDA_PX
) -> pd.DataFrame:
    """Una fila por fotograma con balón: la mejor candidata no fija, en metros con la lente."""
    filas = []
    for e in cache:
        buenas = [
            d for d in e["dets"]
            if (int((d[2] + d[4]) / 2 // celda), int((d[3] + d[5]) / 2 // celda)) not in fijas
        ]  # fmt: skip
        if not buenas:
            continue
        d = max(buenas, key=lambda d: float(d[6]))
        xy = cam.pixel_a_metros(np.array([[(d[2] + d[4]) / 2, d[5]]], float))[0]
        if not np.isfinite(xy).all():
            continue
        x, y = float(xy[0]), float(xy[1])
        if -MARGEN_CAMPO_M <= x <= LARGO + MARGEN_CAMPO_M and (
            -MARGEN_CAMPO_M <= y <= ANCHO + MARGEN_CAMPO_M
        ):
            filas.append(
                {"frame": e["frame_idx"], "tiempo_s": e["t"], "id_jugador": -1,
                 "etiqueta": "balon", "x_m": x, "y_m": y, "es_real": 1}
            )  # fmt: skip
    return mantener_balon(pd.DataFrame(filas))


def mantener_balon(
    bal: pd.DataFrame, mantener_s: float = MANTENER_BALON_S
) -> pd.DataFrame:
    """Añade, tras cada detección aislada, una fila atenuada en el mismo sitio `mantener_s` después.

    Solo donde la pizarra NO va a unir la detección con la siguiente (hueco > 3 s): ahí el balón
    desaparecía a los 0,25 s. Las filas añadidas llevan `es_real = 0`, y la pizarra atenúa sola lo
    que no es detección real.
    """
    if bal.empty:
        return bal
    bal = bal.sort_values("tiempo_s").reset_index(drop=True)
    siguiente = bal["tiempo_s"].shift(-1)
    aislada = siguiente.isna() | ((siguiente - bal["tiempo_s"]) > MAX_HUECO_PIZARRA_S)
    extra = bal[aislada].copy()
    extra["tiempo_s"] = extra["tiempo_s"] + mantener_s
    extra["es_real"] = 0
    return pd.concat([bal, extra], ignore_index=True).sort_values("tiempo_s")


def reloj(t: float) -> str:
    """Los tres relojes de un instante del corte: corte, archivo y reloj impreso."""
    a = t + INICIO_CORTE_ARCHIVO_S
    i = a + INICIO_IMPRESO_S
    return (
        f"{int(t // 60)}:{int(t % 60):02d} corte · {int(a // 60)}:{int(a % 60):02d} archivo"
        f" · {int(i // 3600):02d}:{int(i % 3600 // 60):02d}:{int(i % 60):02d} impreso"
    )


SINCRONIA = """
<script>
// El vídeo manda: la página que contiene a la pizarra le envía el tiempo y ella se dibuja ahí.
window.addEventListener('message', (e) => {
  if (!e.data || typeof e.data.t !== 'number') return;
  T = Math.min(Math.max(e.data.t, TMIN), TMAX);
  dibujar(T);
  refrescarUI();
});
</script>
"""

PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alevín B · vídeo y pizarra</title>
<style>
:root { --fondo: #f6f7f9; --texto: #111827; --tenue: #6b7280; --borde: #e5e7eb; }
@media (prefers-color-scheme: dark) {
  :root { --fondo: #0f1115; --texto: #e5e7eb; --tenue: #9ca3af; --borde: #262a33; } }
body { margin: 0; background: var(--fondo); color: var(--texto);
  font: 14px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; }
header { padding: 14px 16px 6px; }
h1 { font-size: 17px; margin: 0 0 4px; }
.nota { color: var(--tenue); font-size: 12.5px; margin: 0; max-width: 1100px; }
.reloj { font-variant-numeric: tabular-nums; font-weight: 650; padding: 6px 16px; }
main { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 8px 16px 16px; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; } }
video, iframe { width: 100%; border: 1px solid var(--borde); border-radius: 8px; background: #000; }
/* la pizarra trae su cabecera y su barra debajo del campo: necesita más alto que el vídeo */
iframe { height: min(82vh, 760px); background: var(--fondo); }
</style></head><body>
<header>
  <h1>Alevín B · parte 1 · __TRAMO__</h1>
  <p class="nota">Jugadores con su clasificación (A, B, porteros, árbitro y staff en gris). Balón
  PROVISIONAL: la detección de más confianza de cada fotograma, sin las marcas fijas; tras cada
  detección se mantiene 1,5 s atenuado (ayuda visual) y entre detecciones cercanas se une. Donde no
  se detecta, no se pinta: en esta cámara el balón mide 2-4 px en casi todo el campo.
  La pizarra sigue al vídeo: dale al play o arrastra el vídeo.</p>
  <p class="nota">__AVISO_EQUIPOS__</p>
</header>
<div class="reloj" id="reloj">--</div>
<main>
  <video id="video" src="__VIDEO__" controls playsinline preload="auto"></video>
  <iframe id="pizarra" src="__PIZARRA__" title="Pizarra"></iframe>
</main>
<script>
const DESDE = __DESDE__, INICIO_ARCHIVO = __INICIO_ARCHIVO__, INICIO_IMPRESO = __INICIO_IMPRESO__;
const video = document.getElementById('video'), pizarra = document.getElementById('pizarra');
const r2 = (n) => String(Math.floor(n)).padStart(2, '0');
function relojes(t) {
  const a = t + INICIO_ARCHIVO, i = a + INICIO_IMPRESO;
  return `${Math.floor(t / 60)}:${r2(t % 60)} corte · `
    + `${Math.floor(a / 60)}:${r2(a % 60)} archivo · `
    + `${r2(i / 3600)}:${r2(i % 3600 / 60)}:${r2(i % 60)} impreso`;
}
function sincronizar() {
  const t = DESDE + video.currentTime;
  pizarra.contentWindow && pizarra.contentWindow.postMessage({ t }, '*');
  document.getElementById('reloj').textContent = relojes(t);
  requestAnimationFrame(sincronizar);
}
requestAnimationFrame(sincronizar);
</script>
</body></html>
"""


def recortar_video(desde: float, hasta: float, destino: Path) -> None:
    """Tramo recodificado a 1280 px de ancho (el original pesa 1 GB la media hora)."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(desde), "-i", str(VIDEO),
         "-t", str(hasta - desde), "-vf", "scale=1280:-2", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "26", "-an", "-movflags", "+faststart", str(destino)],
        check=True,
    )  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--desde", type=float, default=600.0, help="segundos del CORTE de la p1"
    )
    ap.add_argument("--hasta", type=float, default=900.0)
    ap.add_argument("--csv", type=Path, default=DATOS / "posiciones_alevinb_p1.csv")
    ap.add_argument("--balon", type=Path, default=DATOS / "cache_alevinb_p1_balon.pkl")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument(
        "--aviso-equipos", default=AVISO_EQUIPOS, help="nota sobre los colores (HTML)"
    )
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)

    jug = pd.read_csv(a.csv)
    jug = jug[(jug.tiempo_s >= a.desde) & (jug.tiempo_s <= a.hasta)]
    partes = [jug]
    resumen = {"tramo": [reloj(a.desde), reloj(a.hasta)], "filas_jugadores": len(jug)}
    if a.balon.exists():
        cache = pickle.load(open(a.balon, "rb"))["cache"]
        fijas = celdas_fijas(cache)
        lc = _lente()
        bal = balon_provisional(
            [e for e in cache if a.desde <= e["t"] <= a.hasta],
            fijas,
            lc.cargar_camara(CAMARA),
        )
        partes.append(bal)
        frames_tramo = sum(1 for e in cache if a.desde <= e["t"] <= a.hasta)
        resumen.update(
            celdas_fijas=len(fijas),
            frames_balon_en_tramo=frames_tramo,
            frames_con_balon_pintado=len(bal),
        )
    else:
        resumen["balon"] = f"sin caché de balón ({a.balon.name}): solo jugadores"
    tramo = pd.concat(partes, ignore_index=True).sort_values(["tiempo_s", "id_jugador"])
    csv_tramo = a.salida / "tramo.csv"
    tramo.to_csv(csv_tramo, index=False)

    pizarra = a.salida / "pizarra.html"
    generar_replay(
        csv_tramo,
        pizarra,
        modelo=cargar_modelo("f11").con_dimensiones(LARGO, ANCHO),
        titulo="Alevín B · pizarra",
        espejar="y",  # la banda cercana (y = 0) abajo, como en el vídeo
    )
    pizarra.write_text(pizarra.read_text().replace("</body>", SINCRONIA + "</body>"))
    recortar_video(a.desde, a.hasta, a.salida / "video.mp4")
    pagina = (
        PAGINA.replace("__TRAMO__", f"{reloj(a.desde)} → {reloj(a.hasta)}")
        .replace("__AVISO_EQUIPOS__", a.aviso_equipos)
        .replace("__VIDEO__", "video.mp4")
        .replace("__PIZARRA__", "pizarra.html")
        .replace("__DESDE__", str(a.desde))
        .replace("__INICIO_ARCHIVO__", str(INICIO_CORTE_ARCHIVO_S))
        .replace("__INICIO_IMPRESO__", str(INICIO_IMPRESO_S))
    )
    (a.salida / "index.html").write_text(pagina, encoding="utf-8")
    (a.salida / "resumen.json").write_text(
        json.dumps(resumen, indent=1, ensure_ascii=False)
    )
    print(json.dumps(resumen, indent=1, ensure_ascii=False))
    print(f"✓ {a.salida / 'index.html'}")


if __name__ == "__main__":
    main()
