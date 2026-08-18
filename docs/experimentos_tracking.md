# Experimentos de optimización del tracking (Tarea 3)

> **FIX POST-DECISIÓN (validación en Colab, 12-jul-2026): fit del
> clasificador con recortes cercanos.** En producción, el fit con TODOS
> los recortes colapsó (A=10571/B=204/otro=0 → CSV con cero B): la masa
> de recortes lejanos (histogramas-ruido de jugadores <28 px) emborronaba
> la separación y la fusión automática era estructuralmente frágil (en el
> caché de referencia ya daba equilibrio 0.46). El fit filtrado a my<34
> (la zona donde la señal de color existe) separa dos equipos casi
> perfectos (A=1242/B=1233, equilibrio 0.99) y es robusto al cambio de
> detector. Camino de entrenamiento ÚNICO banco↔producción en
> `pipeline_equipos.entrenar_clasificador` (exige el caché de detecciones
> si el filtro está activo: la divergencia ya no puede existir).
>
> Números oficiales tras el fix: **cobertura colectiva candidato 0.376 →
> 0.456** (A=0.49/B=0.41, antes 0.32/0.44), oficial 0.140 → 0.184;
> accuracy de campo candidato 0.654, porteros 1.000. La decisión de
> perfil no cambia: el candidato amplía su ventaja (0.456 vs 0.184).
>
> **SEGUNDA CAUSA RAÍZ (misma validación): normalización de la feature de
> color.** El fit filtrado seguía colapsando en Colab (A=2554/B=44,
> umbral 0.50) porque `_color_torso` de producción normalizaba el
> histograma por SUMA (L1) mientras el extractor validado del notebook
> normalizaba en **L2** (`cv2.normalize` por defecto). Forense: el 96 %
> de las features del caché de referencia tienen ‖f‖₂ = 1.0 exacto (el
> 4 % restante, ceros de máscara vacía) — imposible con L1. Todos los
> umbrales del sistema (barrido de fusión 0.5-1.3, veto de color 1.2,
> mediana 0.90/p90 1.16 del briefing) viven en escala L2; en L1 las
> distancias se encogen y la fusión colapsa. Reproducido en local: las
> MISMAS features de referencia re-normalizadas a L1 → A=2548/B=44 con
> umbral 0.50, idéntico al log de Colab. Fix: extracción unificada en
> `extraer_color_torso()` (única función, normalización L2, usada por el
> clasificador y el modo full) con tests de regresión bin a bin.

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

## Tanda "ventana" tras el diagnóstico replay-vs-vídeo (17-jul-2026)

**Diagnóstico previo (con GT), corrigiendo los IDs del feedback visual:**
- El "duplicado 51/39" no existe (25 m de mediana); el par sombra real es
  **51/19**: 2.84 m de mediana en 22 frames comunes, zona lejana (my≈54)
  — duplicado de SAHI separado por el ruido de proyección del fondo, por
  encima del dist_max=1.5 de la exclusión.
- Los "delanteros en equipos distintos" son **identidades QUIMERA**:
  id 39 mapea a GT 21 (A, 25 votos) Y GT 20 (B, 18 votos); id 10 va 5/5
  entre un A y un B. Cadenas contaminadas en el cosido secuencial: el
  clasificador les pone UNA etiqueta necesariamente errónea a tramos.
  No es clasificación errónea de identidades estables.
- Métrica nueva de seguimiento: **quimeras** = identidades con ≥10 votos
  GT cuyo track dominante es <60 % de los votos. Candidato actual: 29/47.

**Variantes medidas (cobertura manda; tasa IDSW no empeora):**

| variante | nIds | cobertura | IDF1 | tasa IDSW | quimeras |
|---|---|---|---|---|---|
| candidato actual | 58 | **0.456** | 0.330 | **0.341** | 29/47 |
| 3j exclusión por co-observación (k=3-5, cm 4-8) | 75-87 | 0.457-0.460 | 0.284-0.287 | 0.416-0.422 | 37-38 |
| dedup dos niveles 1.5/2.0-3.0 (my>45) | 56-58 | 0.451-0.458 | 0.328-0.330 | 0.335-0.343 | 26-29 |
| 3k veto de firmas en el cosido | 64 | 0.437 | 0.335 | 0.347 | 25/45 |

**Decisiones (timebox ejecutado): NINGUNA se adopta.**
- **3j RECHAZADA**: la co-observación también está corrompida — los pares
  co-observados son mayoritariamente duplicados de SAHI del fondo
  separados >1.5 m por ruido (el fenómeno 51/19), así que la exclusión
  bloquea fusiones correctas de la cota v1.
- **Dedup dos niveles NEUTRO**: fusionaría al par 51/19 (2.84 ≤ 3.0) pero
  el efecto neto es ±0.005 — fusiona sombras y también algún par real.
- **3k RECHAZADA por cobertura** (0.456→0.437) aunque confirma la
  dirección (quimeras 29→25, IDF1 +0.005): las etiquetas por tracklet
  siguen siendo ruido y vetan cosidos correctos.

**Cierre de la veta (cuarta confirmación, ahora con diagnóstico visual):**
toda señal disponible a nivel de fragmento (color, velocidad, distancia
co-observada, co-observación pura, firmas por tracklet) está por debajo
del suelo de ruido del fondo del campo. Las quimeras del centro se crean
en el cosido secuencial y no hay señal fiable para vetarlas a esta
resolución. El desbloqueo real sigue siendo aguas arriba: modelo v4 /
mejores cajas / suavizado de posiciones antes de asociar. Los mecanismos
3j (excl_coobservacion) y 3k (etiquetas_veto) quedan implementados,
testeados y en off.

**Banco visual (nuevo criterio de entrega):** sin variante adoptada, el
CSV del candidato no cambia → el replay actual sigue siendo el vigente
(outputs/replay.html). No hay comparación que mostrar: eso también es un
resultado del criterio.

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

---

## Salto v4pre — re-medición completa con el modelo nuevo (08-ago-2026)

**Contexto:** modelo v4pre validado en detección (yolov8s, 478 imágenes,
mAP50 ~0.90 vs 0.857 del v3). Cachés nuevos del mismo tramo de validación
(`cache_detecciones_v4pre.pkl`, `cache_colores_v4pre.pkl`; 500 frames,
11.404 detecciones vs 11.350). Banco con `configs/evaluation_v4pre.yaml`.

### Radiografía aguas arriba: qué cambió de verdad en este tramo

| señal (sin tracking) | v3 | v4pre |
|---|---|---|
| recall de detección vs GT (umbral prof.) | 0.724 | 0.728 |
| recall en el fondo (my>45) | 0.598 | 0.607 |
| error de localización mediana, my 51+ | 1.18 m (p90 2.32) | 1.16 m (p90 2.45) |
| dets sin GT por frame | 6.6 | 6.4 |
| tracklets Etapa A (min_frames=3) | 309 (longitud p90 18) | **212 (longitud p90 30)** |
| obs en tracklets ≥30 frames | 49 % | **60 %** |

**Hallazgo honesto:** la subida de mAP50 NO se traduce en este tramo en
más recall ni en menos ruido de localización (el techo diagnosticado del
fondo sigue intacto). Lo que SÍ cambia es la **consistencia temporal**:
las mismas detecciones forman tracklets más largos y menos parpadeantes.
Esa es la palanca que desbloquea la interpolación (ver más abajo).

### Perfiles v3 vs v4pre (banco completo)

| métrica | oficial v3 | oficial v4pre | candidato v3 | candidato v4pre |
|---|---|---|---|---|
| nº identidades | 89 | 82 | 58 | 52 |
| cobertura colectiva | 0.184 | 0.141 | **0.456** | **0.453** |
| IDF1 (propia, umbral prof.) | 0.229 | 0.158 | 0.330 | 0.334 |
| IDSW / tasa | 130 / — | 114 / — | 512 / 0.341 | 508 / 0.339 |
| recall/frame | 0.259 | 0.188 | 0.677 | 0.675 |
| HOTA (TrackEval) | 0.106 | 0.056 | 0.171 | 0.157 |
| quimeras | — | — | 29/47 | 24/41 |
| accuracy equipos campo / porteros | 0.559 / 1.000 | 0.621 / 1.000 | 0.654 / 1.000 | 0.750 / 1.000 |

- El **oficial EMPEORA** con v4pre: con min_frames=3 entran un 27 % menos
  de observaciones (2.840 vs 3.869) — menos tracklets pero más largos; el
  perfil goloso vive de la masa de fragmentos y la pierde.
- El **candidato queda igual** en cobertura (0.453 vs 0.456) con quimeras
  algo mejores (24/41 vs 29/47). El candidato sigue siendo el default.

### Auditoría del fit de equipos (el OJO prioritario: 0 'otro', A/B 2:1)

Causa raíz (no es el bug L1 de julio): con las features v4pre el barrido
auto elige **umbral de fusión 1.00 → exactamente 2 meta-grupos
(A=2054/B=1068, otro=0)**. Sin masa 'otro' en el fit no hay prototipo
'otro', y `predict_color` no puede devolver 'otro' NUNCA → CSV sin
inclasificables y desequilibrio 2:1 (el grupo A absorbe la masa dudosa).
Con v3 la masa 'otro' cercana era pequeña (126) y no mordía; el v4pre
recorta más jugadores cerca (3.122 vs 2.601) y la masa dudosa real es
~805 features.

¿Eligió mal el barrido? Medido con el candidato v4pre:

| fit | etiquetas | cobertura | acc. campo | contaminación B→A |
|---|---|---|---|---|
| auto (u=1.00, sin 'otro') | 32A/16B | **0.453** | 0.750 | 9/22 ids |
| forzado u=0.85 (equipos 1249/1068 + otro 805) | 19A/16B/13otro | 0.414 | 0.636 | 4 (y 5 B→otro) |
| fit 0.85 pero prediciendo sin cajón 'otro' | 32A/16B | 0.455 | 0.750 | 9/22 ids |

- **Por cobertura (criterio de producto) el auto NO eligió mal**: forzar
  el cajón 'otro' pierde 4 pts de cobertura (excluye masa mayoritariamente
  correcta). El empate 0.453/0.455 con prototipos limpios demuestra que la
  absorción no contamina los prototipos.
- **La contaminación B→A es real pero NO es del fit**: las 9 identidades
  B etiquetadas A son 6 quimeras (votos GT mezclados A/B — no existe
  etiqueta correcta) y 3 identidades del fondo con 0 recortes cercanos
  (sin señal de color). Persisten idénticas con cualquier umbral.
- **Decisión: el fit auto se mantiene.** Punto abierto de producto: con
  0 % 'otro' el banner de transparencia del informe pierde sentido en
  este tramo (no hay excluidos); el coste real es que el heatmap de A
  arrastra posiciones de quimeras. Se re-evaluará con el v4 definitivo.

### Re-apertura de variantes aparcadas (candidato v4pre como base)

| variante | nIds | IDF1 | IDSW | tasa | recall | cobertura | quimeras |
|---|---|---|---|---|---|---|---|
| candidato v4pre (base) | 52 | 0.334 | 508 | 0.339 | 0.675 | 0.453 | 24/41 |
| **3a interpolación (max_hueco 6 s)** | 52 | 0.227 | 617 | **0.320** | **0.869** | **0.566** | 36/46 |
| dedup dos niveles my>45 (2.0-3.0 m) | 50-51 | 0.334 | 493-505 | 0.331 | 0.672 | 0.454 | 23/39 |
| 3k veto de firmas en el cosido | 50 | 0.317 | 549 | 0.361 | 0.685 | 0.467 | 27/42 |
| 3j excl. co-observación (k=3-5) | 80-81 | 0.278 | 661 | 0.413 | 0.722 | 0.478 | 36/61 |
| 3a + dedup 3.0 (combo) | 50 | 0.235 | 607 | 0.317 | 0.864 | 0.566 | 34/44 |

**Atribución de 3a (la clave del salto):** la misma interpolación sobre
v3 sube la cobertura menos (0.456→0.532) y **EMPEORA la tasa**
(0.341→0.356 — por eso se rechazó en su día); sobre v4pre la cobertura
sube +0.113 (0.453→0.566) y la tasa **BAJA** (0.339→0.320). El desbloqueo
es del modelo (tracklets más largos → huecos que se rellenan sobre
identidades correctas), no del criterio de medida.

**Decisiones (criterio: cobertura manda + tasa IDSW no empeora):**
- **3a interpolación: ADOPTADA.** +11 pts de cobertura con la tasa
  bajando. Contras documentados: IDF1 posicional baja (0.334→0.227, las
  posiciones interpoladas heredan los errores de identidad) y las
  quimeras suben (24→36) — el CSV gana continuidad, no pureza de
  identidad.
- **dedup dos niveles: NEUTRO otra vez (off).** Y el combo 3a+dedup solo
  añade mejoras marginales (tasa 0.320→0.317, quimeras 36→34): fuera por
  disciplina de una-variante.
- **3k y 3j: RECHAZADAS de nuevo** — suben cobertura (0.467/0.478) pero
  la tasa empeora (0.361/0.413). El ruido de las señales por fragmento
  sigue por encima del umbral útil también con v4pre.

### Adopción y cableado

- `configs/tracking.yaml`: `interpolacion.activa: true` (la aplican banco
  y processor DESPUÉS del perfil; produce trayectorias, no tracklets).
- `src/tracking_data/processor.py`: `exportar_posiciones` acepta
  `trayectorias` y el meta lleva `"interpolacion": true`.
- `configs/processor.yaml`: cachés por defecto → v4pre.
- CSV vigente regenerado: **22.680 posiciones** (9.927 sin interpolar),
  51 identidades, reparto A/B 2.2:1 y 0 'otro' (auditado arriba).
- Banco visual: `outputs/replay_v4pre.html` (contra `outputs/replay.html`
  del v3 para la comparación).

**Aprendizaje del salto:** un mejor detector no mueve las métricas de
tracking por la vía esperada (recall/ruido iguales en este tramo), pero
sí por una lateral: la consistencia temporal. La primera variante de
post-procesado que nunca había pagado (la interpolación, rechazada en julio) paga en
cuanto los fragmentos de debajo son estables. Prioridad siguiente: v4
definitivo y re-medir el ruido de localización del fondo, que sigue
siendo el techo de IDF1/quimeras.

---

## Concurrencia: el número que el replay gritaba y el banco no miraba (08-ago-2026)

**Feedback visual (replay v4pre):** ~44 círculos simultáneos para ~23
personas reales, racimos del mismo equipo montados, y una ficha con
equipo asignado paseando por fuera de la banda superior.

### Métrica nueva de primera clase: concurrencia por frame

`concurrencia_por_frame` (src/evaluation/metricas.py) reporta la mediana,
el p90 y el máximo de identidades SIMULTÁNEAS predichas frente a las del
GT, y sale en la tabla estándar del banco. Motivo: IDF1, HOTA y cobertura
puntúan **por posición emparejada**, así que no penalizan dibujar el
doble de fichas — un pipeline puede mejorar en las tres y ser inservible
en pantalla. Medido en el tramo: GT mediana **22**, pipeline vigente
**47**.

### Diagnóstico del exceso (con números)

Contraste identidad-a-identidad contra el GT (47 de 52 identidades tienen
track GT dominante):

| nº de identidades pred por track GT | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| nº de tracks GT | 8 | 9 | 3 | 3 |

- **(a) fragmentación del mismo jugador: 24 identidades sobrantes** —
  15 tracks GT reciben 2-4 fichas cada uno. Es la causa dominante.
- **(b) entrelazadas: 0 pares** — la interpolación las convirtió en
  simultáneas; antes se alternaban (por eso "parpadeaban" y ahora se ven).
- **(c) staff: 2 identidades sin track GT** — el juez de línea (mediana
  (51.2, −3.3), 500 observaciones) y un artefacto de proyección
  (−125, −313). Las otras 3 sin GT son ruido de corta duración.

**Dato estructural que lo explica todo:** sin interpolar, la concurrencia
es **20** (por debajo del GT). Con `max_hueco=6 s` sube a 47 porque el
**56 % de las posiciones exportadas son interpoladas**, y hay identidades
con solo un 11 % de observaciones reales dibujándose 500 frames. La
interpolación no creó identidades: hizo visibles a la vez las que antes
se turnaban.

### Por qué la distancia sola no vale como criterio de fusión

Los "duplicados montados" NO están a <2 m: los pares co-locados con
solape sostenido tienen mediana **3,5-5 m** (el ruido de proyección del
fondo mete esa distancia entre dos observaciones del mismo jugador).
Validado contra el GT, a esa distancia la geometría no discrimina:

