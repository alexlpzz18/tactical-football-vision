#!/usr/bin/env python
"""Hoja RÁPIDA de GT del balón (≤ 20 min de Alex). docs/diagnostico_23oct_f.md, bloque 3.

`generar`: 200 frames del benjamín (parte entera), al azar y separados ≥ 3 s:
- 60 + 60 + 60 CON candidata, por tercil de metros por píxel en la candidata ELEGIDA por el
  selector de producción (cerca / media / lejos);
- 20 SIN ninguna candidata (¿estaba el balón y no se detectó?).

Villaviciosa no entra: no existe caché de balón de Villaviciosa.

Escribe `outputs/gt_balon_rapido/index.html`. Se abre en el navegador y, por cada imagen:
    A          la candidata marcada (círculo rojo) ES el balón
    R          no es el balón, y el balón NO se ve
    clic       el balón está AHÍ (en otro sitio, o no había candidata)
    N          no se puede decir
    ← / →      anterior / siguiente
La lupa (abajo a la derecha) amplía ×4 alrededor del ratón. Las respuestas se guardan solas en
el navegador; al final, «Descargar CSV» baja `respuestas_gt_balon.csv`.

`leer`: pasa ese CSV a `data/annotations/gt_balon_benja/gt_balon_por_frame.csv`
(frame, respuesta, x_px, y_px). No mide nada.

Uso:
    python scripts/gt_balon_rapido.py generar
    python scripts/gt_balon_rapido.py leer ~/Downloads/respuestas_gt_balon.csv
"""

import argparse
import csv
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
VIDEO = R / "data/raw/benja_gredos_p1_20min.mp4"
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
CSV_JUGADORES = R / "outputs/arbitro_obs/posiciones.csv"
CAMPO = R / "configs/campo_benja.yaml"
SALIDA = R / "outputs/gt_balon_rapido"
GT = R / "data/annotations/gt_balon_benja/gt_balon_por_frame.csv"
FPS = 29.97002997002997
POR_ZONA, SIN_CANDIDATA, SEPARACION_S = 60, 20, 3.0


def relojes(frame: int) -> str:
    t = frame / FPS
    r = t + 93
    return f"{int(t // 60)}:{t % 60:04.1f} arch / {int(r // 60)}:{r % 60:04.1f} repr"


def separados(frames, n, rng) -> list[int]:
    """Hasta n frames al azar, separados ≥ SEPARACION_S entre sí."""
    elegidos: list[int] = []
    for f in rng.permutation(sorted(frames)):
        if all(abs(int(f) - g) / FPS >= SEPARACION_S for g in elegidos):
            elegidos.append(int(f))
        if len(elegidos) == n:
            break
    return sorted(elegidos)


def elegir() -> list[dict]:
    from src.balon.tracking_balon import escala_px_por_m

    spec = importlib.util.spec_from_file_location(
        "gv", R / "scripts/generar_video_detecciones.py"
    )
    gv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gv)
    activo = gv.balon_activo(CACHE_BALON, CSV_JUGADORES, CAMPO)  # {frame: (det, aereo)}
    todas = {
        e["frame_idx"]: e["dets"] for e in pickle.load(open(CACHE_BALON, "rb"))["cache"]
    }
    H = np.load(R / "data/calibracion_benja/homografia_benja.npy")
    m_px = {
        f: 1.0 / escala_px_por_m(H, (d[2] + d[4]) / 2, d[5])
        for f, (d, _a) in activo.items()
    }
    cortes = np.quantile(list(m_px.values()), [1 / 3, 2 / 3])
    rng = np.random.default_rng(0)
    filas = []
    for zona, cond in (
        ("cerca", lambda v: v <= cortes[0]),
        ("media", lambda v: cortes[0] < v <= cortes[1]),
        ("lejos", lambda v: v > cortes[1]),
    ):
        for f in separados([f for f, v in m_px.items() if cond(v)], POR_ZONA, rng):
            d = activo[f][0]
            filas.append(
                {"frame": f, "zona": zona, "elegida": [float(v) for v in d[2:6]]}
            )
    vacios = [f for f, d in todas.items() if not d]
    for f in separados(vacios, SIN_CANDIDATA, rng):
        filas.append({"frame": f, "zona": "sin_candidata", "elegida": None})
    for r in filas:
        r["otras"] = [
            [float(v) for v in d[2:6]]
            for d in todas.get(r["frame"], [])
            if r["elegida"] is None or [float(v) for v in d[2:6]] != r["elegida"]
        ]
        r["relojes"] = relojes(r["frame"])
    rng.shuffle(filas)  # barajadas: la zona no se ve al marcar
    return filas, [round(float(c), 4) for c in cortes]


