#!/usr/bin/env python
"""GT de IDENTIDAD: ¿en qué punto una identidad deja de ser el mismo niño?

Por qué hace falta, y es la limitación que bloquea media línea de trabajo:
el benjamín **no tiene GT posicional**, así que allí no se pueden contar
quimeras del mismo equipo (el caso #43) ni juzgar si conviene mirar los
cruces. La accuracy de equipos que se usa hoy sale de un traslado con
pérdida y, peor, **premia fragmentar** — medido: trocear una identidad
sucia en trozos limpios la sube automáticamente.

Con este GT se puede contar pureza de verdad en F7.

Cómo se usa: cada identidad es una tira de recortes ordenada en el
tiempo. Se hace clic en el recorte **a partir del cual ya no es el mismo
niño**; eso parte la identidad en segmentos. Varios clics, varios cortes.

El CSV sale indexado por **posición y tiempo** (frame, x_m, y_m) además
de por id del sistema. Los ids no sobreviven a un cambio de detector
—medido: 27 de 30 identidades del mini-GT anterior eran otra persona con
el v4, mediana 38 m— pero dónde y cuándo estuvo alguien, sí.

Uso:
    python scripts/etiquetar_identidad_gt.py \\
        --config configs/processor_benja_emb.yaml \\
        --csv data/tracking_benja/posiciones_benja_emb.csv \\
        --salida outputs/etiquetar_identidad_benja.html
"""

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.tracking.cache_io import cargar_cache  # noqa: E402

# Se reutilizan los helpers de recorte de la herramienta de equipos: son
# los que dibujan la caja del jugador en azul y las vecinas en blanco,
# que es lo que hizo usable la tira (sin eso "coges a dos personas en
# uno", dicho por Alex).
_spec = importlib.util.spec_from_file_location(
    "etiquetar_equipos_gt", RAIZ / "scripts" / "etiquetar_equipos_gt.py"
)
_eq = importlib.util.module_from_spec(_spec)
sys.modules["etiquetar_equipos_gt"] = _eq
_spec.loader.exec_module(_eq)

logger = logging.getLogger("etiquetar_identidad")

PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>__TITULO__</title>
<style>
 body { background:#11131a; color:#e5e7eb; font-family:-apple-system,
        BlinkMacSystemFont,'Segoe UI',sans-serif; margin:0; padding:0 16px 60px; }
 header { position:sticky; top:0; z-index:5; background:#171a21;
          padding:12px 16px; margin:0 -16px 16px; border-bottom:1px solid #2a2f3a; }
 h1 { font-size:16px; margin:0 0 6px; }
 .ayuda { font-size:13px; color:#9ca3af; line-height:1.5; }
 .barra { height:4px; background:#2a2f3a; border-radius:2px; margin-top:8px; }
 .barra > div { height:100%; background:#60a5fa; border-radius:2px; width:0; }
 button { background:#2a2f3a; color:#e5e7eb; border:1px solid #3a4150;
          border-radius:6px; padding:5px 12px; font-size:13px; cursor:pointer; }
 .ficha { background:#171a21; border:1px solid #2a2f3a; border-radius:10px;
          padding:10px 12px; margin-bottom:12px; }
 .ficha.tocada { border-color:#f472b6; }
 .cab { display:flex; gap:14px; align-items:baseline; font-size:13px;
        color:#9ca3af; margin-bottom:8px; flex-wrap:wrap; }
 .cab b { color:#e5e7eb; font-size:15px; }
 .tira { display:flex; gap:0; overflow-x:auto; padding-bottom:6px; }
 .col { position:relative; cursor:pointer; flex:0 0 auto; padding:0 2px; }
 .col img { display:block; border-radius:4px; }
 .col .t { font-size:10px; color:#6b7280; text-align:center; margin-top:2px; }
 .col.corte { border-left:3px solid #f472b6; margin-left:4px; padding-left:4px; }
 .col.corte .t { color:#f472b6; font-weight:600; }
 .seg { position:absolute; top:2px; left:4px; background:#0009; color:#fff;
        font-size:10px; padding:0 4px; border-radius:3px; }
</style></head><body>
<header>
  <h1>__TITULO__</h1>
  <div class="ayuda">
    Haz clic en el recorte <b>a partir del cual ya NO es el mismo niño</b>.
    Se marca con una línea rosa y empieza un segmento nuevo.
    Vuelve a hacer clic para deshacer. Si la identidad es siempre el mismo
    niño, no toques nada.
  </div>
  <div style="margin-top:8px">
    <span id="cuenta"></span> &nbsp;
    <button id="exportar">Exportar CSV</button>
  </div>
  <div class="barra"><div id="barra"></div></div>
</header>
<div id="lista"></div>
<script>
const IDENTIDADES = __DATOS__;
const cortes = {};   // id -> Set de índices de recorte

function clave(id, j) { return id + ':' + j; }
function segmentoDe(d, j) {
  let s = 0;
  for (let k = 1; k <= j; k++) if (cortes[clave(d.id, k)]) s++;
  return s;
}
function tocada(d) { return d.crops.some((_c, j) => cortes[clave(d.id, j)]); }

function pinta() {
  const lista = document.getElementById('lista');
  lista.innerHTML = '';
  IDENTIDADES.forEach(d => {
    const f = document.createElement('div');
    f.className = 'ficha' + (tocada(d) ? ' tocada' : '');
    const nSeg = 1 + d.crops.filter((_c, j) => j > 0 && cortes[clave(d.id, j)]).length;
    f.innerHTML = `
      <div class="cab">
        <b>#${d.id}</b>
        <span>${d.n_obs} obs · ${d.t_ini}-${d.t_fin}s</span>
        <span>equipo: ${d.prediccion}</span>
        <span style="color:${nSeg > 1 ? '#f472b6' : '#6b7280'}">
          ${nSeg > 1 ? nSeg + ' personas' : 'una persona'}</span>
      </div>
      <div class="tira">${d.crops.map((c, j) => `
        <div class="col${j > 0 && cortes[clave(d.id, j)] ? ' corte' : ''}"
             data-id="${d.id}" data-j="${j}">
          <img src="${c.img}" loading="lazy">
          <div class="seg">${segmentoDe(d, j)}</div>
          <div class="t">${c.t}s</div>
        </div>`).join('')}</div>`;
    lista.appendChild(f);
  });
  lista.querySelectorAll('.col').forEach(col => {
    col.onclick = () => {
      const j = +col.dataset.j;
      if (j === 0) return;   // el primero no puede ser un corte
      const k = clave(+col.dataset.id, j);
      cortes[k] ? delete cortes[k] : cortes[k] = true;
      const y = window.scrollY; pinta(); window.scrollTo(0, y);
    };
  });
  const n = IDENTIDADES.filter(tocada).length;
  document.getElementById('cuenta').textContent =
    n + ' identidades con cambio de persona de ' + IDENTIDADES.length;
  document.getElementById('barra').style.width = (100*n/IDENTIDADES.length) + '%';
}

document.getElementById('exportar').onclick = () => {
  const filas = ['id_sistema,orden,frame,t_s,x_m,y_m,segmento,es_corte'];
  IDENTIDADES.forEach(d => d.crops.forEach((c, j) => {
    filas.push([d.id, j, c.f, c.t, c.x, c.y, segmentoDe(d, j),
                (j > 0 && cortes[clave(d.id, j)]) ? 1 : 0].join(','));
  }));
  const url = URL.createObjectURL(new Blob([filas.join('\\n')], {type:'text/csv'}));
  const a = document.createElement('a');
  a.href = url; a.download = '__NOMBRE_CSV__'; a.click();
};
pinta();
</script></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--salida", default="outputs/etiquetar_identidad.html")
    p.add_argument(
        "--muestras",
        type=int,
        default=16,
        help="Recortes por identidad. Más que en el GT de equipos: un "
        "cambio de persona puede ocurrir en cualquier punto de la vida.",
    )
    p.add_argument("--min-obs", type=int, default=25)
    p.add_argument("--titulo", default=None)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(open(args.config))
    datos = cargar_cache(cfg["rutas"]["cache"])
    cache_dets = {e["frame_idx"]: e["dets"] for e in datos["cache"]}
    df = pd.read_csv(args.csv)

    identidades = _eq.construir_identidades(df, cache_dets, args.muestras, args.min_obs)
    crops = _eq.extraer_crops(cfg["rutas"]["video"], identidades, cache_dets)

    fps = datos["fps"]
    payload = []
    for d in identidades.values():
        trozos = crops.get(d["id"], [])
        if len(trozos) < 3:
            continue
        payload.append(
            {
                "id": d["id"],
                "n_obs": d["n_obs"],
                "t_ini": d["t_ini"],
                "t_fin": d["t_fin"],
                "prediccion": d["prediccion"],
                "crops": [
                    {
                        "img": c["img"],
                        "t": round(c["frame"] / fps, 1),
                        "f": c["frame"],
                        "x": c.get("x", ""),
                        "y": c.get("y", ""),
                    }
                    for c in trozos
                ],
            }
        )

    titulo = args.titulo or f"GT de identidad — {Path(args.csv).stem}"
    html = (
        PLANTILLA.replace("__TITULO__", titulo)
        .replace("__DATOS__", json.dumps(payload))
        .replace("__NOMBRE_CSV__", f"gt_identidad_{Path(args.csv).stem}.csv")
    )
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(html, encoding="utf-8")
    mb = Path(args.salida).stat().st_size / 1e6
    print(f"\n✓ {args.salida}  ({mb:.1f} MB)")
    print(f"  {len(payload)} identidades con ≥{args.min_obs} observaciones")
    print(f"  {sum(len(d['crops']) for d in payload)} recortes embebidos")
    print("  Clic en el recorte donde deja de ser el mismo niño. Exportar CSV.")


if __name__ == "__main__":
    main()
