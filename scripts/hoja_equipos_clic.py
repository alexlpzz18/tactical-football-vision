#!/usr/bin/env python
"""Hoja de EQUIPO para marcar con clics (docs/registro_mision.md): verdad de referencia de equipo.

Muestra N detecciones repartidas por TODO el partido (bloques de tiempo × franja de profundidad),
cada una con su recorte ampliado y su caja. Alex pulsa una tecla por recorte y descarga un CSV.

- La caja dibujada es LA DE LA FILA: la detección muestreada (frame y caja del caché), no «la más
  cercana a una posición». La verdad queda indexada por frame y caja (no por id del sistema, que
  caduca), y sirve para medir cualquier versión del sistema.
- Los fotogramas se leen con el ffmpeg de línea de comandos (CLAUDE.md).
- El muestreo NO mira ninguna etiqueta del sistema: no hay forma de sesgarlo hacia sus aciertos.

Uso:
    python scripts/hoja_equipos_clic.py --cache data/tracking_alevinb/cache_alevinb_p1.pkl \\
        --video data/raw/alevinb_p1.mp4 --largo 100 --ancho 64 --n 300 \\
        --salida outputs/hoja_equipos_alevinb
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.utils.video_ffmpeg import leer_frames_ffmpeg  # noqa: E402

PAGINA = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hoja de equipos</title>
<style>
:root { --fondo:#111418; --panel:#1b2027; --texto:#e8eaed; --tenue:#9aa3ad; --ok:#3fb27f; }
body { margin:0; background:var(--fondo); color:var(--texto);
  font:16px/1.4 system-ui,sans-serif; }
main { max-width:760px; margin:0 auto; padding:16px; }
img { width:100%; image-rendering:pixelated; border-radius:8px; background:#000; }
.botones { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:12px 0; }
button { padding:14px 8px; font-size:16px; border:0; border-radius:8px; background:var(--panel);
  color:var(--texto); cursor:pointer; }
button.sel { outline:3px solid var(--ok); }
.tenue { color:var(--tenue); font-size:14px; }
.barra { height:8px; background:var(--panel); border-radius:4px; overflow:hidden; }
.barra div { height:100%; background:var(--ok); }
nav { display:flex; gap:8px; align-items:center; margin:8px 0; }
nav button { padding:8px 12px; }
</style></head><body><main>
<h2>Hoja de equipos · __TITULO__</h2>
<p class="tenue">Marca de qué equipo es la persona del <b>recuadro amarillo</b> (a la izquierda,
ampliada; a la derecha, su entorno). Teclas: <b>1</b> __E1__ · <b>2</b> __E2__ · <b>3</b> portero ·
<b>4</b> árbitro · <b>5</b> no juega (entrenador, público, nadie) · <b>0</b> no se sabe ·
<b>←</b> atrás. Se guarda solo en este navegador; al acabar, «Descargar CSV».</p>
<div class="barra"><div id="prog"></div></div>
<nav><button id="atras">← atrás</button><span id="pos"></span>
<button id="saltar">sin marcar siguiente →</button>
<button id="bajar">Descargar CSV</button></nav>
<img id="img" alt="recorte">
<div class="botones" id="botones"></div>
<p class="tenue" id="info"></p>
</main><script>
const ITEMS = __ITEMS__;
const OPC = [["1","__E1__","E1"],["2","__E2__","E2"],["3","portero","K"],["4","árbitro","R"],
             ["5","no juega","N"],["0","no se sabe","X"]];
const CLAVE = "hoja_equipos___ID__";
let marcas = {};
try { marcas = JSON.parse(localStorage.getItem(CLAVE) || "{}"); } catch (e) {}
let i = ITEMS.findIndex(it => !(it.n in marcas)); if (i < 0) i = 0;
const $ = id => document.getElementById(id);
function pinta() {
  const it = ITEMS[i];
  $("img").src = it.img;
  $("pos").textContent = (i + 1) + " / " + ITEMS.length;
  $("info").textContent = "minuto " + it.reloj + " · franja " + it.franja;
  $("prog").style.width = (100 * Object.keys(marcas).length / ITEMS.length) + "%";
  $("botones").innerHTML = "";
  for (const [tecla, nombre, cod] of OPC) {
    const b = document.createElement("button");
    b.textContent = tecla + " · " + nombre;
    if (marcas[it.n] === cod) b.className = "sel";
    b.onclick = () => marca(cod);
    $("botones").appendChild(b);
  }
}
function marca(cod) {
  marcas[ITEMS[i].n] = cod;
  try { localStorage.setItem(CLAVE, JSON.stringify(marcas)); } catch (e) {}
  if (i < ITEMS.length - 1) i++;
  pinta();
}
document.addEventListener("keydown", e => {
  const o = OPC.find(o => o[0] === e.key);
  if (o) marca(o[2]);
  if (e.key === "ArrowLeft" && i > 0) { i--; pinta(); }
  if (e.key === "ArrowRight" && i < ITEMS.length - 1) { i++; pinta(); }
});
$("atras").onclick = () => { if (i > 0) { i--; pinta(); } };
$("saltar").onclick = () => {
  const j = ITEMS.findIndex(it => !(it.n in marcas)); if (j >= 0) { i = j; pinta(); }
};
$("bajar").onclick = () => {
  const filas = ["n,frame,x1,y1,x2,y2,franja,marca"].concat(ITEMS.map(it =>
    [it.n, it.frame, it.x1, it.y1, it.x2, it.y2, it.franja, marcas[it.n] || ""].join(",")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([filas.join("\\n")], {type: "text/csv"}));
  a.download = "marcas___ID__.csv"; a.click();
};
pinta();
</script></body></html>
"""


