"""Replay táctico 2D: HTML autocontenido con el partido animado sobre el campo.

Genera, a partir del CSV de posiciones del pipeline, una página HTML sin
dependencias externas (canvas + JS inline) con un círculo por identidad
moviéndose en el tiempo. Es a la vez producto (visualización para el
entrenador) y herramienta de DIAGNÓSTICO: puesta al lado del vídeo real
permite ver qué detectamos y qué no.

Decisiones de diseño:
- Los datos van embebidos como JSON compacto por identidad (arrays de
  t/x/y): un partido completo (~90 min, ~1M filas) produce un HTML grande
  pero manejable; un tramo corto, uno ligero. Funciona con cualquier tramo
  porque el reloj usa el tiempo ABSOLUTO del vídeo (tiempo_s del CSV).
- Interpolación visual lineal entre observaciones consecutivas de la misma
  identidad, PERO nunca a través de huecos mayores que `max_hueco_s`: un
  hueco largo se muestra como desaparición (honesto para el diagnóstico:
  si no lo detectamos, no se pinta).
- Colores por etiqueta: A azul, B rojo, porteros en tono oscuro de su
  equipo, 'otro' gris translúcido.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.campo import ANCHO_M, LARGO_M
from src.campo_modelo import MODELO_F11, ModeloCampo

logger = logging.getLogger(__name__)

COLUMNAS_REQUERIDAS = ["frame", "tiempo_s", "id_jugador", "etiqueta", "x_m", "y_m"]

# Colores por etiqueta (relleno, borde)
COLORES = {
    "A": ("#2563eb", "#1d4ed8"),
    "B": ("#dc2626", "#b91c1c"),
    "portero_A": ("#1e3a8a", "#172554"),
    "portero_B": ("#7f1d1d", "#450a0a"),
    "otro": ("rgba(128,128,128,0.45)", "rgba(90,90,90,0.6)"),
    # Staff (línier / cuerpo técnico, detectado fuera del campo por la
    # regla posicional): gris translúcido, no compite visualmente con los
    # jugadores pero se ve que el sistema lo detectó y lo descartó.
    "staff": ("rgba(120,120,120,0.30)", "rgba(80,80,80,0.45)"),
}


def _oscurecer(hex_color: str, factor: float = 0.55) -> str:
    """Versión más oscura de un color, para los porteros de ese equipo."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : (i + 2)], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(c * factor) for c in (r, g, b))


def _borde(hex_color: str) -> str:
    """Borde del círculo: el mismo color un poco más oscuro."""
    return _oscurecer(hex_color, 0.75)


def colores_con_equipos(colores_equipo: dict | None) -> dict:
    """Paleta del replay usando los colores REALES de cada equipo.

    `colores_equipo` viene del meta del processor ({'A': '#e8721c', ...}),
    derivado del prototipo de color del clasificador. Es producto puro: si
    un equipo juega de naranja, su ficha es naranja y el entrenador no
    necesita leyenda. Sin ese dato, se usan los colores por convenio de
    siempre (azul/rojo), que es lo que ocurre con los CSV antiguos.
    """
    paleta = dict(COLORES)
    for equipo in ("A", "B"):
        color = (colores_equipo or {}).get(equipo)
        if not color:
            continue
        paleta[equipo] = (color, _borde(color))
        # El portero viste distinto, pero interesa que se lea de qué
        # equipo es: su color es el del equipo, oscurecido.
        paleta[f"portero_{equipo}"] = (_oscurecer(color), _oscurecer(color, 0.4))
    return paleta


def _leyenda(paleta: dict) -> str:
    """Leyenda del replay con los colores REALMENTE usados.

    Iba con los colores por convenio escritos a mano en la plantilla: al
    pintar los equipos de su color de camiseta, la leyenda decía azul
    mientras las fichas eran naranjas.
    """
    filas = [
        ("A", "Equipo A"),
        ("B", "Equipo B"),
        ("portero_A", "Portero A"),
        ("portero_B", "Portero B"),
        ("otro", "Sin equipo"),
        ("staff", "No jugador"),
    ]
    return "\n      ".join(
        f'<span><i class="punto" style="background:{paleta[clave][0]}"></i>'
        f"{texto}</span>"
        for clave, texto in filas
        if clave in paleta
    )


