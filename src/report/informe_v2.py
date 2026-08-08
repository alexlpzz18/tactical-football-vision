"""Informe táctico v2: catálogo de métricas POR EQUIPO desde el CSV.

Qué se muestra y qué se promete lo decide configs/informe.yaml (el
catálogo): las métricas 'activas' se calculan desde el CSV sin pasos
manuales; las 'proximamente' se muestran en gris con badge y con QUÉ falta
para activarlas. Encender una métrica cuando llegue su dependencia =
cambiar su estado en el yaml + implementar su calculadora — el informe
falla claro si el yaml promete como activa algo que el código no sabe
calcular.

Cada métrica activa lleva su definición breve al pie: el entrenador debe
entender qué mide sin manual. generate_report.py (MVP1) queda intacto
como legacy.
"""

import base64
import html as html_mod
import io
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin display: solo renderizamos a PNG en memoria
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from scipy.ndimage import gaussian_filter  # noqa: E402

from src.campo import ANCHO_M, LARGO_M  # noqa: E402
from src.metrics.collective import compute_collective_metrics  # noqa: E402
from src.report.metricas_informe import (  # noqa: E402
    calcular_metricas_equipo,
    preparar_contextos,
)

logger = logging.getLogger(__name__)

RUTA_CATALOGO = Path("configs/informe.yaml")

# Estética de cada equipo: (nombre de colormap, color de acento)
ESTILO_EQUIPO = {"A": ("Blues", "#2563eb"), "B": ("Reds", "#dc2626")}

# Métricas del catálogo que este código sabe calcular y renderizar.
# Si el yaml declara 'activa' una clave que no está aquí, el informe falla
# claro: la config no puede prometer lo que el código no sabe hacer.
CLAVES_IMPLEMENTADAS = {
    "heatmap",
    "centroide",
    "amplitud_profundidad",
    "altura_linea_defensiva",
    "altura_bloque",
    "distancia_lineas",
    "basculacion",
    "territorio",
}


def cargar_catalogo(ruta: Path = RUTA_CATALOGO) -> dict:
    """Carga y valida el catálogo de métricas del informe."""
    with open(ruta) as f:
        catalogo = yaml.safe_load(f)
    activas = [m for m in catalogo["metricas"] if m["estado"] == "activa"]
    sin_calculadora = [
        m["clave"] for m in activas if m["clave"] not in CLAVES_IMPLEMENTADAS
    ]
    if sin_calculadora:
        raise ValueError(
            f"El catálogo declara activas métricas sin calculadora: {sin_calculadora}. "
            "Impleméntalas en el informe o márcalas 'proximamente' en configs/informe.yaml."
        )
    return catalogo


# ────────────────────────── gráficos (PNG base64) ──────────────────────────


