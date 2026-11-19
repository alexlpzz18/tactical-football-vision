#!/usr/bin/env python
"""¿Ve una persona el balón en esta cámara? Paso previo a etiquetar (docs/registro_mision.md, H5).

En el alevín B el balón mide 2-4 px en casi todo el campo y el detector solo lo ve parado. Antes de
pedir 2 horas de etiquetado, 40 fotogramas al azar de toda la parte: si Alex lo ve en la mayoría,
se etiqueta; si no lo ve ni él, el límite es la cámara.

- Se eligen fotogramas en los que el detector NO ve un balón (los casos difíciles: es donde haría
  falta el etiquetado), repartidos por bloques de tiempo. El muestreo no mira nada más.
- Cada fotograma va con su vecino (f + `--separacion`) para poder alternarlos: a veces el balón solo
  se distingue porque se mueve. Queda apuntado si hizo falta.
- El clic guarda la posición en píxeles del fotograma ORIGINAL (sirve después como etiqueta).
- Los fotogramas se leen con el ffmpeg de línea de comandos.

Uso:
    python scripts/hoja_balon_visible.py --video data/raw/alevinb_p1.mp4 \\
        --balon data/tracking_alevinb/cache_alevinb_p1_balon.pkl --salida outputs/hoja_balon_visible
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
<title>¿Se ve el balón?</title>
<style>
:root { --fondo:#111418; --panel:#1b2027; --texto:#e8eaed; --tenue:#9aa3ad; --ok:#3fb27f; }
body { margin:0; background:var(--fondo); color:var(--texto); font:16px/1.4 system-ui,sans-serif; }
header { padding:12px 16px; }
#marco { overflow:auto; height:62vh; background:#000; cursor:crosshair; position:relative; }
#img { display:block; width:100%; }
#punto { position:absolute; width:22px; height:22px; margin:-11px 0 0 -11px; border-radius:50%;
  border:2px solid #ffe600; pointer-events:none; display:none; }
nav { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:10px 16px; }
button { padding:10px 12px; font-size:15px; border:0; border-radius:8px; background:var(--panel);
  color:var(--texto); cursor:pointer; }
button.sel { outline:3px solid var(--ok); }
.tenue { color:var(--tenue); font-size:14px; margin:4px 0; }
.barra { height:8px; background:var(--panel); } .barra div { height:100%; background:var(--ok); }
</style></head><body>
<header><b>¿Se ve el balón? · __TITULO__</b>
<p class="tenue"><b>Haz clic sobre el balón</b> si lo ves. Si no: <b>N</b> no lo veo ·
<b>X</b> no hay balón en juego (parado fuera, saque sin sacar, no está en la imagen).
Ayudas: <b>Z</b> acerca o aleja donde está el ratón · <b>M</b> (mantener pulsada) alterna con el
fotograma siguiente para verlo moverse · <b>← →</b> cambia de foto. Al acabar, «Descargar CSV».</p>
</header>
<div class="barra"><div id="prog"></div></div>
<div id="marco"><img id="img" alt="fotograma"><div id="punto"></div></div>
<nav><button id="atras">←</button><span id="pos"></span><button id="sig">→</button>
<button id="no">N · no lo veo</button><button id="x">X · no hay balón en juego</button>
<button id="bajar">Descargar CSV</button><span class="tenue" id="info"></span></nav>
<script>
const ITEMS = __ITEMS__, CLAVE = "hoja_balon___ID__";
let marcas = {};
try { marcas = JSON.parse(localStorage.getItem(CLAVE) || "{}"); } catch (e) {}
let i = ITEMS.findIndex(it => !(it.n in marcas)); if (i < 0) i = 0;
let zoom = 1, usoMov = false, raton = [0.5, 0.5];
const $ = id => document.getElementById(id), img = $("img"), marco = $("marco");
function guarda() { try { localStorage.setItem(CLAVE, JSON.stringify(marcas)); } catch (e) {} }
function pinta() {
  const it = ITEMS[i], m = marcas[it.n];
  img.src = it.img; usoMov = !!(m && m.mov);
  $("pos").textContent = (i + 1) + " / " + ITEMS.length;
  $("info").textContent = "reloj del vídeo " + it.reloj +
    (m ? " · marcado: " + (m.v === "S" ? "lo veo" : m.v === "N" ? "no lo veo" : "sin balón") : "");
  $("prog").style.width = (100 * Object.keys(marcas).length / ITEMS.length) + "%";
  $("no").className = m && m.v === "N" ? "sel" : "";
  $("x").className = m && m.v === "X" ? "sel" : "";
  punto();
}
function punto() {
  const m = marcas[ITEMS[i].n], p = $("punto");
  if (m && m.v === "S") {
    p.style.display = "block";
    p.style.left = (m.x / ITEMS[i].w * img.clientWidth) + "px";
    p.style.top = (m.y / ITEMS[i].h * img.clientHeight) + "px";
  } else p.style.display = "none";
}
function marca(v, x, y) {
  marcas[ITEMS[i].n] = {v: v, x: x || "", y: y || "", mov: usoMov ? 1 : 0}; guarda();
  if (v !== "S" && i < ITEMS.length - 1) i++;
  pinta();
}
function ponZoom(z) {
  zoom = z; img.style.width = (100 * zoom) + "%";
  marco.scrollLeft = raton[0] * img.clientWidth - marco.clientWidth / 2;
  marco.scrollTop = raton[1] * img.clientHeight - marco.clientHeight / 2;
  punto();
}
img.addEventListener("mousemove", e => {
  raton = [e.offsetX / img.clientWidth, e.offsetY / img.clientHeight]; });
img.addEventListener("click", e => marca("S",
  Math.round(e.offsetX / img.clientWidth * ITEMS[i].w * 10) / 10,
  Math.round(e.offsetY / img.clientHeight * ITEMS[i].h * 10) / 10));
img.addEventListener("load", punto);
let alterna = null;
document.addEventListener("keydown", e => {
  const k = e.key.toLowerCase();
  if (k === "n") marca("N"); if (k === "x") marca("X");
  if (k === "z") ponZoom(zoom === 1 ? 4 : 1);
  if (k === "m" && !alterna) {
    usoMov = true; let b = false;
    alterna = setInterval(() => { b = !b; img.src = b ? ITEMS[i].img2 : ITEMS[i].img; }, 250);
  }
  if (e.key === "ArrowLeft" && i > 0) { i--; pinta(); }
  if (e.key === "ArrowRight" && i < ITEMS.length - 1) { i++; pinta(); }
});
document.addEventListener("keyup", e => {
  if (e.key.toLowerCase() === "m" && alterna) {
    clearInterval(alterna); alterna = null; img.src = ITEMS[i].img; }
});
$("atras").onclick = () => { if (i > 0) { i--; pinta(); } };
$("sig").onclick = () => { if (i < ITEMS.length - 1) { i++; pinta(); } };
$("no").onclick = () => marca("N"); $("x").onclick = () => marca("X");
$("bajar").onclick = () => {
  const filas = ["n,frame,reloj,marca,x,y,con_movimiento"].concat(ITEMS.map(it => {
    const m = marcas[it.n] || {v: "", x: "", y: "", mov: ""};
    return [it.n, it.frame, it.reloj, m.v, m.x, m.y, m.mov].join(","); }));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([filas.join("\\n")], {type: "text/csv"}));
  a.download = "balon_visible___ID__.csv"; a.click();
};
pinta();
</script></body></html>
"""