| umbral | pares mismo equipo | MISMO track GT | tracks GT distintos |
|---|---|---|---|
| ≤4 m | 2 | 1 | 1 |
| ≤5 m | 14 | 6 | 8 |
| ≤6 m | 29 | 7 | 22 |

Se probaron dos discriminadores adicionales sobre esos pares y **ninguno
separa** (p50 prácticamente idéntico en duplicados y en jugadores
distintos): paralelismo del movimiento (0,027 vs 0,028) y estabilidad del
offset (cv 0,68 vs 0,36, solapados). Quinta confirmación del patrón: no
hay señal fina fiable a esta resolución.

### Regla de staff por homografía (ADOPTADA)

`src/team_classification/staff.py`: identidad cuya posición **mediana**
cae fuera del rectángulo del campo (tolerancia 2 m, mínimo 5
observaciones) → etiqueta `staff`, fuera de equipos, del informe y en
gris translúcido en el replay. Verificado en el GT: los 23 tracks
anotados tienen su mediana DENTRO del campo, así que la regla no puede
robar jugadores. Marca 1 identidad en el tramo (el línier); el artefacto
(−125,−313) tiene 13 observaciones y también cae. Misma filosofía que la
regla de porteros: geometría barata donde el color no puede llegar —
especialmente ahora que el fit v4pre no produce cajón 'otro'.

### Consolidación de fichas montadas (ADOPTADA, antes de interpolar)

`src/tracking/consolidacion.py`: fusiona identidades del **mismo equipo**
con distancia mediana ≤ `dist_max` sobre ≥ `min_frames_comunes` frames
compartidos (transitiva, deduplicando por frame y conservando la posición
de la ficha con más observaciones REALES). Nunca cruza equipos ni toca
`staff`/`otro`.

**Hallazgo de orden:** consolidar **ANTES** de interpolar es mejor que
después — después se comparan estelas interpoladas entre sí y la fusión
hereda los fantasmas. La composición vive en `perfiles.py::postprocesar`,
compartida banco↔producción.

| variante (v4pre, candidato) | nIds | concurr. | cobertura | IDF1 | tasa IDSW | acc. equipos | quimeras |
|---|---|---|---|---|---|---|---|
| **vigente (interp 6 s)** | 52 | **47** | **0.566** | 0.227 | 0.320 | 0.733 | 36/46 |
| consolidar DESPUÉS d=4 | 50 | 45 | 0.566 | 0.246 | 0.311 | 0.698 | 34/44 |
| consolidar DESPUÉS d=5 | 38 | 33 | 0.519 | 0.292 | 0.257 | 0.750 | 24/33 |
| consolidar ANTES d=4 n=20 | 49 | 44 | 0.569 | 0.239 | 0.317 | 0.791 | 33/44 |
| consolidar ANTES d=5 n=20 | 46 | 41 | 0.564 | 0.245 | 0.318 | 0.775 | 32/41 |
| **consolidar ANTES d=6 n=20 (ADOPTADA)** | 41 | **36** | **0.557** | **0.281** | **0.304** | **0.800** | **27/36** |
| consolidar ANTES d=7 n=20 | 30 | 25 | 0.456 | 0.346 | 0.206 | 0.792 | 16/25 |
| consolidar ANTES d=8 n=20 | 27 | 23 | 0.405 | 0.334 | 0.184 | 0.857 | 15/22 |
| sin interpolar (referencia) | 52 | 20 | 0.453 | 0.334 | 0.339 | 0.750 | 24/41 |

**Decisión: d=6.0, n=20, antes de interpolar.** Concurrencia 47→36,
IDF1 0.227→0.281, tasa de IDSW 0.320→0.304, accuracy de equipos
0.733→0.800, quimeras 36→27. La cobertura baja 0.009 (0.566→0.557):
**es una desviación consciente del criterio literal "cobertura no baja"**,
porque todo lo demás mejora y 0,9 puntos están en el nivel de ruido. A
7,0 m hay un acantilado (cobertura 0.456): ahí ya se fusionan jugadores
distintos.

**Tensión estructural documentada (importante para el TFM):** cobertura y
concurrencia empujan en direcciones opuestas — la cobertura premia tener
MÁS identidades (más oportunidades de cubrir una posición GT), así que
una métrica de producto que solo mire cobertura siempre preferirá dibujar
fantasmas. Por eso la concurrencia entra como métrica de primera clase y
no como nota al pie.

**Lo que NO se hace y por qué:** llevar la concurrencia al rango 23-30 que
pedía el encargo **cuesta ~10 puntos de cobertura** (d=7,0) o recortar la
interpolación a `max_hueco` 1-2 s (concurrencia 27-32, cobertura
0.505-0.531). Es una decisión de producto, no técnica: hay que elegir
entre un replay más limpio y un heatmap más completo. Queda medido y
parametrizado (`consolidacion.dist_max`, `interpolacion.max_hueco`) para
cambiarlo en una línea de config.

### Estado tras la adopción

- CSV vigente: 17.619 posiciones, **40 identidades** (52 → 41 tras
  consolidar, una de ellas staff), concurrencia mediana 36.
- Replay: `outputs/replay_v4pre_consolidado.html` (contra
  `outputs/replay_v4pre.html` sin consolidar y `outputs/replay.html` del v3).
- Banner del informe: separa "sin equipo asignable" de "personal no
  jugador" para no mezclar dos cosas distintas.

---

## Objetivo "replay creíble" (08-ago-2026)

**Objetivo medible fijado por producto** (no receta): concurrencia p50
≤ 26, cero transiciones >8,5 m/s sostenidas, y cobertura del CSV del
informe ≥ 0,55. Presupuesto: 5 variantes; parar si dos consecutivas no
acercan.

### Métrica nueva: transiciones imposibles

`transiciones_imposibles` (src/evaluation/metricas.py) cuenta RACHAS de
velocidad > `v_max` que duran ≥ `duracion_min`, e informa de la velocidad
máxima observada. Un salto de un frame es ruido; media ficha cruzando el
campo medio segundo es lo que destruye la credibilidad.

**Diagnóstico de partida:** 94 rachas y v_max **309 m/s**. Y el dato que
decide el enfoque: las rachas son **las mismas con y sin interpolación**
(962 de los pasos imposibles son entre dos observaciones REALES). No las
crea la interpolación: son cadenas quimera del cosido.

### Variantes medidas

| # | variante | conc p50 | rachas | cob. informe | v_max |
|---|---|---|---|---|---|
| — | punto de partida (consolid + interp 6 s) | 36 | 94 | 0.557 | 309 |
| 1 | **corte por velocidad imposible sostenida** | 35 | **0** | 0.553 | 309 |
| 2 | replay: interpolado ≤ X s de un real (0,6-2 s) | 27-33 | 0 | 0.553 | 309 |
| 3 | **+ replay: fichas efímeras fuera (vida ≥ 2 s)** | **26** | 0 | 0.553 | 309 |
| 4 | **+ corte de saltos instantáneos (60 m/s)** | **24** | **0** | **0.551** | **60** |

**V1 — corte por velocidad (hipótesis (a) de Alex): ADOPTADA.** Parte la
identidad donde teletransporta de forma sostenida. Detalle de
implementación que costó una iteración: cortar *por el medio* de la racha
deja media racha en cada trozo (94 → 27 rachas); hay que **escindir el
tramo entero** (94 → 0). Coste nulo en concurrencia: cortar parte en el
TIEMPO, así que en cada frame sigue viva una sola pieza.

**V2+V3 — el replay no pinta ficción (hipótesis (b) de Alex): ADOPTADAS.**
El informe y el replay tienen necesidades opuestas: el informe agrega
posiciones (quiere cobertura) y el replay muestra jugadores (quiere
credibilidad). Se separan los consumidores, no los datos: el CSV lleva
una columna `es_real` y el replay descarta (a) posiciones interpoladas a
más de 0,6 s de una detección real y (b) identidades cuya vida real es
< 2 s (confeti de fragmentos). La cobertura del informe no se toca por
construcción. Añadido de credibilidad: las fichas se **desvanecen** con
la antigüedad en vez de desaparecer de golpe.

**V4 — saltos instantáneos: ADOPTADA.** La verificación de V3 destapó que
seguía habiendo saltos de hasta 37 m en un frame (v_max 309 m/s) que no
formaban racha y eran lo más visible del replay. Diagnóstico: **ya vienen
del perfil** (443 pasos >20 m/s antes de consolidar; la consolidación
añade hasta 710 pero no los origina), y endurecer la consolidación con un
criterio de p90 no los toca. Se corta en cualquier paso > `v_teleport`.
Umbral 60 m/s = 7,2 m en un frame, 3× el ruido del fondo (p90 2,45 m ≈
20 m/s a dt=0,12 s): por debajo de 40 m/s la cobertura ya cae de 0,55.

### Resultado final (artefactos reales)

| | CSV del informe | replay |
|---|---|---|
| filas / identidades | 16.643 / 243 | 12.191 / 108 |
| concurrencia p50 / p90 | 34 / 36 | **24 / 29** |
| rachas >8,5 m/s sostenidas | **0** | **0** |
| v_max | 60 m/s | 60 m/s |
| cobertura colectiva | **0.551** | — |

**Los tres criterios se cumplen.** Coste honesto: el CSV tiene 243
identidades (fragmentación del corte) y el replay muestra 236 cortes
visuales en 60 s (≈2,5 por ficha y minuto) — el precio de no pintar lo
que no se sabe. La verificación que manda es visual.

**Aprendizaje transferible:** ante un defecto visual, la palanca no
estaba en el sitio esperado ni por Alex ni por el sistema. Las tres
métricas clásicas (IDF1/HOTA/cobertura) eran ciegas a los dos defectos
reales — exceso de fichas y teletransportes — porque puntúan por posición
emparejada. Instrumentar primero el defecto (concurrencia, transiciones)
y solo después buscar la palanca evitó optimizar a ciegas.

---

## Auditoría de escala y sesgo de localización (08-ago-2026)

**Defecto reportado:** en el replay los jugadores se ven MÁS JUNTOS que en
el vídeo. Dos hipótesis del encargo: (1) las medidas del campo (100×64)
son estimadas y podrían estar mal; (2) el detector corta piernas y el pie
proyectado se sesga con la profundidad.

### Hipótesis 2 — sesgo de piernas cortadas: REFUTADA

Error CON SIGNO (pred − GT) por franja, sobre 1.614 detecciones casadas
(el GT está etiquetado con cajas completas, así que el sesgo es medible
limpiamente):

| franja my | n | sesgo my | \|err\| my | alto caja pred / GT |
|---|---|---|---|---|
| 0-17 | 63 | −0.14 m | 0.21 | 1.00 |
| 17-34 | 384 | +0.17 m | 0.55 | 0.95 |
| 34-51 | 935 | +0.21 m | 0.68 | 0.95 |
| 51-99 | 232 | −0.37 m | 0.92 | 1.00 |

**Sesgo global +0,12 m** y cajas predichas al 95-100 % del alto de las del
GT: no hay piernas cortadas sistemáticamente. El sesgo está muy por debajo
del error absoluto de localización, así que **no se implementa corrección**
— habría sido optimizar ruido.

### Hipótesis 1 — escala: CONFIRMADA, con otra causa raíz

Proyectando los clics de calibración con la H de producción y midiendo
marcas cuyo tamaño es REGLAMENTARIO (no depende del campo):

| marca (reglamento) | medido | error |
|---|---|---|
| penalti → línea de fondo (11 m) | 10.85 | −1.4 % |
| área → línea de fondo (16,5 m) | 16.50 | 0.0 % |
| diámetro del círculo (18,30 m) | 19.14 | +4.6 % |
| ancho área izquierda (40,32 m) | 36.18 | **−10.3 %** |
| ancho área derecha (40,32 m) | 32.42 | **−19.6 %** |

- **El eje longitudinal está validado**: las dos marcas en x salen con
  <1,5 % de error, así que el largo de 100 m se sostiene.
- **El transversal es inconsistente consigo mismo**: el círculo (centro de
  la imagen) se pasa un 4,6 % y las áreas (periferia) se quedan cortas un
  10-20 %. Eso comprime las distancias entre jugadores a los lados del
  campo — el defecto que se ve.

**Ningún tamaño de campo lo arregla.** Barrido completo de (largo, ancho)
con validación cruzada (ajustar con el marco, medir las marcas): el error
medio baja del 13,1 % (100×64) al 6,8 % (98×78) pero nunca cuadra círculo
y áreas a la vez, y el óptimo se va a anchos imposibles. La firma —centro
bien, periferia comprimida— es de **distorsión radial residual**: los
coeficientes de lente (k1=−1.5, k2=0.5) también fueron estimados.

**Reajuste conjunto (distorsión + campo): PROBADO Y RECHAZADO.** Optimizar
(a, b, L, W) sobre las marcas reglamentarias mejora 5× su consistencia
(círculo +1,6 %, área izq +3,4 %) y deriva un ancho de ~67 m. Pero falla
la validación independiente: deja al **5,8 % de las posiciones del GT
fuera del campo** (frente al 0,3 % con la calibración actual). Con 13
clics concentrados en la franja central de la imagen el problema está
infradeterminado. **La solución real es recalibrar** con clics repartidos
por todo el encuadre o con un patrón; queda documentado como la deuda
técnica que limita la precisión métrica del sistema.

### Lo que sí se ADOPTA: coherencia del modelo del campo

La auditoría destapó un desajuste que no era de medición sino de unidades:
**la homografía mapea a 100×64 pero el replay, el informe, `collective.py`
y `processor.yaml` dibujaban y analizaban sobre 105×68.** Los jugadores
vivían en el 95 % del largo y el 94 % del ancho del campo dibujado, lo que
(a) los junta visualmente y (b) desplaza los límites de tercios, pasillos
y de la regla de staff.

Corregido con una **única fuente de verdad** (`src/campo.py`) de la que
tiran todos los consumidores, más un test anti-regresión que compara los
defaults del replay, del informe, de `collective.py` y de los dos yaml.
Ocupación del campo dibujado (p1-p99): largo 74 % → **77 %**, ancho 66 %
→ **70 %**. Cobertura colectiva intacta (0.551).

**Aprendizaje:** de las dos hipótesis, una era refutable con una medición
de 20 líneas y la otra escondía un bug de unidades que ninguna de las dos
predecía. Medir primero las dos y solo después tocar código evitó
implementar una corrección de piernas que habría añadido un parámetro
libre para compensar ruido.

---

## Caso nuevo: campo de FÚTBOL 7 (benjamines) — 08-ago-2026

Segundo caso de uso, **aditivo**: cámara normal (sin distorsión) detrás de
portería, campo de F7. Todo lo de Villaviciosa (modelo F11 100×64,
homografía, cachés, GT, banco y configs) queda intacto; el F7 se
selecciona por config y usa sus propios archivos.

### Modelo de campo parametrizable

`src/campo_modelo.py` saca la geometría a datos: un `ModeloCampo`
(nombre, largo, ancho) + unas `MarcasReglamentarias` (área, penalti,
círculo, portería). La distinción importante es **qué es reglamento y qué
es medida**: las marcas interiores las fija la modalidad y no dependen del
tamaño del campo — son justo las que permiten auditar la escala—, mientras
que largo y ancho son estimaciones hasta que se miden.

| | F11 (IFAB) | F7 (Fed. Madrid) |
|---|---|---|
| área (ancho × profundidad) | 40,32 × 16,5 | **26 × 12** |
| penalti | 11 | **9** |
| círculo (radio) | 9,15 | **6** |
| portería | 7,32 | **6** |
| dimensiones | 100 × 64 (calibrado) | 62 × 40 (estimado) |

Los puntos clicables se **generan del modelo** en vez de estar
hardcodeados: centro, círculo (4 puntos), medios de banda, penaltis,
esquinas interiores de área, cortes del área con la línea de fondo,
postes y esquinas — 25 puntos para cualquier campo. `marcar_puntos.py` y
`calcular_homografia.py` aceptan `--campo f7` o `--config`, con los
**defaults del F11 sin cambios** (rutas y comportamiento de siempre).

Los 15 puntos históricos del F11 salen del modelo con la coordenada
idéntica al decimal — hay un test que lo fija contra la lista original y
otro que comprueba que el JSON de clics de Villaviciosa sigue encajando.
El modelo añade 10 puntos opcionales (círculo horizontal, cortes de área
con el fondo, postes) que van justo en la dirección que pedía la auditoría
de ayer: más clics repartidos por el encuadre.

