# flake8: noqa: E501
"""
Generador de informe HTML a partir de las métricas calculadas.
MVP1: gráficos (mapa de calor, zonas) + KPIs numéricos (ahora y futuros).
El análisis con IA queda como hueco reservado (se rellenará en MVP2).
Reutilizable: cuando los datos mejoren, el informe mejora sin tocar este código.
"""

import json
from pathlib import Path


def _heat_color(t: float):
    """Color RGB para una intensidad t (0 a 1): verde→amarillo→rojo."""
    if t <= 0.5:
        r = int(2 * t * 255)
        g = 200
    else:
        r = 255
        g = int((1 - (t - 0.5) * 2) * 200)
    return f"rgb({r},{g},40)"


def _build_heatmap_svg(grid, nx, ny, w=1000, h=640):
    """SVG del campo con el mapa de calor superpuesto."""
    cell_w = w / nx
    cell_h = h / ny
    max_val = max((max(row) for row in grid), default=0) or 1

    celdas = ""
    for cy in range(ny):
        for cx in range(nx):
            val = grid[cy][cx]
            if val == 0:
                continue
            t = val / max_val
            color = _heat_color(t)
            opacity = 0.25 + 0.65 * t
            x = cx * cell_w
            y = cy * cell_h
            celdas += (
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w:.1f}" '
                f'height="{cell_h:.1f}" fill="{color}" opacity="{opacity:.2f}"/>\n'
            )

    lineas = f"""
    <rect x="0" y="0" width="{w}" height="{h}" fill="none" stroke="white" stroke-width="3"/>
    <line x1="{w/2}" y1="0" x2="{w/2}" y2="{h}" stroke="white" stroke-width="3"/>
    <circle cx="{w/2}" cy="{h/2}" r="91.5" fill="none" stroke="white" stroke-width="3"/>
    <rect x="0" y="{h/2-201.6}" width="165" height="403.2" fill="none" stroke="white" stroke-width="3"/>
    <rect x="{w-165}" y="{h/2-201.6}" width="165" height="403.2" fill="none" stroke="white" stroke-width="3"/>
    """

    return f"""<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;background:#2d6a3e;border-radius:8px;">
{celdas}
{lineas}
</svg>"""


def _zona_dominante(z):
    """Devuelve el nombre de la zona con más presencia."""
    pares = {
        "Izquierda": z["izquierda_pct"],
        "Centro": z["centro_pct"],
        "Derecha": z["derecha_pct"],
    }
    return max(pares, key=pares.get)