def elegir(balon: list, n: int, separacion: int, rng) -> list:
    """`n` frames del caché de balón SIN detección, uno por bloque de tiempo."""
    sin = [e for e in balon if not e["dets"]]
    bloques = np.array_split(np.arange(len(sin)), n)
    elegidos = [sin[int(rng.choice(b))] for b in bloques if len(b)]
    return [(e["frame_idx"], e["t"]) for e in elegidos if e["frame_idx"] >= separacion]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument(
        "--balon", type=Path, required=True, help="caché de detecciones de balón"
    )
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument(
        "--separacion", type=int, default=3, help="fotogramas hasta el vecino"
    )
    ap.add_argument("--titulo", default="alevín B, parte 1")
    ap.add_argument("--inicio-reloj-s", type=float, default=9 * 3600 + 30 * 60 + 1)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(a.semilla)
    balon = pickle.load(open(a.balon, "rb"))["cache"]
    elegidos = elegir(balon, a.n, a.separacion, rng)
    (a.salida / "img").mkdir(parents=True, exist_ok=True)
    pedir = sorted({f + s for f, _t in elegidos for s in (0, a.separacion)})
    tam = {}
    for f, img in leer_frames_ffmpeg(a.video, pedir):
        cv2.imwrite(
            str(a.salida / "img" / f"{f}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 93]
        )
        tam[f] = img.shape[:2]
    items = []
    for n, (f, t) in enumerate(elegidos):
        s = int(t + a.inicio_reloj_s)
        items.append(
            {
                "n": n,
                "frame": int(f),
                "reloj": f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}",
                "img": f"img/{f}.jpg",
                "img2": f"img/{f + a.separacion}.jpg",
                "w": int(tam[f][1]),
                "h": int(tam[f][0]),
            }
        )
    html = (
        PAGINA.replace("__ITEMS__", json.dumps(items))
        .replace("__TITULO__", a.titulo)
        .replace("__ID__", a.salida.name)
    )
    (a.salida / "index.html").write_text(html)
    print(f"✓ {a.salida / 'index.html'}: {len(items)} fotogramas")


if __name__ == "__main__":
    main()