def _heatmap_png(
    df_equipo, largo, ancho, colormap, celdas_por_metro=0.5, sigma_celdas=1.6
):
    """Mapa de calor suavizado de un equipo → PNG en base64.

    Rejilla fina (2 m por celda) + filtro gaussiano + interpolación
    bilineal: presencia continua, sin celdas duras. Intensidad RELATIVA
    al máximo del propio equipo.
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
    return _fig_a_base64(fig, "#2e7d46")


def _basculacion_png(metricas_por_equipo, ancho, t_min, t_max):
    """Serie temporal de basculación de ambos equipos → PNG base64."""
    fig, ax = plt.subplots(figsize=(9.5, 2.8), dpi=110)
    for nombre, met in metricas_por_equipo.items():
        if met.basculacion_t:
            ax.plot(
                met.basculacion_t,
                met.basculacion_y,
                color=ESTILO_EQUIPO[nombre][1],
                lw=1.8,
                label=f"Equipo {nombre}",
            )
    ax.axhline(ancho / 2, color="#999", lw=0.8, ls="--")
    ax.set_ylim(0, ancho)
    ax.set_xlim(t_min, t_max)
    ax.set_ylabel("eje ancho (m)", fontsize=9)
    ticks = np.linspace(t_min, t_max, 7)
    ax.set_xticks(ticks)
    ax.set_xticklabels([_mmss(t) for t in ticks], fontsize=8)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=9, loc="upper right", frameon=False)
    ax.text(t_min, 1.5, "banda cercana a cámara", fontsize=7.5, color="#888")
    ax.text(t_min, ancho - 4.5, "banda lejana", fontsize=7.5, color="#888")
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    return _fig_a_base64(fig, "white")


def _dibujar_lineas_campo(ax, largo, ancho):
    """Líneas reglamentarias del campo sobre el heatmap (en metros)."""
    blanco = dict(color="white", lw=1.3, alpha=0.9)
    ax.plot([0, largo, largo, 0, 0], [0, 0, ancho, ancho, 0], **blanco)
    ax.plot([largo / 2, largo / 2], [0, ancho], **blanco)
    ax.add_patch(plt.Circle((largo / 2, ancho / 2), 9.15, fill=False, **blanco))
    for x0, direccion in ((0, 1), (largo, -1)):
        for profundo, mitad in ((16.5, 20.16), (5.5, 9.16)):
            xs = [x0, x0 + direccion * profundo, x0 + direccion * profundo, x0]
            ys = [
                ancho / 2 - mitad,
                ancho / 2 - mitad,
                ancho / 2 + mitad,
                ancho / 2 + mitad,
            ]
            ax.plot(xs, ys, **blanco)


def _fig_a_base64(fig, color_fondo):
    buffer = io.BytesIO()
    fig.tight_layout(pad=0.3)
    fig.savefig(buffer, format="png", bbox_inches="tight", facecolor=color_fondo)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


# ─────────────────────────── piezas de HTML ────────────────────────────


def _mmss(t):
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def _kpi(valor, etiqueta, acento):
    v = valor if valor is not None else "N/D"
    return (
        f'<div class="kpi"><div class="v" style="color:{acento}">{v}</div>'
        f'<div class="l">{etiqueta}</div></div>'
    )


def _barra_segmentos(segmentos, acento):
    """Barra horizontal de porcentajes [(etiqueta, pct, opacidad), ...]."""
    partes = []
    for etiqueta, pct, opacidad in segmentos:
        texto = f"{etiqueta} {pct:.0f}%" if pct >= 8 else ""
        partes.append(
            f'<div class="zona" title="{etiqueta} {pct:.1f}%" '
            f'style="width:{pct}%;background:{acento};opacity:{opacidad}">{texto}</div>'
        )
    return '<div class="zonas">' + "".join(partes) + "</div>"


def _tarjetas_proximamente(catalogo):
    tarjetas = []
    for metrica in catalogo["metricas"]:
        if metrica["estado"] != "proximamente":
            continue
        tarjetas.append(
            f'<div class="kpi future"><span class="badge">Próximamente</span>'
            f'<div class="v">{metrica["nombre"]}</div>'
            f'<div class="l">(requiere: {metrica["requiere"]})</div></div>'
        )
    return "".join(tarjetas)


def _seccion_analisis_ia(texto: str | None, modelo: str) -> str:
    """Tarjeta "Análisis táctico con IA": rellena o con placeholder.

    Sin texto (sin --con-ia, sin API key o fallo de la llamada) el
    informe sale igual con el hueco marcado: degradación limpia.
    """
    if texto is None:
        cuerpo = (
            '<div class="ia-placeholder">Sección pendiente: genera el informe '
            "con <code>--con-ia</code> y una <code>ANTHROPIC_API_KEY</code> "
            "configurada (ver <code>.env.example</code>) para rellenarla.</div>"
        )
    else:
        parrafos = [
            f"<p>{html_mod.escape(p.strip())}</p>".replace("\n", "<br>")
            for p in texto.split("\n\n")
            if p.strip()
        ]
        nota = (
            f'<div class="ia-nota">Redactado automáticamente por IA ({modelo}) '
            "exclusivamente a partir de las métricas de este informe; no ha "
            "visto el vídeo ni eventos del partido.</div>"
        )
        cuerpo = "".join(parrafos) + nota
    return (
        '<div class="card"><h2>Análisis táctico con IA</h2>'
        f'<div class="ia-cuerpo">{cuerpo}</div></div>'
    )


def _definiciones(catalogo):
    filas = []
    for metrica in catalogo["metricas"]:
        if metrica["estado"] == "activa":
            filas.append(
                f'<li><b>{metrica["nombre"]}:</b> {metrica["definicion"].strip()}</li>'
            )
    return "".join(filas)


# ─────────────────────────── informe completo ───────────────────────────


def generar_informe_v2(
    csv_path: str | Path,
    salida_html: str | Path,
    largo: float = LARGO_M,
    ancho: float = ANCHO_M,
    partido: str = "Partido",
    categoria: str = "fútbol base",
    con_ia: bool = False,
    ruta_catalogo: Path = RUTA_CATALOGO,
) -> Path:
    """Genera el informe v2 (HTML autocontenido) desde el CSV de posiciones."""
    catalogo = cargar_catalogo(ruta_catalogo)
    params = catalogo.get("parametros", {})

    df = pd.read_csv(csv_path)
    if len(df) == 0 or "equipo" not in df.columns:
        raise ValueError(
            f"El CSV {csv_path} está vacío o no tiene columna 'equipo' "
            "(¿es un CSV del pipeline v2?)."
        )

    colectivas = compute_collective_metrics(
        str(csv_path), field_length=largo, field_width=ancho
    )
    por_equipo = colectivas.get("por_equipo", {})
    if not por_equipo:
        raise ValueError(
            f"El CSV {csv_path} no tiene posiciones con equipo asignado (0/1)."
        )

    contextos = preparar_contextos(df, largo)
    metricas_eq = {
        nombre: calcular_metricas_equipo(
            ctx,
            largo,
            ancho,
            n_defensas=params.get("n_defensas", 4),
            n_atacantes=params.get("n_atacantes", 3),
            ventana_basculacion_s=params.get("ventana_basculacion_s", 2.0),
        )
        for nombre, ctx in contextos.items()
    }

    n_total = len(df)
    n_otro = int((df["equipo"] == 2).sum())
    pct_otro = 100 * n_otro / n_total
    # El staff (línier / cuerpo técnico, detectado FUERA del campo) va al
    # mismo cajón que 'otro' pero no es lo mismo: uno es una detección que
    # el sistema descarta a propósito, el otro un jugador sin equipo
    # asignable. Se cuentan por separado para que el banner no mienta.
    n_staff = int((df["etiqueta"] == "staff").sum()) if "etiqueta" in df.columns else 0
    n_sin_equipo = n_otro - n_staff
    t_min, t_max = float(df["tiempo_s"].min()), float(df["tiempo_s"].max())

    # ── columnas por equipo ──
    columnas = []
    for nombre in ("A", "B"):
        if nombre not in por_equipo:
            continue
        eq = por_equipo[nombre]
        met = metricas_eq[nombre]
        colormap, acento = ESTILO_EQUIPO[nombre]
        png = _heatmap_png(
            df[df["equipo"] == (0 if nombre == "A" else 1)], largo, ancho, colormap
        )
        centroide_txt = f"({eq['centroide']['x_m']:.0f}, {eq['centroide']['y_m']:.0f})"
        sin_orientacion = contextos[nombre].x_porteria is None
        nota_orientacion = (
            '<div class="leyenda-hm">Sin portero detectado en el tramo: las '
            "métricas de orientación (alturas, líneas, tercios) no son "
            "calculables.</div>"
            if sin_orientacion
            else ""
        )
        tercios_html = (
            _barra_segmentos(
                [
                    ("Defensa", met.tercios["defensa_pct"], 0.55),
                    ("Medio", met.tercios["medio_pct"], 0.8),
                    ("Ataque", met.tercios["ataque_pct"], 1.0),
                ],
                acento,
            )
            if met.tercios
            else ""
        )
        pasillos_html = _barra_segmentos(
            [
                ("Cercano", met.pasillos["cercano_pct"], 0.55),
                ("Central", met.pasillos["central_pct"], 0.8),
                ("Lejano", met.pasillos["lejano_pct"], 1.0),
            ],
            acento,
        )

        def _metros(valor):
            return None if valor is None else f"{valor:.1f} m"

        kpi_linea = _kpi(
            _metros(met.altura_linea_defensiva), "Altura línea defensiva", acento
        )
        kpi_bloque = _kpi(_metros(met.altura_bloque), "Altura del bloque", acento)
        kpi_lineas = _kpi(
            _metros(met.distancia_lineas), "Distancia entre líneas", acento
        )
        columnas.append(
            f"""
      <div class="col">
        <h2 style="color:{acento}">Equipo {nombre}</h2>
        <div class="kpis">
          {_kpi(f"{eq['amplitud_m']:.1f} m", "Amplitud", acento)}
          {_kpi(f"{eq['profundidad_m']:.1f} m", "Profundidad", acento)}
          {_kpi(centroide_txt, "Centroide (m)", acento)}
        </div>
        <div class="kpis" style="margin-top:12px">
          {kpi_linea}
          {kpi_bloque}
          {kpi_lineas}
        </div>
        {nota_orientacion}
        <h3>Tercios (desde su portería)</h3>
        {tercios_html}
        <h3>Pasillos (eje ancho)</h3>
        {pasillos_html}
        <h3>Mapa de calor</h3>
        <img src="data:image/png;base64,{png}" alt="Mapa de calor equipo {nombre}">
        <div class="leyenda-hm">Presencia relativa (suavizado gaussiano):
          claro = poca · intenso = mucha · máximo propio de cada equipo</div>
      </div>"""
        )

    basculacion_png = _basculacion_png(metricas_eq, ancho, t_min, t_max)

    # ── Análisis táctico con IA (opcional; nunca rompe el informe) ──
    cfg_ia = catalogo.get("analisis_ia", {})
    modelo_ia = cfg_ia.get("modelo", "claude-sonnet-4-6")
    analisis_texto = None
    if con_ia:
        try:
            from src.report import analisis_ia

            contexto_partido = {
                "partido": partido,
                "categoria": categoria,
                "tramo_inicio_video": _mmss(t_min),
                "duracion_tramo_s": round(t_max - t_min, 1),
                "pct_posiciones_sin_equipo": round(pct_otro, 1),
            }
            definiciones_ia = {
                m["clave"]: m["definicion"].strip()
                for m in catalogo["metricas"]
                if m["estado"] == "activa"
            }
            analisis_texto = analisis_ia.generar_analisis(
                analisis_ia.construir_json_metricas(colectivas, metricas_eq, contextos),
                definiciones_ia,
                contexto_partido,
                modelo=modelo_ia,
                max_tokens=cfg_ia.get("max_tokens", 1024),
            )
        except Exception as e:
            logger.warning(
                "Análisis con IA no disponible (%s); el informe sale con "
                "placeholder.",
                e,
            )
    seccion_ia = _seccion_analisis_ia(analisis_texto, modelo_ia)

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
  .card > h2 {{ font-size: 17px; }}
  .equipos {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  @media (max-width: 760px) {{ .equipos {{ grid-template-columns: 1fr; }} }}
  .kpis {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .kpi {{ flex: 1; min-width: 100px; background: #f8f8f7; border-radius: 8px;
          padding: 12px; text-align: center; }}
  .kpi .v {{ font-size: 20px; font-weight: 700; }}
  .kpi .l {{ font-size: 12px; color: #666; margin-top: 2px; }}
  .kpi.future {{ opacity: 0.6; min-width: 190px; }}
  .kpi.future .v {{ color: #777; font-size: 14.5px; padding: 3px 0; }}
  .kpi.future .l {{ font-size: 11px; }}
  .kpi.future .badge {{ font-size: 9px; background: #e0e0e0; color: #777; padding: 2px 6px;
                        border-radius: 10px; text-transform: uppercase; letter-spacing: .5px; }}
  .zonas {{ display: flex; height: 36px; border-radius: 8px; overflow: hidden; }}
  .zona {{ display: flex; align-items: center; justify-content: center; color: white;
           font-size: 12px; font-weight: 600; }}
  img {{ width: 100%; border-radius: 8px; display: block; }}
  .leyenda-hm {{ font-size: 12px; color: #777; margin-top: 6px; }}
  .definiciones {{ font-size: 12.5px; color: #555; }}
  .definiciones li {{ margin-bottom: 6px; }}
  .ia-cuerpo p {{ font-size: 14.5px; margin: 0 0 12px; }}
  .ia-placeholder {{ color: #888; font-style: italic; font-size: 13.5px;
                     background: #f8f8f7; border: 1px dashed #ddd;
                     border-radius: 8px; padding: 14px 16px; }}
  .ia-placeholder code {{ font-style: normal; background: #eee;
                          padding: 1px 5px; border-radius: 4px; }}
  .ia-nota {{ font-size: 11.5px; color: #999; margin-top: 10px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Informe táctico — {partido}</h1>
  <div class="sub">Tramo {_mmss(t_min)}–{_mmss(t_max)} (reloj del vídeo) ·
    {colectivas['resumen']['frames_con_deteccion']} frames ·
    {colectivas['resumen']['ids_unicos']} identidades · Tactical Lens</div>

  <div class="banner">Transparencia: el {pct_otro:.0f}&#8202;% de las posiciones
    ({n_otro} de {n_total}) queda excluido de las métricas por equipo —
    {n_sin_equipo} sin equipo asignable a esta distancia de cámara y
    {n_staff} de personal no jugador (detectado fuera de las líneas del campo:
    juez de línea o cuerpo técnico).</div>

  <div class="card">
    <div class="equipos">
      {''.join(columnas)}
    </div>
  </div>

  <div class="card">
    <h2>Basculación lateral del bloque</h2>
    <img src="data:image/png;base64,{basculacion_png}" alt="Basculación lateral">
  </div>

  {seccion_ia}

  <div class="card">
    <h2>Próximamente</h2>
    <div class="kpis">
      {_tarjetas_proximamente(catalogo)}
    </div>
  </div>

  <div class="card definiciones">
    <h2>Qué mide cada métrica</h2>
    <ul>
      {_definiciones(catalogo)}
    </ul>
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