def muestrear(cache: list, largo: float, ancho: float, n: int, eje: int, rng) -> list:
    """N detecciones del campo, con cupos iguales por bloque de tiempo y tercio de profundidad.

    Como mucho una detección por franja y frame (así un frame no llena la hoja de vecinos).
    """
    lado = ancho if eje == 1 else largo
    n_bloques = max(1, n // 30)
    limites = np.linspace(cache[0]["t"], cache[-1]["t"] + 1e-6, n_bloques + 1)
    por_celda: dict = {}
    for e in cache:
        b = int(np.searchsorted(limites, e["t"], side="right") - 1)
        vistos = set()
        orden = rng.permutation(len(e["dets"]))
        for k in orden:
            d = e["dets"][k]
            if not (1.0 <= d[0] <= largo - 1.0 and 1.0 <= d[1] <= ancho - 1.0):
                continue
            franja = min(int(d[eje] / lado * 3), 2)
            if franja in vistos:
                continue
            vistos.add(franja)
            por_celda.setdefault((b, franja), []).append((e["frame_idx"], e["t"], d))
    cupo = max(1, n // (n_bloques * 3))
    elegidas = []
    for celda in sorted(por_celda):
        c = por_celda[celda]
        for k in rng.choice(len(c), min(cupo, len(c)), replace=False):
            elegidas.append((celda[1], *c[k]))
    return sorted(elegidas, key=lambda x: x[1])


def recorte(img: np.ndarray, caja, lado_px: int = 420) -> np.ndarray:
    """Izquierda: la persona ampliada. Derecha: su entorno (200 px) con la caja en amarillo."""
    x1, y1, x2, y2 = [float(v) for v in caja]
    h, w = img.shape[:2]

    def ventana(medio_lado):
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        a, b = int(max(0, cx - medio_lado)), int(max(0, cy - medio_lado))
        c, d = int(min(w, cx + medio_lado)), int(min(h, cy + medio_lado))
        trozo = img[b:d, a:c].copy()
        escala = lado_px / max(trozo.shape[:2])
        trozo = cv2.resize(
            trozo, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC
        )
        p1 = (int((x1 - a) * escala) - 2, int((y1 - b) * escala) - 2)
        p2 = (int((x2 - a) * escala) + 2, int((y2 - b) * escala) + 2)
        cv2.rectangle(trozo, p1, p2, (0, 230, 255), 1)
        lienzo = np.zeros((lado_px, lado_px, 3), np.uint8)
        lienzo[: trozo.shape[0], : trozo.shape[1]] = trozo[:lado_px, :lado_px]
        return lienzo

    cerca = ventana(max(x2 - x1, y2 - y1) * 1.1)
    lejos = ventana(100)
    return np.hstack([cerca, lejos])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--largo", type=float, required=True)
    ap.add_argument("--ancho", type=float, required=True)
    ap.add_argument("--eje-profundidad", choices=["x", "y"], default="y")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--equipo1", default="blanco")
    ap.add_argument("--equipo2", default="verde oscuro")
    ap.add_argument("--titulo", default="alevín B, parte 1")
    ap.add_argument(
        "--inicio-reloj-s", type=float, default=0.0, help="reloj del vídeo en t=0"
    )
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(a.semilla)
    cache = pickle.load(open(a.cache, "rb"))["cache"]
    cache = [{**e, "dets": [d for d in e["dets"] if d[6] >= a.conf]} for e in cache]
    eje = 1 if a.eje_profundidad == "y" else 0
    elegidas = muestrear(cache, a.largo, a.ancho, a.n, eje, rng)
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "img").mkdir(exist_ok=True)
    por_frame: dict = {}
    for n, (franja, frame, t, d) in enumerate(elegidas):
        por_frame.setdefault(frame, []).append((n, franja, t, d))
    items = []
    nombres = ["cerca", "media", "lejos"]
    for frame, img in leer_frames_ffmpeg(a.video, por_frame):
        for n, franja, t, d in por_frame[frame]:
            ruta = f"img/{n:04d}.jpg"
            cv2.imwrite(
                str(a.salida / ruta),
                recorte(img, d[2:6]),
                [cv2.IMWRITE_JPEG_QUALITY, 90],
            )
            s = int(t + a.inicio_reloj_s)
            items.append(
                {
                    "n": n,
                    "frame": int(frame),
                    "x1": round(float(d[2]), 2),
                    "y1": round(float(d[3]), 2),
                    "x2": round(float(d[4]), 2),
                    "y2": round(float(d[5]), 2),
                    "franja": nombres[franja],
                    "reloj": f"{s // 60}:{s % 60:02d}",
                    "img": ruta,
                }
            )
    # orden barajado: que no se marquen seguidas las del mismo minuto (el contexto ayuda de más)
    items = [items[k] for k in rng.permutation(len(items))]
    ident = a.salida.name
    html = (
        PAGINA.replace("__ITEMS__", json.dumps(items))
        .replace("__TITULO__", a.titulo)
        .replace("__E1__", a.equipo1)
        .replace("__E2__", a.equipo2)
        .replace("__ID__", ident)
    )
    (a.salida / "index.html").write_text(html)
    (a.salida / "muestra.json").write_text(json.dumps(items, indent=1))
    print(f"✓ {a.salida / 'index.html'}: {len(items)} recortes")


if __name__ == "__main__":
    main()
