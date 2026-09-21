# El balón con alas: no faltaba un modelo de movimiento, sobraban dos bugs

21-sep-2026. Encargo de Alex, a partir de una investigación externa: *"el
problema NO es el detector, es que hoy no existe ningún modelo de movimiento.
Cuando el balón se pierde varios frames, el sistema conecta la última
posición con la siguiente sin más lógica que «es lo más cercano» — de ahí las
alas y los saltos imposibles."* Plan: Kalman con estado, puerta de estático
en el propio tracker, suavizador RTS, cortes en los toques.

**La premisa era parcialmente incorrecta, y medirla antes de construir
cambió el resultado.** Lo que producía las alas eran **dos bugs del
post-proceso**, no la falta de un filtro. Ambos corregidos, con tests.
Reproducir: la comparación completa está en `scripts/procesar_balon.py` +
las medidas de este documento.

## 0. La premisa, contra el código

`src/balon/tracking_balon.py` ya tenía: candidatos agrupados por
continuidad espacial (8 m), puerta de balón estático (quieto y lejos de los
jugadores), desempate por cercanía a un jugador, fases aéreas por velocidad y
por tamaño, y relleno de huecos con umbrales medidos. **Lo que no tiene es un
filtro con estado.** Y el filtro de marcas ya quita las estáticas.

## 1. Cuántas alas hay de verdad, y de dónde salen

Sobre la serie de balón de la parte entera (5.676 filas marcadas `es_real=1`):

| | antes |
|---|---|
| pasos entre filas reales con v > 40 m/s | **274** (5,6 %) · máximo 241 m/s |
| filas «reales» a **más de 1 m de toda detección cruda** | **686 = 12,1 %** |

**Un balón no va a 40 m/s.** Y, lo que decide el diagnóstico: **el 59 % de las
filas imposibles no está cerca de NINGUNA detección** (mediana 2,7 m), contra
el 9,6 % del resto (mediana 0,08 m). No eran detecciones saltando: eran
posiciones **que el sistema fabricaba y etiquetaba como medidas**.

### Bug 1: el suavizado cruzaba vuelos y huecos

`preparar_para_replay` promediaba la lista de observaciones de SUELO como si
fueran consecutivas, y esa lista **se salta los vuelos y los huecos**. En el
borde de un vuelo mezclaba el punto de despegue con el de aterrizaje. Con
una ventana de 3 muestras, una fila pegada a un vuelo de 24 m se desplazaba
8 m. Esa fila salía con `es_real=1`.

Arreglo: el suavizado solo promedia **dentro de un tramo continuo**
(contigüidad en la trayectoria y hueco de tiempo ≤ 0,2 s,
`max_hueco_suavizado_s`). 0,15 y 0,2 s dan lo mismo; a 0,3 s ya se cuelan
filas (0,4 %).

| sobre las filas reales | actual | **por tramos** | sin suavizar |
|---|---|---|---|
| a >1 m de toda detección | 12,1 % | **0,1 %** | 0,0 % |
| pasos >20 m/s | 420 | **51** | 113 |
| pasos >40 m/s | 270 | **30** | 30 |
| σ temblor | 0,04 m | **0,03 m** | 0,07 m |

Mejora TODAS las columnas, y hasta queda mejor que la detección cruda en
temblor: suaviza, pero solo lo que debe.

### Bug 2: la recta del vuelo se repartía por índice, no por tiempo

Con Bug 1 arreglado, las filas de suelo quedaron limpias (**0 pasos imposibles
entre filas reales, antes 248**), pero **el problema se movió**: los pasos
imposibles que atraviesan una fase aérea o un relleno pasaron de **69 a 272**.
El salto ya no se esparcía sobre el suelo: aparecía entero en la recta de
despegue→aterrizaje (`alfa = (i − previo) / (siguiente − previo)`, por índice de
muestra). Con detecciones perdidas dentro del vuelo, unos pasos salían enormes y
otros diminutos.

**De 98 vuelos con pasos imposibles, 88 tenían una velocidad media física entre
sus extremos** (mediana 13 m/s, p75 23). Arreglo: `alfa` por tiempo.

