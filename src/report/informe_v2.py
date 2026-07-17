"""Informe táctico v2: métricas POR EQUIPO con heatmaps suavizados.

Evolución del informe MVP1 (generate_report.py, que queda intacto como
legacy): dos columnas A vs B con centroide, amplitud, profundidad y zonas;
mapa de calor por equipo con suavizado gaussiano (nada de celdas duras) y
leyenda; y nota de transparencia con el % de posiciones sin equipo
asignable (excluidas del cómputo, no escondidas).

Diseñado para partido completo pero funciona con cualquier tramo: el
encabezado muestra el rango temporal real del CSV (reloj del vídeo).
"""

import base64
import io
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin display: solo renderizamos a PNG en memoria
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.ndimage import gaussian_filter  # noqa: E402

from src.metrics.collective import compute_collective_metrics  # noqa: E402

logger = logging.getLogger(__name__)

# Estética de cada equipo: (nombre de colormap, color de acento)
ESTILO_EQUIPO = {"A": ("Blues", "#2563eb"), "B": ("Reds", "#dc2626")}


def _heatmap_png(
    df_equipo: pd.DataFrame,
    largo: float,
    ancho: float,
    colormap: str,
    celdas_por_metro: float = 0.5,
    sigma_celdas: float = 1.6,
) -> str:
    """Mapa de calor suavizado de un equipo → PNG en base64.

    Rejilla fina (2 m por celda) + filtro gaussiano (sigma en celdas) +
    interpolación bilineal del render: presencia continua, sin celdas
    duras. La intensidad es RELATIVA al máximo del propio equipo.
    """
    nx = max(int(largo * celdas_por_metro), 10)
    ny = max(int(ancho * celdas_por_metro), 8)
    rejilla, _, _ = np.histogram2d(
        df_equipo["y_m"],
        df_equipo["x_m"],
        bins=[ny, nx],
        range=[[0, ancho], [0, largo]],
    )
    suave = gaussian_filter(rejilla, sigma=sigma_celdas)
    if suave.max() > 0:
        suave = suave / suave.max()

    fig, ax = plt.subplots(figsize=(6.4, 4.35), dpi=110)
    ax.set_facecolor("#2e7d46")
    ax.imshow(
        suave,
        extent=[0, largo, ancho, 0],
        cmap=colormap,
        interpolation="bilinear",
        alpha=0.85,
        vmin=0,
        vmax=1,
    )
    _dibujar_lineas_campo(ax, largo, ancho)
    ax.set_xlim(-2, largo + 2)
    ax.set_ylim(ancho + 2, -2)
    ax.set_xticks([])
    ax.set_yticks([])
    for lado in ax.spines.values():
        lado.set_visible(False)

    buffer = io.BytesIO()
    fig.tight_layout(pad=0.3)
    fig.savefig(buffer, format="png", bbox_inches="tight", facecolor="#2e7d46")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _dibujar_lineas_campo(ax, largo: float, ancho: float) -> None:
    """Líneas reglamentarias del campo sobre el heatmap (en metros)."""
    blanco = dict(color="white", lw=1.3, alpha=0.9)
    ax.plot([0, largo, largo, 0, 0], [0, 0, ancho, ancho, 0], **blanco)
    ax.plot([largo / 2, largo / 2], [0, ancho], **blanco)
    ax.add_patch(plt.Circle((largo / 2, ancho / 2), 9.15, fill=False, **blanco))
    for x0, direccion in ((0, 1), (largo, -1)):
        # área grande (16.5 x 40.32) y pequeña (5.5 x 18.32)
        for profundo, mitad in ((16.5, 20.16), (5.5, 9.16)):
            xs = [x0, x0 + direccion * profundo, x0 + direccion * profundo, x0]
            ys = [
                ancho / 2 - mitad,
                ancho / 2 - mitad,
                ancho / 2 + mitad,
                ancho / 2 + mitad,
            ]
            ax.plot(xs, ys, **blanco)


def _mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def _barra_zonas(zonas: dict, acento: str) -> str:
    """Barra horizontal izquierda/centro/derecha de un equipo."""
    partes = []
    for clave, etiqueta, opacidad in (
        ("izquierda_pct", "Izq", 0.55),
        ("centro_pct", "Centro", 0.8),
        ("derecha_pct", "Der", 1.0),
    ):
        pct = zonas[clave]
        # En segmentos minúsculos el texto no cabe: se deja en el title
        texto = f"{etiqueta} {pct:.0f}%" if pct >= 8 else ""
        partes.append(
            f'<div class="zona" title="{etiqueta} {pct:.1f}%" '
            f'style="width:{pct}%;background:{acento};opacity:{opacidad}">'
            f"{texto}</div>"
        )
    return '<div class="zonas">' + "".join(partes) + "</div>"