### Auditoría de escala generalizada

`scripts/auditar_escala.py` aplica a cualquier modelo el método que
destapó el problema del F11: proyectar los clics, medir las marcas
reglamentarias y reportar el error **por eje**. Corriéndolo sobre
Villaviciosa reproduce los números de ayer (longitudinal 0,7 % de error
medio, transversal 11,5 %; ancho medido 67,0 m vs 64 asumidos) y ahora
además separa los dos diagnósticos posibles: error concentrado en un eje =
dimensión mal; error que cambia con la posición en la imagen = distorsión
de lente, que cambiar las medidas NO arregla.

### Física de la cámara tras portería (medida, no estimada)

Ensayo con cámara sintética equivalente (3 m de altura, 12 m tras la
portería, campo 62×40):

| distancia a cámara | m/píxel | factor |
|---|---|---|
| 15 m (área cercana) | 0.062 | 1× |
| 32 m (medio campo) | 0.282 | 4,5× |
| 57 m (área lejana) | 0.888 | 14× |
| 71 m (fondo) | 1.373 | **22×** |

**La mitad lejana ocupa el 14 % de los píxeles que ocupa la cercana.** Con
ruido de clic de 2 px, el error de calibración es 0,27 m en la mitad
cercana y 0,94 m en la lejana. Es física de la proyección: el factor va
con el cuadrado de la distancia. Consecuencias registradas en
`data/calibracion_benja/README.md`: saltar los puntos del fondo al marcar,
recalibrar los umbrales por profundidad para este campo y asumir que el
análisis será progresivamente peor con la distancia.

A favor de este caso: **sin distorsión de lente**, así que se evita el
residuo radial que impide cuadrar círculo y áreas en Villaviciosa.

---

## ¿Aporta nuestro tracking sobre un tracker estándar? (10-ago-2026)

La pregunta de fondo del proyecto, respondida con datos. ByteTrack (el de
`supervision`, tal cual viene, sin tocar un parámetro) sobre las MISMAS
detecciones cacheadas del tramo de validación de Villaviciosa (v4pre),
medido con el MISMO banco, y con NUESTRO clasificador de equipos aplicado
sobre SUS identidades. Reproducible: `scripts/comparar_tracker.py`.

Solo cambia quién decide las identidades: las posiciones en metros salen
del mismo caché en todos los casos.

| pipeline | nIds | cob. | conc | IDF1 | IDSW | tasa | recall | quimeras | equipos |
|---|---|---|---|---|---|---|---|---|---|
| ByteTrack tal cual | 237 | 0,516 | 20 | **0,406** | 251 | 0,165 | 0,687 | **5/41** | 0,655 |
| ByteTrack con fps real (8,3) | 262 | 0,511 | 20 | **0,408** | 230 | **0,151** | 0,688 | **4/39** | 0,650 |
| ByteTrack + nuestro post completo | 229 | 0,441 | 19 | 0,393 | 218 | 0,163 | 0,602 | 2/33 | 0,632 |
| ByteTrack + solo interpolación | 237 | 0,533 | **23** | 0,386 | 279 | 0,176 | 0,715 | 6/41 | 0,624 |
| ByteTrack + interpolación + corte | 252 | 0,531 | 23 | 0,363 | 284 | 0,180 | 0,712 | 8/44 | 0,633 |
| Nuestro candidato (sin post) | 52 | 0,453 | 20 | 0,334 | 508 | 0,339 | 0,675 | 24/41 | **0,750** |
| Nuestro pipeline COMPLETO (producción) | 244 | **0,551** | 34 | 0,259 | 534 | 0,301 | **0,800** | 23/43 | 0,661 |
| *referencia GT* | *23* | *1,000* | *22* | | | | | | |

`conc` = mediana de identidades simultáneas · `tasa` = IDSW por posición
emparejada · `quimeras` = identidades con ≥10 votos de GT cuyo GT
dominante no llega al 60 %.

### Veredicto: el estándar gana, y no por poco

Comparando lo que hay que comparar — **ByteTrack + solo interpolación**
frente a **nuestro pipeline completo**:

- cobertura 0,533 vs 0,551 → perdemos **0,018** (un 3 %)
- concurrencia 23 vs 34 → el GT es 22. ByteTrack **acierta el número de
  personas en el campo**; nosotros pintamos un 50 % de fichas de más
- IDF1 0,386 vs 0,259 → **+49 %** a favor del estándar
- tasa de IDSW 0,176 vs 0,301 → **casi la mitad** de saltos de identidad
- quimeras 6/41 vs 23/43 → **4× menos** identidades contaminadas

Es decir: el estándar cede 3 % de cobertura y gana en TODO lo demás,
incluidas las dos cosas que más trabajo nos ha costado arreglar a mano
(la concurrencia del replay y las quimeras).

Y el dato más incómodo: **ByteTrack tal cual, sin nada nuestro, ya cumple
el objetivo de replay creíble** (concurrencia 20 ≤ 26) con 5 quimeras,
cuando a nosotros nos costó cuatro variantes medidas llegar a 24 con 23
quimeras.

### Por qué perdimos: 52 identidades "limpias" no lo eran

Nuestro candidato produce 52 identidades para 23 personas y ByteTrack 237.
Durante meses leímos eso como una ventaja nuestra. Es al revés:

- las 52 nuestras contienen **24 quimeras** (mezclan jugadores distintos)
- las 237 de ByteTrack contienen **5**

ByteTrack fragmenta mucho (p50 = 7 observaciones por identidad, 66 de un
solo par de frames) pero **casi nunca mezcla**. Nosotros hacemos lo
contrario: cosido global + exclusión espacial + cota de plantilla fuerzan
fusiones para llegar a ~23, y esas fusiones forzadas son las quimeras.

La asimetría es la clave: **fragmentar es un error recuperable**
(dos trozos del mismo jugador se pueden coser después); **mezclar no lo
es** (una vez que una identidad contiene a dos jugadores, ninguna métrica
colectiva posterior es fiable). Optimizamos el número de identidades, que
es un proxy, en vez de la pureza, que es lo que importa.

### El post-proceso solo tapa nuestros propios defectos

Aplicado entero a ByteTrack, el post-proceso lo **empeora**: 0,516 → 0,441
de cobertura. La consolidación mismo-equipo y el corte de velocidad están
calibrados para los defectos de nuestro tracker; sobre uno que no los
tiene, solo restan. La única pieza que aporta en ambos casos es la
**interpolación** (+0,017 sobre ByteTrack).

### Lo que SÍ aporta nuestro trabajo (y hay que conservar)

Nada de esto lo da un tracker estándar, y es lo que sostiene el producto:

- **el tracking en METROS** y la homografía: ByteTrack decide identidades
  en píxeles, pero todo lo demás (métricas, umbral por profundidad,
  reglas de portero y staff, escalado por resolución) vive en el campo
- **el banco de evaluación** — es literalmente lo que ha permitido
  descubrir este resultado; sin cobertura colectiva, concurrencia y
  quimeras habríamos seguido celebrando las 52 identidades
- **el clasificador de equipos**, ortogonal al tracker (de hecho es la
  única columna donde ganamos: 0,750 vs 0,655)
- **la interpolación** y el filtro de credibilidad del replay
- las reglas de **portero/staff** por geometría de campo

### Decisión

**Se adopta ByteTrack como base de identidades**, con nuestra
interpolación encima, y se conserva todo lo demás (metros, banco,
equipos, reglas, replay). Pendiente antes de sustituir en producción:
recuperar la cobertura perdida cosiendo fragmentos de ByteTrack **con
criterio de pureza** (no de cupo), que es exactamente el problema que
nuestra Etapa B intentaba resolver — pero partiendo de identidades que no
vienen ya contaminadas.

Nota de honestidad sobre el experimento: el caché es 1 de cada 3 frames
(dt = 0,12 s), lo que penaliza el modelo de movimiento de ByteTrack. Se le
dio su mejor oportunidad pasándole el fps efectivo real (fila 2) y mejora
todavía un poco (IDF1 0,408, tasa 0,151). El resultado no es un artefacto
del submuestreo: es a pesar de él.

---

## Benjamín: umbrales MEDIDOS, no estimados (10-ago-2026)

El 09-ago se activó el escalado por resolución con `jitter_px: 2.0` y
`hueco_min: 1.5` **estimados a ojo**. Aquí se miden sobre el propio caché.

### Dos bugs que la medición destapó

1. **`hueco_min` bajo la sección `cosido`**, que no acepta esa clave:
   `configs/tracking_benja.yaml` **crasheaba en su primer uso real**.
   Blindado con un test que carga todos los `configs/tracking*.yaml`.
2. **El escalado por resolución nunca llegaba a producción**:
   `processor.py` llamaba a `postprocesar()` sin el argumento
   `resolucion`. Los tests unitarios pasaban porque probaban las piezas
   sueltas. Se ve en la tabla: las variantes A, B y C daban resultados
   IDÉNTICOS hasta conectarlo.

### Jitter real de las cajas

Residuo del punto de pie respecto a un ajuste lineal local de 5 frames,
9.910 muestras: **p50 1,06 px · rms 2,4 px · p90 4,0 px**. Es constante
en píxeles a cualquier profundidad (2,2–2,8 px rms en las cuatro zonas):
es ruido del detector, y lo que cambia con la distancia es cuántos metros
vale ese píxel. El ruido del *desplazamiento* entre dos frames es
√2 · 2,4 ≈ **3,5 px**, que es el número que usa el corte.

### Error de interpolar un hueco (p90, metros)

| hueco | x 0-15 m | x 15-30 m | x 30-45 m | x 45-62 m |
|---|---|---|---|---|
| 0,30 s | 0,24 | 0,42 | 0,74 | 1,07 |
| 1,10 s | 0,41 | 0,66 | 1,12 | 1,48 |
| 2,10 s | 0,92 | 1,33 | 1,88 | 2,13 |
| 3,10 s | 1,64 | 2,10 | 2,69 | 2,79 |

Dos lecturas: el 1,07 m del fondo con hueco de 0,3 s **no es error de
interpolación**, es el suelo de ruido de proyección; e `max_hueco: 6.0`,
heredado del F11, inventaba >1,6 m **incluso en la mejor zona**. Topes
nuevos: 2,5 s / 1,2 s (≈1 m de ficción máxima).

### Variantes medidas (tramo min 5-6, sin GT: métricas de estabilidad)

| variante | ids | cortes | conc | % interp | vida p50 | ids <2 s | 31-45 m: n / vida |
|---|---|---|---|---|---|---|---|
| A. sin escalado (baseline) | 89 | 138 | 27 | 48,6 | 7,2 s | 24 | 42 / 8,0 s |
| B. escalado, jitter 2,0 estimado | 81 | 107 | 16 | 17,7 | 8,6 s | 19 | 34 / 13,5 s |
| C. escalado, jitter 3,5 medido | 83 | 124 | 15 | 16,4 | 7,0 s | 26 | 38 / 6,9 s |
| D. C + huecos medidos | 83 | 124 | 15 | 13,2 | 7,0 s | 26 | 38 / 6,9 s |
| **E. corte 3,5 / consol 2,0 + huecos** | **72** | **93** | **16** | **14,7** | **9,5 s** | **16** | **31 / 30,2 s** |
| F. E con consolidación 1,5 | 72 | 93 | 16 | 14,7 | 9,5 s | 16 | 31 / 30,2 s |
| *referencia F7* | *~15* | *0* | *15* | | | | |

### El hallazgo: el jitter medido empeoraba las cosas

C (jitter 3,5 medido) sale **peor** que B (2,0 estimado) en toda métrica
de estabilidad. No es que la medición esté mal: es que `jitter_px`
alimentaba dos umbrales que hacen preguntas distintas.

- El **corte de velocidad** pregunta *"¿este salto cabe dentro del
  ruido?"*. Necesita el ruido real (3,5 px) o trocea identidades sanas.
- La **consolidación** pregunta *"¿estas dos fichas son la misma
  persona?"*. Ensancharla con todo el margen de ruido sobre-fusiona
  jugadores distintos, y el corte trocea después esas quimeras.

Separarlos (`jitter_px_consolidacion`) es la variante E, adoptada: en la
franja 31-45 m las identidades pasan de **38 de 6,9 s a 31 de 30,2 s**
(×4 de vida), los cortes de 138 a 93 y la concurrencia de 27 a 16 —
la plantilla real de F7 es 14 jugadores + árbitro.

Honestidad sobre el alcance: **el benjamín no tiene ground truth**, así
que aquí no hay cobertura ni IDF1, solo métricas de estabilidad y la
plantilla conocida como referencia. Son proxies; el veredicto es visual.

### Entregables

`outputs/detecciones_benja.mp4` (600 frames, 10.904 cajas, 18,2/frame,
codec avc1) y los cuatro replays `replay_benja_{normal,x,y,xy}.html`.

---

## El vídeo de diagnóstico pintaba sobre el fotograma equivocado (10-ago-2026)

Feedback visual: en `outputs/detecciones_benja.mp4` **todas** las cajas
salían desplazadas, poco en el centro y mucho en los bordes, con el
portero cercano a metros de su caja. La hipótesis natural era una
re-proyección (pintar metros devueltos a píxeles con H⁻¹).

**No era eso.** El código ya pintaba los píxeles crudos del caché. El
fallo estaba en el reproductor:

```
cap.set(CAP_PROP_POS_FRAMES, 8991)  →  el vídeo quedó en el frame 9292
```

**301 frames, 10 segundos de desincronía.** `cap.set` no busca el frame
pedido en vídeo comprimido: salta al fotograma clave más cercano. Las
cajas eran correctas; el fotograma debajo, no.

### Por qué el síntoma parecía espacial

Es lo que hizo el diagnóstico difícil: un desfase puramente TEMPORAL se
ve como un desplazamiento que crece hacia los bordes. Con la cámara
detrás de la portería, en 10 s un jugador cercano recorre cientos de
píxeles y uno del fondo apenas unos pocos — exactamente la firma radial
que se atribuyó a la lente o a la homografía.

### Verificación (no de confianza, medida)

Criterio objetivo: una caja bien alineada contiene a un jugador, es
decir, píxeles que se apartan del fondo. Se barrió el desfase midiendo la
energía de primer plano dentro de las cajas:

| desfase | −3 | −1 | **0** | +1 | +3 |
|---|---|---|---|---|---|
| energía (caché vs vídeo) | 24,45 | 26,66 | **27,22** | 27,52 | 26,44 |
| energía (MP4 regenerado) | 33,29 | 40,84 | **41,16** | 38,80 | 32,00 |

El pico limpio en 0 confirma dos cosas: **el caché estaba bien
etiquetado** (el fallo era solo de reproducción) y el MP4 regenerado ya
va sincronizado.

### Arreglo

`posicionar_en_frame()` en `processor.py`: verifica el salto y, si no cayó
donde debía, rebobina y avanza decodificando. No decodifica siempre
porque cuesta 27 s llegar al minuto 5 de este vídeo (minutos en un
partido entero). Ojo con la trampa que costó un test: `cap.set` acepta un
frame inexistente y `cap.get` devuelve tan tranquilo la posición pedida,
así que hay que comprobar además `FRAME_COUNT`.

El mismo `cap.set` estaba en el modo `full` del processor (línea 434), con
lo que el bug era latente en la generación de cachés: aquí el caché salió
bien, pero no había nada que lo garantizara. Corregido en ambos.

Test de regresión: `test_posicionar_deja_el_video_en_el_frame_pedido`,
sobre un vídeo sintético en el que cada frame lleva su número escrito en
su propio brillo.

## Umbrales del benjamín, ya medidos y no estimados (10-ago-2026)

`jitter_px: 2.0` y `hueco_min: 1.5` eran estimaciones mías. Medidos sobre
el caché:

- **Jitter de caja**: 9.910 residuos del punto de apoyo respecto a un
  ajuste lineal local de 5 frames → p50 1,06 px, rms 2,4 px, p90 4,0 px,
  y **prácticamente igual en las cuatro zonas de profundidad** (2,2-2,8
  px). Correcto: el temblor es del detector y en píxeles no depende de la
  distancia; lo que depende es cuántos metros vale ese píxel. Como el
  umbral se aplica a un desplazamiento (diferencia de dos temblores
  independientes), el valor es √2 · 2,4 ≈ **3,5 px**.