### Cuenta final sobre lo que SE PINTA (pasos > 40 m/s)

| | real→real | con fila no real | no real→no real | **TOTAL** |
|---|---|---|---|---|
| antes (los dos bugs) | 248 | 66 | 3 | **317** |
| + suavizado por tramos | 0 | 161 | 111 | 272 |
| + recta por tiempo | **0** | 95 | 33 | **128** |

⚠️ **Tras el primer arreglo el total solo bajó de 317 a 272**: los 248 pasos
entre filas reales desaparecieron, pero casi todo reapareció en las filas no
reales. Lo cazó desglosar por tipo de fila en vez de mirar el total. (Una
primera versión de esta tabla contaba dos veces las filas «no real → no
real» y decía 383: un doble conteo mío, corregido.)

### Efectos laterales, comprobados

- **Contactos: idénticos byte a byte** (se calculan sobre la trayectoria cruda).
  Filas reales (5.676) y fases aéreas (2.407) sin cambio.
- **Relleno de huecos: 226 → 395 frames** (verificado corriendo el código de
  `HEAD` contra el nuevo sobre la misma serie). No es un cambio de regla: la
  guarda de velocidad calcula la velocidad previa sobre las posiciones ya
  suavizadas, que en los bordes de un vuelo estaban mezcladas (mecanismo
  inferido; no he aislado cuál de los dos arreglos lo produce). 395 se parece
  al 377 que midió el documento original
  (`docs/relleno_de_huecos_balon.md`): **producción estaba rellenando de menos
  por este bug.** Los rellenos siguen con `es_real=False`.
- Tests: `tests/test_suavizado_balon.py` (7). Mutados: cazadas la contigüidad,
  el hueco de tiempo, el suavizado apagado y el reparto por índice. **Una
  mutación escapó al principio** (quitar la contigüidad, porque mi vuelo era
  más largo que el umbral y el tiempo lo cortaba solo) y hizo falta un test con un
  vuelo de una sola muestra.

## 2. Lo que el plan proponía, medido

### Punto 1: Kalman para predecir en los huecos → NEGATIVO (dos intentos)

434 huecos con tres muestras de suelo previas. Error en el punto donde el
balón REAPARECE, y % a menos de 2 m:

| | mantener (hoy) | vel. constante | vel. amortiguada (≈ Kalman) |
|---|---|---|---|
| **todos** | **69 %** · 1,10 m | 64 % · 1,00 m | 67 % · 0,85 m |
| hueco <0,5 s · lento | 91 % | 91 % | 91 % |
| hueco <0,5 s · normal | 86 % | 83 % | 84 % |
| hueco <0,5 s · **rápido** | **72 %** | 51 % | 58 % |
| hueco ≥0,5 s · cualquiera | 3-26 % | 0-25 % | 10-31 % |

Mantener la posición **gana o empata en el acierto**; extrapolar hace daño en
el tramo rápido y en los huecos largos **nada funciona**: cuando el balón se
pierde más de 0,5 s, un toque cambia su trayectoria y ninguna física la
predice. Segundo intento, mismo resultado ⇒ **se abandona para el relleno.**

### Punto 1 bis: elegir el candidato por proximidad a la predicción → pequeño

Con la verdad de las marcas (3.442 desempates, 1.956 con posición previa de
≤1 s):

| criterio | acierta |
|---|---|
| confianza | 88,5 % |
| cercanía a un jugador (el actual) | 96,4 % |
| **continuidad con la pista** | **98,0 %** |

Discordantes: continuidad acierta y jugador falla **59**; al revés **28**.
**Cota SUPERIOR**: la «pista previa» aquí es limpia, y en producción sería la
propia selección, con sus errores. Y sobre los 32 pasos imposibles que quedan
tras los dos arreglos, **solo en 10 había otro candidato compatible con la
física**: el techo sobre lo que motivó el plan es **0,2 % de los pasos**. No se
construye.

### Punto 2: puerta de velocidad que sustituya al filtro de marcas → NEGATIVO

Racha estática (detecciones que no se mueven >3 px) sobre las 21.255
detecciones crudas, con las marcas conocidas como verdad:

| racha estática ≥ | **marcas cazadas** | no-marcas RETIRADAS |
|---|---|---|
| 0,3 s | 84,8 % | 632 (6,8 %) |
| 1 s | 68,0 % | 278 (3,0 %) |
| 3 s | 41,2 % | 128 (1,4 %) |
| 10 s | 13,5 % | 0 |

**Ninguna cumple los dos criterios pedidos.** El filtro actual caza el
100 % (las marcas se detectan de forma intermitente y cortan las rachas), y
la puerta se lleva balón real: **a 0,3 s, el 78 % de lo que retira está a
menos de 3 m de un jugador (mediana 0,9 m), contra el 7 % de las marcas
(mediana 14,5 m)**. Son las faltas, saques y córners: justo donde el producto
necesita el balón. La variante «estático **y lejos** de los jugadores» es
literalmente la guarda que ya existe (`dist_max_jugadores`).

Sobre «funcionaría desde el primer frame sin ver 20 minutos»: el
procesamiento es en diferido y siempre tiene el partido entero, así que no
es una restricción que hoy pague.

### Punto 3: suavizador RTS → NO CONSTRUIDO

Tras el Bug 1 el temblor es **0,028 m** (σ), 30 veces por debajo del error
de anclaje contra el GT (~0,9 m). Un RTS podría bajar ese número, pero no
hay nada visible que arreglar: no se construye. Volver a mirarlo si un
cliente ve temblor.

### Punto 4: no sobre-suavizar los toques → NO APLICA

Los contactos salen de la trayectoria cruda, y el suavizado (ventana de 0,2 s)
solo actúa sobre lo pintado. No se ha tocado.

## 3. Lo que queda, y la única vía del plan que sale positiva

Quedan **46 vuelos con pasos imposibles pintados**. Casi todos tienen **una
sola fila aérea entre dos filas de suelo a 8-41 m en 0,13 s**: no son vuelos,
son **dos detecciones que no son el mismo balón**. Y la causa es que la
«señal 1» de `detectar_fases_aereas` (velocidad proyectada > 20 m/s) marca
como aéreo cualquier salto imposible, así que **un cambio de candidato se
disfraza de vuelo**.

**En píxeles se separan de forma limpia**, con 695 vuelos con las dos cajas:

| | n | salto (px) mediana | p90 | velocidad (px/s) mediana | p90 |
|---|---|---|---|---|---|
| extremos a >40 m/s | 44 | **539** | 1.331 | **2.105** | 10.001 |
| físicos (≤40 m/s) | 651 | 33 | 295 | 86 | 346 |

| umbral (px/s) | imposibles cazados | vuelos físicos afectados |
|---|---|---|
| 600 | 41 de 44 | 4,3 % |
| **1.000** | **38 de 44** | **1,4 %** |
| 1.500 | 28 de 44 | 0,2 % |

⇒ **Una puerta de continuidad EN PÍXELES (~1.000 px/s) separa un vuelo de
un cambio de candidato.** Es lo que el plan pedía —un tracker con estado y
puerta— pero en el espacio donde el vuelo no se amplifica, y sin necesidad de
Kalman. **No está construida**; BACKLOG 28. ⚠️ Los 9 «vuelos físicos» que
pillaría pueden ser también cambios de candidato: sin GT del balón no se
puede saber.

## La lección

Se propuso la solución que la investigación externa recomendaba para
«objetos pequeños y rápidos» —un modelo de movimiento— sin comprobar que el
síntoma viniera de ahí. Venía de **nuestro suavizado promediando a través
de un vuelo** y de **una interpolación por índice**. Y la señal estaba en el
propio CSV: **una fila que dice `es_real=1` tiene que coincidir con una
detección, y el 12,1 % no lo hacía.** Comprobar una etiqueta de «medido»
contra lo medido es la medida más barata del proyecto.

Y un segundo aviso: arreglar el primer bug **movió** el problema en vez de
quitarlo (69 → 272 pasos por las filas no reales; total 317 → 272). Mirar solo
las filas reales lo habría dado por cerrado con 248 → 0; el desglose por tipo
de fila mostró que faltaba el segundo bug.
