#!/usr/bin/env python
"""Herramienta visual para etiquetar el ground truth de equipos.

Sustituye a la plantilla CSV rellenable a mano. El problema de aquella no
era el formato sino el trabajo que exigía: para poner una etiqueta había
que abrir el vídeo, buscar el instante, localizar al jugador por su
posición en metros y volver al CSV. Treinta veces.

Aquí cada identidad se presenta ya resuelta: una tira de recortes REALES
del jugador sacados del vídeo, repartidos a lo largo de su vida, y seis
botones. Un clic por identidad, y el HTML descarga el CSV al terminar.

El HTML es autocontenido (las imágenes van embebidas en base64), así que
se puede abrir sin servidor y sin este repo delante.

Uso:
    python scripts/etiquetar_equipos_gt.py \\
        --config configs/processor_benja.yaml \\
        --csv data/tracking_benja/posiciones_benja.csv \\
        --nombre-a Blanco --nombre-b Naranja \\
        --salida outputs/etiquetar_equipos_benja.html
"""

import argparse
import base64
import json
import logging
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracking.cache_io import cargar_cache  # noqa: E402
from src.tracking_data.processor import posicionar_en_frame  # noqa: E402

logger = logging.getLogger("etiquetar")

MARGEN_CROP = 0.25  # holgura alrededor de la caja, para dar contexto


def elegir_muestras(observaciones, n_muestras, alto_min=18):
    """Reparte n muestras a lo largo de la vida, cogiendo las más nítidas.

    La vida se parte en n tramos y de cada uno se coge la caja MÁS GRANDE,
    que es la más cercana a la cámara y por tanto la que mejor se ve. Así
    la tira cubre toda la vida de la identidad (para notar si cambia de
    persona a mitad) sin llenarse de manchas del fondo.
    """
    if not observaciones:
        return []
    observaciones = sorted(observaciones, key=lambda o: o["frame"])
    nitidas = [o for o in observaciones if o["alto"] >= alto_min] or observaciones
    tramos = np.array_split(
        np.array(nitidas, dtype=object), min(n_muestras, len(nitidas))
    )
    elegidas = []
    for tramo in tramos:
        if len(tramo) == 0:
            continue
        elegidas.append(max(tramo, key=lambda o: o["alto"]))
    return elegidas


