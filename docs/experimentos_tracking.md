# Experimentos de optimización del tracking (Tarea 3)

Cada variante se prueba UNA A UNA contra el banco de evaluación
(`scripts/evaluar_tracking.py`) y solo se conserva si mejora IDF1/HOTA sin
subir los ID switches. Métrica oficial: **umbral por profundidad**
`clip(0.4 + 0.045·my, 1.0, 4.0) m` sobre los 100 frames comunes GT∩caché
del tramo min 5-6.

## Baseline (rama feature/banco-evaluacion, commit 7e3b7d4)

Pipeline: Etapa A conservadora + cosido v2 solo-movimiento
(309 tracklets → 89 identidades; sin caché de colores).

| métrica | oficial (profundidad) | fijo 2.0 m | TrackEval (cajas 2×2 m) |
|---|---|---|---|
| IDF1 | **0.229** | 0.226 | 0.104 |
| ID switches | **130** | 111 | 51 |
| Fragmentaciones | **163** | 148 | 94 |
| Recall/frame | **0.259** | 0.245 | — |
| Precision/frame | **0.730** | 0.692 | — |
| HOTA | — | — | 0.106 (DetA 0.085 / AssA 0.133) |
| MOTA | — | — | −0.176 |

Contexto clave: solo el **34 %** de las detecciones del caché acaba en
tracklets ≥3 frames (mediana 5 frames/tracklet) — el cuello de botella del
baseline es la **cobertura**, no los switches.

---

## Variante 3a — Interpolación de huecos dentro de identidades

**Qué:** relleno lineal de los frames de caché que caen entre dos
observaciones reales consecutivas de la misma identidad (nunca extrapolar),
con hueco máximo configurable. Implementación: `src/tracking/interpolacion.py`,
config `interpolacion:` en `configs/tracking.yaml`, flag `--interpolar` en el
script.

**Medición (métrica oficial, barrido de max_hueco):**

| variante | IDF1 | IDSW | Frag | recall | precision |
|---|---|---|---|---|---|
| sin interpolar (baseline) | 0.229 | 130 | 163 | 0.259 | 0.730 |
| interp. max_hueco=0.5 s | 0.227 | 135 | 166 | 0.264 | 0.716 |
| interp. max_hueco=1.0 s | 0.228 | 138 | 167 | 0.269 | 0.702 |
| interp. max_hueco=2.0 s | 0.231 | 134 | 159 | 0.281 | 0.672 |
| interp. max_hueco=3.0 s | 0.230 | 147 | 165 | 0.303 | 0.633 |
| interp. max_hueco=6.0 s | 0.223 | 205 | 206 | 0.402 | 0.474 |

**Decisión: RECHAZADA como palanca aislada** (config `activa: false`).
Sube mucho el recall (0.26→0.40 con 6 s) pero la precisión cae más deprisa
y los IDSW se disparan: la interpolación propaga los errores de identidades
mal cosidas. El mejor punto (2 s) da +0.002 IDF1 con +4 IDSW → no cumple el
criterio.

**Aprendizaje:** la interpolación no crea identidad, la amplifica. Re-medir
esta variante DESPUÉS de mejorar la calidad del cosido (veto de color,
segunda pasada, cosido global): con identidades más puras, el mismo relleno
debería convertir cobertura en IDF1.

---

## Variante 3b — Rescate de tracklets cortos cosidos

**Qué:** la Etapa A se corre con `min_frames=1` (los tracklets de 1-2
frames entran al cosido) y el filtro de calidad se aplica DESPUÉS, a nivel
de identidad (`filtrar_identidades_cortas`, mínimo 3 frames en total).
Config `rescate_cortos:` en `configs/tracking.yaml`, flag
`--rescatar-cortos`.

**Medición (métrica oficial):**

| variante | nIds | IDF1 | IDSW | Frag | recall | precision |
|---|---|---|---|---|---|---|
| baseline | 89 | 0.229 | 130 | 163 | 0.259 | 0.730 |
| rescate de cortos | 477 | 0.165 | 975 | 257 | **0.720** | 0.709 |

**Decisión: RECHAZADA en su forma actual** (config `activo: false`).

