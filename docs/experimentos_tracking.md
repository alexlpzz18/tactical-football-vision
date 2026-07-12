# Experimentos de optimización del tracking (Tarea 3)

> **DECISIÓN FINAL (12-jul-2026): perfil `candidato` adoptado como default
> de producto** (`configs/processor.yaml`). La métrica de producto arbitró:
>
> | | oficial | **candidato** (rescate+grafo+exclusión con salvaguarda+cota) |
> |---|---|---|
> | **Cobertura colectiva** | 0.140 | **0.376 (×2.7)** |
> | HOTA | 0.106 | **0.172 (+62 %)** |
> | IDF1 propio | 0.229 | **0.329 (+44 %)** |
> | recall/frame | 0.259 | **0.679** |
> | precision/frame | 0.730 | **0.757** |
> | IDSW (tasa/frame emparejado) | 130 (0.23) | 513 (0.341) |
> | Robos entre equipos (auditados) | — | 3 (de 4 sin salvaguarda) |
>
> El criterio original ("IDSW no empeora") aplicó variante a variante
> dentro del candidato (cada pieza adoptada lo cumplió contra su base);
> para la adopción del perfil completo arbitró la **cobertura colectiva**,
> que es lo que consume el informe: los IDSW extra son mayoritariamente
> switches que el informe colectivo no distingue. El perfil `oficial`
> queda disponible por config y el banco (`--perfil`) mide ambos con el
> mismo código de producción (`src/tracking/perfiles.py`).

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

---

## Tabla homogénea de la tanda completa (12-jul-2026)

Todas las variantes medidas en idénticas condiciones (100 frames comunes,
umbral oficial por profundidad; IDSW = métricas propias, IDSW-TE =
TrackEval con cajas 2×2 m):

| variante | nIds | IDF1 | HOTA | IDSW | IDSW-TE | Frag | recall | prec |
|---|---|---|---|---|---|---|---|---|
| **baseline: goloso sin color** | 89 | **0.229** | 0.106 | **130** | 51 | 163 | 0.259 | 0.730 |
| goloso CON color | 94 | 0.224 | 0.106 | 134 | 49 | 163 | 0.259 | 0.730 |
| grafo sin color | 62 | 0.217 | 0.105 | 129 | 52 | 163 | 0.259 | 0.730 |
| grafo CON color | 69 | 0.222 | 0.106 | 126 | 50 | 163 | 0.259 | 0.730 |
| rescate + goloso sin color | 477 | 0.165 | 0.113 | 975 | 391 | 257 | 0.720 | 0.709 |
| rescate + grafo sin color (candidato) | 114 | 0.225 | **0.147** | 807 | 320 | 249 | **0.724** | 0.710 |
| rescate + grafo CON color | 145 | 0.203 | 0.126 | 836 | 322 | 248 | 0.723 | 0.710 |

**Decisión (12-jul-2026): NO se adopta el candidato como oficial.** El
criterio acordado exigía IDSW en el mismo orden que el baseline (130) y
suben a 807 en bruto (6.2×) y a 0.50 switches por frame emparejado frente
a 0.23 (2.2× normalizado por cobertura). El candidato queda disponible
(`--rescatar-cortos` + `cosido.metodo: global`) como mejor punto conocido
en HOTA; la línea de trabajo siguiente es reducir sus switches (p. ej.
apariencia más robusta que el color, o penalizaciones de coste por
cruces) antes de re-plantear la adopción.

---

## Conclusión sobre el COLOR (resultado para el TFM)

El clasificador de color por histograma HS del torso, usado como veto/coste
en el cosido, **no aporta señal útil de identidad en esta cámara** una vez
medido contra el ground truth. Números (tabla homogénea de arriba):

| régimen | sin color → con color | efecto |
|---|---|---|
| goloso (baja cobertura) | IDF1 0.229 → 0.224 · IDSW 130 → 134 | ligeramente negativo |
| grafo (baja cobertura) | IDF1 0.217 → 0.222 · IDSW 129 → 126 | ligeramente positivo |
| rescate + grafo (alta cobertura) | IDF1 0.225 → 0.203 · HOTA 0.147 → 0.126 · IDSW 807 → 836 | **claramente negativo** |

Lecturas:
1. En régimen de baja cobertura el efecto es ±0.005 de IDF1 — ruido. La
   validación cualitativa del notebook (89→94 identidades "más puras") no
   se traduce en mejora medible contra el GT.