def _filtrar_creible(
    df: pd.DataFrame, max_edad_interp_s: float, min_vida_s: float
) -> pd.DataFrame:
    """Deja solo lo que un entrenador puede creerse (ver generar_replay).

    1. Fichas EFÍMERAS fuera: una identidad cuyas detecciones reales
       abarcan menos de `min_vida_s` no es un jugador, es un fragmento.
    2. Interpolado VIEJO fuera: una posición inventada a más de
       `max_edad_interp_s` de la detección real más cercana de esa misma
       identidad es ficción; mejor que la ficha desaparezca a que pasee
       sola por el campo.

    Requiere la columna `es_real`; sin ella devuelve el CSV tal cual (los
    CSV antiguos no la tienen y siguen funcionando).
    """
    if "es_real" not in df.columns:
        logger.info("CSV sin columna 'es_real': el replay pinta todo el CSV.")
        return df

    conservar = []
    for _id_jugador, grupo in df.groupby("id_jugador"):
        grupo = grupo.sort_values("tiempo_s")
        tiempos_reales = grupo.loc[grupo["es_real"] == 1, "tiempo_s"].to_numpy()
        if len(tiempos_reales) == 0:
            continue
        if tiempos_reales[-1] - tiempos_reales[0] < min_vida_s:
            continue
        edades = np.min(
            np.abs(grupo["tiempo_s"].to_numpy()[:, None] - tiempos_reales[None, :]),
            axis=1,
        )
        conservar.append(grupo[(grupo["es_real"] == 1) | (edades <= max_edad_interp_s)])

    if not conservar:
        raise ValueError(
            "Tras el filtro de credibilidad no queda ninguna ficha: revisa "
            "max_edad_interp_s / min_vida_s."
        )
    filtrado = pd.concat(conservar)
    logger.info(
        "Filtro de credibilidad: %d → %d posiciones, %d → %d identidades "
        "(interpolado ≤ %.1f s de un real, vida ≥ %.1f s)",
        len(df),
        len(filtrado),
        df["id_jugador"].nunique(),
        filtrado["id_jugador"].nunique(),
        max_edad_interp_s,
        min_vida_s,
    )
    return filtrado