def generar_informe_v2(
    csv_path: str | Path,
    salida_html: str | Path,
    largo: float = 105.0,
    ancho: float = 68.0,
    partido: str = "Partido",
) -> Path:
    """Genera el informe v2 (HTML autocontenido) desde el CSV de posiciones."""
    df = pd.read_csv(csv_path)
    if len(df) == 0 or "equipo" not in df.columns:
        raise ValueError(
            f"El CSV {csv_path} está vacío o no tiene columna 'equipo' "
            "(¿es un CSV del pipeline v2?)."
        )

    metricas = compute_collective_metrics(
        str(csv_path), field_length=largo, field_width=ancho
    )
    por_equipo = metricas.get("por_equipo", {})
    if not por_equipo:
        raise ValueError(
            f"El CSV {csv_path} no tiene posiciones con equipo asignado (0/1)."
        )

    # Transparencia: cuántas posiciones quedan fuera por no tener equipo
    n_total = len(df)
    n_otro = int((df["equipo"] == 2).sum())
    pct_otro = 100 * n_otro / n_total

    t_min, t_max = float(df["tiempo_s"].min()), float(df["tiempo_s"].max())

    columnas_html = []
    for nombre in ("A", "B"):
        if nombre not in por_equipo:
            continue
        eq = por_equipo[nombre]
        colormap, acento = ESTILO_EQUIPO[nombre]
        png = _heatmap_png(
            df[df["equipo"] == (0 if nombre == "A" else 1)], largo, ancho, colormap
        )
        centroide_txt = f"({eq['centroide']['x_m']:.0f}, {eq['centroide']['y_m']:.0f})"
        columnas_html.append(
            f"""
      <div class="col">
        <h2 style="color:{acento}">Equipo {nombre}</h2>
        <div class="kpis">
          <div class="kpi"><div class="v" style="color:{acento}">{eq['amplitud_m']:.1f} m</div>
            <div class="l">Amplitud</div></div>
          <div class="kpi"><div class="v" style="color:{acento}">{eq['profundidad_m']:.1f} m</div>
            <div class="l">Profundidad</div></div>
          <div class="kpi"><div class="v" style="color:{acento}">{centroide_txt}</div>
            <div class="l">Centroide (m)</div></div>
        </div>
        <h3>Presencia por zonas</h3>
        {_barra_zonas(eq['zonas'], acento)}
        <h3>Mapa de calor</h3>
        <img src="data:image/png;base64,{png}" alt="Mapa de calor equipo {nombre}">
        <div class="leyenda-hm">Presencia relativa (suavizado gaussiano):
          claro = poca · intenso = mucha · máximo propio de cada equipo</div>
      </div>"""
        )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Informe v2 — {partido}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f5f5f4; color: #1d1d1f; margin: 0; padding: 32px; line-height: 1.6; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 26px; margin-bottom: 4px; }}
  h2 {{ font-size: 18px; margin: 0 0 14px; }}
  h3 {{ font-size: 13.5px; margin: 18px 0 6px; color: #555; text-transform: uppercase;
        letter-spacing: .4px; }}
  .sub {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
  .banner {{ background: #fff4ed; border: 1px solid #f4d9c6; color: #9a5520;
             padding: 12px 16px; border-radius: 8px; font-size: 13.5px; margin-bottom: 24px; }}
  .card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  .equipos {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  @media (max-width: 760px) {{ .equipos {{ grid-template-columns: 1fr; }} }}
  .kpis {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .kpi {{ flex: 1; min-width: 100px; background: #f8f8f7; border-radius: 8px;
          padding: 12px; text-align: center; }}
  .kpi .v {{ font-size: 20px; font-weight: 700; }}
  .kpi .l {{ font-size: 12px; color: #666; margin-top: 2px; }}
  .zonas {{ display: flex; height: 36px; border-radius: 8px; overflow: hidden; }}
  .zona {{ display: flex; align-items: center; justify-content: center; color: white;
           font-size: 12px; font-weight: 600; }}
  img {{ width: 100%; border-radius: 8px; display: block; }}
  .leyenda-hm {{ font-size: 12px; color: #777; margin-top: 6px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Informe táctico — {partido}</h1>
  <div class="sub">Tramo {_mmss(t_min)}–{_mmss(t_max)} (reloj del vídeo) ·
    {metricas['resumen']['frames_con_deteccion']} frames ·
    {metricas['resumen']['ids_unicos']} identidades · Tactical Lens</div>

  <div class="banner">Transparencia: el {pct_otro:.0f}&#8202;% de las posiciones
    ({n_otro} de {n_total}) no tiene equipo asignable a esta distancia de cámara
    y queda excluido de las métricas por equipo.</div>

  <div class="card">
    <div class="equipos">
      {''.join(columnas_html)}
    </div>
  </div>
</div>
</body>
</html>
"""
    salida_html = Path(salida_html)
    salida_html.parent.mkdir(parents=True, exist_ok=True)
    salida_html.write_text(html, encoding="utf-8")
    logger.info("Informe v2 generado: %s", salida_html)
    return salida_html