- **Interpolación**: error p90 de rellenar un hueco, escondiendo
  observaciones reales. En la zona lejana ya hay 1,07 m de error con
  0,3 s de hueco — eso no es la interpolación, es el ruido de proyección;
  interpolar hasta 1,2 s solo añade ~0,45 m. Y `max_hueco: 6.0` era
  demasiado generoso **incluso cerca**: a 3,1 s ya se inventan 1,64 m.
  → `max_hueco: 2.5`, `hueco_min: 1.2`.

Resultado sobre el tramo: **138 → 93 cortes** de velocidad y 125 → 105
identidades.

### Lo que queda al descubierto (y enlaza con el baseline de ByteTrack)

Los 93 cortes restantes no son ruido de umbral. En el log del tramo:

```
Cota de plantilla:  28 fusiones → 56 identidades
Corte por velocidad: 93 cortes → 55 → 105 identidades
```

Fusionamos 28 pares para acercarnos a la plantilla de F7 y acto seguido
cortamos 93 veces porque esas fusiones son físicamente imposibles. Es el
mismo hallazgo del baseline de ByteTrack visto en otro campo: la cota de
plantilla optimiza el NÚMERO de identidades a costa de su PUREZA, y el
corte de velocidad no hace más que deshacer lo que la cota forzó.

---

# MIGRACIÓN A BYTETRACK (11-ago-2026, rama feature/migracion-bytetrack)

Decisión adoptada tras el banco comparativo: ByteTrack pasa a ser la
etapa de ASOCIACIÓN, y encima van nuestras piezas que ganan o son únicas.
Nada del pipeline vigente se borra: `oficial` y `candidato` siguen
seleccionables y el `candidato` sigue siendo el default hasta que se
decida el cambio de producto.

## Hito 1 — ByteTrack como etapa de asociación (`src/tracking/asociacion_bytetrack.py`)

Los parámetros se declaran en unidades FÍSICAS (segundos), no en frames:
un caché submuestreado 1-de-3 hace que "50 frames de buffer" signifiquen
cosas distintas según la cámara.

El `det_idx` viaja pegado a la detección (`Detections.data`), así que se
recupera exacto al otro lado en vez de reconstruirlo reconociendo la caja
por su geometría, como hacía el script del banco.

### El parámetro que estaba interpretado al revés

`minimum_matching_threshold` **no es un IoU mínimo**: es la distancia
máxima (1 − IoU) admitida al emparejar, así que subirlo lo hace MÁS
permisivo. Medido:

| emparejamiento | nIds | % detecciones usadas | cobertura |
|---|---|---|---|
| 0,50 | 2.125 | 65 % | 0,443 |
| 0,80 (default de la librería) | 262 | 89 % | 0,519 |
| 0,95 | 186 | 92 % | 0,547 |
| **0,98** | **183** | **93 %** | **0,549** |
| 0,995 | 179 | 93 % | 0,549 |

El default de la librería **descartaba el 11 % de nuestras detecciones**.
Tiene sentido físico: nuestros jugadores miden 15-40 px y el IoU entre
frames consecutivos cae mucho más rápido que en los vídeos con los que se
calibró ByteTrack. Este solo cambio ya sube la cobertura de 0,519 a 0,549.

Bajar `umbral_activacion` de 0,25 a 0,10 sube la accuracy de equipos
(0,655 → 0,674) sin coste en el resto.

## Hito 2 — Cosido por PUREZA (`src/tracking/cosido_pureza.py`)

Módulo nuevo, no una variante de `stitcher.py`: aquel cose para llegar a
un número de identidades y este cose para no contaminar ninguna. Tres
diferencias de fondo:

1. **Veto de ambigüedad** — si el segundo mejor candidato compite con el
   mejor, no se cose. Con 22 personas parecidas, un empate significa que
   no sabemos cuál es, y unir a ciegas es cómo se fabrica una quimera.
2. **Mejor mutuo** — A se une a B solo si son la mejor opción el uno del
   otro.
3. **Prohibido el solape temporal** — dos fragmentos que coexisten en un
   frame son dos personas.

Y explícitamente **sin cota de plantilla**, que es la pieza que fabricaba
nuestras quimeras.

### Los dos vetos, justificados con medida

| variante | nIds | cob. | conc | IDF1 | tasa | quimeras | equipos |
|---|---|---|---|---|---|---|---|
| sin veto de ambigüedad | 110 | 0,554 | 24 | 0,439 | 0,146 | **11**/38 | 0,712 |
| sin veto de color | 125 | 0,543 | 24 | 0,436 | 0,147 | **9**/38 | 0,707 |
| **con los dos (adoptado)** | 142 | **0,558** | 23 | 0,443 | 0,147 | **5**/40 | 0,714 |

Quitar cualquiera de los dos casi duplica las quimeras sin ganar
cobertura. No son adornos defensivos: son el motivo de que esto funcione.

### Rechazado: la consolidación

El encargo pedía consolidación "solo si aporta medida". No aporta: sobre
esta base hunde la cobertura de 0,558 a **0,460**. Igual que el resto del
post-proceso, estaba calibrada para tapar defectos de nuestra asociación
y sobre una que no los tiene solo resta. Queda fuera del perfil.

## Hito 3 — Tabla final contra el banco completo

| pipeline | nIds | cob. | conc | IDF1 | tasa IDSW | quimeras | equipos |
|---|---|---|---|---|---|---|---|
| ByteTrack pelado (defaults librería) | 236 | 0,544 | 24 | 0,366 | 0,186 | 6/43 | 0,626 |
| ByteTrack afinado + interpolación | 183 | 0,549 | 22 | 0,449 | 0,141 | 5/38 | 0,728 |
| **perfil `bytetrack` (adoptado)** | 142 | **0,558** | **23** | **0,443** | **0,147** | **5**/40 | 0,714 |
| perfil `candidato` + post (producción hoy) | 244 | 0,551 | 34 | 0,259 | 0,301 | 23/43 | 0,661 |
| *referencia GT* | *23* | *1,000* | *22* | | | | |

**Objetivo del encargo cumplido**: superar 0,533 de cobertura sin degradar
la pureza. Se supera (0,558) y además la pureza MEJORA respecto a
ByteTrack pelado.

Frente al pipeline de producción actual, la base nueva:
- empata en cobertura (+0,007), que era la única columna donde ganábamos
- acierta el número de personas en el campo (23 vs 34, GT 22)
- IDF1 +71 %, tasa de IDSW a menos de la mitad
- **5 quimeras en vez de 23**

## Hito 4 — Integración

Perfil `bytetrack` en `src/tracking/perfiles.py`, seleccionable por
config, con su sección en `configs/tracking.yaml`. No pasa por la Etapa A
ni por el cosido/exclusión/cota del candidato. El banco y producción
comparten el mismo código, como siempre: medido por `correr_perfil`, da
exactamente los mismos números que el banco de la migración.

Tests: `tests/test_migracion_bytetrack.py` (15), centrados en las
propiedades de pureza — incluida la contraprueba de que es el veto de
ambigüedad, y no otra cosa del camino, lo que impide unir ante un empate.

## Hito 5 — El benjamín con la base nueva

El caso F7 es la prueba independiente: cámara distinta, campo distinto,
sin GT etiquetado. Con `perfil: bytetrack` en `configs/processor_benja.yaml`:

| | candidato (antes) | bytetrack (ahora) |
|---|---|---|
| detecciones usadas | 89 % | **96 %** |
| identidades | 125 → 105 | **72** |
| cortes de velocidad | 138 → 93 | **0** (no hay nada que cortar) |
| fichas por frame (p50) | 33 | **15** |

Las **15 fichas por frame son exactamente las personas reales de un F7**
(7+7 jugadores más el árbitro), sin haber puesto ninguna cota: sale de la
asociación, no de un cupo. Es la confirmación más limpia de que el
problema nunca fue el número de identidades sino cómo lo forzábamos.

Los 93 cortes de velocidad desaparecen solos. No es que se hayan
desactivado y ya: es que la cadena que los provocaba —fusionar 28 pares
por cupo y luego trocearlos porque son imposibles— ya no existe.

### El post-proceso reparador, desactivado por medida

`postprocesar` ahora salta consolidación y corte para los perfiles de
`_SOLO_INTERPOLA`. Medido sobre la base ByteTrack en Villaviciosa:

| | cob. | IDF1 | quimeras |
|---|---|---|---|
| solo interpolación | **0,558** | **0,443** | 5 |
| + corte de velocidad | 0,553 | 0,402 | 5 |
| + post-proceso completo | 0,459 | 0,433 | 2 |

El corte pierde IDF1 sin ganar pureza y la consolidación se lleva un 18 %
de la cobertura.

### Límite honesto que queda: la precisión en el fondo, no la identidad

En el CSV del benja aparecen velocidades de hasta 158 m/s. Diagnóstico
por zonas (mediana de velocidad y % de pasos por encima de 8,5 m/s):

| zona x | v mediana | % > 8,5 m/s |
|---|---|---|
| 0-15 m | 0,9 m/s | 1,6 % |
| 15-30 m | 2,1 m/s | 4,9 % |
| 30-45 m | 2,2 m/s | 9,4 % |
| 45-70 m | 2,3 m/s | 13,3 % |

La mediana se mantiene en ~2 m/s a cualquier profundidad —físicamente
correcto para benjamines— y lo que escala con la distancia es la cola.
Es **ruido de proyección**, no quimeras: en el fondo un píxel vale 0,53 m,
así que el temblor de la caja se traduce en decenas de m/s.

Cortar identidades por eso sería el arreglo equivocado: destruiría
identidades buenas para tapar un problema de precisión de medida. El
arreglo correcto es SUAVIZAR las posiciones (que no toca la identidad),
y queda pendiente de medir antes de adoptarse — no se añade sin banco.

---

# REVISIÓN VISUAL DEL BENJA (11-ago-2026)

## 0 — Diagnóstico frame-a-frame (antes de medicar)

Herramienta nueva: `scripts/comparar_instante.py`. Congela un instante y
pone lado a lado el fotograma REAL con las cajas crudas y el punto de
apoyo, y el replay de ESE mismo frame, más una tabla por jugador con su
posición proyectada y la incertidumbre que le corresponde por su zona.

**Veredicto: confirmada la hipótesis del ruido píxel→metro, y NO hay
sesgo sistemático.** La geometría es correcta en los tres instantes (el
reparto de jugadores por el campo casa con el vídeo). Lo que cambia con
la profundidad es la PRECISIÓN:

| instante | cajas | en la mitad lejana | incertidumbre allí (mediana / peor) |
|---|---|---|---|
| 0:11 (dispersos) | 19 | 5 | ±1,85 m / ±1,85 m |
| 0:15 (amontonados) | 19 | 13 | ±0,97 m / ±1,85 m |
| 0:58 (mitad lejana) | 20 | 16 | ±1,26 m / ±1,85 m |

La incertidumbre va de **±0,11 m junto a la cámara a ±1,85 m en el
fondo** (jitter medido de 3,5 px × los metros-por-píxel de cada zona). A
dt=0,1 s eso son ±18 m/s de velocidad aparente: las colas de 158 m/s.
Un jugador puede estar detectado perfectamente y aun así aparecer a dos
metros de donde está.

Dos hallazgos que ninguna métrica agregada había enseñado, y que el
diagnóstico sí: **dos `portero_A` a la vez** en el instante de 0:58, y
público del fondo proyectado a x=71, 80 y 95 m sobre un campo de 62.
Ambos acabaron siendo la misma causa (ver punto 2).

## 1 — `bytetrack` promocionado a default

`configs/processor.yaml` y el del benjamín. `oficial` y `candidato`
siguen seleccionables por config; no se borra nada.

## 2 — Porteros cruzados: la causa era una config imposible de verificar

`equipo_mx_alto` / `equipo_mx_bajo` eran dos claves que había que
"ajustar al partido" a mano. Nadie puede verificar eso mirando un replay,
y en el benjamín estaban al revés.

**Ahora se deducen de los datos** (`deducir_lados`): el equipo que
defiende la portería x=0 tiene a sus jugadores, en promedio, más cerca de
ella. En el benjamín, A 30,0 m vs B 34,1 m sobre 62 → A defiende x=0, y
el portero cercano es `portero_A` (estaba como `portero_B`). Coincide con
la verificación visual.

Costó dos intentos, y los dos fallos son instructivos:

1. **Los porteros no pueden votar.** No porque "voten al equipo
   contrario" —eso lo refutó un test que escribí para demostrarlo— sino
   porque visten distinto y el clasificador de color les asigna equipo
   casi al azar; con su posición extrema, ese voto basura arrastra la
   media. Dejándolos votar: A 42,4 vs B 34,2 (invertido).
2. **El público tampoco.** Esto corre ANTES de la regla de staff, así que
   los espectadores proyectados a x=71-95 seguían contando. Solo votan
   posiciones dentro del campo.

Villaviciosa: **sin cambios** (0,558 / 23 / 0,443 / 0,147 / 5 quimeras).
La deducción coincide con lo que allí estaba ajustado a mano, pero ya no
depende de que alguien lo acierte.

## 4 — Suavizado de posiciones: adoptado

| variante | cob. | IDF1 | tasa IDSW | quimeras | v99 | % > 8,5 m/s |
|---|---|---|---|---|---|---|
| sin suavizado | 0,558 | 0,443 | 0,147 | 5 | 30 m/s | — |
| savgol 0,5 s + resolución | **0,567** | **0,452** | 0,125 | **3** | 16 m/s | — |
| **media 0,5 s + resolución (adoptado)** | 0,550 | 0,447 | **0,120** | 4 | **5 m/s** | **0,1 %** |

Todas las variantes MEJORAN el banco, así que la elección es entre
cobertura y credibilidad visual. Se adopta la media porque el objetivo
del encargo era matar las colas imposibles: deja el 99,9 % de los pasos
por debajo de 8,5 m/s. savgol conserva 0,017 más de cobertura y está a un
cambio de config.

En el benjamín: **p99 de 34,9 → 5,9 m/s y el máximo de 158,7 → 22,9**.

Detalle de diseño: el suavizado NO añade ni quita puntos (la cobertura no
se paga por construcción) y solo toca las posiciones reales; las
interpoladas ya son suaves.

## 5 — Replay: orientación fijada y bug del espejado

`espejar: y` vive ahora en `configs/campo_benja.yaml` — es una propiedad
de la cámara de ese partido, no del comando que uno teclee.

El bug del dibujo eran dos errores de la misma familia: `strokeRect`
dibuja desde una esquina y una anchura, así que al voltear el origen la
esquina pasaba a ser la contraria y las áreas salían hacia el lado
equivocado; y `ctx.arc` conserva el sentido angular, así que el frontal
del área miraba al revés. Arreglado de raíz: los rectángulos se dan por
sus DOS esquinas y los arcos se muestrean en metros, todo pasando por
`px`/`py`, de modo que cualquier volteo sale coherente solo.

## 3 — Clasificación en cruces: PENDIENTE

No se ha abordado. Es el único punto del encargo sin entregar.

---

# PUNTO 3 Y REVISIÓN FINAL (11-ago-2026)

Colocación **aprobada** por revisión visual frame a frame (9321 y 9441
perfectos; en 10728 un jugador en la esquina del área desplazado unos
metros, dentro del ±1,85 m de esa zona). Todo lo que queda es
clasificación y reglas.

## 3a — Excluir del voto los recortes ocluidos: NEGATIVO

`src/team_classification/oclusion.py` marca los recortes cuya caja se
pisa con otra detección para que no voten color.

| IoU umbral | % recortes excluidos | cob. | equipos | quimeras |
|---|---|---|---|---|
| off | 0 % | 0,563 | 0,718 | 4 |
| 0,30 | 5 % | 0,561 | 0,718 | 4 |
| 0,15 | 15 % | 0,561 | 0,718 | 4 |
| 0,10 | 21 % | 0,561 | 0,718 | 4 |
| 0,05 | 27 % | 0,563 | 0,718 | 4 |

**Ni una décima**, ni excluyendo el 27 % de los recortes. La razón, en
retrospectiva evidente: el voto es una MEDIA sobre cientos de recortes
por identidad, y una minoría contaminada ya se promedia sola.

El resultado negativo señaló dónde está el problema de verdad: nuestra
clasificación es POR IDENTIDAD, una etiqueta para toda su vida, así que
"la clasificación falla tras el cruce" solo puede significar que la
identidad cambió de PERSONA en el cruce. No es un problema de voto sino
de asociación. Queda escrito el módulo (en off) y planteado el ataque
correcto —partir la identidad donde el color cambia de forma sostenida,
`src/tracking/corte_color.py`, que en el prototipo encuentra 10 de 48
identidades con cambio real (pureza 0,53 → 0,97 en el mejor caso)— pero
NO está medido contra el banco todavía.