def generar_replay(
    csv_path: str | Path,
    salida_html: str | Path,
    largo: float | None = None,
    ancho: float | None = None,
    max_hueco_s: float = 3.0,
    modelo: "ModeloCampo | None" = None,
    titulo: str = "Replay táctico",
    max_edad_interp_s: float = 0.6,
    min_vida_s: float = 2.0,
    espejar: str | None = None,
    colores_equipo: dict | None = None,
) -> Path:
    """Genera el HTML del replay desde el CSV de posiciones.

    El replay NO pinta todo el CSV: el informe necesita cobertura (agrega
    posiciones en heatmaps y medias) mientras que el replay necesita
    credibilidad (un entrenador que ve una ficha inventada pasear sola
    deja de creerse el resto). Por eso filtra — el mismo CSV sirve a los
    dos consumidores con criterios distintos.

    Args:
        csv_path: CSV con columnas frame, tiempo_s, id_jugador, etiqueta,
            x_m, y_m (equipo es opcional; el color sale de la etiqueta).
            Si trae `es_real`, se aplica el filtro de credibilidad.
        salida_html: dónde escribir el HTML autocontenido.
        largo, ancho: dimensiones del campo en metros (ejes de la
            homografía: x = portería a portería).
        max_hueco_s: hueco máximo (s) que la animación interpola; huecos
            mayores se muestran como desaparición.
        titulo: título de la página.
        max_edad_interp_s: antigüedad máxima de una posición interpolada
            respecto a una detección real de la misma identidad.
        min_vida_s: duración mínima (detecciones reales) para pintar una
            identidad.
        espejar: 'x', 'y' o 'xy' para voltear la vista y que coincida con
            lo que se ve en el vídeo. El replay es cenital y la cámara no:
            según dónde esté, la izquierda de la pantalla puede ser la
            derecha del campo, y comparar replay y vídeo se vuelve un
            ejercicio de gimnasia mental. Solo afecta al DIBUJO; los datos
            y las métricas no se tocan.
        colores_equipo: {'A': '#rrggbb', 'B': '#rrggbb'} del meta del
            processor. Sin ellos, azul y rojo por convenio.
    """
    if espejar not in (None, "", "x", "y", "xy"):
        raise ValueError(f"espejar debe ser 'x', 'y' o 'xy' (recibido {espejar!r})")
    # El MODELO decide qué campo se pinta. Sin él, el F11 de Villaviciosa
    # con las dimensiones de src/campo.py (comportamiento histórico);
    # largo/ancho sueltos siguen aceptándose y ajustan el modelo.
    modelo = modelo or MODELO_F11.con_dimensiones(LARGO_M, ANCHO_M)
    if largo is not None or ancho is not None:
        modelo = modelo.con_dimensiones(
            largo if largo is not None else modelo.largo,
            ancho if ancho is not None else modelo.ancho,
        )
    largo, ancho = modelo.largo, modelo.ancho

    df = pd.read_csv(csv_path)
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltan:
        raise ValueError(
            f"El CSV {csv_path} no tiene las columnas requeridas: {faltan}"
        )
    if len(df) == 0:
        raise ValueError(f"El CSV {csv_path} está vacío.")

    df = _filtrar_creible(df, max_edad_interp_s, min_vida_s)

    identidades = []
    for id_jugador, grupo in df.sort_values("tiempo_s").groupby("id_jugador"):
        etiquetas = grupo["etiqueta"].mode()
        # Opacidad por antigüedad: las posiciones interpoladas se
        # desvanecen conforme se alejan de una detección real, para que la
        # ficha no aparezca y desaparezca de golpe.
        if "es_real" in grupo.columns:
            tiempos_reales = grupo.loc[grupo["es_real"] == 1, "tiempo_s"].to_numpy()
            edades = np.min(
                np.abs(grupo["tiempo_s"].to_numpy()[:, None] - tiempos_reales[None, :]),
                axis=1,
            )
            alfas = [
                round(
                    float(max(0.35, 1.0 - 0.65 * (e / max(max_edad_interp_s, 1e-6)))), 2
                )
                for e in edades
            ]
        else:
            alfas = [1.0] * len(grupo)
        identidades.append(
            {
                "id": int(id_jugador),
                "et": str(etiquetas.iloc[0]) if len(etiquetas) else "otro",
                "t": [round(float(v), 2) for v in grupo["tiempo_s"]],
                "x": [round(float(v), 2) for v in grupo["x_m"]],
                "y": [round(float(v), 2) for v in grupo["y_m"]],
                "a": alfas,
            }
        )

    t_min = float(df["tiempo_s"].min())
    t_max = float(df["tiempo_s"].max())
    paleta = colores_con_equipos(colores_equipo)

    html = (
        _PLANTILLA.replace("__TITULO__", titulo)
        .replace("__DATOS__", json.dumps(identidades, separators=(",", ":")))
        .replace("__COLORES__", json.dumps(paleta, separators=(",", ":")))
        .replace("__LEYENDA__", _leyenda(paleta))
        .replace("__ESPEJO_X__", "true" if espejar and "x" in espejar else "false")
        .replace("__ESPEJO_Y__", "true" if espejar and "y" in espejar else "false")
        .replace("__LARGO__", str(largo))
        .replace("__ANCHO__", str(ancho))
        .replace("__TMIN__", str(t_min))
        .replace("__TMAX__", str(t_max))
        .replace("__MAX_HUECO__", str(max_hueco_s))
        .replace(
            "__CAMPO__",
            json.dumps(modelo.geometria_dibujo(), separators=(",", ":")),
        )
    )

    salida_html = Path(salida_html)
    salida_html.parent.mkdir(parents=True, exist_ok=True)
    salida_html.write_text(html, encoding="utf-8")
    logger.info(
        "Replay generado: %s (%d identidades, t=%.1f–%.1f s)",
        salida_html,
        len(identidades),
        t_min,
        t_max,
    )
    return salida_html


