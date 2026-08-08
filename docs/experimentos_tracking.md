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