La histéresis post-cruce no aplica a este diseño: no hay reasignación por
frame que estabilizar, porque cada identidad se clasifica una sola vez.

## 3b y 3c — Árbitro y entrenadores por distancia al color: NEGATIVO

Ataque: si un recorte está lejos de AMBOS prototipos, es "otro".

**Umbral absoluto.** Calibrado con el caché del benjamín, usando como
control positivo el staff que la geometría ya identifica:

| grupo | p10 | p50 | p90 |
|---|---|---|---|
| jugadores dentro del campo | 0,283 | 0,336 | 0,656 |
| staff (fuera del campo) | 0,712 | 0,850 | 0,972 |
| etiquetados A/B pero fuera | 0,790 | 0,907 | 0,908 |

Separación casi perfecta, y 0,70 cae justo en el hueco. Llevado a
Villaviciosa, **hunde la accuracy de equipos de 0,718 a 0,482**: cada
partido tiene su propia escala de color y un número en unidades de
histograma no viaja.

**Umbral relativo** a la separación entre prototipos (la forma correcta
de expresarlo, ya implementada):

| umbral | Villaviciosa: equipos | benjamín: no-jugadores captados dentro del campo |
|---|---|---|
| 1,5 · sep | 0,718 (sin efecto) | 0 |
| 1,2 · sep | 0,718 (sin efecto) | 0 |
| 1,0 · sep | 0,682 | 1 |
| 0,9 · sep | — | 2 |

Donde es seguro no hace nada, y donde actúa cuesta más de lo que gana.

**Conclusión, y es el límite que pedías documentar**: el amarillo del
árbitro NO está lejos de los dos prototipos en un histograma HS de un
torso de 15-40 px. Con esta feature, el color no separa a los
no-jugadores. Para el árbitro y los entrenadores que se meten en el campo
hace falta **comportamiento** (pegado a banda, no acompaña el flujo del
juego, velocidad media muy baja), no color. Queda implementado y en off
(`agregacion.dist_max_prototipo: null`).

## 2 — El replay ya no pinta nada fuera del campo

`_filtrar_fuera_del_campo`. En el tramo del benjamín deja de pintar **553
posiciones**. La regla de staff ya las sacaba de las métricas; ahora
tampoco existen en el dibujo, ni en gris.

## 3 (bug de porteros) — Era un artefacto rancio mío

Los tres PNG del diagnóstico se generaron ANTES del fix y con la paleta
de convenio azul/rojo, no con los colores reales. La cadena estaba bien.

Aprovechando la duda, se midió un discriminador mucho más fuerte que la
media de x — el ÚLTIMO HOMBRE ante cada portería, que por geometría
defensiva pertenece al equipo que la defiende:

| señal | veredicto |
|---|---|
| último hombre junto a x=0 | A 96 % / B 4 % |
| último hombre junto a x=62 | A 0 % / B 100 % |
| media de x (la señal débil) | A 30,0 < B 34,1 |

Las tres coinciden: **A defiende x=0**, que es lo que produce
`deducir_lados`. La señal del último hombre es candidata a sustituir a la
media si algún partido futuro sale ambiguo.

---

# PAQUETE AUTÓNOMO (11-ago-2026)

## 1 — Corte por color contra el banco: NEGATIVO

| variante | nIds | cob. | IDF1 | tasa IDSW | quimeras | equipos |
|---|---|---|---|---|---|---|
| **sin corte (adoptado)** | 142 | **0,563** | **0,451** | **0,119** | **4** | 0,718 |
| pureza 0,85 / ganancia 0,08 | 152 | 0,561 | 0,446 | 0,124 | 5 | 0,716 |
| pureza 0,90 / ganancia 0,05 | 154 | 0,559 | 0,446 | 0,125 | 5 | 0,701 |
| pureza 0,80 / ganancia 0,12 | 150 | 0,562 | 0,447 | 0,123 | 5 | 0,720 |
| agresivo 0,95 / 0,02 | 157 | 0,551 | 0,435 | 0,126 | 6 | 0,690 |

Negativo en TODAS las configuraciones, y lo más elocuente: **sube las
quimeras de 4 a 5**, que es exactamente lo contrario de su propósito.

Se investigó por qué, sin encontrar una explicación limpia. La pureza del
voto por identidad tiene mediana 0,93 y 27 de 47 identidades por encima
de 0,90, así que el voto por recorte NO es basura. Y la cola de baja
pureza no se explica por la profundidad (mediana 46,4 m en las de pureza
< 0,75 frente a 45,1 m en las de > 0,90). No se fuerza una narrativa: el
resultado es negativo y el módulo queda escrito y en off.

**Tercera vez que cortar identidades sale mal** (velocidad, post-proceso
completo, y ahora color). El patrón ya es difícil de ignorar: sobre una
asociación que casi no mezcla, cualquier corte destruye más de lo que
arregla.

## 2 — Catálogo absoluto de equipaciones arbitrales: ADOPTADO

El giro que lo hace funcionar: en vez de preguntar "¿está lejos de estos
dos equipos?" (relativo, y por eso no viajaba entre partidos), preguntar
"¿es esto una equipación de árbitro?" (absoluto, y por eso universal).

Validado en los DOS cachés:

| | resultado |
|---|---|
| benjamín | Desactiva solo `naranja_fluor` (el equipo B viste naranja, H=6 S=248) y **encuentra al árbitro**: identidad 31, verde flúor, 493 observaciones, mediana en (31, 24) m — el centro exacto del campo. Salía etiquetado como equipo B. |
| Villaviciosa | **0 identidades marcadas**: no roba ni un jugador. Banco idéntico (0,563 / 0,451 / 0,119 / 4 quimeras). |

La **regla de conflicto no es un adorno**: sin ella, en el benjamín el
arquetipo naranja habría etiquetado a media plantilla de árbitro.

También marca al portero (azul eléctrico), así que el catálogo se aplica
ANTES de la regla de porteros: sobre un portero manda su POSICIÓN, no su
color.

**Limitación documentada**: el arquetipo NEGRO queda declarado pero
inactivo. La feature de color es un histograma HS —`extraer_color_torso`
descarta V a propósito, por robustez a la iluminación— y sin V el negro
es indistinguible del blanco y del gris. Habilitarlo exige añadir un
estadístico de V al caché, o sea regenerarlos en Colab.

## 3 — Fichas más pequeñas

Radio de 1,1 → 0,8 m (−27 %), parametrizable (`radio_ficha_m` en el
config del campo, o `--radio`). El argumento es honesto: la
incertidumbre real de una posición va de ±0,11 m a ±1,85 m según la
zona, así que un círculo grande y nítido promete una exactitud que no
tenemos.

## 4 — Mini-GT de equipos del benjamín: plantilla lista

`data/tracking_benja/mini_gt_equipos.csv` (45 identidades, 32 con ≥25
observaciones) + instrucciones. Solo hay que rellenar `equipo_real`, y
con las 25-30 primeras filas ya sale una medida útil. Permitirá medir la
accuracy de equipos en el caso F7, que hoy solo se puede medir en
Villaviciosa.

## 5 — Partido entero por tramos

- `src/tracking/fusion_caches.py`: fusión con orden temporal garantizado,
  sin duplicados (los tramos se piden CON solape a propósito) y con
  verificación de metadatos — mezclar dt distintos rompería en silencio
  todos los umbrales físicos del sistema.
- `huecos_de_cobertura()`: detecta el tramo que falta. Es la comprobación
  que evita el peor final posible, creer que el partido está entero
  cuando una sesión de Colab murió por el camino.
- `scripts/planificar_tramos.py` + `scripts/fusionar_caches.py`. Para el
  benjamín entero: 5 tramos de 4 min con 5 s de solape, ya escritos en
  `configs/tramos_benja/` con su guía.
- 4 tests sintéticos: orden, duplicados por solape, metadatos
  incompatibles y detección de hueco.

## 6 — Detector de balón: plan y config

`docs/plan_deteccion_balon.md` y `configs/entrenamiento_balon.yaml`. Nada
ejecutado (faltan etiquetas y GPU).

Recomendación razonada: **modelo dedicado**, no una clase más. El
argumento no es de precisión abstracta sino de riesgo: añadir una clase
obliga a reentrenar el detector de jugadores y pone en juego su mAP50
0,90, del que depende todo el sistema, por un objeto con desbalance 1:20,
de 5-12 px y que necesita otra resolución de entrada, otro tile de SAHI y
otro umbral. Reconsiderar si el modelo dedicado no pasa de mAP50 0,5.

La augmentation sigue una sola regla —nada que pueda dejar la imagen sin
el balón dentro— con `mosaic` a 1.0 como la pieza más valiosa (4 balones
por batch en vez de 1) y `mixup`, `copy_paste` y `erasing` a cero.
Comprobación obligatoria antes de entrenar: volcar 50 imágenes aumentadas
y contar cuántas conservan el balón; por debajo del 95 %, la augmentation
está en contra del objetivo.

Evaluación a IoU 0,3 (no 0,5: con 8 px, 2 px de error ya bajan de 0,5 y
esa detección sigue siendo útil), con error en metros y continuidad
temporal. Los frames SIN balón visible son imprescindibles en el GT: sin
ellos no se mide el falso positivo, que es el error que más molesta.

---

# FRENTES DE CLASIFICACIÓN E IDS (11-ago-2026)

## 1 — Barrido de ByteTrack: ADOPTADO, y con un bug de traducción por medio

Antes del barrido apareció un fallo mío en la traducción de parámetros.
La librería NO usa `lost_track_buffer` como número de frames: calcula
`max_time_lost = int(frame_rate / 30 · lost_track_buffer)`. Como yo
además lo multiplicaba por el fps efectivo, **se escalaba dos veces** y
la memoria real era de 4 frames (0,5 s) cuando el config pedía 2 s.
Despejando, para una memoria de T segundos hace falta `T · 30`,
independientemente del frame_rate.

Barrido completo (todas con cosido por pureza + interpolación):

| variante | frag. ByT | nIds | Frag | IDSW | cob. | IDF1 | quimeras |
|---|---|---|---|---|---|---|---|
| buffer 0,5 s (lo que había) | 183 | 142 | 259 | 237 | 0,558 | 0,443 | 5/40 |
| buffer 1,0 s | 167 | 126 | 240 | 258 | 0,574 | 0,437 | 8/37 |
| buffer 2,0 s | 155 | 126 | 230 | 264 | 0,583 | 0,434 | 7/39 |
| buffer 4,0 s | 148 | 122 | 231 | 279 | 0,587 | 0,424 | 7/40 |
| buffer 8,0 s | 138 | 118 | 207 | 302 | 0,608 | 0,414 | 12/37 |
| buffer 1,5 + empar. 0,995 | 151 | 116 | 235 | 251 | **0,586** | **0,448** | 6/38 |
| **buffer 2,0 + empar. 0,995 (adoptado)** | 147 | **115** | **224** | 259 | 0,575 | 0,444 | **5**/37 |
| buffer 3,0 + empar. 0,995 | 143 | 116 | 219 | 284 | 0,592 | 0,425 | 9/40 |
| + min_frames_consecutivos 2 | 103 | 82 | 262 | 210 | 0,542 | 0,463 | 10/36 |
| + min_frames_consecutivos 3 | 79 | 65 | 260 | 175 | 0,524 | 0,465 | 7/34 |

Se adopta **buffer 2,0 s + emparejamiento 0,995**, que es la única que
cumple el criterio de forma estricta: identidades 142 → **115** (−19 %),
Frag 259 → **224**, cobertura +0,017 y, sobre todo, **quimeras en 5 e
IDF1 que no baja** (0,443 → 0,444).

`buffer 1,5` da más cobertura (0,586) e IDF1 (0,448) pero paga una
quimera más; queda anotado como la opción agresiva.

Dos hallazgos secundarios: **`track_activation_threshold` no tiene ningún
efecto** (0,05 y 0,20 dan resultados idénticos) porque el caché ya viene
filtrado a confianza ≥ 0,3; y `min_frames_consecutivos` sube mucho el
IDF1 pero se lleva por delante la cobertura y dispara las quimeras.

## 2 — Cosido, vuelta de tuerca: NEGATIVO

Con la base sana, la configuración actual **ya está en el óptimo**:

| cosido | nIds | Frag | cob. | IDF1 | quimeras |
|---|---|---|---|---|---|
| sin cosido | 147 | 249 | 0,560 | 0,441 | 4/35 |
| **actual (hueco 4, ambig 0,15)** | 115 | **224** | **0,575** | **0,444** | 5/37 |
| hueco 6 | 112 | 223 | 0,579 | 0,436 | 6/35 |
| hueco 8 | 108 | 223 | 0,581 | 0,438 | 7/36 |
| hueco 6 + ambig 0,30 | 124 | 237 | 0,570 | 0,440 | **3**/36 |

Alargar el hueco a secas compra 0,005 de cobertura y cuesta dos quimeras.

Se implementó además la idea concreta de **hueco largo solo con firma de
color exigente** (`max_hueco_con_firma` + `color_estricto`). Resultado:
**cero uniones nuevas** con cualquier combinación probada (hueco 8 y 12,
firma 0,4 / 0,6 / 0,9 / 1,1). No es que el veto de color sea demasiado
estricto —a 1,1 está por encima de la mediana de pares legítimos y sigue
sin unir nada—: sencillamente no quedan pares en esa ventana temporal que
pasen el resto de condiciones. El cosido actual ya los captura.

Queda implementado y desactivado (`max_hueco_con_firma: 0`), listo para
rebarrer si la feature v2 mejora la señal de color.

## 3 — Feature de color v2: implementada, pendiente de cachés

`src/team_classification/feature_v2.py`. Añade dos bloques al vector:

- **canal V del pecho** (16 bins) → desbloquea el arquetipo NEGRO del
  catálogo arbitral;
- **histograma HS del pantalón** (8×8) → muchas equipaciones se
  distinguen mejor abajo, y el pantalón se ocluye menos en los
  amontonamientos, que es donde falla la clasificación.

**La parte delicada es la compatibilidad**, y se resuelve así: los
primeros 256 valores de la v2 son bit a bit la v1 (hay test que lo fija).
Todos los umbrales calibrados en esa escala —fusión del fit 0,5-1,3, veto
de color 1,2, firmas— siguen significando lo mismo. `parte_camiseta_hs()`
acepta las dos longitudes, así que los cachés viejos funcionan sin tocar
nada, y la versión viaja en el meta.

Un test cazó un fallo real de diseño por el camino: el arquetipo negro
tenía rangos comodín de H y S, así que `contiene()` devolvía True para
CUALQUIER color y la regla de conflicto lo desactivaba siempre. Ahora
tiene su propio criterio (brillo bajo Y saturación baja: un granate
también es oscuro, pero no es negro).

Listo para lanzar: `configs/processor_v2color.yaml` y
`configs/processor_benja_v2color.yaml` (copias con `version_color: 2` y
rutas nuevas, sin pisar los cachés actuales) y el plan de re-medición en
`docs/regenerar_caches_color_v2.md`, con un **paso 0 de control**: medir
con el caché v2 usando solo el bloque HS debe dar exactamente
0,575 / 0,444 / 5 quimeras; si no, algo se movió y hay que parar ahí.

## Efecto colateral en el benjamín

Con los parámetros nuevos: 72 → **67 identidades**, y el catálogo arbitral
marca ahora **dos** identidades de verde flúor (204 y 487 recortes) en vez
de una. O el árbitro quedó partido en dos fragmentos, o hay un segundo
colegiado; en ambos casos la etiqueta correcta es la que se les pone
('otro'), pero conviene mirarlo en el vídeo.

---

# HERRAMIENTA VISUAL DE MINI-GT DE EQUIPOS (11-ago-2026)

Sustituye a la plantilla CSV rellenable a mano, que queda borrada. El
problema de aquella no era el formato sino el trabajo que exigía: para
poner UNA etiqueta había que abrir el vídeo, buscar el instante, localizar
al jugador por su posición en metros y volver al CSV. Treinta veces. Una
tarea así no se hace, y un GT que no se rellena no mide nada.