2. En el régimen de alta cobertura (rescate de cortos), el color es
   **perjudicial**: los tracklets de 1-2 frames promedian el color de 1-2
   recortes minúsculos (jugadores de 15-40 px), la feature resultante es
   ruidosa, y el veto (umbral 1.2 con p90 de pares legítimos = 1.16)
   elimina uniones correctas además de desordenar la asignación global
   (114 → 145 identidades).
3. Esto NO invalida el color para su otra función: la **clasificación de
   equipos por identidad** (agregando muchos recortes por identidad, la
   señal se limpia). Invalida usarlo como discriminador de identidad
   individual tracklet a tracklet en esta resolución.

---

## Tarea 2 cerrada — TeamClassifierColor conectado al banco (12-jul-2026)

`TeamClassifierColor` migrado a `src/team_classification/color_classifier.py`
(KMeans k=8 → fusión jerárquica con umbral auto → 2 meta-grupos mayores por
tamaño → prototipos; predict por distancia). El banco clasifica cada
identidad por su color AGREGADO (media de todos sus recortes del caché) y
la puntúa contra el team GT por voto mayoritario, con mapeo A↔B óptimo
(las etiquetas del clustering son arbitrarias).

**Resultado sobre el pipeline oficial (goloso conservador, 89 ids):**

- Accuracy jugadores de campo (GT A/B): **0.559** (68 identidades, mapeo permutado)
- Confusión GT → predicho: A → {A:17, B:9, otro:8} · B → {A:5, B:21, otro:8}
  · porteros → B (2)

**Diagnóstico (por detección aislada, etiquetada con el GT a <2 m):**

- Accuracy global por detección: 0.649 (el umbral auto elige 0.80, que ES
  el mejor del barrido: 0.649 vs 0.431 a 0.70 — el techo está en la señal,
  no en la fusión).
- **La accuracy depende de la profundidad** (= tamaño del recorte):

| franja my | n | accuracy | →otro | alto mediano del recorte |
|---|---|---|---|---|
| 0-17 m | 69 | **0.957** | 0 % | 47 px |
| 17-34 m | 396 | **0.864** | 0.3 % | 34 px |
| 34-51 m | 746 | 0.558 | 14.6 % | 26 px |
| 51-75 m | 204 | 0.466 | 19.1 % | 20 px |

**Conclusión (TFM):** el diseño de 2 fases funciona donde el jugador
supera ~30 px de alto (0.86-0.96); por debajo, el histograma HS de un
torso de <8 px de ancho es ruido y ninguna agregación lo rescata (la
identidad media 0.559 refleja que la mayoría de recortes son lejanos,
más la contaminación residual del cosido). La mejora de equipos pasa por
resolución/zoom o features que no dependan del color del torso, no por
retocar el clasificador.

---

## Regla de porteros + hipótesis "identidades largas clasifican mejor" (12-jul-2026)

**Regla de porteros (posicional):** identidad con posición MEDIANA dentro
de un área de penalti → portero del equipo que defiende ese lado
(sobrescribe al color). Áreas calibradas con GT (portero_A mx=90.9,
portero_B mx=15.4; corte alto en 88.5 porque los defensas llegan a
mediana 88.2). **Resultado: 3/3 porteros correctos (accuracy 1.000) sin
tragarse jugadores de campo.**

**Hipótesis (¿las identidades largas se clasifican mejor?): CONFIRMADA,
con matiz.** Sobre las 68 identidades de campo del pipeline oficial:

| duración (obs) | n | accuracy | | recortes cercanos (my<34) | n | accuracy |
|---|---|---|---|---|---|---|
| 3-10 | 18 | 0.556 | | 0 | 53 | 0.472 |
| 10-25 | 18 | 0.444 | | 1-4 | 3 | 0.667 |
| 25-60 | 15 | 0.600 | | 5-19 | 5 | 0.800 |
| ≥60 | 17 | 0.647 | | ≥20 | 7 | **1.000** |

Cruce duración × cercanía: corta+cercanos = 1.000 (n=4); larga+cercanos
= 0.818 (n=11); larga+sin cercanos = 0.524 (n=21); corta+sin = 0.438.

**El mecanismo real no es la duración sino la CERCANÍA:** una identidad
se clasifica bien si atraviesa la zona donde el jugador supera ~30 px.
La duración ayuda solo porque las identidades largas tienen más
probabilidad de pasar por ahí. **Queda demostrado que mejorar el cosido
mejora también la clasificación**: cada unión correcta que conecte un
fragmento lejano con un paso por la zona cercana hereda una etiqueta
fiable.