# Plantilla autocontenida. Tokens __X__ sustituidos en generar_replay
# (sin f-strings: las llaves de JS/CSS quedan intactas).
_PLANTILLA = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITULO__</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f5f5f4; color: #1d1d1f; margin: 0; padding: 24px; }
  .wrap { max-width: 1000px; margin: 0 auto; }
  h1 { font-size: 22px; margin: 0 0 2px; }
  .sub { color: #666; font-size: 13px; margin-bottom: 14px; }
  .card { background: white; border-radius: 12px; padding: 18px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
  canvas { width: 100%; height: auto; display: block; border-radius: 8px; }
  .controles { display: flex; align-items: center; gap: 12px; margin-top: 12px;
               flex-wrap: wrap; }
  button { font-size: 15px; padding: 6px 14px; border-radius: 8px; border: 1px solid #ddd;
           background: #f8f8f7; cursor: pointer; }
  button:hover { background: #eee; }
  select { font-size: 13px; padding: 5px 8px; border-radius: 8px; border: 1px solid #ddd; }
  input[type=range] { flex: 1; min-width: 200px; }
  .reloj { font-variant-numeric: tabular-nums; font-weight: 700; font-size: 16px;
           min-width: 120px; }
  .leyenda { display: flex; gap: 14px; font-size: 12.5px; color: #444;
             margin-top: 10px; flex-wrap: wrap; }
  .leyenda span { display: inline-flex; align-items: center; gap: 5px; }
  .punto { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
</style>
</head>
<body>
<div class="wrap">
  <h1>__TITULO__</h1>
  <div class="sub" id="meta"></div>
  <div class="card">
    <canvas id="campo"></canvas>
    <div class="controles">
      <button id="play">▶</button>
      <select id="vel">
        <option value="0.25">0.25×</option><option value="0.5">0.5×</option>
        <option value="1" selected>1×</option><option value="2">2×</option>
        <option value="4">4×</option><option value="8">8×</option>
      </select>
      <input type="range" id="barra" min="0" max="1000" value="0">
      <div class="reloj"><span id="reloj">--:--</span> / <span id="fin">--:--</span></div>
    </div>
    <div class="leyenda">
      __LEYENDA__
    </div>
  </div>
</div>
<script>
const DATOS = __DATOS__;
const COLORES = __COLORES__;
const LARGO = __LARGO__, ANCHO = __ANCHO__;
const CAMPO = __CAMPO__;
const TMIN = __TMIN__, TMAX = __TMAX__;
const MAX_HUECO = __MAX_HUECO__;
const PAD = 5;              // metros de margen alrededor del campo
const ESCALA = 10;          // píxeles por metro (canvas interno)
const RADIO_M = 1.1;        // radio del círculo del jugador, en metros

const canvas = document.getElementById('campo');
const W = (LARGO + 2 * PAD) * ESCALA, H = (ANCHO + 2 * PAD) * ESCALA;
canvas.width = W; canvas.height = H;
const ctx = canvas.getContext('2d');
// Espejado de la VISTA (no de los datos): sirve para que el replay se
// vea con la misma orientación que el vídeo y comparar sea inmediato.
const ESPEJO_X = __ESPEJO_X__, ESPEJO_Y = __ESPEJO_Y__;
const px = (x) => ((ESPEJO_X ? LARGO - x : x) + PAD) * ESCALA;
const py = (y) => ((ESPEJO_Y ? ANCHO - y : y) + PAD) * ESCALA;

// Punteros por identidad para buscar el par de keyframes que envuelve a T
const punteros = DATOS.map(() => 0);

// El campo se dibuja de la GEOMETRÍA del modelo (CAMPO), no de
// constantes: así un partido de F7 sale con su círculo de 6 m y sus
// áreas de 26x12, y no con las medidas de un campo de F11.
function dibujarCampo() {
  ctx.fillStyle = '#2e7d46';
  ctx.fillRect(0, 0, W, H);
  // bandas de césped alternas
  ctx.fillStyle = 'rgba(255,255,255,0.045)';
  for (let i = 0; i < 12; i += 2)
    ctx.fillRect(px(i * LARGO / 12), py(0), LARGO / 12 * ESCALA, ANCHO * ESCALA);
  ctx.strokeStyle = 'rgba(255,255,255,0.92)';
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.lineWidth = 2;
  for (const [[x1, y1], [x2, y2]] of CAMPO.lineas) {
    ctx.beginPath(); ctx.moveTo(px(x1), py(y1)); ctx.lineTo(px(x2), py(y2)); ctx.stroke();
  }
  for (const c of CAMPO.circulos) {
    ctx.beginPath(); ctx.arc(px(c.cx), py(c.cy), c.r * ESCALA, 0, 7); ctx.stroke();
  }
  for (const a of CAMPO.arcos) {
    ctx.beginPath(); ctx.arc(px(a.cx), py(a.cy), a.r * ESCALA, a.desde, a.hasta); ctx.stroke();
  }
  for (const [x, y] of CAMPO.puntos) {
    ctx.beginPath(); ctx.arc(px(x), py(y), 3, 0, 7); ctx.fill();
  }
  for (const p of CAMPO.porterias) {
    ctx.strokeRect(px(p.x), py(p.y), p.ancho * ESCALA, p.alto * ESCALA);
  }
}

function posicionEn(ident, i, T) {
  // Avanza el puntero hasta el último keyframe con t <= T (con rebobinado)
  const ts = ident.t;
  let p = punteros[i];
  if (p >= ts.length || ts[p] > T) p = 0;
  while (p + 1 < ts.length && ts[p + 1] <= T) p++;
  punteros[i] = p;
  if (ts[p] > T) return null;                       // aún no ha aparecido
  const alfa = ident.a ? ident.a[p] : 1;
  if (p === ts.length - 1)
    return ts[p] >= T - 0.25 ? [ident.x[p], ident.y[p], alfa] : null;
  const dt = ts[p + 1] - ts[p];
  if (dt > MAX_HUECO) return null;                  // hueco: no inventamos posición
  const a = dt > 0 ? (T - ts[p]) / dt : 0;
  const alfaSig = ident.a ? ident.a[p + 1] : 1;
  return [ident.x[p] + a * (ident.x[p+1] - ident.x[p]),
          ident.y[p] + a * (ident.y[p+1] - ident.y[p]),
          alfa + a * (alfaSig - alfa)];
}

function dibujar(T) {
  dibujarCampo();
  ctx.font = 'bold ' + (RADIO_M * ESCALA) + 'px -apple-system, sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (let i = 0; i < DATOS.length; i++) {
    const pos = posicionEn(DATOS[i], i, T);
    if (!pos) continue;
    const [relleno, borde] = COLORES[DATOS[i].et] || COLORES['otro'];
    // Transparencia por antigüedad: cuanto más lejos está la posición de
    // una detección real, más se desvanece la ficha (aparecer/desaparecer
    // de golpe se lee como un fallo; el desvanecido se lee como "aquí el
    // sistema ya no lo ve").
    const opacidad = pos.length > 2 ? pos[2] : 1;
    ctx.save();
    ctx.globalAlpha = opacidad;
    ctx.beginPath();
    ctx.arc(px(pos[0]), py(pos[1]), RADIO_M * ESCALA, 0, 7);
    ctx.fillStyle = relleno; ctx.fill();
    ctx.strokeStyle = borde; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = 'rgba(255,255,255,0.92)';
    ctx.fillText(DATOS[i].id, px(pos[0]), py(pos[1]) + 0.5);
    ctx.restore();
  }
}

// ── Reproducción ──
// Driver con setInterval + tiempo real transcurrido (performance.now):
// requestAnimationFrame se congela en pestañas de fondo y el replay debe
// seguir avanzando (típico: replay en una pantalla, vídeo real en otra).
let T = TMIN, temporizador = null, ultimo = null;
const btn = document.getElementById('play');
const vel = document.getElementById('vel');
const barra = document.getElementById('barra');
const reloj = document.getElementById('reloj');

function mmss(t) {
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}
function refrescarUI() {
  reloj.textContent = mmss(T);
  barra.value = Math.round(1000 * (T - TMIN) / Math.max(TMAX - TMIN, 1e-9));
}
function paso() {
  const ahora = performance.now();
  T += (ahora - ultimo) / 1000 * parseFloat(vel.value);
  ultimo = ahora;
  if (T >= TMAX) { T = TMAX; alternar(false); }
  dibujar(T); refrescarUI();
}
function alternar(estado) {
  const activar = estado === undefined ? temporizador === null : estado;
  btn.textContent = activar ? '⏸' : '▶';
  if (activar && temporizador === null) {
    if (T >= TMAX) T = TMIN;   // replay desde el principio si estaba al final
    ultimo = performance.now();
    temporizador = setInterval(paso, 33);
  } else if (!activar && temporizador !== null) {
    clearInterval(temporizador);
    temporizador = null;
  }
}
btn.addEventListener('click', () => alternar());
document.addEventListener('keydown', (e) => {
  if (e.code === 'Space') { e.preventDefault(); alternar(); }
});
barra.addEventListener('input', () => {
  T = TMIN + (TMAX - TMIN) * barra.value / 1000;
  dibujar(T); reloj.textContent = mmss(T);
});

document.getElementById('fin').textContent = mmss(TMAX);
document.getElementById('meta').textContent =
  DATOS.length + ' identidades · tramo ' + mmss(TMIN) + '–' + mmss(TMAX) +
  ' (reloj del vídeo) · generado por Tactical Lens';
dibujar(T); refrescarUI();
</script>
</body>
</html>
"""