`scripts/etiquetar_equipos_gt.py` genera un HTML autocontenido donde cada
identidad llega ya resuelta: una tira de 8 recortes REALES del jugador,
sacados del vídeo, y seis botones. Un clic (o una tecla del 1 al 6) por
identidad, y el propio HTML descarga el CSV.

## Etiquetado POR RECORTE (rediseño tras el feedback de Alex)

La primera versión pedía UNA etiqueta por identidad. Alex la probó y dio
con el fallo de raíz: *"el #9 a veces es blanco y otras naranja porque los
ids están mal; así no puedo clasificarlo, no son la misma persona"*. Una
identidad quimera no tiene una etiqueta correcta, y forzarla producía un
GT corrupto.

La solución que propuso es mejor que la que yo había intentado (una
tijera para partir la identidad a mano): **etiquetar cada recorte**. Así
la quimera no hay que localizarla — sale sola de los datos en cuanto dos
recortes de la misma identidad discrepan.

Coste de clics: el caso normal sigue siendo un clic gracias al atajo
"todos =", y solo las tiras que cambian piden atención recorte a recorte.
Lo que se gana es doble: un GT de equipos correcto Y un **ground truth de
quimeras verificado a ojo**, que hasta ahora solo se estimaba por
asociación con el GT de Villaviciosa y nunca se había comprobado en el
benjamín.

`scripts/medir_equipos_gt.py` explota las dos cosas: tasa de quimeras con
su composición (`B×4, A×3`), y accuracy ponderada por observaciones donde
las de una quimera solo cuentan **en la proporción de su persona
dominante** — el resto pertenecen a otro jugador.

Dos bugs encontrados por verificar en el navegador en vez de dar el HTML
por bueno: los atajos de teclado salían como cuadrados negros, y un doble
desescapado (`\n` en vez de `\\n` dentro de la plantilla) partía la
cadena y dejaba la página **entera en blanco**. El segundo no lo habría
visto ningún test de Python.

## Dos decisiones de diseño que no son cosméticas

**Las muestras se reparten a lo largo de la vida de la identidad**, no se
cogen las 8 mejores. Dentro de cada tramo sí se elige la caja más grande
—la más cercana a la cámara, la más nítida, que con jugadores de 15-40 px
decide si el color se distingue o no—, pero los tramos cubren de
principio a fin. Así **una quimera se ve de un vistazo**: la tira empieza
naranja y acaba blanca. Si todas las muestras salieran del momento en que
mejor se ve, esa información se perdería. Hay test para las dos cosas.

**Los botones llevan el color REAL de cada equipo**, leído del meta del
processor, para que el botón se parezca a la camiseta que hay que
reconocer y no haya que traducir "A/B" mentalmente.

Un bug encontrado al verificarlo en el navegador en vez de darlo por
bueno: los atajos de teclado salían como cuadrados negros, porque el
`<kbd>` heredaba el color oscuro del botón sobre fondo oscuro.

## Generado para el benjamín

`outputs/etiquetar_equipos_benja.html`: 30 identidades con ≥25
observaciones, 237 recortes, 0,7 MB. Ya se aprecia en la primera pantalla
que la identidad #9 mezcla jugadores de los dos equipos en su tira — es
una de las quimeras, visible sin abrir el vídeo.

## La medición, cuando llegue el CSV

`scripts/medir_equipos_gt.py`. Dos criterios, y el segundo es el que
manda:

- **accuracy por identidad**: cuántas identidades se aciertan;
- **accuracy por OBSERVACIÓN**: ponderada por cuántas posiciones aporta
  cada identidad. Es la que importa, porque fallar una identidad de 600
  posiciones no cuesta lo mismo que fallar una de 30, y lo que llega al
  informe son posiciones.

Además, matriz de confusión y lista de fallos ordenada por peso, para
saber dónde atacar. El árbitro etiquetado como `arbitro` cuenta acierto
si el sistema lo saca del juego como `otro`: el sistema no tiene esa
etiqueta, y sacarlo del juego ES el comportamiento correcto.

---

# MINI-GT DEL BENJAMÍN: PRIMERA MEDIDA Y FIX DE PORTEROS (11-ago-2026)

Primera vez que se mide la clasificación de equipos en el caso F7. Antes
solo se podía en Villaviciosa, que es donde hay GT de tracking.

| métrica | antes del fix | tras el fix |
|---|---|---|
| accuracy por OBSERVACIÓN | 0,860 | **0,867** |
| solo identidades limpias | 0,854 | **0,868** |
| solo jugadores de campo | 0,750 (15/20) | **0,800 (16/20)** |
| accuracy por identidad | 0,733 (22/30) | **0,767 (23/30)** |

El 0,867 es MEJOR que el 0,714 de Villaviciosa, y tiene sentido: naranja
contra blanco separa mejor que las dos equipaciones de allí.

## Cuidado con el 53 % de quimeras: era mi criterio, no el dato

El script marcaba quimera en cuanto UN recorte discrepaba, que no es
comparable con el criterio del banco (dominante < 60 %). Desglosado:

| pureza | ids | qué es |
|---|---|---|
| 1,00 | 14 | limpias |
| 0,75-0,88 | 4 | uno o dos recortes discrepan |
| 0,62-0,75 | 9 | mezcla clara |
| **< 0,60** | **3** | quimera según el criterio del banco |

Con el criterio del banco son **3 de 30**, comparable a las 5/40 de
Villaviciosa. El número sólido y más duro es otro:

> **El 15 % de las observaciones no pertenecen a la identidad que las
> tiene** (1.351 de 8.765).

Las 4 tiras de pureza 0,88 se mandan a revisión humana
(`--solo-ids` + `--gt-previo` resaltan el recorte discrepante sobre las
etiquetas ya puestas): a simple vista, la #8 repite el mismo portero en
los 8 recortes —error de etiquetado— y la #6 empieza con un jugador
naranja y sigue con blancos —quimera real—, pero lo decide Alex.

## Fix: EXCLUSIVIDAD de porteros

La regla convertía en portero a CUALQUIER identidad cuya mediana cayera
en un área. En el benjamín reetiquetaba a **10 identidades**: defensas
que viven ahí, delanteros que presionan, y el id 55 (jugador de campo del
equipo B) que Alex detectó.

Ahora el área tiene dueño único y lo decide la **permanencia**:

```
Identidad 55 vive en el área alto (78 obs) pero NO es portero:
la 8 lleva 593. Se queda con su etiqueta de color
```

De 10 porteros a **2**, que es exactamente lo que hay en un F7. El id 55
sigue fallando, pero ya por otro motivo (el color le da A y es B): el
fallo se ha movido de la regla geométrica al clasificador, que es donde
se puede atacar con la feature v2.

---

# BARRIDO COMBINADO DE LA ASOCIACIÓN (12-ago-2026)

El barrido anterior movía un parámetro cada vez. Este explora la rejilla
conjunta: buffer × emparejamiento × cosido (30 combinaciones), porque un
buffer más largo fragmenta menos y deja al cosido menos trabajo — el
óptimo de uno puede no serlo con el otro.

**Resultado: ninguna de las 30 supera el criterio estricto** (cobertura
sube, quimeras ≤5, IDF1 no baja, concurrencia ≈23). El punto adoptado
sigue siendo el mejor compromiso.

Referencia adoptada: buffer 2,0 · empar 0,995 · hueco 4 / ambig 0,15 →
115 ids, cob **0,575**, conc **23**, IDF1 **0,444**, tasa 0,147, 5 quimeras.

Lo más cerca que se estuvo, en dos direcciones opuestas:

| combinación | cob. | conc | IDF1 | quimeras | por qué no |
|---|---|---|---|---|---|
| buffer 3,0 · 0,995 · hueco 4/0,15 | **0,579** | 25 | 0,425 | 9 | +0,004 de cobertura a cambio de casi doblar las quimeras |
| buffer 1,5 · 0,995 · hueco 6/0,30 | 0,565 | 24 | 0,446 | **3** | mejor pureza que la referencia, pero −0,010 de cobertura |

La lectura: hay un **frente de Pareto claro entre cobertura y pureza**, y
el punto adoptado está sobre él. Todo lo que sube la cobertura paga en
quimeras y todo lo que baja las quimeras paga en cobertura — no hay
combinación que gane en las dos, ni siquiera explorando interacciones.

Un patrón nuevo que el barrido de uno-en-uno no enseñaba: **la
concurrencia sube a 24-25 en TODA la rejilla salvo en el punto adoptado**
(23, que es el valor del GT). Es decir, el punto actual no solo está en el
frente, sino que es el único que además clava el número de personas en el
campo. Eso refuerza mantenerlo.

Reproducible: `scripts/barrido_asociacion.py` (acepta `--config` para
repetirlo con los cachés v2color cuando estén).

---

# RE-MEDICIÓN v2color (12-ago-2026)

## Villaviciosa: el paso 0 FALLA, y por un fallo mío de config

| | nIds | cob. | conc | IDF1 | quimeras | equipos |
|---|---|---|---|---|---|---|
| v1 (referencia) | 115 | **0,559** | 25 | **0,453** | **5**/38 | **0,671** |
| v2color | 122 | 0,488 | 25 | 0,360 | 10/46 | 0,580 |

No es la feature: **es otro detector**. `configs/processor.yaml` apunta a
`best_v3.pt`, y yo generé `processor_v2color.yaml` copiándolo sin
comprobar el modelo. La guía de Colab enlazaba `best_v4pre.pt`, pero el
config pedía el viejo, así que el caché v2color de Villaviciosa está
hecho con un detector de mAP50 0,857 en vez de 0,90.

La comprobación que lo demuestra, comparando caja a caja en los 500
frames comunes: de ~4.456 cajas del v1, **3.879 no tienen pareja** en el
v2color, y de las 577 que sí la tienen, 360 traen un bloque HS distinto
(distancia mediana 0,238, máxima 1,287 — sobre un veto de 1,2). Con la
misma feature y el mismo modelo, esas cifras tendrían que ser 0.

**El caché v2color de Villaviciosa no sirve** para comparar. Hay que
regenerarlo con `best_v4pre.pt` y con el tramo del banco, no el vídeo
entero.

## Benjamín: el paso 0 SÍ pasa

Su config sí usa `best_v4pre.pt`, y se nota: **detecciones idénticas**
(10.904 en las dos versiones) y 67 identidades en ambas. La única
diferencia es una identidad que pasa de A a B.

Contra el mini-GT, los dos son **exactamente iguales**:

| | v1 | v2color |
|---|---|---|
| accuracy por observación | 0,867 | 0,867 |
| solo identidades limpias | 0,868 | 0,868 |
| solo jugadores de campo | 0,800 | 0,800 |

**El id 4 NO se endereza** (570 obs, sigue A→B). Tampoco los demás
fallos, salvo que aparece uno nuevo pequeño (id 11, 38 obs).

## Arquetipo NEGRO: activo y funcionando, pero no encuentra a nadie

El canal V ya llega (el log imprime `V=131`, `V=49`, `V=124`), así que el
arquetipo se activa solo, como estaba diseñado. En este tramo no marca a
nadie: la identidad 24 tiene V=49 —oscura— pero S=248, así que es azul
eléctrico y no negro. El criterio (V<60 **y** S<90) hace justo lo que
debe: no confundir un azul oscuro saturado con una equipación negra.

## Veredicto sobre la v2

Por el criterio de adopción escrito en `docs/regenerar_caches_color_v2.md`
—"sustituye a la v1 si el paso 0 sale idéntico y al menos uno de los
pasos 1-3 mejora sin que ninguno empeore"— la v2 **no se adopta**: en el
benjamín empata en todo y en Villaviciosa no se ha podido medir.

Lo que sí queda demostrado es que **la v2 es inocua**: con el mismo
detector da los mismos números, que era la garantía que prometía el
diseño (los 256 primeros valores son bit a bit la v1). Su valor sigue
siendo potencial —el arquetipo negro y el pantalón— y sin comprobar.

---

# BARRIDO DEL FIT DEL CLASIFICADOR (16-ago-2026)

Primer barrido que mide las DOS patas a la vez: GT de tracking de
Villaviciosa y mini-GT de equipos del benjamín. Hasta ahora un ajuste
podía enderezar un caso y romper el otro sin que nadie lo viera.

## Hallazgo 1: dos de los cuatro diales no hacen nada

24 combinaciones de umbral de fusión × mínimo de features × radio, y
**todas las filas con el mismo radio dan cifras idénticas**. Es decir:

- el **rango y paso del barrido automático de fusión** (0,5-1,3/0,05 vs
  0,4-1,6/0,05 vs 0,6-1,1/0,02) no cambia el resultado: el barrido
  converge al mismo umbral se le dé el rango que se le dé;
- el **mínimo de features** (100 vs 300) tampoco: nunca llega a morder,
  siempre hay recortes de sobra.

Dos diales menos que tocar, y dos que no hay que volver a barrer.

## Hallazgo 2: el id 4 NO es un problema del fit

De 24 combinaciones, 12 "enderezan" el id 4. Todas son las de radio 20 y
35 — justo aquellas en las que **el clasificador colapsa**:

| radio | Villaviciosa cob. | equipos | benja acc | id 4 |
|---|---|---|---|---|
| 20 | 0,359 | 0,434 | 0,247 | ✅ |
| 25 | 0,543 | 0,645 | 0,830 | ❌ |
| 30 | 0,556 | 0,671 | 0,822 | ❌ |
| 35 | 0,550 | 0,658 | 0,190 | ✅ |

Acierta el id 4 por accidente, porque casi todo se etiqueta del mismo
equipo. **No hay ninguna configuración sana del fit que lo arregle**: su
fallo está en otro sitio (probablemente en el propio recorte o en una
mezcla de identidad), no en cómo se entrena el clasificador.

## Hallazgo 3: eran DOS diales, no uno — y uno de ellos estaba corto

El primer barrido movía a la vez el radio del **fit** y el de la
**agregación**. Separados, cada uno manda en una pata distinta:

| r. fit | r. agregación | Villaviciosa cob. | equipos | benja acc |
|---|---|---|---|---|
| 22 | 45 | 0,368 | 0,447 | 0,883 |
| 25 | 25 | 0,543 | 0,645 | 0,830 |
| 25 | 35 | 0,550 | 0,658 | 0,867 |
| **25** | **45** | **0,559** | **0,671** | **0,883** |
| 28 | 45 | 0,559 | 0,671 | 0,883 |

- El **radio del fit** manda en Villaviciosa: por debajo de 25 colapsa,
  y entre 25 y 30 da cifras **idénticas** (0,559 / 0,453 / 5 quimeras /
  0,671), así que ahí no hay riesgo.
- El **radio de agregación** manda en el benjamín, de forma monótona:
  25 → 0,830, 35 → 0,867, 45 → **0,883**. El 35 que tenía configurado se
  quedaba corto.

## ADOPTADO por la excepción vigente

Se sube el radio de agregación del benjamín de 35 a **45 m**. Mejora
todas las métricas medidas y no degrada ninguna:

| benjamín | antes | después |
|---|---|---|
| accuracy por OBSERVACIÓN | 0,867 | **0,883** |
| solo identidades limpias | 0,868 | **0,903** |
| solo jugadores de campo | 0,800 (16/20) | **0,850 (17/20)** |
| accuracy por identidad | 0,767 (23/30) | **0,800 (24/30)** |

Villaviciosa queda **intacta** (su config ya usaba 45 en agregación).

Reproducible: `scripts/barrido_fit.py`.

---

# BARRIDO DE SUAVIZADO × INTERPOLACIÓN (16-ago-2026)

24 combinaciones (ventana 0,3/0,5/0,8/1,2 s × hueco 1,5/2,5/4 s ×
media/savgol), juzgadas con DOS varas: las del banco y las tres del
replay (concurrencia, v99, % de pasos imposibles).

**La hipótesis de Alex se confirma: los dos óptimos son distintos.**

| preset | ventana | hueco | método | cobertura | IDF1 | quimeras | % saltos |
|---|---|---|---|---|---|---|---|
| **informe** | 0,5 s | 4,0 s | savgol | **0,569** | 0,450 | 6 | 2,9 % |
| **replay** | 0,8 s | 4,0 s | media | 0,537 | 0,446 | 7 | **0,2 %** |
| *(default actual)* | 0,5 s | 2,5 s | media | 0,538 | 0,445 | 8 | 0,4 % |

El informe compra **32 milésimas de cobertura** a cambio de **+2,7 puntos
de saltos imposibles**. Para un mapa de calor eso es un buen negocio; para
un replay que se mira jugada a jugada, no.

## El patrón que lo explica