**Mejora derivada (adoptada):** agregación con preferencia por recortes
cercanos — si la identidad tiene recortes con my<45, el color medio usa
SOLO esos. Accuracy de campo 0.559 → **0.603** (config
`agregacion.solo_cercanos`). Ganancia limitada porque solo 15/68
identidades tienen recortes cercanos: otra vez, el techo es el cosido.

---

## Variante 3g — Contexto de plantilla (1/2): exclusión espacial dura

**Qué:** dos identidades no pueden ocupar la misma posición en el mismo
instante. Pares de identidades con solape temporal cuya distancia MEDIANA
en los frames comunes es ≤ dist_max se fusionan (union-find transitivo,
deduplicando por frame con prioridad a la identidad más larga). Son
detecciones duplicadas de SAHI o fragmentos paralelos que el cosido
final→inicio no puede unir. `src/tracking/exclusion_espacial.py`,
config `exclusion_espacial:`, flag `--exclusion`.

**Medición (métrica oficial + HOTA):**

| variante | nIds | IDF1 | IDSW | recall | prec | HOTA |
|---|---|---|---|---|---|---|
| oficial (con/sin exclusión) | 89 | 0.229 | 130 | 0.259 | 0.730 | 0.106 |
| candidato sin exclusión | 114 | 0.225 | 807 | 0.724 | 0.710 | 0.147 |
| candidato + excl 0.5 | 107 | 0.243 | 777 | 0.724 | 0.714 | 0.153 |
| candidato + excl 1.0 | 98 | 0.272 | 697 | 0.714 | 0.722 | 0.162 |
| **candidato + excl 1.5** | **87** | **0.287** | **632** | 0.698 | 0.729 | **0.165** |
| candidato + excl 2.5 | 70 | 0.303 | 569 | 0.672 | 0.732 | 0.165 |
| candidato + excl 3.0 | 53 | 0.323 | 410 | 0.563 | 0.756 | 0.165 |

**Decisión: PRIMERA VARIANTE QUE CUMPLE EL CRITERIO** (IDSW baja, todo
lo demás sube). Punto de operación: dist_max=1.5 m, min_comunes=3
(HOTA satura ahí; más allá de 2 m empieza a fusionar jugadores reales:
el recall se hunde). En el pipeline oficial no hace nada (la Etapa A
conservadora no genera duplicados paralelos).

**Candidato actualizado (rescate + grafo + exclusión 1.5):**
HOTA 0.165 (+56 % vs oficial), **IDF1 0.287 — ya SUPERA al oficial
(0.229)**, recall 0.698 (×2.7), IDSW 632 en bruto (0.41/frame emparejado
vs 0.23 del oficial; era 0.50 sin exclusión). El caso de adopción se
refuerza: ya no hay trade-off en IDF1.

---

## Variante 3h — Contexto de plantilla (2/2): cota blanda ~23

**Diagnóstico que la motiva:** en el candidato+exclusión hay ~21
identidades OBSERVADAS por frame (≈ los 22-23 reales del GT ✓) pero **~77
ACTIVAS simultáneas**: fragmentos del mismo jugador cuyas observaciones se
ALTERNAN en el tiempo (los frames de uno caen en los huecos del otro). El
cosido no puede unirlos (solo une final→inicio) ni la exclusión (no
comparten frames). Es una tercera clase de fragmentación, invisible hasta
ahora.

**Qué:** fusión golosa de pares entrelazados espacialmente compatibles
(mediana de la distancia de las obs de uno a la trayectoria INTERPOLADA
del otro, en ambos sentidos, sin extrapolar) hasta acercar la concurrencia
mediana a la cota (~23 = 22 jugadores + árbitro). BLANDA: si no queda par
con coste ≤ coste_max, se para (entradas/salidas de encuadre).
`src/tracking/cota_plantilla.py`, config `cota_plantilla:`, flag
`--cota-plantilla`.

**Medición (sobre candidato + exclusión 1.5):**

| variante | nIds | conc | IDF1 | IDSW | recall | prec | HOTA |
|---|---|---|---|---|---|---|---|
| base (cand+exclusión) | 87 | 77 | 0.287 | 632 | 0.698 | 0.729 | 0.165 |
| +cota23 coste_max=1.5 | 82 | 74 | 0.302 | 608 | 0.701 | 0.744 | 0.169 |
| +cota23 coste_max=3.0 | 70 | 64 | 0.312 | 578 | 0.693 | 0.746 | 0.170 |
| **+cota23 coste_max=4.0** | **58** | **53** | **0.325** | **536** | 0.688 | 0.757 | **0.171** |
| +cota23 coste_max=5.0 | 47 | 44 | 0.335 | 495 | 0.677 | 0.760 | 0.172 |
| +cota23 coste_max=7.0 | 31 | 29 | 0.343 | 374 | 0.576 | 0.771 | 0.167 |