**Aprendizaje (el más importante de la tanda):** las detecciones SÍ están
— con los cortos dentro, el recall por frame sube de 0.26 a **0.72** con
precisión 0.71. Lo que se hunde es la asociación de identidad: el cosido
goloso 1-a-1 no puede encadenar 7.604 fragmentos (477 identidades, IDSW
×7.5). **El techo del sistema no es la detección, es el cosido.** Esta
variante debe re-intentarse cuando el cosido tenga señal de apariencia
(color) y/o formulación global en grafo.

---

## Variante 3c — Segunda pasada de cosido (huecos largos)

**Qué:** cada identidad de la 1ª pasada se fusiona en un super-tracklet
(`fusionar_identidad`, velocidad recalculada por EMA) y se vuelve a coser
con huecos más largos y tolerancia más plana. Config `segunda_pasada:`,
flag `--segunda-pasada`.

**Medición (métrica oficial, barrido de parámetros):**

| variante | nIds | IDF1 | IDSW | Frag | recall | precision |
|---|---|---|---|---|---|---|
| baseline (1 pasada) | 89 | 0.229 | 130 | 163 | 0.259 | 0.730 |
| 2ª pasada mh=12 tb=1.5 tps=1.5 | 81 | 0.229 | 130 | 163 | 0.259 | 0.730 |
| 2ª pasada mh=12 tb=1.5 tps=0.8 | 87 | 0.229 | 130 | 163 | 0.259 | 0.730 |
| 2ª pasada mh=20 tb=1.5 tps=0.8 | 83 | 0.230 | 130 | 163 | 0.259 | 0.730 |
| 2ª pasada mh=12 tb=2.0 tps=2.0 | 75 | 0.230 | 130 | 163 | 0.259 | 0.730 |
| 2ª pasada mh=30 tb=2.0 tps=0.5 | 82 | 0.230 | 130 | 163 | 0.259 | 0.730 |

**Decisión: NEUTRA → queda `activa: false`.** Reduce el número de
identidades (fusiona ruido) pero no reconecta al mismo jugador: IDF1
+0.001-0.002 (ruido), IDSW/recall idénticos. Sin señal de color, extrapolar
la posición a través de huecos de 6-30 s es adivinar; la mecánica queda
implementada para re-medirla con color.

---

## Conclusión de la tanda de cobertura (3a, 3b, 3c)

Las tres palancas fallan por la MISMA causa: la calidad del cosido
solo-movimiento es el cuello de botella que limita todo lo demás.
La evidencia de 3b (recall 0.72 con precisión 0.71 a nivel de frame) acota
el techo alcanzable: las detecciones existen, falta encadenarlas bien.

**Próximos pasos recomendados, en orden:**
1. **Caché de colores** (generar en Colab) → activa el veto de color del
   cosido, la mejora ya validada experimentalmente (89 → ~94 identidades
   más puras).
2. **Cosido global en grafo** (húngaro/min-cost sobre la matriz
   tracklet→tracklet) en vez de goloso — imprescindible para que 3b escale
   a miles de fragmentos.
3. Re-medir 3a, 3b y 3c sobre ese cosido mejorado.

---

## Variante 3d — Veto de color en el cosido goloso

**Qué:** con `cache_colores_min5_60s.pkl` (10.893 features; los recortes
minúsculos no tienen color → esos tracklets van solo por movimiento),
color medio por tracklet (299/309 con color) y veto suave del cosido v2.

**Verificación de fidelidad:** 94 identidades CON color — exactamente la
referencia del notebook (test de regresión añadido).

**Medición (métrica oficial):**

| variante | nIds | IDF1 | IDSW | Frag | recall | precision |
|---|---|---|---|---|---|---|
| goloso sin color (baseline) | 89 | 0.229 | 130 | 163 | 0.259 | 0.730 |
| goloso con color | 94 | 0.224 | 134 | 163 | 0.259 | 0.730 |

**Decisión: NEUTRA-NEGATIVA sobre el goloso.** Consistente con lo medido
en Colab: el color en esta cámara es señal débil (p90 de pares legítimos
= 1.16 con veto en 1.2 → veta ~10 % de uniones correctas). Se mantiene
disponible (`--color/--no-color`) y como término de coste en el global.

---

## Variante 3e — Cosido GLOBAL en grafo (asignación de coste mínimo)