**Savitzky-Golay conserva los picos** —para eso está, es su virtud— y
entre esos picos están los del ruido: da sistemáticamente más cobertura y
**3× más saltos** (v99 de 15-20 m/s frente a 5-8 de la media). La media
los aplana: replay limpio, algo menos de cobertura.

Y la ventana se comporta como se espera: alargarla con media limpia más
(1,2 s deja el v99 en 4,7 m/s) pero se come la cobertura (0,510). Con
savgol, alargarla no limpia — porque el pico sobrevive de todos modos.

## Adopción: NINGUNA, y hay un motivo extra

Ninguno de los dos presets mejora todas las métricas, así que la decisión
es de Alex. Pero además apareció un efecto colateral que conviene no meter
por la puerta de atrás: **subir la ventana a 0,8 altera el perfil legacy
`oficial`**, que pasa de 89 a 96 identidades. El suavizado corre ANTES del
corte de velocidad, así que cambiar la ventana cambia qué rachas resultan
imposibles y por tanto dónde se corta.

El default se queda en lo calibrado (0,5 · 2,5 · media) y los dos presets
quedan **declarados en `configs/tracking.yaml` bajo `presets`** para
elegirlos explícitamente al generar informe o replay.

---

# EL v4 CONTRA EL BANCO (16-ago-2026)

`best_v4.pt` — yolov8m, 837 imágenes (328 + 150 de Alex + 359 del
ayudante), 224 épocas. Detección: **mAP50 0,944** frente a 0,900 del
v4pre, mAP50-95 0,619, precisión 0,965, recall 0,914.

## Villaviciosa: mejora en todo menos en lo que se preguntaba

| | nIds | cob. | conc | IDF1 | tasa IDSW | quimeras | equipos |
|---|---|---|---|---|---|---|---|
| v4pre | 115 | 0,559 | 25 | 0,453 | 0,123 | **5**/38 | 0,671 |
| **v4** | **83** | **0,598** | **23** | **0,484** | **0,100** | 8/38 | **0,758** |

Cobertura +0,039, IDF1 +0,031, tasa de IDSW −0,023, concurrencia de 25 a
**23** (el GT es 22) y accuracy de equipos +0,087. Todo mejor.

**Menos las quimeras, que suben de 5 a 8.**

## La respuesta a la pregunta grande: NO

*¿Caen las quimeras de cruce con mejor detección?* **No: suben.** Y la
explicación es coherente con todo lo demás que se ve en la tabla.

El v4 fragmenta mucho menos: 115 → **83 identidades** con más cobertura,
o sea identidades más largas y más completas. Pero una identidad larga
tiene más ocasiones de contener a dos personas que una corta. Mejor
detección compra continuidad, y la continuidad es exactamente lo que
convierte un cruce mal resuelto en una quimera con recorrido.

Dicho de otro modo: **la quimera de cruce no es un problema de
detección**, y ya no queda dónde esconderlo. Es de asociación en el
instante del cruce, que es donde ByteTrack decide con IoU en píxeles
sobre dos cajas superpuestas.

## Benjamín: empeora, y el número está medido dos veces

| | v4pre | v4 |
|---|---|---|
| accuracy por observación | **0,883** | 0,740 |
| identidades | 67 | 86 |

Con la salvedad de que solo 35 de las 84 identidades del v4 encontraron
equivalente en el mini-GT, así que la cifra cubre un subconjunto.

## Un fallo de medición propio, y la lección

La primera pasada dio **0,178** en el benjamín. No era real: el mini-GT
de equipos está etiquetado sobre los **ids del v4pre**, y los ids no
sobreviven a un cambio de detector. Comprobado: **27 de las 30
identidades del mini-GT caen a más de 5 m de donde estaba la misma id con
el v4**, con mediana de 38 m. El id 8 era el portero lejano y con el v4
está en la portería contraria.

Comparar por número de id era comparar personas distintas. Ahora
`medir_v4.py` traslada las etiquetas por **solape espacio-temporal**, que
es lo que sí sobrevive a un cambio de modelo.

Lo incómodo del fallo: es exactamente el argumento que se le dio a Alex
para aplazar el GT de parejas de ids —"hoy caducarían"— y no se aplicó al
mini-GT de equipos, que sí se reutilizó. **Cualquier GT indexado por id
del sistema caduca al cambiar el detector**; los que sobreviven son los
indexados por posición y tiempo.

## Casos con nombre

| caso | v4pre | v4 |
|---|---|---|
| id 4 (570 obs, A→B) | ✗ | ✗ sigue |
| id 32 (naranja etiquetado A) | ✗ | ✗ sigue |
| id 19→4 (misma persona, dos ids) | ✗ | ✗ sigue (19→[42], 4→[2,31,33,54,63]) |

Los tres resisten al barrido del fit **y** al detector nuevo. Ya no es
plausible que sean del clasificador ni de la detección: queda el recorte o
la asociación.

**Y el id 4 explica la subida de quimeras mejor que cualquier promedio.**
El id 4 del v4pre lo cubren **cinco identidades del v4**, cuando la
mediana es 1. O sea: donde el v4pre tenía una identidad larga y sucia, el
v4 ve cinco tramos. La quimera del v4pre era real y el v4 la parte —
solo que al partirla no la resuelve, la reparte.

### Un artefacto propio, cazado a tiempo

La primera pasada con traslado daba 0,727 y **id 32 ✅ arreglado**. Era
falso: cuando varias identidades nuevas caen sobre una vieja, el traslado
asignaba "la última gana", que con cinco candidatas es echar a suertes.
Con **voto mayoritario ponderado por observaciones** el número es 0,740 y
el id 32 **sigue mal**. La versión que daba la buena noticia era la que
estaba mal implementada.

## Decisión

**NO se adopta automáticamente**: la excepción exige mejorar todo sin
degradar nada, y las quimeras empeoran en Villaviciosa (5 → 8) y la
accuracy en el benjamín (0,883 → 0,727). La decisión es de Alex.

Lectura para decidir: en Villaviciosa el v4 es netamente mejor en las
métricas de producto (cobertura, concurrencia, equipos) y solo pierde en
pureza; el benjamín va en dirección contraria y merece mirarse antes de
adoptar.


---

# RE-BARRIDO DEL v4 CON SU PROPIA CAJA DE CAMBIOS (17-ago-2026)

Crítica de Alex, y era correcta: toda la configuración —buffer, umbral de
emparejamiento, cosido, confianza— se ajustó sobre las detecciones del
**v4pre**. Se cambió el detector y se dejó puesta la caja de cambios del
anterior. Declarar peor al v4 así era comparar el v4 mal ajustado contra
el v4pre bien ajustado.

`scripts/barrido_v4.py`. Aviso: el caché del v4 se generó con
`confianza: 0.3`, así que solo se puede SUBIR el umbral. Probar 0,25
exigiría otra pasada de Colab.

## El punto ganador, y gana a los dos en TODO

| | nIds | cob. | conc | IDF1 | tasa | quim |
|---|---|---|---|---|---|---|
| v4pre (adoptado) | 115 | 0,559 | 25 | 0,453 | 0,123 | 5 |
| v4 con caja del v4pre | 83 | 0,598 | 23 | 0,484 | 0,100 | 8 |
| **v4 con la suya** | **64** | **0,612** | **21** | **0,537** | **0,069** | **3** |

Ganador: `conf 0.45 · buffer 1.5 · empar 0.995 · minf 2 · hueco 4 ·
color 0.9`. Cobertura, IDF1, tasa de IDSW y quimeras, todo mejor que los
dos. Concurrencia 21 con GT 22 (el v4pre daba 25).

No es un pico aislado: a conf 0,45 con `minf 2` toda la vecindad da 3-4
quimeras y cobertura ~0,60. Es una meseta.

## El control que da valor a la cifra

**El v4pre NO gana subiendo la confianza**: a 0,5 su cobertura se hunde a
0,477 y sus quimeras suben a 6. La palanca es específica del v4, que es
lo que cabía esperar de un detector con recall 0,914 — tiene margen para
tirar detecciones dudosas sin quedarse ciego. Sin este control, el
barrido no probaría nada.

## Corrección de la lectura anterior

Lo de "el v4 sube las quimeras de 5 a 8" era **un artefacto de medirlo
con los parámetros del v4pre**. Con los suyos baja a 3. La conclusión de
que la detección no es la palanca sigue en pie —el salto grande no vino
de mAP50— pero el v4 **no es peor**: estaba mal ajustado.

Lo que NO cambia: en la pata del benjamín el v4 mejora con los
parámetros nuevos (0,740 → **0,802**) pero **sigue por debajo del v4pre
(0,883)**, y Alex vio mezcla a ojo. Por eso no se adopta por la
excepción: no mejora todo en las dos patas.

## Aviso de sobreajuste, dicho antes de que lo pregunte nadie

El ganador se eligió sobre el MISMO tramo con el que se mide. 36 combinaciones
sobre un tramo de 500 frames encuentran buenos números por azar. Lo que
lo hace algo más creíble es la meseta y que la pata del benjamín también
sube. Lo que lo confirmaría es un tramo distinto.

---

# PASO 0: ¿DÓNDE NACEN LAS QUIMERAS? (17-ago-2026)

`scripts/diagnostico_quimeras.py`, sobre el v4 ya bien ajustado (32
identidades con más de una persona, 195 observaciones de cambio contra
1.462 normales). El control es lo que da valor: se compara el cambio
contra las observaciones normales **de las mismas identidades**.

| señal previa al cambio | en CAMBIOS | en normales | ratio |
|---|---|---|---|
| caja solapada (IoU>0,1, ventana 3) | 39,0 % | 21,1 % | **1,8×** |
| pérdida real (hueco > 15 frames) | 19,5 % | 6,4 % | **3,0×** |

## Veredicto: la hipótesis original es solo PARCIALMENTE cierta

El solape existe como factor pero es **débil y minoritario**: 6 de cada
10 cambios de persona ocurren **sin** solape apreciable cerca, y con
1,8× un veto ahí tendría muchos falsos positivos.

**La señal más limpia es otra: la re-entrada tras perder el track (3,0×).**
El salto no ocurre tanto en el instante del cruce como al RECUPERAR una
identidad que se había perdido y engancharla a la persona equivocada.

Esto es exactamente para lo que servía el paso 0. El camino A tal como
estaba escrito —"veto de color solo en el instante de cruce"— cubriría
la señal más débil de las dos. **Hay que reescribirlo**: la puerta de
apariencia debe ponerse en la RE-ENTRADA (cuando el buffer devuelve un
track perdido), y secundariamente en el solape.

Nota de método: la primera versión de esta medición daba "100 % en ambos
grupos" para el hueco previo. No era un hallazgo: aquí solo hay
observaciones en frames con GT (1 de cada 15), así que dos consecutivas
distan 15 por construcción y el umbral de 9 lo cumplía todo.


---

# LA PUERTA DE APARIENCIA EN LA RE-ENTRADA (17-ago-2026)

`src/tracking/puerta_reentrada.py`. Rediseño del "camino A" después de
que el paso 0 refutara su premisa: la puerta no va en el instante del
cruce (1,8×) sino en la RE-ENTRADA tras perder el track (3,0×).

Qué hace: cuando ByteTrack recupera una identidad que estuvo perdida, se
compara la firma de color de antes con la de después. Si no casan, la
identidad se parte ahí y el trozo nuevo sale aparte, para que el cosido
por pureza decida con su propio criterio.

Va DESPUÉS de la asociación y ANTES del cosido. `sv.ByteTrack` es una
caja cerrada y no admite un coste de apariencia dentro, así que esta es
la posición más cercana al problema que el código permite.

## Medición (banco, v4 con su config)

| puerta | nIds | cob. | conc | IDF1 | tasa | quim |
|---|---|---|---|---|---|---|
| desactivada | 64 | 0,610 | 21 | 0,540 | 0,071 | 5 |
| **color 0,9 · hueco 0,5 s** | 79 | 0,619 | 21 | **0,546** | 0,072 | **3** |
| color 1,1 · hueco 0,5 s | 66 | **0,625** | 21 | 0,540 | 0,071 | 4 |
| color 0,7 · hueco 0,5 s | 100 | 0,591 | 21 | 0,530 | 0,089 | 3 |

**Tres quimeras es la mejor cifra que ha dado el proyecto** (el v4pre
adoptado da 5). Adoptado 0,9 en el perfil del v4, aceptando +0,001 de
tasa de IDSW, que es ruido. La variante 1,1 no degrada absolutamente
nada y sube más la cobertura, si se prefiere ese compromiso.

Demasiado estricta (0,7) se pasa de frenada: 100 identidades y la tasa
de IDSW sube a 0,089. La puerta tiene el mismo filo que los tres cortes
fallidos y hay que dejarla en el punto medido, no en el más exigente.

## Por qué esta vez el corte SUBE la cobertura

Los tres cortes fallidos (velocidad, post-proceso, color) bajaban la
cobertura porque troceaban identidades sanas. Este la sube (0,610 →
0,619) porque solo mira los puntos de re-entrada —el 6 % de las
transiciones— y porque partir una quimera **le devuelve al cosido la
posibilidad de recolocar bien los dos trozos**. Cortar donde el sistema
ya estaba adivinando no destruye información: la libera.

Es la doctrina de Alex, literal: no cortar en todos los frames, solo
decidir mejor donde el sistema ya está adivinando.

## Salvaguarda contra el cuarto negativo

La puerta se ABSTIENE si no hay al menos `min_obs_firma` (3)
observaciones con color a cada lado. Con una o dos muestras la firma es
ruido y el corte sería aleatorio, que es exactamente cómo se estropearon
los intentos anteriores.


---

# ¿EL PROBLEMA DEL BENJAMÍN ES DE DETECCIÓN? NO (17-ago-2026)

`scripts/comparar_deteccion_benja.py`. La pregunta decide dónde va el
esfuerzo de etiquetado, así que se responde con datos y no con intuición.
No hay GT de detección en este tramo —no se puede medir mAP— pero sí se
puede medir cuántas cajas salen, con cuánta confianza, y sobre todo
**dónde caen**.

| | frames | dets | /frame | conf media | % <0,5 |
|---|---|---|---|---|---|
| v4pre | 600 | 10.904 | 18,2 | 0,819 | 4,6 % |
| v4 | 600 | 12.120 | 20,2 | 0,814 | 11,8 % |

**Dentro del campo** (lo que de verdad importa: en un F7 hay ~15
personas, 7v7 + árbitro):

| | dentro/frame | % fuera del campo | % de las tiradas por el filtro 0,45 |
|---|---|---|---|
| v4pre | 14,1 | 22,6 % | 83,3 % |
| v4 | **14,4** | 28,5 % | 80,7 % |

## Las tres conclusiones

1. **El v4 no detecta peor en el benjamín: detecta algo mejor.** 14,4
   jugadores en campo por frame frente a 14,1, con ~15 personas
   presentes. La detección está prácticamente completa en los dos.

2. **La confianza es la misma** (0,819 vs 0,814). Si el v4 estuviera
   perdido en un dominio que no conoce, dudaría aquí — y no duda. Las 2
   cajas/frame extra caen **fuera del campo** (28,5 % vs 22,6 %): son
   banquillo y público, no jugadores.

3. **El filtro de 0,45 quita público, no jugadores lejanos.** El 80,7 %
   de lo que tira está fuera del campo. Esto despeja la sospecha
   razonable de que el filtro se estuviera comiendo a los del fondo.

## Consecuencia para el esfuerzo

**El cuello de botella del F7 no es la detección.** Etiquetar más frames
del benjamín no arreglaría lo que se ve mal en el vídeo: las mezclas de
identidad y los errores de equipo nacen aguas abajo, en la asociación y
en el clasificador. Ahí es donde tiene retorno el trabajo.

Matiz honesto de la medición: cuenta cajas y confianza, no corrección.
Sin GT de detección no se puede descartar que las cajas del v4 estén peor
ajustadas aunque sean igual de numerosas. Lo que sí descarta, con
holgura, es la hipótesis de "el v4 está ciego en el benjamín".


---

# EL TECHO DE LA PUERTA DE COLOR: LA QUIMERA DEL MISMO EQUIPO

Hallazgo de Alex etiquetando el mini-GT (17-ago-2026), identidad #43 del
benjamín: **todo naranja de principio a fin, pero en el sexto recorte se
cruza con otro naranja y a partir de ahí sigue al otro.**

