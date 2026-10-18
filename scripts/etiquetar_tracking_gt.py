#!/usr/bin/env python
"""GT de TRACKING del benjamín: seguir a cada jugador clic a clic.

Por qué este formato y no el anterior. La primera herramienta enseñaba
tiras de recortes del sistema, y eso tiene un punto ciego que Alex
detectó: **si el recorte ya está mal, no te enteras**. Aquí se ve el
FOTOGRAMA ENTERO y el humano decide dónde está la persona, sin que el
sistema condicione la respuesta.

Lo que se obtiene deja de ser "dónde se rompe una identidad" y pasa a ser
la **segunda pata de banco de verdad** para el F7: cobertura, IDF1,
concurrencia y quimeras —incluidas las del mismo equipo— medidas sin
traslados con pérdida.

Flujo: **jugador a jugador**, no frame a frame. Se elige a alguien en el
primer fotograma y se le sigue por los 60; luego el siguiente. Seguir a
una persona es una tarea mental sencilla; identificar a quince en cada
fotograma, no.

Tres cosas que evitan que 900 clics se desperdicien:

- **"No la distingo"** salta la identidad entera. Si un niño del fondo no
  se ve, es mejor dejarlo fuera que inventar dónde está: un GT
  contaminado es peor que no tener GT.
- **Estela de los clics anteriores**, para no perder el hilo. Con 19
  personas en cuadro y 2,5 cruces por fotograma, perder a quién sigues a
  mitad de los 60 clics generaría quimeras *en el propio GT*.
- **Guardado incremental** en el navegador: cerrar no pierde nada.

La salida va indexada por **posición y tiempo** (frame + píxeles + metros),
nunca por id del tracker — la lección del mini-GT que caducó entero al
cambiar de detector.

Uso:
    python scripts/etiquetar_tracking_gt.py \\
        --config configs/processor_benja_emb.yaml \\
        --ini 325 --dur 30
"""

import argparse
import base64
import json
import logging
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("gt_tracking")

# Alto nominal de la caja que se sintetiza a partir del clic. El clic
# marca los PIES, que es lo que proyecta la homografía; el alto solo sirve
# para que el formato case con el del GT de Villaviciosa.
ALTO_CAJA = 40
ANCHO_CAJA = 18

PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>__TITULO__</title>
<style>
 body{background:#0e1016;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,
      'Segoe UI',sans-serif;margin:0;padding:0}
 header{background:#171a21;padding:10px 16px;border-bottom:1px solid #2a2f3a;
        display:flex;gap:16px;align-items:center;flex-wrap:wrap}
 h1{font-size:15px;margin:0}
 .chip{background:#2a2f3a;border-radius:6px;padding:3px 10px;font-size:13px}
 button{background:#2a2f3a;color:#e5e7eb;border:1px solid #3a4150;border-radius:6px;
        padding:5px 12px;font-size:13px;cursor:pointer}
 button.pri{background:#60a5fa;color:#0b0d12;border-color:#60a5fa;font-weight:600}
 button.peligro{background:#3a2430;border-color:#7f3355;color:#f9a8d4}
 #lienzo{position:relative;cursor:crosshair;display:block;margin:0 auto}
 #lupa{position:fixed;width:260px;height:260px;border:2px solid #60a5fa;border-radius:50%;
       pointer-events:none;display:none;background-repeat:no-repeat;z-index:20;
       box-shadow:0 4px 24px #000a}
 #lupa::after{content:'';position:absolute;left:50%;top:50%;width:11px;height:11px;
       margin:-6px 0 0 -6px;border:1px solid #f472b6;border-radius:50%}
 .barra{height:4px;background:#2a2f3a;width:100%}
 .barra>div{height:100%;background:#60a5fa;width:0}
 .ayuda{font-size:12px;color:#9ca3af;padding:6px 16px}
</style></head><body>
<header>
  <h1 id="titulo"></h1>
  <span class="chip" id="quien"></span>
  <span class="chip" id="progreso"></span>
  <button id="atras">← anterior</button>
  <button id="saltar">No se ve (saltar frame)</button>
  <button class="peligro" id="nodistingo">No distingo a este jugador</button>
  <button class="pri" id="siguiente">Siguiente jugador →</button>
  <button id="exportar">Exportar GT</button>
</header>
<div class="barra"><div id="barra"></div></div>
<div class="ayuda">
  Clic en los <b>PIES</b> del jugador que estás siguiendo. La estela rosa son
  tus clics anteriores. Rueda del ratón o mover = lupa. Todo se guarda solo.
</div>
<canvas id="lienzo"></canvas>
<div id="lupa"></div>
<script>
const FRAMES = __FRAMES__;      // [{f, t, img}]
const META = __META__;
const LLAVE = 'gt_tracking_' + META.tramo;

let estado = JSON.parse(localStorage.getItem(LLAVE) || 'null') || {
  jugador: 1, i: 0, marcas: {}, descartados: []
};

const lienzo = document.getElementById('lienzo');
const ctx = lienzo.getContext('2d');
const lupa = document.getElementById('lupa');
const imgs = {};

function guarda() { localStorage.setItem(LLAVE, JSON.stringify(estado)); }
function clave(j, i) { return j + ':' + i; }

function carga(i, cb) {
  if (imgs[i]) return cb(imgs[i]);
  const im = new Image();
  im.onload = () => { imgs[i] = im; cb(im); };
  im.src = FRAMES[i].img;
}

function pinta() {
  const i = estado.i;
  carga(i, im => {
    const ancho = Math.min(window.innerWidth - 20, im.width);
    const escala = ancho / im.width;
    lienzo.width = im.width; lienzo.height = im.height;
    lienzo.style.width = ancho + 'px';
    ctx.drawImage(im, 0, 0);
    // Estela: los clics anteriores de ESTE jugador
    const previos = [];
    for (let k = Math.max(0, i - 6); k < i; k++) {
      const m = estado.marcas[clave(estado.jugador, k)];
      if (m) previos.push(m);
    }
    previos.forEach((m, n) => {
      const a = 0.25 + 0.6 * (n + 1) / previos.length;
      ctx.strokeStyle = 'rgba(244,114,182,' + a + ')';
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(m.x, m.y, 14, 0, 7); ctx.stroke();
      if (n > 0) {
        ctx.beginPath(); ctx.moveTo(previos[n-1].x, previos[n-1].y);
        ctx.lineTo(m.x, m.y); ctx.stroke();
      }
    });
    const actual = estado.marcas[clave(estado.jugador, i)];
    if (actual) {
      ctx.strokeStyle = '#60a5fa'; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.arc(actual.x, actual.y, 18, 0, 7); ctx.stroke();
    }
    lupa.style.backgroundImage = 'url(' + FRAMES[i].img + ')';
    lupa.dataset.escala = escala;
  });
  const hechos = FRAMES.filter((_f, k) => estado.marcas[clave(estado.jugador, k)]).length;
  document.getElementById('titulo').textContent = META.titulo;
  document.getElementById('quien').textContent = 'Jugador ' + estado.jugador;
  document.getElementById('progreso').textContent =
    'frame ' + (estado.i + 1) + '/' + FRAMES.length + ' · ' + hechos + ' marcados';
  document.getElementById('barra').style.width =
    (100 * (estado.i + 1) / FRAMES.length) + '%';
  guarda();
}

lienzo.onclick = e => {
  const r = lienzo.getBoundingClientRect();
  const escala = lienzo.width / r.width;
  estado.marcas[clave(estado.jugador, estado.i)] = {
    x: Math.round((e.clientX - r.left) * escala),
    y: Math.round((e.clientY - r.top) * escala)
  };
  if (estado.i < FRAMES.length - 1) estado.i++;
  pinta();
};
lienzo.onmousemove = e => {
  const r = lienzo.getBoundingClientRect();
  const escala = lienzo.width / r.width;
  const x = (e.clientX - r.left) * escala, y = (e.clientY - r.top) * escala;
  const Z = 4;
  lupa.style.display = 'block';
  lupa.style.left = (e.clientX + 24) + 'px';
  lupa.style.top = (e.clientY - 130) + 'px';
  lupa.style.backgroundSize = (lienzo.width * Z) + 'px ' + (lienzo.height * Z) + 'px';
  lupa.style.backgroundPosition = (-x * Z + 130) + 'px ' + (-y * Z + 130) + 'px';
};
lienzo.onmouseleave = () => { lupa.style.display = 'none'; };

document.getElementById('saltar').onclick = () => {
  if (estado.i < FRAMES.length - 1) estado.i++;
  pinta();
};
document.getElementById('atras').onclick = () => {
  if (estado.i > 0) estado.i--;
  pinta();
};
document.getElementById('nodistingo').onclick = () => {
  if (!confirm('¿Descartar al jugador ' + estado.jugador + ' entero?')) return;
  estado.descartados.push(estado.jugador);
  FRAMES.forEach((_f, k) => delete estado.marcas[clave(estado.jugador, k)]);
  estado.jugador++; estado.i = 0; pinta();
};
document.getElementById('siguiente').onclick = () => {
  estado.jugador++; estado.i = 0; pinta();
};
document.onkeydown = e => {
  if (e.key === 'ArrowRight') document.getElementById('saltar').click();
  if (e.key === 'ArrowLeft') document.getElementById('atras').click();
};

document.getElementById('exportar').onclick = () => {
  const filas = ['jugador,frame,t_s,x_px,y_px'];
  Object.entries(estado.marcas).forEach(([k, m]) => {
    const [j, i] = k.split(':').map(Number);
    filas.push([j, FRAMES[i].f, FRAMES[i].t, m.x, m.y].join(','));
  });
  const url = URL.createObjectURL(new Blob([filas.join('\\n')], {type:'text/csv'}));
  const a = document.createElement('a');
  a.href = url; a.download = 'gt_tracking_' + META.tramo + '.csv'; a.click();
};
pinta();
</script></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--ini", type=float, default=325.0, help="segundo inicial")
    p.add_argument("--dur", type=float, default=30.0)
    p.add_argument("--paso", type=int, default=15, help="1 de cada N frames")
    p.add_argument("--calidad", type=int, default=82)
    p.add_argument("--salida", default="outputs/etiquetar_tracking_benja.html")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(open(args.config))
    cap = cv2.VideoCapture(cfg["rutas"]["video"])
    if not cap.isOpened():
        raise SystemExit(f"No se puede abrir {cfg['rutas']['video']}")
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Múltiplos de `paso` dentro del tramo: la misma alineación que el GT
    # de Villaviciosa, y por tanto frames que el caché ya contiene.
    f0 = int(np.ceil(args.ini * fps / args.paso) * args.paso)
    f1 = int((args.ini + args.dur) * fps)
    objetivo = list(range(f0, f1, args.paso))

    posicionar_en_frame(cap, objetivo[0])
    frames, idx = [], objetivo[0]
    pendientes = set(objetivo)
    while pendientes and idx <= objetivo[-1]:
        ok, fr = cap.read()
        if not ok:
            break
        if idx in pendientes:
            ok2, buf = cv2.imencode(
                ".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, args.calidad]
            )
            if ok2:
                frames.append(
                    {
                        "f": idx,
                        "t": round(idx / fps, 2),
                        "img": "data:image/jpeg;base64,"
                        + base64.b64encode(buf).decode("ascii"),
                    }
                )
            pendientes.discard(idx)
        idx += 1
    cap.release()

    m0, s0 = divmod(args.ini, 60)
    tramo = f"{int(m0)}m{int(s0):02d}s_{int(args.dur)}s"
    meta = {
        "tramo": tramo,
        "titulo": f"GT de tracking — benjamín {int(m0)}:{int(s0):02d} "
        f"(+{int(args.dur)} s, 1 de cada {args.paso} frames)",
    }
    html = (
        PLANTILLA.replace("__TITULO__", meta["titulo"])
        .replace("__FRAMES__", json.dumps(frames))
        .replace("__META__", json.dumps(meta))
    )
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(html, encoding="utf-8")
    mb = Path(args.salida).stat().st_size / 1e6
    print(f"\n✓ {args.salida}  ({mb:.1f} MB)")
    print(
        f"  {len(frames)} fotogramas ({objetivo[0]}–{objetivo[-1]}), "
        f"1 de cada {args.paso}"
    )
    print(
        f"  Clics por jugador: {len(frames)}. Con 15 personas: " f"{len(frames) * 15}"
    )


if __name__ == "__main__":
    main()