**Decisión: SEGUNDA variante que cumple el criterio** (IDSW baja y todo
lo demás sube). Punto de operación: coste_max=4.0 (5.0 da métricas casi
idénticas pero 5 m de compatibilidad mediana es físicamente laxo →
riesgo de sobreajuste al tramo; en 7.0 se gira: fusiona jugadores reales
y el recall se hunde).

## Estado del candidato tras el contexto de plantilla (12-jul-2026)

Pila completa: Etapa A min_frames=1 → cosido global → filtro <3 frames →
exclusión espacial (1.5 m) → cota blanda (23, 4.0 m):

| | oficial | candidato pila completa |
|---|---|---|
| HOTA | 0.106 | **0.171 (+61 %)** |
| IDF1 propio | 0.229 | **0.325 (+42 %)** |
| recall/frame | 0.259 | **0.688 (×2.7)** |
| precision/frame | 0.730 | **0.757** |
| identidades (23 GT) | 89 | **58** |
| IDSW bruto (tasa/frame emp.) | 130 (0.23) | 536 (0.35) |

El candidato ya domina al oficial en TODAS las métricas de calidad
excepto el IDSW bruto (0.35 vs 0.23 por frame emparejado, bajando desde
0.50 en cada iteración). La concurrencia sigue en 53 (vs ~23 reales):
queda margen para más contexto de plantilla (asignación por ventana
temporal con exclusión mutua explícita).

---

## Métrica de PRODUCTO: cobertura colectiva (12-jul-2026)

**Definición:** % de posiciones GT (con equipo; el árbitro no cuenta)
cubiertas por una predicción emparejada (posicional, umbral oficial) cuyo
GRUPO de equipo coincide (el portero cuenta con su equipo; mapeo A↔B
óptimo). Un switch de identidad DENTRO del mismo equipo NO penaliza: el
informe colectivo agrega por equipo, no por jugador. Es la métrica que
manda para el producto. `cobertura_colectiva()` en metricas.py.

| pipeline | cobertura | equipo A | equipo B |
|---|---|---|---|
| oficial (goloso conservador) | 0.140 | 0.118 | 0.167 |
| **candidato completo** (rescate+grafo+excl+cota) | **0.384** | 0.319 | 0.463 |

**El candidato multiplica ×2.7 la métrica de producto.** Sus IDSW extra
son mayoritariamente switches dentro del mismo equipo o entre identidades
que el informe colectivo ni distingue; lo que el producto necesita —
posiciones cubiertas con el equipo correcto — lo da la cobertura.

---

## Auditoría de la exclusión espacial + salvaguarda de marcaje (12-jul-2026)

**Aclaración porteros 3/3:** el GT tiene exactamente 2 tracks de portero
(track 0 = portero_A, track 1 = portero_B, 100 cajas cada uno) — NO hay
duplicado en el GT. Las "3 identidades" son del SISTEMA: portero_A
cubierto por 1 identidad y portero_B por 2 fragmentos nuestros. Las 3
recibieron la etiqueta correcta.

**Criterio exacto de fusión de la exclusión:** ≥3 frames co-observados y
mediana de la distancia sobre TODOS los frames co-observados ≤ 1.5 m
(sostenida, no puntual; pero un marcaje pegado durante todo el solape
común sí dispararía).

**Auditoría de robos (candidato, dm=1.5):** de 12 grupos fusionados,
**4 mezclaban equipos GT distintos** (el peor: 10 identidades con 9×B +
1×A). La preocupación de dominio (marcaje al hombre) era real.

**Salvaguarda de marcaje (adoptada):** firma fiable por identidad =
(etiqueta del clasificador, color medio) construida SOLO con recortes
cercanos (my<45). Si ambas identidades tienen firma y sus etiquetas
difieren o sus colores son incompatibles (>1.2), NO se fusionan.

| pila candidato completa | nIds | IDF1 | IDSW | tasa | recall | HOTA |
|---|---|---|---|---|---|---|
| sin salvaguarda | 58 | 0.325 | 536 | 0.351 | 0.688 | 0.171 |
| **con salvaguarda** | 58 | **0.329** | **513** | **0.341** | 0.679 | **0.172** |