Es una quimera perfecta y la puerta de re-entrada **no puede verla por
diseño**: compara firmas de color, y los dos jugadores visten igual. La
firma casa porque es la misma camiseta; simplemente no es la misma
persona.

Esto pone un techo a toda la línea de la apariencia, y conviene tenerlo
escrito antes de invertir más en ella. Para el cruce entre compañeros los
únicos criterios que quedan son geométricos —continuidad de trayectoria,
velocidad, dirección— porque no hay nada que distinguir en el aspecto.
Es, literalmente, el caso difícil que el proyecto eligió a propósito:
"equipaciones idénticas entre compañeros" está en la definición del
producto.

## Cuánto pesa (Villaviciosa, medido)

`scripts/diagnostico_quimeras.py` ahora lo cuenta:

| | quimeras |
|---|---|
| mezclan jugadores de EQUIPOS DISTINTOS | 31 (97 %) |
| mezclan jugadores del MISMO equipo | 1 (3 %) |

En Villaviciosa el techo está lejos: 31 de 32 quimeras son entre equipos
y la puerta de color **sí** podría verlas. Que solo baje de 5 a 3 dice
que el problema es el umbral y la cobertura de la puerta, no su
principio — hay margen para afinarla.

**Ojo con extrapolar esto al benjamín**: la proporción está medida en
Villaviciosa, y el caso que vio Alex es del benjamín. Cuando esté su
mini-GT se podrá contar allí, y si en el F7 dominan las del mismo equipo,
la conclusión cambia y hay que ir a criterios geométricos.

## Mejora de la herramienta que salió de aquí

Los recortes llevan holgura para dar contexto, y esa holgura mete a
menudo a otro jugador en el cuadro: quien etiqueta no sabe a cuál se
refiere la pregunta. Ahora `recortar()` dibuja el rectángulo del jugador
en cuestión sobre el recorte.

Detalle que un test cazó: hay que recortar sobre una **copia** del frame.
Sin ella, la marca de un jugador se quedaría pintada en los recortes de
todos los demás del mismo instante — un fallo silencioso que habría
envenenado el etiquetado sin dar ningún error.

---

# PUNTO 1: ¿CLASIFICADOR O TRACKER? (19-ago-2026)

`scripts/diagnostico_fallos_clasificacion.py`. Un jugador sale con el
equipo equivocado por dos motivos con soluciones distintas:

- **(a) identidad PURA mal clasificada**: el tracker acertó (una
  identidad = una persona) y falló el color. Se arregla clasificando
  mejor.
- **(b) identidad CONTAMINADA**: la identidad mezcla a dos personas, así
  que **no existe etiqueta correcta** — la mitad de sus observaciones van
  a estar mal se elija lo que se elija. Ningún clasificador lo salva.

Criterio acordado: si más del 30 % cae en (b), la prioridad es el
tracker.

## Resultado en Villaviciosa (v4 ajustado + puerta)

De 1.706 observaciones casadas con el GT, **418 mal etiquetadas (24,5 %)**.
Reparto según cuán exigente sea la definición de "contaminada" —qué
fracción de la identidad tiene que ser la segunda persona:

| umbral | puras | contaminadas | (a) | (b) |
|---|---|---|---|---|
| 0 % (una obs suelta basta) | 21 | 38 | 8,6 % | **91,4 %** |
| 5 % | 26 | 33 | 10,8 % | **89,2 %** |
| 10 % | 33 | 26 | 15,1 % | **84,9 %** |
| 20 % | 39 | 20 | 47,1 % | **52,9 %** |

**El veredicto aguanta en todos**: incluso con la definición más estricta
—donde la segunda persona tiene que ser el 20 % de la identidad— la
asociación explica más de la mitad. En el rango razonable (5-10 %) es del
85-89 %.

La sensibilidad importaba: con el umbral en 0, **una sola observación**
casada con otra persona marca la identidad como contaminada, y eso podía
ser ruido de asociación en un cruce en vez de una quimera de verdad. No
lo era.

Lectura del umbral 20 %: el salto de (a) a 47 % no es que el clasificador
empeore, es que a esa exigencia las identidades con contaminación del
10-19 % pasan a contarse como "puras" **arrastrando sus errores**. Por eso
la franja creíble es 5-10 %, no 20.

## Qué aporta ya la puerta de re-entrada

| | obs mal | % del total |
|---|---|---|
| sin puerta | 448 | 26,3 % |
| con puerta | 418 | 24,5 % |

Ahorra 30 observaciones, un 7 % relativo. Positivo pero modesto: confirma
que la puerta va en la dirección correcta y que su techo está donde ya se
midió (ciega al cruce entre compañeros del mismo equipo).

## Consecuencia para el orden del trabajo

**La prioridad es el TRACKER.** El clasificador de color, sobre
identidades limpias, solo se equivoca en el 8,6 % de sus observaciones —y
su confusión dominante es `A → otro` (27 obs), que huele a regla de staff
o árbitro, no a color mal medido.

Eso reordena los puntos pendientes:

- **Punto 4 (tracker con apariencia) y punto 3 (partir quimeras con
  GTA-Link) suben**: atacan el 85-90 % del problema.
- **Punto 2 (embeddings en vez de HSV) baja**: por bueno que sea el
  clasificador, su techo de mejora aquí es ~9 % de los fallos.

Con un matiz que no conviene perder: el embedding del punto 2 es el mismo
que necesitan el 3 y el 4 (ver `docs/embedding_unico.md`), así que
benchmarkear backbones **no** es trabajo tirado — solo que su primer
beneficiario deja de ser la clasificación.

---

# EL BUG `A → otro`: dos causas, ninguna era la que dije (19-ago-2026)

El diagnóstico del punto 1 dejó como error dominante del clasificador
`A → otro` (27 obs) y yo apunté a "la regla de staff o el árbitro". **La
regla de staff no tiene nada que ver**: las cinco identidades afectadas
están DENTRO del campo (0,00 m fuera, con tolerancia de 2 m).

Las causas son dos, y distintas entre sí:

## 1. Falso positivo del catálogo arbitral (id 40, el gordo)

Un jugador real del equipo A, con 110 observaciones en el centro del
campo (x 43-50, y 20-38), lo marca `identificar_arbitros` como árbitro.

La regla de conflicto del catálogo existe y funciona, pero protege al
**prototipo** del equipo: desactiva un arquetipo si la equipación media
de A o B cae dentro. Lo que no cubre es la **dispersión alrededor del
prototipo** — un jugador concreto cuyo color se aparta lo suficiente
puede caer en un arquetipo que no choca con la media de su equipo.

Arreglo a medir: exigir además que la identidad esté más lejos de A y B
que cierto margen antes de aceptar el arquetipo. Es decir, que el
catálogo solo mande cuando el color NO se parece a ningún equipo.

## 2. El prototipo `otro` absorbe identidades cortas (ids 22, 31, 53, 76)

7, 14, 16 y **1** observación respectivamente. El fit produce un
prototipo `otro` (contra lo que decía una nota antigua sobre el v4pre) y
las medias ruidosas de identidades cortas caen ahí.

Arreglo a medir: mínimo de observaciones para poder asignar `otro`. Con
una sola observación la media de color es ruido, y forzar la elección
entre A y B acierta el 50 % por azar en vez del 0 % actual.

Ninguno de los dos está implementado: son fallos de menos del 9 % de los
fallos totales (el punto 1 dice que el 85-90 % es asociación), así que
van por detrás del tracker. Quedan apuntados con su arreglo.

---

# LA PUERTA POR EMBEDDING: las dos patas (19-ago-2026)

## Pata 1 — Villaviciosa: barrido fino

`scripts/barrido_puerta_embedding.py`. Rango útil 0,04-0,13, ya sabido.

| umbral | nIds | cob. | conc | IDF1 | quim | **mismo eq** |
|---|---|---|---|---|---|---|
| 0,040 | 79 | 0,602 | 21 | 0,543 | **2** | 1 |
| 0,050 | 74 | 0,612 | 21 | 0,548 | **2** | 1 |
| 0,060 | 69 | 0,621 | 21 | 0,552 | 3 | 1 |
| **0,070** | 68 | **0,623** | 21 | **0,553** | 3 | **1** |
| **0,080** | 68 | **0,623** | 21 | **0,553** | 3 | **1** |
| 0,090 | 66 | 0,612 | 21 | 0,534 | 4 | 1 |
| 0,100 | 64 | 0,612 | 21 | 0,537 | 3 | 1 |
| **color 0,9** | 79 | 0,622 | 21 | 0,542 | **4** | **2** |

Los otros ejes: **hueco 0,5 s** gana (0,3 empata, ≥0,8 pierde);
**min_obs** es plano entre 1 y 8 (se deja en 3); **ponderar por tamaño no
cambia NINGUNA decisión** — el comprobador de puntos idénticos lo cazó, y
por eso se queda desactivado en vez de añadir complejidad que no paga.

Nota: 0,04-0,05 dan **2 quimeras**, mejor que las 3 del ganador, pero
hunden la cobertura a 0,602-0,612. Es el error de siempre y se descarta.

## Pata 2 — benjamín (sin GT posicional)

**Lo que NO se puede medir ahí, dicho claro**: las quimeras del mismo
equipo. Requieren identidad etiquetada y el benjamín no la tiene; el
caso #43 fue una observación visual de Alex, no un dataset. El mini-GT
del v4 tampoco llegó, así que la accuracy de equipos sigue saliendo del
traslado con pérdida.

| puerta | nIds | cortes | conc | acc equipos |
|---|---|---|---|---|
| color 0,9 | 84 | 21 | 17,4 | 0,787 |
| embedding 0,06 | 89 | 20 | 17,4 | 0,796 |
| **embedding 0,08** | **79** | 10 | 17,4 | **0,796** |
| embedding 0,10 | 77 | 7 | 17,4 | 0,811 |

El embedding bate al color en accuracy con **menos identidades** (79 vs
84) y la misma concurrencia. En F7 hay ~15 personas y la concurrencia es
17,4 en todas las variantes: la puerta no la mueve.

## Balance de las dos patas

| | Villaviciosa | benjamín |
|---|---|---|
| quimeras | 4 → **3** | (no medible) |
| del mismo equipo | 2 → **1** | (no medible) |
| IDF1 | 0,542 → **0,553** | — |
| cobertura | 0,622 → **0,623** | — |
| concurrencia | 21 = 21 | 17,4 = 17,4 |
| accuracy equipos | — | 0,787 → **0,796** |
| tasa de IDSW | 0,068 → 0,069 | — |

Mejora en todo **menos** la tasa de IDSW, que sube 0,001. Es ruido, pero
la excepción exige no degradar NADA, así que **no se adopta solo**: la
decisión es de Alex.

# EL TECHO DE LA PUERTA EN EL F7: los saltos salen en CRUCES

`scripts/sospechosas_de_quimera.py`. Sin GT posicional no se puede
afirmar qué identidad es quimera, pero sí señalar dónde mirar.

Y al hacerlo aparece algo que no esperaba: **de los 106 saltos de
apariencia por encima del umbral en el benjamín, casi todos tienen hueco
de 0,1-0,3 s** — o sea son CRUCES, y la puerta ni los examina, porque por
diseño solo mira re-entradas (hueco ≥ 0,75 s).

| dist | id | minuto | hueco | ¿la puerta? |
|---|---|---|---|---|
| 0,172 | 23 | 5:10,0 | 0,30 s | no la mira (cruce) |
| 0,164 | 23 | 5:10,1 | 0,10 s | no la mira (cruce) |
| 0,132 | 15 | **5:07,7** | 1,70 s | **sí, cortada** |
| 0,125 | 7 | 5:20,7 | 0,10 s | no la mira (cruce) |
| 0,122 | 32 | 5:47,4 | 0,10 s | no la mira (cruce) |

Recuento: **106 saltos en cruces que la puerta no mira**, y 35
re-entradas con salto por debajo del umbral.

El paso 0 midió que la re-entrada era la señal limpia (3,0× frente a 1,8×
del solape) **en Villaviciosa**. En el F7 la foto puede ser distinta, y
esta tabla lo sugiere. No es contradicción —aquella medía dónde nacen las
quimeras y esta dónde salta la apariencia— pero abre una pregunta
concreta: **extender la puerta a los cruces**, ahora que la señal ya no es
el color sino un embedding que sí distingue compañeros.

Primera versión de este script: la columna "¿la puerta cortó?" se
calculaba solo con la distancia y decía "sí" en saltos que la puerta ni
examina. Habría mandado a Alex a mirar los sitios equivocados.

---

# EXTENDER LA PUERTA A LOS CRUCES: medido y RECHAZADO (19-ago-2026)

El razonamiento que lo motivaba es correcto y conviene dejarlo escrito:
**la restricción "solo re-entradas" venía de que la firma era COLOR**, y
con color mirar un cruce entre compañeros es inútil —visten igual, no hay
nada que comparar—. Con un embedding sí hay señal, así que la restricción
era herencia de la señal antigua, no una propiedad del problema.

Implementado (`mirar_cruces`) y medido en las dos patas.

## Villaviciosa (la única pata con GT de identidad)

| variante | nIds | cob. | conc | IDF1 | quim | mismo eq |
|---|---|---|---|---|---|---|
| **solo re-entradas** | 68 | 0,623 | 21 | 0,553 | **3** | 1 |
| re-entradas + cruces | 70 | 0,623 | 21 | 0,553 | **4** | 1 |
| + cruces, umbral 0,06 | 86 | 0,627 | 21 | 0,543 | 4 | 1 |
| + cruces, umbral 0,10 | 64 | 0,612 | 21 | 0,537 | 3 | 1 |

**Empeora**: las quimeras suben de 3 a 4 y las del mismo equipo se quedan
en 1. Cortar en los cruces añade identidades sin comprar pureza.

## Benjamín — y por qué su número NO se puede leer solo

| variante | nIds | cortes | conc | acc equipos |
|---|---|---|---|---|
| emb 0,08 solo re-entradas | **79** | 10 | 17,4 | 0,796 |
| emb 0,08 + cruces | 91 | 36 | 17,4 | 0,822 |
| emb 0,06 + cruces | **136** | 132 | 17,4 | **0,840** |

Aquí la accuracy sube mucho… **y las identidades también**: 136 para ~15
personas en campo. No es coincidencia: la accuracy se mide **por
identidad**, así que trocear una identidad sucia en trozos limpios la
sube automáticamente. **La métrica premia fragmentar**, y en el benjamín
no hay cobertura ni quimeras que compensen ese sesgo porque no hay GT
posicional.

Dicho de otro modo: el 0,840 no dice que el tracking sea mejor, dice que
hay más identidades y más cortas. En Villaviciosa, donde sí se puede
medir pureza y cobertura a la vez, la misma variante empeora.

## Decisión: NO se adopta

`mirar_cruces: false`. La única pata capaz de juzgarlo dice que sube las
quimeras, y la otra tiene una métrica que no puede distinguir "mejor" de
"más troceado".

Queda implementado y con su flag: si algún día hay GT de identidad del
benjamín, la pregunta se puede reabrir con datos que sí decidan.

## Un fallo que cazó el comprobador de puntos idénticos

La primera medición dio "solo re-entradas" y "con cruces" **idénticas**.
No era un hallazgo: `obs[k]` es `(frame, (frame, det_idx))` y la clave
del conjunto de cruces es `(frame, det_idx)`, así que la comparación no
casaba **nunca** y la extensión no hacía nada. Tras arreglarlo, 4 de 4
puntos distintos — y el resultado real es el negativo de arriba.

Es la segunda vez en dos sesiones que "todas las filas iguales" tapa un
bug en vez de un empate. El reflejo va camino de ser la comprobación más
rentable del proyecto.

---

# LIMITACIÓN ANOTADA: el benjamín no tiene GT de identidad

Para que no se nos olvide, porque condiciona toda métrica que salga de
esa pata:

1. **Las quimeras del mismo equipo no se pueden contar allí.** Requieren
   identidad etiquetada por posición y tiempo. El caso #43 de Alex fue
   una observación visual, no un dataset.
2. **La accuracy de equipos sale del traslado con pérdida** sobre un
   mini-GT indexado por ids del v4pre: solo 35 de ~80 identidades
   encuentran equivalente.
3. **Esa accuracy premia fragmentar**, como acaba de verse con los
   cruces.

Consecuencia: si la pata del benjamín se vuelve la métrica que decide
—y va camino, porque el F7 es el caso objetivo del producto— **hay que
hacer un GT de identidad del benjamín**, indexado por posición y tiempo,
no por id del sistema.