PAGINA = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>GT rápido del balón</title>
<style>
body{margin:0;background:#111;color:#eee;font:15px system-ui,sans-serif}
#barra{padding:8px 12px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
#marco{position:relative;width:100%}#img{width:100%;display:block;cursor:crosshair}
#capa{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none}
#lupa{position:fixed;right:12px;bottom:12px;width:320px;height:320px;border:2px solid #ff0;
background:#000}
button{font-size:15px;padding:4px 10px}
.r{color:#f66}.ok{color:#6f6}
</style></head><body>
<div id="barra"><b id="pos"></b><span id="reloj"></span><span id="resp"></span>
<span>A = es el balón · R = no es y no se ve · clic = el balón está aquí · N = no se sabe ·
← →</span><button onclick="descargar()">Descargar CSV</button><span id="hechos"></span></div>
<div id="marco"><img id="img"><canvas id="capa"></canvas></div><canvas id="lupa" width="320"
height="320"></canvas>
<script>
const F = __FILAS__;
const CLAVE = "gt_balon_rapido_23oct_f";
let R = {}; try { R = JSON.parse(localStorage.getItem(CLAVE) || "{}"); } catch (e) {}
let i = 0;
const img = document.getElementById("img"), capa = document.getElementById("capa"),
  lupa = document.getElementById("lupa");
function guardar(){ try { localStorage.setItem(CLAVE, JSON.stringify(R)); } catch (e) {} }
function dibujar(){
  const f = F[i]; capa.width = img.clientWidth; capa.height = img.clientHeight;
  const k = img.clientWidth / img.naturalWidth, c = capa.getContext("2d");
  c.lineWidth = 1; c.strokeStyle = "rgba(255,255,0,.6)";
  f.otras.forEach(b => c.strokeRect(b[0]*k-4, b[1]*k-4, (b[2]-b[0])*k+8, (b[3]-b[1])*k+8));
  if (f.elegida){ const b = f.elegida; c.lineWidth = 3; c.strokeStyle = "#f22"; c.beginPath();
    c.arc((b[0]+b[2])/2*k, (b[1]+b[3])/2*k, Math.max(14, (b[2]-b[0])*k), 0, 7); c.stroke(); }
  const r = R[f.frame];
  if (r && r.x != null){ c.strokeStyle = "#2f2"; c.lineWidth = 3; c.beginPath();
    c.arc(r.x*k, r.y*k, 12, 0, 7); c.stroke(); }
  document.getElementById("pos").textContent = (i+1) + " / " + F.length;
  document.getElementById("reloj").textContent = "f" + f.frame + "  " + f.relojes;
  document.getElementById("resp").innerHTML = r ? "<span class=ok>" + r.respuesta +
    "</span>" : "<span class=r>sin responder</span>";
  document.getElementById("hechos").textContent = Object.keys(R).length + " respondidas";
}
function ir(n){ i = Math.max(0, Math.min(F.length-1, n)); img.src = "img/f" + F[i].frame + ".jpg"; }
img.onload = dibujar; window.onresize = dibujar;
function responder(resp, x, y){ R[F[i].frame] = {respuesta: resp, x: x, y: y}; guardar(); ir(i+1); }
document.onkeydown = e => {
  const f = F[i];
  if (e.key === "a" || e.key === "A"){ if (!f.elegida) return; const b = f.elegida;
    responder("acepta", (b[0]+b[2])/2, (b[1]+b[3])/2); }
  else if (e.key === "r" || e.key === "R") responder("rechaza_no_visible", null, null);
  else if (e.key === "n" || e.key === "N") responder("no_se", null, null);
  else if (e.key === "ArrowRight") ir(i+1); else if (e.key === "ArrowLeft") ir(i-1);
};
img.onclick = e => { const k = img.naturalWidth / img.clientWidth;
  responder("clic", Math.round(e.offsetX*k), Math.round(e.offsetY*k)); };
img.onmousemove = e => { const k = img.naturalWidth / img.clientWidth, c = lupa.getContext("2d");
  c.imageSmoothingEnabled = false;
  c.drawImage(img, e.offsetX*k-40, e.offsetY*k-40, 80, 80, 0, 0, 320, 320);
  c.strokeStyle = "#ff0"; c.strokeRect(150, 150, 20, 20); };
function descargar(){
  let t = "frame,zona,respuesta,x_px,y_px\\n";
  F.forEach(f => { const r = R[f.frame]; if (r) t += [f.frame, f.zona, r.respuesta,
    r.x == null ? "" : r.x, r.y == null ? "" : r.y].join(",") + "\\n"; });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([t], {type: "text/csv"}));
  a.download = "respuestas_gt_balon.csv"; a.click();
}
ir(0);
</script></body></html>"""


def generar() -> None:
    import cv2

    from src.utils.video_ffmpeg import leer_frames_ffmpeg

    filas, cortes = elegir()
    (SALIDA / "img").mkdir(parents=True, exist_ok=True)
    for f, img in leer_frames_ffmpeg(VIDEO, [r["frame"] for r in filas]):
        cv2.imwrite(str(SALIDA / f"img/f{f}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    (SALIDA / "frames.json").write_text(
        json.dumps({"cortes_m_por_px": cortes, "filas": filas}, indent=1)
    )
    (SALIDA / "index.html").write_text(PAGINA.replace("__FILAS__", json.dumps(filas)))
    por_zona = {}
    for r in filas:
        por_zona[r["zona"]] = por_zona.get(r["zona"], 0) + 1
    print(f"✓ {len(filas)} frames {por_zona} · cortes m/px {cortes}")
    print(f"  abre {SALIDA / 'index.html'}")


def leer(ruta: Path) -> None:
    filas = list(csv.DictReader(open(ruta)))
    validas = {"acepta", "rechaza_no_visible", "clic", "no_se"}
    malas = [r for r in filas if r["respuesta"] not in validas]
    if malas:
        raise ValueError(f"Respuestas desconocidas: {malas[:3]}")
    GT.parent.mkdir(parents=True, exist_ok=True)
    with open(GT, "w", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["frame", "zona", "respuesta", "x_px", "y_px"]
        )
        w.writeheader()
        w.writerows(filas)
    print(f"✓ {len(filas)} respuestas → {GT}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["generar", "leer"])
    ap.add_argument("csv", nargs="?")
    args = ap.parse_args()
    if args.accion == "generar":
        generar()
    else:
        leer(Path(args.csv))


if __name__ == "__main__":
    main()