def generate_report(metrics_json: str, output_html: str, partido: str = "Partido"):
    """Genera el informe HTML a partir del JSON de métricas."""
    with open(metrics_json) as f:
        m = json.load(f)

    hm = m["heatmap"]
    heatmap_svg = _build_heatmap_svg(hm["grid"], hm["nx"], hm["ny"])

    z = m["zonas"]
    r = m["resumen"]
    c = m["centroide"]
    zona_dom = _zona_dominante(z)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Informe — {partido}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f5f5f4; color: #1d1d1f; margin: 0; padding: 32px; line-height: 1.6; }}
  .wrap {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 26px; margin-bottom: 4px; }}
  .sub {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
  .banner {{ background: #fff4ed; border: 1px solid #f4d9c6; color: #9a5520;
             padding: 12px 16px; border-radius: 8px; font-size: 13.5px; margin-bottom: 24px; }}
  .card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  .card h2 {{ font-size: 17px; margin: 0 0 16px; }}
  .kpis {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .kpi {{ flex: 1; min-width: 120px; background: #f8f8f7; border-radius: 8px; padding: 14px; text-align: center; }}
  .kpi .v {{ font-size: 24px; font-weight: 700; color: #0a8f6e; }}
  .kpi .l {{ font-size: 12px; color: #666; margin-top: 2px; }}
  .kpi.future {{ opacity: 0.55; }}
  .kpi.future .v {{ color: #999; font-size: 15px; padding: 4px 0; }}
  .kpi.future .badge {{ font-size: 9px; background: #e0e0e0; color: #777; padding: 2px 6px;
                        border-radius: 10px; text-transform: uppercase; letter-spacing: .5px; }}
  .zonas {{ display: flex; height: 40px; border-radius: 8px; overflow: hidden; margin-top: 8px; }}
  .zona {{ display: flex; align-items: center; justify-content: center; color: white;
           font-size: 13px; font-weight: 600; }}
  .ia-slot {{ border: 1.5px dashed #cdb4f0; background: #faf7ff; border-radius: 10px;
              padding: 20px; text-align: center; color: #7c5cc4; font-size: 14px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Informe táctico — {partido}</h1>
  <div class="sub">Generado automáticamente · Tactical Lens</div>

  <div class="banner">
    ⚠️ <strong>Informe preliminar (MVP1).</strong> Datos de una muestra del partido con detección
    en fase de mejora. Las cifras validan el sistema; la cobertura completa de jugadores, la
    posesión y el análisis con IA llegarán con las próximas mejoras.
  </div>

  <div class="card">
    <h2>Resumen del procesamiento</h2>
    <div class="kpis">
      <div class="kpi"><div class="v">{r['total_posiciones']}</div><div class="l">posiciones detectadas</div></div>
      <div class="kpi"><div class="v">{r['frames_con_deteccion']}</div><div class="l">frames con detección</div></div>
      <div class="kpi"><div class="v">{c['x_m']}, {c['y_m']}</div><div class="l">centroide (m)</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Indicadores clave</h2>
    <div class="kpis">
      <div class="kpi"><div class="v">{m['amplitud_m']} m</div><div class="l">Amplitud (ancho)</div></div>
      <div class="kpi"><div class="v">{m['profundidad_m']} m</div><div class="l">Profundidad (largo)</div></div>
      <div class="kpi"><div class="v">{zona_dom}</div><div class="l">Zona dominante</div></div>
    </div>
    <div class="kpis" style="margin-top:16px;">
      <div class="kpi future"><span class="badge">Próximamente</span><div class="v">Posesión</div><div class="l">requiere detección de balón</div></div>
      <div class="kpi future"><span class="badge">Próximamente</span><div class="v">Distancia recorrida</div><div class="l">requiere tracking estable</div></div>
      <div class="kpi future"><span class="badge">Próximamente</span><div class="v">PPDA / presión</div><div class="l">requiere balón y eventos</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Mapa de calor — presencia en el campo</h2>
    {heatmap_svg}
  </div>

  <div class="card">
    <h2>Presencia por zonas (a lo largo del campo)</h2>
    <div class="zonas">
      <div class="zona" style="width:{z['izquierda_pct']}%;background:#3b82c4;">{z['izquierda_pct']}%</div>
      <div class="zona" style="width:{z['centro_pct']}%;background:#0a8f6e;">{z['centro_pct']}%</div>
      <div class="zona" style="width:{z['derecha_pct']}%;background:#c2691a;">{z['derecha_pct']}%</div>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:12px;color:#666;margin-top:6px;">
      <span>Izquierda</span><span>Centro</span><span>Derecha</span>
    </div>
  </div>

  <div class="card">
    <h2>Análisis táctico con IA</h2>
    <div class="ia-slot">
      🧠 El análisis e insights generados por IA a partir de estas métricas
      estarán disponibles en la próxima versión (MVP2), cuando la calidad de los datos
      permita un análisis fiable.
    </div>
  </div>
</div>
</body>
</html>"""

    Path(output_html).parent.mkdir(parents=True, exist_ok=True)
    with open(output_html, "w") as f:
        f.write(html)
    print(f"Informe generado en {output_html}")


if __name__ == "__main__":
    generate_report(
        "data/metrics/metricas_p1.json",
        "data/reports/informe_p1.html",
        partido="Alevín A vs Casarrubuelos",
    )