**Qué:** en vez de aceptar candidatos por orden de coste (goloso), se
resuelve el emparejamiento bipartito óptimo tracklet→sucesor
(`min_weight_full_bipartite_matching` sobre matriz dispersa n×2n con
columnas dummy de coste `coste_no_union`). Config `cosido.metodo: global`.
La generación de candidatos pasa a ventana temporal por bisección
(mismo conjunto, O(n·k)) para escalar a miles de fragmentos.

**Medición sobre los 309 tracklets estándar (barrido de coste_no_union):**
el global nunca supera al goloso aquí (mejor: IDF1 0.224, IDSW 128, con
color y cnu=1.4). Con pocos fragmentos largos apenas hay conflictos que
resolver globalmente.

**Medición sobre el RESCATE DE CORTOS (7.604 fragmentos) — donde importa:**

| variante 3b re-medida | nIds | IDF1 | IDSW | Frag | recall | prec | HOTA |
|---|---|---|---|---|---|---|---|
| baseline (goloso, sin rescate) | 89 | 0.229 | 130 | 163 | 0.259 | 0.730 | 0.106 |
| rescate + goloso sin color | 477 | 0.165 | 975 | 257 | 0.720 | 0.709 | 0.113 |
| rescate + goloso con color | 538 | 0.170 | 924 | 261 | 0.716 | 0.708 | — |
| **rescate + GLOBAL sin color** | **114** | **0.225** | 807 | 249 | **0.724** | **0.710** | **0.147** |
| rescate + global con color (cnu=1.4) | 205 | 0.218 | 825 | 252 | 0.722 | 0.709 | 0.146 |

**Decisión: el cosido global DESBLOQUEA el rescate de cortos.**
`rescate + global sin color` logra HOTA 0.147 (**+39 %** sobre baseline),
recall ×2.8 (0.26→0.72) e IDF1 propio prácticamente plano (0.225 vs
0.229). Los IDSW absolutos suben (130→807), pero no son comparables entre
niveles de cobertura tan distintos: con 2.8× más frames emparejados hay
2.8× más ocasiones de switch (tasa por frame emparejado: 0.23→0.50, sube
pero mucho menos que el bruto). El color vuelve a ser neutro-negativo.

---

## Re-medición de 3a y 3c sobre el mejor cosido (rescate + global sin color)

| variante | IDF1 | IDSW | Frag | recall | prec | HOTA |
|---|---|---|---|---|---|---|
| mejor cosido (sin extras) | 0.225 | 807 | 249 | 0.724 | 0.710 | 0.147 |
| +3a interp max_hueco=1 s | 0.183 | 777 | 171 | 0.808 | 0.504 | — |
| +3a interp max_hueco=2 s | 0.162 | 766 | 138 | 0.854 | 0.411 | 0.129 |
| +3a interp max_hueco=6 s | 0.100 | 874 | 73 | 0.934 | 0.214 | 0.097 |
| +3c 2ª pasada (3 combos) | 0.225 | 807 | 249 | 0.724 | 0.710 | — |

**3a: RECHAZADA definitivamente sobre este cosido** — con recall ya en
0.72, interpolar solo añade posiciones fantasma (la precisión se hunde).
**3c: NEUTRA otra vez** (métricas idénticas: fusiona ruido, no reconecta).

---

## Estado tras la tanda (12-jul-2026)

**Candidato a nuevo pipeline oficial:** Etapa A con `min_frames=1` +
cosido `global` (cnu=2.0, sin color) + filtro de identidades <3 frames:

| | baseline oficial | candidato (rescate+global) |
|---|---|---|
| HOTA | 0.106 | **0.147** (+39 %) |
| IDF1 propio | **0.229** | 0.225 (−0.004) |
| recall/frame | 0.259 | **0.724** (×2.8) |
| precision/frame | 0.730 | 0.710 |
| IDSW (tasa por frame emparejado) | 130 (0.23) | 807 (0.50) |

Pendiente de decisión: adoptarlo como oficial (el criterio estricto "sin
subir IDSW" no se cumple en bruto, pero el IDSW bruto no es comparable
entre coberturas; HOTA — que pondera ambas cosas — mejora un 39 %).