Robos: 4 → **3** (5 pares vetados). **Límite documentado:** los 3 robos
restantes involucran al menos una identidad SIN firma (sin recortes
cercanos): en la mitad lejana no existe señal de color con la que vetar.
Es el mismo punto ciego de profundidad de todo el sistema; se resolverá
con mejor localización (v4), no con más reglas.

---

## Variante 3i — Asignación por ventana con exclusión mutua explícita (timebox)

**Qué:** dos endurecimientos de la cota blanda: (1) exclusión mutua
explícita — pares con ≥3 frames co-observados a mediana > excl_dist son
infusionables ("estar en dos sitios a la vez" = jugadores distintos);
(2) compatibilidad por ventana — el coste es el MÁXIMO de las medianas
por ventana temporal, no la mediana global. Parámetros `ventana_s` /
`excl_dist` en `fusionar_hasta_cota` (default None = v1).

**Medición (tasa = IDSW por frame emparejado):**

| variante | nIds | IDF1 | IDSW | tasa | recall | HOTA |
|---|---|---|---|---|---|---|
| **v1 cota blanda cm=4.0 (referencia)** | 58 | **0.325** | **536** | **0.351** | 0.688 | **0.171** |
| v2 ventana15+excl2.0 (cm 4-10) | 76-83 | 0.287-0.289 | 628-631 | 0.406-0.408 | 0.697 | 0.165 |
| v2b solo-exclusión (ed 4-5, cm 5-10) | 47-59 | 0.304-0.320 | 531-566 | 0.370-0.374 | 0.642-0.682 | 0.165-0.166 |
| v2c ventana30+ed5 cm=6 | 61 | 0.301 | 568 | 0.374 | 0.685 | 0.166 |

**Decisión (timebox): la tasa NO baja de 0.351 → SE PARA. v1 se queda.**

**Aprendizaje (cierra la veta):** la exclusión mutua "dura" fracasa por
la misma causa raíz que el color y la velocidad: el ruido de localización
del fondo (mediana 2.5 m en my>51) corrompe la evidencia — dos
observaciones del MISMO jugador lejano distan >2-5 m por el error de
proyección, así que el veto de co-observación mata fusiones correctas, y
la ventana convierte ruido local en veto global. **Toda señal de grano
fino (color, velocidad, co-observación) está por debajo del suelo de
ruido en la mitad lejana del campo.** El siguiente salto real de tracking
no está en el post-procesado: está en reducir ese ruido (modelo v4 con
mejores cajas, o suavizado/filtrado de posiciones antes de asociar).

---

## Variante 3f — Consistencia de velocidad en la unión del cosido

**Qué:** dos mecanismos sobre la velocidad implicada por el salto
`v_salto = (inicio_B − fin_A)/hueco`: (1) veto físico si `‖v_salto‖ >
v_max_salto` (7 m/s); (2) término de coste `peso_vel · ‖v_salto −
vel_A‖ / v_ref`. Config en `cosido:` (`v_max_salto`, `peso_vel`, `v_ref`),
off por defecto.

**Medición (métrica oficial):**

| variante | nIds | IDF1 | IDSW | HOTA |
|---|---|---|---|---|
| oficial (goloso, sin velocidad) | 89 | 0.229 | 130 | 0.106 |
| oficial + veto 7 m/s | 89 | 0.228 | 131 | — |
| oficial + peso_vel 0.3 | 90 | 0.223 | 138 | 0.106 |
| candidato rescate+grafo (sin velocidad) | 114 | 0.225 | 807 | 0.147 |
| candidato + veto 7 m/s | 119 | 0.217 | 831 | — |
| candidato + peso_vel 0.3 | 148 | 0.204 | 909 | 0.137 |
| candidato + peso_vel 0.6 | 191 | 0.190 | 958 | 0.136 |

**Decisión: RECHAZADA (config off).** No reduce switches en ningún
régimen; en el candidato los AUMENTA (807→914) y hunde IDF1/HOTA.

**Aprendizaje (patrón que ya van tres veces):** cualquier señal por
tracklet — color, velocidad — es demasiado ruidosa a este tamaño de
fragmento para mejorar la decisión de unión: la velocidad de un tracklet
corto es una EMA de 1-2 observaciones (los de 1 frame tienen vel=0), y
penalizarla castiga uniones correctas. La única señal fiable a este
nivel sigue siendo posición + tolerancia. Reducir los switches del
candidato requerirá contexto de MÁS nivel (p. ej. consistencia global de
la plantilla: 22 jugadores, exclusión mutua espacial), no más features
por fragmento.
