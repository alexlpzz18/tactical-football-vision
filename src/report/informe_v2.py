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
from src.campo_modelo import MODELO_F11, ModeloCampo  # noqa: E402
from src.metrics.collective import compute_collective_metrics  # noqa: E402
from src.report.metricas_informe import (  # noqa: E402
    calcular_metricas_equipo,
    preparar_contextos,
)

logger = logging.getLogger(__name__)

RUTA_CATALOGO = Path("configs/informe.yaml")

# Estética por defecto de cada equipo: (colormap, color de acento). Solo
# se usa si el meta del processor no trae los colores reales.
ESTILO_EQUIPO = {"A": ("Blues", "#2563eb"), "B": ("Reds", "#dc2626")}


def _colormap_de(color_hex: str):
    """Colormap continuo que va del blanco al color REAL del equipo.

    Pintar el mapa de calor del blanco a la camiseta hace que no haga
    falta leyenda: el naranja del mapa es el naranja del equipo. Con
    'Blues' y 'Reds' fijos había que traducir mentalmente.
    """
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list("equipo", ["#ffffff", color_hex])


def _legible(color_hex: str, minimo: float = 110.0) -> str:
    """Oscurece un color hasta que se lea como TEXTO sobre blanco.

    El color de camiseta vale para un fondo, pero no siempre para letra:
    el equipo blanco del benjamín es #b7bbeb, y sus KPI en ese tono sobre
    la tarjeta clara resultaban ilegibles. Se conserva el tono —para que
    siga identificando al equipo— y se le baja la luminosidad lo justo.
    """
    r, g, b = bytes.fromhex(color_hex.lstrip("#"))
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum <= minimo:
        return color_hex
    factor = minimo / max(lum, 1.0)
    return "#%02x%02x%02x" % tuple(min(255, int(c * factor)) for c in (r, g, b))


def _contraste(color_hex: str) -> str:
    """Negro o blanco, el que se lea sobre ese fondo."""
    r, g, b = bytes.fromhex(color_hex.lstrip("#"))
    return "#111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#fff"


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


def _heatmap_png(df_equipo, modelo, colormap, celdas_por_metro=0.5, sigma_celdas=1.6):
    """Mapa de calor suavizado de un equipo → PNG en base64.

    Rejilla fina (2 m por celda) + filtro gaussiano + interpolación
    bilineal: presencia continua, sin celdas duras. Intensidad RELATIVA
    al máximo del propio equipo.
    """
    largo, ancho = modelo.largo, modelo.ancho
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
    _dibujar_lineas_campo(ax, modelo)
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