def recortar(frame, caja, margen=MARGEN_CROP):
    """Recorte con holgura, en color, listo para embeber."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = caja
    dx, dy = (x2 - x1) * margen, (y2 - y1) * margen
    x1 = max(0, int(x1 - dx))
    y1 = max(0, int(y1 - dy))
    x2 = min(w, int(x2 + dx))
    y2 = min(h, int(y2 + dy))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    # Altura fija para que la tira se lea de un vistazo; el ancho sigue
    # la proporción real del recorte.
    alto_destino = 120
    escala = alto_destino / crop.shape[0]
    ancho = max(12, int(crop.shape[1] * escala))
    return cv2.resize(crop, (ancho, alto_destino), interpolation=cv2.INTER_CUBIC)


def a_base64(crop):
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")


def construir_identidades(df, cache_dets, n_muestras, min_obs):
    """{id: {datos, observaciones}} casando el CSV con las cajas del caché.

    El CSV solo guarda metros; las cajas viven en el caché. Se emparejan
    por cercanía en metros dentro del mismo frame, que es exacta salvo
    empates porque ambas salen de la MISMA proyección.
    """
    reales = df[df.es_real == 1] if "es_real" in df.columns else df
    identidades = {}
    for id_j, grupo in reales.groupby("id_jugador"):
        if len(grupo) < min_obs:
            continue
        observaciones = []
        for fila in grupo.itertuples():
            dets = cache_dets.get(int(fila.frame))
            if not dets:
                continue
            d2 = [(d[0] - fila.x_m) ** 2 + (d[1] - fila.y_m) ** 2 for d in dets]
            k = int(np.argmin(d2))
            if d2[k] > 4.0:
                continue
            d = dets[k]
            observaciones.append(
                {
                    "frame": int(fila.frame),
                    "caja": (d[2], d[3], d[4], d[5]),
                    "alto": d[5] - d[3],
                    # ANCLA: dónde estaba, en metros. Es lo que hace que
                    # esta etiqueta sobreviva a un cambio de detector —
                    # los ids no lo hacen (medido: 27 de 30 identidades
                    # del mini-GT anterior eran otra persona con el v4).
                    "x": round(float(d[0]), 2),
                    "y": round(float(d[1]), 2),
                }
            )
        if not observaciones:
            continue
        identidades[int(id_j)] = {
            "id": int(id_j),
            "n_obs": len(grupo),
            "x_m": round(float(grupo.x_m.mean()), 1),
            "y_m": round(float(grupo.y_m.mean()), 1),
            "t_ini": round(float(grupo.tiempo_s.min()), 1),
            "t_fin": round(float(grupo.tiempo_s.max()), 1),
            "prediccion": str(grupo.etiqueta.mode().iloc[0]),
            "muestras": elegir_muestras(observaciones, n_muestras),
        }
    return dict(sorted(identidades.items(), key=lambda kv: -kv[1]["n_obs"]))


def extraer_crops(ruta_video, identidades):
    """Decodifica UNA vez el rango necesario y saca todos los recortes."""
    necesarios = {}
    for datos in identidades.values():
        for m in datos["muestras"]:
            necesarios.setdefault(m["frame"], []).append(
                (datos["id"], m["caja"], m.get("x", ""), m.get("y", ""))
            )
    if not necesarios:
        return {}

    cap = cv2.VideoCapture(str(ruta_video))
    if not cap.isOpened():
        raise FileNotFoundError(f"No se puede abrir {ruta_video}")
    primero, ultimo = min(necesarios), max(necesarios)
    posicionar_en_frame(cap, primero)

    crops: dict[int, list[str]] = {}
    frame_idx = primero
    while frame_idx <= ultimo:
        ok, frame = cap.read()
        if not ok:
            break
        for id_j, caja, x_m, y_m in necesarios.get(frame_idx, []):
            crop = recortar(frame, caja)
            if crop is None:
                continue
            dato = a_base64(crop)
            if dato:
                # El ancla viaja con el recorte hasta el CSV: sin ella la
                # etiqueta solo sirve mientras los ids no cambien.
                crops.setdefault(id_j, []).append(
                    {"img": dato, "frame": frame_idx, "x": x_m, "y": y_m}
                )
        frame_idx += 1
    cap.release()
    logger.info(
        "Recortes extraídos: %d identidades, %d imágenes",
        len(crops),
        sum(len(v) for v in crops.values()),
    )
    return crops


PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>__TITULO__</title>
<style>
 :root { color-scheme: dark }
 body { margin:0; background:#0f1115; color:#e8eaed;
        font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif }
 header { position:sticky; top:0; z-index:5; background:#171a21;
          border-bottom:1px solid #262b36; padding:12px 20px;
          display:flex; align-items:center; gap:18px; flex-wrap:wrap }
 h1 { font-size:17px; margin:0; font-weight:600 }
 .progreso { flex:1; min-width:160px; height:8px; background:#262b36; border-radius:4px }
 .progreso div { height:100%; width:0; background:#4ade80; border-radius:4px;
                 transition:width .2s }
 button { font:inherit; border:0; border-radius:8px; padding:9px 14px;
          cursor:pointer; color:#0f1115; font-weight:600 }
 main { padding:20px; max-width:1250px; margin:0 auto }
 .ficha { background:#171a21; border:1px solid #262b36; border-radius:12px;
          padding:16px; margin-bottom:16px }
 .ficha.hecha { opacity:.5 }
 .ficha.quimera { border-color:#f472b6 }
 .cab { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;
        margin-bottom:10px }
 .cab b { font-size:16px } .cab span { color:#9aa4b2; font-size:13px }
 .marca { margin-left:auto; font-weight:700; font-size:13px }
 .todos { display:flex; align-items:center; gap:6px; margin-bottom:10px;
          font-size:12px; color:#9aa4b2; flex-wrap:wrap }
 .tira { display:flex; gap:10px; overflow-x:auto; padding-bottom:6px }
 .col { display:flex; flex-direction:column; align-items:center; gap:5px }
 .col img { height:120px; border-radius:6px; background:#0b0d11; display:block }
 /* El recorte que NO coincide con la mayoría de su tira: es el que hay
    que mirar para decidir si fue un error de etiquetado o una quimera. */
 .col.discrepa img { outline:3px solid #f472b6; outline-offset:1px }
 .col.discrepa .t { color:#f472b6; font-weight:700 }
 .col .t { font-size:10px; color:#6b7280 }
 .swatches { display:flex; gap:3px }
 .sw { width:19px; height:19px; border-radius:5px; border:2px solid transparent;
       cursor:pointer; padding:0 }
 .sw.on { border-color:#e8eaed; box-shadow:0 0 0 2px #0f1115 inset }
 .sw.mini { width:15px; height:15px }
</style></head><body>
<header>
  <h1>__TITULO__</h1>
  <div class="progreso"><div id="barra"></div></div>
  <span id="cuenta">0 / 0</span>
  <span id="quimeras" style="color:#f472b6; font-weight:600"></span>
  <button id="exportar">Exportar CSV</button>
  <div style="flex-basis:100%; font-size:13px; color:#9aa4b2">
    Etiqueta <b>cada recorte</b>. Lo normal es usar “todos =” y listo; si
    en alguna tira cambia la persona a mitad, corrige solo esos recortes
    y la identidad quedará marcada sola como
    <b style="color:#f472b6">quimera</b>.
  </div>
</header>
<main id="lista"></main>
<script>
const IDENTIDADES = __DATOS__;
const OPCIONES = __OPCIONES__;
const resp = {};                       // 'id:j' -> valor
const PREVIAS = __PREVIAS__;           // etiquetas ya puestas, por id@t

const clave = (id, j) => id + ':' + j;
function etiquetasDe(d) {
  return d.crops.map((_c, j) => resp[clave(d.id, j)]).filter(Boolean);
}
function completa(d) { return etiquetasDe(d).length === d.crops.length; }
function esQuimera(d) {
  const e = etiquetasDe(d);
  return e.length > 1 && new Set(e).size > 1;
}

function swatches(id, j, mini) {
  return OPCIONES.map(o =>
    `<button class="sw${mini ? ' mini' : ''}${resp[clave(id,j)] === o.valor ? ' on' : ''}"
             style="background:${o.color}" title="${o.texto}"
             data-id="${id}" data-j="${j}" data-v="${o.valor}"></button>`).join('');
}

// Precarga: lo que ya etiquetaste vuelve marcado, para poder REVISARLO
// en vez de repetirlo.
(function precargar() {
  IDENTIDADES.forEach(d => d.crops.forEach((c, j) => {
    const v = PREVIAS[d.id + '@' + c.t];
    if (v) resp[clave(d.id, j)] = v;
  }));
})();

function pinta() {
  const lista = document.getElementById('lista');
  lista.innerHTML = '';
  IDENTIDADES.forEach(d => {
    const q = esQuimera(d);
    const ficha = document.createElement('div');
    ficha.className = 'ficha' + (completa(d) ? ' hecha' : '') + (q ? ' quimera' : '');
    ficha.id = 'f' + d.id;
    const e = etiquetasDe(d);
    const marca = q
      ? `<span class="marca" style="color:#f472b6">QUIMERA · ${new Set(e).size} personas</span>`
      : (e.length && completa(d)
         ? `<span class="marca" style="color:${OPCIONES.find(o=>o.valor===e[0]).color}">
              ${OPCIONES.find(o=>o.valor===e[0]).texto}</span>` : '');
    ficha.innerHTML = `
      <div class="cab">
        <b>#${d.id}</b>
        <span>${d.n_obs} obs · ${d.t_ini}-${d.t_fin}s · (${d.x_m}, ${d.y_m}) m</span>
        <span>predicción: ${d.prediccion}</span>${marca}
      </div>
      <div class="todos">todos =
        ${OPCIONES.map(o =>
          `<button class="sw" style="background:${o.color}" title="${o.texto}"
                   data-todos="${d.id}" data-v="${o.valor}"></button>`).join('')}
      </div>
      <div class="tira">${d.crops.map((c, j) => `
        <div class="col${(() => {
             const e = etiquetasDe(d);
             if (new Set(e).size < 2) return '';
             const may = [...new Set(e)].sort((a,b) =>
               e.filter(x=>x===b).length - e.filter(x=>x===a).length)[0];
             return resp[clave(d.id, j)] && resp[clave(d.id, j)] !== may
               ? ' discrepa' : '';
           })()}">
          <img src="${c.img}" loading="lazy">
          <div class="t">${c.t}s</div>
          <div class="swatches">${swatches(d.id, j, true)}</div>
        </div>`).join('')}</div>`;
    lista.appendChild(ficha);
  });

  lista.querySelectorAll('button[data-v]').forEach(b => {
    b.onclick = () => {
      if (b.dataset.todos !== undefined) {
        const d = IDENTIDADES.find(x => x.id === +b.dataset.todos);
        d.crops.forEach((_c, j) => resp[clave(d.id, j)] = b.dataset.v);
        const sig = IDENTIDADES.find(x => !completa(x));
        pinta();
        if (sig) document.getElementById('f' + sig.id)
          .scrollIntoView({behavior:'smooth', block:'center'});
      } else {
        resp[clave(+b.dataset.id, +b.dataset.j)] = b.dataset.v;
        const y = window.scrollY; pinta(); window.scrollTo(0, y);
      }
    };
  });
  actualiza();
}

function actualiza() {
  const n = IDENTIDADES.filter(completa).length, total = IDENTIDADES.length;
  document.getElementById('cuenta').textContent = n + ' / ' + total;
  document.getElementById('barra').style.width = (100*n/total) + '%';
  const q = IDENTIDADES.filter(esQuimera).length;
  document.getElementById('quimeras').textContent = q ? q + ' quimeras' : '';
}

document.getElementById('exportar').onclick = () => {
  const filas = ['id_jugador,t_s,frame,x_m,y_m,equipo_real,prediccion,n_obs'];
  IDENTIDADES.forEach(d => d.crops.forEach((c, j) => {
    const r = resp[clave(d.id, j)];
    if (r) filas.push(
      [d.id, c.t, c.f, c.x, c.y, r, d.prediccion, d.n_obs].join(','));
  }));
  if (filas.length === 1) { alert('Todavía no has etiquetado nada.'); return; }
  const url = URL.createObjectURL(new Blob([filas.join('\\n')], {type:'text/csv'}));
  const a = document.createElement('a');
  a.href = url; a.download = '__NOMBRE_CSV__'; a.click();
  URL.revokeObjectURL(url);
};

pinta();
</script></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Config del processor")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--salida", default="outputs/etiquetar_equipos.html")
    parser.add_argument("--nombre-a", default="Equipo A")
    parser.add_argument("--nombre-b", default="Equipo B")
    parser.add_argument("--muestras", type=int, default=8)
    parser.add_argument(
        "--min-obs",
        type=int,
        default=25,
        help="Identidades con menos observaciones no se preguntan: su "
        "etiqueta sería tan dudosa para el humano como para el sistema",
    )
    parser.add_argument(
        "--solo-ids",
        default=None,
        help="Lista de ids separados por coma: genera SOLO esas tiras. "
        "Sirve para revisar las dudosas sin repasar las 30.",
    )
    parser.add_argument(
        "--gt-previo",
        default=None,
        help="CSV ya exportado: precarga tus etiquetas para revisarlas en "
        "vez de empezar de cero.",
    )
    parser.add_argument("--titulo", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    datos = cargar_cache(cfg["rutas"]["cache"])
    cache_dets = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
    df = pd.read_csv(args.csv)

    identidades = construir_identidades(df, cache_dets, args.muestras, args.min_obs)
    if args.solo_ids:
        pedidos = {int(x) for x in args.solo_ids.split(",")}
        identidades = {k: v for k, v in identidades.items() if k in pedidos}
    if not identidades:
        raise SystemExit("Ninguna identidad supera --min-obs")
    crops = extraer_crops(cfg["rutas"]["video"], identidades)

    # Colores de los botones: los REALES del equipo si están en el meta,
    # para que el botón se parezca a la camiseta que hay que reconocer.
    meta = Path(str(Path(args.csv).with_suffix("")) + "_meta.json")
    reales = {}
    if meta.exists():
        reales = json.loads(meta.read_text()).get("colores_equipo") or {}
    color_a = reales.get("A", "#93c5fd")
    color_b = reales.get("B", "#fca5a5")

    opciones = [
        {"texto": args.nombre_b, "valor": "B", "color": color_b},
        {"texto": args.nombre_a, "valor": "A", "color": color_a},
        {
            "texto": f"Portero {args.nombre_b.lower()}",
            "valor": "portero_B",
            "color": "#f59e0b",
        },
        {
            "texto": f"Portero {args.nombre_a.lower()}",
            "valor": "portero_A",
            "color": "#60a5fa",
        },
        {"texto": "Árbitro", "valor": "arbitro", "color": "#a3e635"},
        {"texto": "Otro / No sé", "valor": "otro", "color": "#9ca3af"},
    ]

    fps = datos["fps"]
    payload = []
    for datos_id in identidades.values():
        payload.append(
            {
                "id": datos_id["id"],
                "n_obs": datos_id["n_obs"],
                "x_m": datos_id["x_m"],
                "y_m": datos_id["y_m"],
                "t_ini": datos_id["t_ini"],
                "t_fin": datos_id["t_fin"],
                "prediccion": datos_id["prediccion"],
                "crops": [
                    {
                        "img": c["img"],
                        "t": round(c["frame"] / fps, 1),
                        "f": c["frame"],
                        "x": c.get("x", ""),
                        "y": c.get("y", ""),
                    }
                    for c in crops.get(datos_id["id"], [])
                ],
            }
        )

    # Etiquetas previas, casadas por (id, tiempo del recorte)
    previas = {}
    if args.gt_previo:
        anterior = pd.read_csv(args.gt_previo)
        for fila in anterior.itertuples():
            previas[f"{int(fila.id_jugador)}@{round(float(fila.t_s), 1)}"] = str(
                fila.equipo_real
            )

    titulo = args.titulo or f"Ground truth de equipos — {Path(args.csv).stem}"
    html = (
        PLANTILLA.replace("__DATOS__", json.dumps(payload))
        .replace("__OPCIONES__", json.dumps(opciones, ensure_ascii=False))
        .replace("__TITULO__", titulo)
        .replace("__NOMBRE_CSV__", f"gt_equipos_{Path(args.csv).stem}.csv")
        .replace("__PREVIAS__", json.dumps(previas))
    )
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")

    print(f"\n✓ {salida}  ({salida.stat().st_size / 1e6:.1f} MB)")
    print(f"  {len(payload)} identidades con ≥{args.min_obs} observaciones")
    print(f"  {sum(len(p['crops']) for p in payload)} recortes embebidos")
    print("  Ábrelo, un clic (o tecla 1-6) por identidad, y Exportar CSV.")


if __name__ == "__main__":
    main()