def _dibujar_lineas_campo(ax, modelo):
    """Líneas del campo sobre el heatmap, DERIVADAS del modelo.

    Antes estaban hardcodeadas a F11 (círculo 9,15, área 16,5×40,32): en
    un campo de F7 dibujaban un campo que no era el del partido.
    """
    blanco = dict(color="white", lw=1.3, alpha=0.9)
    geo = modelo.geometria_dibujo()
    for (x1, y1), (x2, y2) in geo["lineas"]:
        ax.plot([x1, x2], [y1, y2], **blanco)
    for circulo in geo["circulos"]:
        ax.add_patch(
            plt.Circle(
                (circulo["cx"], circulo["cy"]), circulo["r"], fill=False, **blanco
            )
        )
    for arco in geo["arcos"]:
        angulos = np.linspace(arco["desde"], arco["hasta"], 24)
        ax.plot(
            arco["cx"] + arco["r"] * np.cos(angulos),
            arco["cy"] + arco["r"] * np.sin(angulos),
            **blanco,
        )
    for x, y in geo["puntos"]:
        ax.plot([x], [y], marker="o", markersize=2.2, color="white", alpha=0.9)
    for p in geo["porterias"]:
        ax.plot(
            [p["x"], p["x"] + p["ancho"], p["x"] + p["ancho"], p["x"]],
            [p["y"], p["y"], p["y"] + p["alto"], p["y"] + p["alto"]],
            **blanco,
        )


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
        # El texto de la barra se pinta en blanco o negro según el fondo
        # REAL (color × opacidad): sobre una camiseta clara, el blanco no
        # se lee.
        r, g, b = bytes.fromhex(acento.lstrip("#"))
        lum = (0.299 * r + 0.587 * g + 0.114 * b) * opacidad + 255 * (1 - opacidad)
        color_txt = "#14181f" if lum > 150 else "#fff"
        partes.append(
            f'<div class="zona" title="{etiqueta} {pct:.1f}%" '
            f'style="width:{pct}%;background:{acento};opacity:{opacidad};'
            f'color:{color_txt}">{texto}</div>'
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
    largo: float | None = None,
    ancho: float | None = None,
    partido: str = "Partido",
    modelo: "ModeloCampo | None" = None,
    categoria: str = "fútbol base",
    con_ia: bool = False,
    ruta_catalogo: Path = RUTA_CATALOGO,
    colores_equipo: dict | None = None,
    nombres_equipo: dict | None = None,
) -> Path:
    """Genera el informe v2 (HTML autocontenido) desde el CSV de posiciones."""
    # El MODELO manda: de él salen las dimensiones y las marcas que se
    # pintan. Sin modelo, el F11 de Villaviciosa con las dimensiones de
    # src/campo.py (comportamiento histórico); largo/ancho sueltos siguen
    # aceptándose y ajustan el modelo.
    modelo = modelo or MODELO_F11.con_dimensiones(LARGO_M, ANCHO_M)
    if largo is not None or ancho is not None:
        modelo = modelo.con_dimensiones(
            largo if largo is not None else modelo.largo,
            ancho if ancho is not None else modelo.ancho,
        )
    largo, ancho = modelo.largo, modelo.ancho

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
        real = (colores_equipo or {}).get(nombre)
        fondo = None
        if real:
            # `acento` va en TEXTO (KPIs, barras), así que se oscurece;
            # `fondo` conserva el color de camiseta puro.
            colormap, acento, fondo = _colormap_de(real), _legible(real), real
        png = _heatmap_png(
            df[df["equipo"] == (0 if nombre == "A" else 1)], modelo, colormap
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
        cab_fondo = fondo or acento
        cab_texto = _contraste(cab_fondo)
        cab_nombre = (nombres_equipo or {}).get(nombre, f"Equipo {nombre}")
        columnas.append(
            f"""
      <div class="col">
        <div class="equipo-cab"
             style="background:{cab_fondo};color:{cab_texto}">
          <span class="camiseta"></span>{cab_nombre}
        </div>
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

    # Chips de la portada: el color de camiseta identifica al equipo sin
    # que haya que leer ninguna leyenda.
    partes = []
    for letra in ("A", "B"):
        color = (colores_equipo or {}).get(letra, ESTILO_EQUIPO[letra][1])
        nombre_eq = (nombres_equipo or {}).get(letra, "Equipo " + letra)
        partes.append(
            '<span class="chip"><span class="camiseta" style="background:'
            + color
            + '"></span>'
            + nombre_eq
            + "</span>"
        )
    chips_equipos = partes[0] + '<span class="vs">VS</span>' + partes[1]

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
  /* Documento pensado para leerse e imprimirse. La jerarquía la marcan el
     tamaño y el peso; el color se reserva para los equipos, que es la
     única información que debe distinguirse de un vistazo. */
  * {{ box-sizing: border-box }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
          sans-serif; background: #eef0f3; color: #14181f; margin: 0;
          padding: 0 0 48px; line-height: 1.6;
          -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 0 24px; }}
  .portada {{ background: linear-gradient(135deg, #10233a 0%, #1c3f5e 100%);
              color: #fff; padding: 52px 0 44px; margin-bottom: 28px; }}
  .portada .wrap {{ display: flex; flex-direction: column; gap: 6px }}
  .marca {{ font-size: 12px; letter-spacing: 2.4px; text-transform: uppercase;
            color: #7fb2d9; font-weight: 600 }}
  .portada h1 {{ font-size: 34px; margin: 6px 0 2px; font-weight: 680;
                 letter-spacing: -0.02em; line-height: 1.15 }}
  .portada .meta {{ color: #b9cde0; font-size: 14.5px }}
  .enfrentamiento {{ display: flex; align-items: center; gap: 14px;
                     margin-top: 22px; flex-wrap: wrap }}
  .chip {{ display: inline-flex; align-items: center; gap: 9px;
           background: rgba(255,255,255,.10);
           border: 1px solid rgba(255,255,255,.18);
           padding: 9px 16px; border-radius: 999px; font-weight: 600;
           font-size: 15px }}
  .chip .camiseta {{ width: 13px; height: 13px; border-radius: 3px;
                     box-shadow: 0 0 0 1.5px rgba(255,255,255,.55) }}
  .vs {{ color: #7fb2d9; font-size: 13px; letter-spacing: 1.5px }}
  h2 {{ font-size: 18px; margin: 0 0 16px; font-weight: 650;
        letter-spacing: -0.01em }}
  h3 {{ font-size: 11.5px; margin: 22px 0 8px; color: #6b7280;
        text-transform: uppercase; letter-spacing: .9px; font-weight: 700 }}
  .banner {{ background: #fff8ee; border-left: 3px solid #e0a458;
             color: #7a4f18; padding: 14px 18px; border-radius: 10px;
             font-size: 13.5px; margin-bottom: 22px }}
  .card {{ background: #fff; border-radius: 14px; padding: 26px;
           margin-bottom: 20px; box-shadow: 0 1px 2px rgba(16,35,58,.06),
           0 8px 24px rgba(16,35,58,.05) }}
  .equipos {{ display: grid; grid-template-columns: 1fr 1fr; gap: 30px }}
  @media (max-width: 800px) {{ .equipos {{ grid-template-columns: 1fr }} }}
  .equipo-cab {{ display: flex; align-items: center; gap: 10px;
                 padding: 11px 16px; border-radius: 10px; font-weight: 700;
                 font-size: 16px; margin-bottom: 16px }}
  .equipo-cab .camiseta {{ width: 12px; height: 12px; border-radius: 3px;
                           background: currentColor; opacity: .55 }}
  .kpis {{ display: flex; gap: 10px; flex-wrap: wrap }}
  .kpi {{ flex: 1; min-width: 104px; background: #f7f8fa;
          border: 1px solid #eaedf1; border-radius: 10px; padding: 13px 12px;
          text-align: center }}
  /* Cifras tabulares: si no, comparar el KPI de un equipo con el del otro
     baila porque los dígitos tienen anchos distintos. */
  .kpi .v {{ font-size: 21px; font-weight: 700;
             font-variant-numeric: tabular-nums; letter-spacing: -0.02em }}
  .kpi .l {{ font-size: 11.5px; color: #6b7280; margin-top: 3px;
             line-height: 1.35 }}
  .kpi.future {{ opacity: .75; min-width: 200px; background: #fbfbfc;
                 border-style: dashed }}
  .kpi.future .v {{ color: #6b7280; font-size: 13.5px; font-weight: 600;
                    padding: 3px 0 }}
  .kpi.future .l {{ font-size: 11px }}
  .kpi.future .badge {{ font-size: 9px; background: #e7eaee; color: #6b7280;
                        padding: 2px 7px; border-radius: 10px;
                        text-transform: uppercase; letter-spacing: .6px;
                        font-weight: 700 }}
  .zonas {{ display: flex; height: 38px; border-radius: 9px; overflow: hidden }}
  .zona {{ display: flex; align-items: center; justify-content: center;
           color: #fff; font-size: 12px; font-weight: 700;
           font-variant-numeric: tabular-nums }}
  img {{ width: 100%; border-radius: 10px; display: block }}
  .leyenda-hm {{ font-size: 11.5px; color: #8a919c; margin-top: 7px }}
  .definiciones {{ font-size: 13px; color: #4b5563 }}
  .definiciones li {{ margin-bottom: 7px }}
  .ia-cuerpo p {{ font-size: 15px; margin: 0 0 13px }}
  .ia-placeholder {{ color: #8a919c; font-style: italic; font-size: 13.5px;
                     background: #f7f8fa; border: 1px dashed #dde1e6;
                     border-radius: 10px; padding: 15px 17px }}
  .ia-placeholder code {{ font-style: normal; background: #eaedf1;
                          padding: 1px 6px; border-radius: 4px }}
  .ia-nota {{ font-size: 11.5px; color: #9aa1ac; margin-top: 11px }}
  .pie {{ text-align: center; color: #8a919c; font-size: 12px; margin-top: 30px }}
  @media print {{
    body {{ background: #fff }}
    .card {{ box-shadow: none; border: 1px solid #e5e8ec; break-inside: avoid }}
    .portada {{ -webkit-print-color-adjust: exact; print-color-adjust: exact }}
  }}
</style>
</head>
<body>
<header class="portada">
  <div class="wrap">
    <div class="marca">Tactical Lens · Informe táctico</div>
    <h1>{partido}</h1>
    <div class="meta">{categoria} · tramo {_mmss(t_min)}–{_mmss(t_max)} del vídeo ·
      {colectivas['resumen']['frames_con_deteccion']} frames analizados ·
      {colectivas['resumen']['ids_unicos']} identidades</div>
    <div class="enfrentamiento">{chips_equipos}</div>
  </div>
</header>

<div class="wrap">

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

  <div class="pie">Generado por Tactical Lens · las métricas salen de la
    detección automática de este vídeo, sin intervención manual</div>
</div>
</body>
</html>
"""
    salida_html = Path(salida_html)
    salida_html.parent.mkdir(parents=True, exist_ok=True)
    salida_html.write_text(html, encoding="utf-8")
    logger.info("Informe v2 generado: %s", salida_html)
    return salida_html
