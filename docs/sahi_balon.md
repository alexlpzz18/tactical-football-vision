# SAHI en el balón: 47 de 47, y la costura no era la culpable

29-ago-2026.

> ⚠️ **La primera mitad de este documento está SUPERADA por la segunda.**
> Se deja tal cual porque el camino importa, pero al leerla: la franja ya
> no es `BANDA_LEJOS = (540, 720)` —se deriva de la homografía— y el
> esquema adoptado es el MIXTO, no el 3×5. Salta a *"Segunda ronda"*.

## El resultado que cierra el fondo

Medido sobre los 47 huecos del fondo (x ≥ 45 m, huecos de 1-8 s), con 4
frames por hueco y 60 frames de control:

| | huecos cerrados | control |
|---|---|---|
| frame entero (imgsz 1280) | **0 de 47** | 60 de 60 |
| SAHI 3×5 solape 0,15 | **47 de 47** | 56 de 60 |

Confirma el muro de 7,1 px de `docs/huecos_de_balon_gt.md`: **todo lo que
dábamos por perdido en el fondo era resolución de entrada**, no oclusión
ni falta de etiquetas. Coste: 123 min de pasada frente a los minutos del
frame entero.

## NEGATIVO: la costura entre tiles no explica los 4 perdidos

Hipótesis de Alex, razonable: los 4 balones que SAHI pierde caen en la
juntura entre dos tiles, así que subir el solape los recuperaría.

**Refutada analíticamente, sin gastar GPU.** El conjunto de control es
determinista (`random.Random(0)`), así que se puede reproducir exactamente
y comprobar con la función de troceado real de SAHI
(`sahi.slicing.get_slice_bboxes`) si cada balón cabe entero en algún tile:

| rejilla | solape | tiles | tile px | balones partidos |
|---|---|---|---|---|
| 2×3 | 0,15 / 0,25 / 0,35 | 12-15 | 640×540 | **0 / 0 / 0** |
| 3×5 | 0,15 / 0,25 / 0,35 | 24-40 | 384×360 | **0 / 0 / 0** |
| 4×6 | 0,15 / 0,25 / 0,35 | 35-54 | 320×270 | **0 / 0 / 0** |

Cero en las nueve combinaciones, y el motivo es de escala: la banda de
solape de la rejilla de producción mide **57 px** y el balón del control
**10,5 px de mediana, 13,3 el mayor**. Tendría que ser cuatro veces más
grande para llegar a una costura.

⚠️ Barrer el solape habría gastado GPU para volver con tres puntos
iguales. Es el mismo principio de siempre —*comprobar que un barrido da
puntos DISTINTOS*—, solo que aplicado ANTES de lanzarlo.

La causa de los 4 hay que buscarla en otro sitio, y el candidato es la
variación de escala: SAHI reescala cada tile a `imgsz`, así que el balón
llega a la red a un tamaño distinto que en el frame entero y su confianza
cambia. Por eso el comparador ahora **lista los frames perdidos con su
confianza**: si son los del filo, no es la rejilla.

## Lo que cambió en el instrumento

`--comparar-sahi` compara ahora varios ESQUEMAS sobre los mismos frames,
decodificando el vídeo una sola vez, y reporta por cada uno: huecos
cerrados, control conservado, **qué frames pierde**, distractores,
candidatos por frame y coste.

Lo de "qué frames pierde" no es un adorno: **un recuento no deja
diagnosticar**. "56 de 60" no dice si los 4 eran los más flojos o los más
lejanos; la lista con su confianza, tamaño y posición, sí.

## La franja: el esquema mixto es horizontal, no vertical

Idea de Alex: frame entero donde el balón es grande, tiles solo donde es
pequeño.

Su primera forma —mitad cercana contra mitad lejana— **no funciona**,
medido: un corte VERTICAL no separa nada, porque el fondo del campo ocupa
el 60 % del ancho de la imagen (p1-p99 de 421 a 1587 px). Un corte en
x=900 px cubriría solo el 65 % del fondo y arrastraría el 46 % de lo
cercano.

Lo que sí separa es la ALTURA, porque con la cámara elevada la distancia
se traduce en altura en la imagen:

| zona | y p1 | y p50 | y p99 | lado mediano |
|---|---|---|---|---|
| cerca (<20 m) | 773 | 901 | 1068 | 26,9 px |
| medio (20-45) | 637 | 694 | 818 | 15,0 px |
| lejos (>45) | 599 | **626** | 666 | 10,5 px |

La correlación entre altura en la imagen y tamaño del balón es **+0,924**.
Es perspectiva, no estadística.

Y los 47 huecos del fondo arrancan todos entre y=590 y y=642, así que:

| banda a trocear | % del alto | huecos dentro | balones <12 px dentro |
|---|---|---|---|
| y 560-700 | 13 % | 100 % | 93 % |
| **y 540-720** | **17 %** | **100 %** | **100 %** |
| y 500-800 | 28 % | 100 % | 100 % |

De ahí una primera banda fija de 540-720: 5-6 tiles en vez de 24.

⚠️ **Esa banda estaba calibrada para esta cámara**, y era el tipo de
número que no viaja entre partidos. **Ya no existe**: se deriva de la
homografía (ver la segunda ronda). Se deja escrito porque el aviso fue
antes que el arreglo, y porque el fallo que evitaba sigue siendo real —
una banda heredada de otro encuadre trocearía césped vacío y dejaría el
fondo sin trocear, sin que el informe se quejara.

## Lo que este instrumento TODAVÍA no mide

El balón ACTIVO. Alex tiene razón en que 1,59 candidatos por frame no dice
nada por sí solo y que lo que decide es si el seleccionado sigue siendo el
correcto — pero `seleccionar_balon_activo` **agrupa por continuidad
espacial entre frames consecutivos**, y los 248 frames de esta comparación
están desperdigados por 20 minutos. Corriéndolo aquí no mediría el
selector: mediría el vacío.

Lo que sí hay mientras tanto es un proxy honesto, la columna
`distractores`: candidatos plausibles a más de 40 px del balón bueno, en
los frames de control donde sabemos cuál es. Son exactamente los que
pueden despistar al selector.

La medida de verdad necesita un TRAMO CONTIGUO (30-60 s que contenga
huecos del fondo), pasarlo entero con cada esquema y comparar el balón
elegido. Es el siguiente instrumento (BACKLOG 18), y puede salir del
piloto de 5 min, que ya tiene caché.

## Guardas

`tests/test_comparador_esquemas.py`. El fallo que vigilan: el esquema
mixto trocea una franja RECORTADA, así que sus cajas salen en coordenadas
de la franja; sin sumarles el `y0` caen fuera del campo, el filtro de
plausibilidad las tira y el informe diría tan tranquilo que el esquema
mixto cierra 0 huecos. **Un negativo falso sobre una idea buena es peor
que no medirla.**

Verificadas mutando el código: quitar el `y0`, quitar la deduplicación y
trocear el frame entero en vez de la franja hacen fallar cada uno a su
test.

⚠️ Y una lección del propio test de mutación: la primera vez, la mutación
del deduplicado salió "7 passed" y parecía que el test no se disparaba. No
era eso — **el reemplazo no coincidía** por la indentación (8/12 contra
12/16) y la mutación fue un no-op. Un test de mutación sin comprobar que
el fichero CAMBIA no prueba nada, exactamente igual que el `str.replace`
que se comió black en el generador de la hoja de GT.

---

# Segunda ronda: por qué trocear la imagen entera PIERDE detecciones buenas

29-ago-2026, tras el barrido de esquemas.

## El resultado

| esquema | huecos del fondo | control | coste |
|---|---|---|---|
| frame entero | 0/47 | 60/60 | — |
| SAHI 3×5 | 47/47 | 56/60 | 123 min |
| **MIXTO franja** | **42/47** | **60/60** | **29 min** |

**Adoptado el mixto** (`balon.esquema: mixto`).

## La causa de lo que pierde el 3×5: el postproceso, no la rejilla

Las pistas de Alex: las confianzas de los perdidos (0,67 · 0,59 · 0,70 ·
0,74) están **en la mediana del control (0,69)**, no en el filo; y 2×3 y
4×6 pierden **los mismos frames exactos**. Causa común a trocear, no de la
rejilla.

Lo es, y se demuestra sin modelo. Dos hechos:

1. `get_sliced_prediction` lleva **`perform_standard_pred=True`** por
   defecto: SAHI **ya corre el frame entero** y lo fusiona con los tiles.
   Su conjunto de candidatos es un SUPERCONJUNTO del frame entero, así que
   no puede perder una detección suya... salvo en la fusión.
2. La fusión es `GREEDYNMM` con métrica **`IOS`** (intersección sobre la
   caja MENOR), umbral 0,5. Con IOS, **una caja grande que contiene al
   balón da 1,00**, aunque sea otro objeto.

Ejecutado sobre dos cajas sintéticas —el balón (10×10, conf 0,69) dentro
de una caja grande y floja (150×120, conf 0,42)—:

```
IoU real : 0,0056      IOS : 1,0000   ← por encima del umbral
GREEDYNMM/IOS  → queda 1: [950, 580, 1100, 700] con score 0,69
NMS            → queda 1: [1000, 620, 1010, 630] con score 0,69
GREEDYNMM/IOU  → quedan 2
```

**No lo suprime: le cambia la geometría.** Se queda con la confianza del
balón y las coordenadas del impostor. Esa caja proyecta a decenas de
metros, el filtro de plausibilidad la tira y la detección desaparece — con
su confianza intacta, que es exactamente lo que Alex observó.

Por qué el mixto no sufre: el frame entero se ejecuta **aparte**
(`_detectar_frame_entero`, sin postproceso de SAHI) y sus cajas se añaden
PRIMERO; lo de la franja solo se suma si no solapa, y con **IoU real** al
0,3, no con IOS. Una caja grande ya no puede tragarse al balón.

⚠️ **ESTO APUNTA AL DETECTOR DE JUGADORES**, que usa SAHI 2×4 con los
mismos defaults. Un jugador dentro de una caja grande —un grupo, una
portería, una sombra— daría IOS = 1,00 y desaparecería igual. Y hay un
síntoma esperando explicación: el **recuento de jugadores sale corto**
(5-6 contra 7-8). No está medido que sea esto; está medido que el
mecanismo existe. Va al backlog.

## Corrección (1-oct-2026): la regla NO es "confianza de la pequeña, geometría de la grande"

Releído el código real instalado (`sahi==0.12.1`,
`sahi/postprocess/combine.py` + `_numpy_backend.py` + `utils.py`, no de
memoria) y confirmado con las dos cajas sintéticas de arriba más un caso
invertido:

```python
GreedyNMMPostprocess(match_threshold=0.5, match_metric="IOS")(
    [balon(score=0.69), impostor(score=0.42)]
)  # → score=0.69, bbox=impostor   (coincide con lo documentado)

GreedyNMMPostprocess(match_threshold=0.5, match_metric="IOS")(
    [balon(score=0.30), impostor(score=0.75)]
)  # → score=0.75, bbox=impostor   (NO coincide con "confianza intacta")
```

La regla real, leída en `_numpy_backend.py::greedy_nmm_from_matrix` +
`utils.py::merge_object_prediction_pair`:

1. Las cajas se procesan en orden de **score descendente**
   (`_score_tiebreak_order`). La caja que sobrevive (`keep_ind`) de cada
   grupo fusionado es **siempre la de mayor confianza del grupo**, sea
   grande o pequeña.
2. El score final es `max(score1, score2)` (`get_merged_score`) — que por
   construcción del punto 1 es **el score que ya tenía la que sobrevive**.
   No es "la confianza del balón" por ser el balón: es la confianza de
   quien gane el pulso de score, y el balón solo gana ese pulso en el
   ejemplo documentado porque 0,69 > 0,42.
3. La geometría final es la **UNIÓN** de las cajas (`calculate_box_union`,
   envolvente mínima), no literalmente "la caja grande". Coincide con la
   caja grande solo cuando esta contiene por completo a la pequeña — que
   es el caso típico de una marca fija o un grupo tragándose al balón o a
   un jugador, así que en la práctica el ejemplo documentado sigue siendo
   representativo.

**Lo que cambia de verdad**: si alguna vez el candidato intruso (una
marca, un grupo, una sombra) tiene **más** confianza que el objeto real
—el caso invertido de arriba—, el resultado hereda la confianza ALTA del
intruso, no la confianza "intacta" del objeto real. Es un caso **peor**
que el documentado: pasa cualquier filtro de confianza con más margen,
no menos. No está medido cuánto pesa este caso invertido en el partido
real (haría falta cruzar scores reales balón-vs-marca para saberlo); solo
está confirmado que el mecanismo lo permite y que la frase "con su
confianza intacta" generaliza mal más allá del ejemplo con el que se
escribió.

No cambia la decisión del esquema mixto (sigue sin pasar por este
postproceso en la franja) ni invalida la medición de huecos cerrados.
Si cambia algo del BACKLOG 19 (IOS vs IOU en jugadores) queda por decidir
con Alex antes de seguir.

## Los 5 huecos que el mixto no cierra: el balón se sale de la franja

Con la franja fija 540-720, tres de los 47 huecos se pierden a y≈600 y
**reaparecen a y=786, 761 y 755**: el balón viene hacia la cámara durante
el hueco y sale de la banda por abajo.

| banda | % del alto | huecos con los dos extremos dentro | tiles |
|---|---|---|---|
| 540-720 (la fija) | 17 % | 44/47 | 5 |
| 500-760 | 24 % | 45/47 | 5 |
| 534-805 (**derivada**) | 25 % | **47/47** | 5 |

Ensanchar sale casi gratis porque el reescalado de cada tile lo manda el
ANCHO (1280/384 = 3,3×), no el alto: la franja puede crecer hacia abajo
sin que el balón llegue más pequeño a la red ni sin añadir tiles.

## La franja, derivada de la homografía (BACKLOG 17, hecho)

`src/balon/franja_lejana.py`. Ya no hay ningún 540-720 en el código.

**Negativo por el camino**: lo primero que se probó fue derivarla del
TAMAÑO del balón, con el jacobiano de la homografía prediciendo el
diámetro en píxeles de una esfera de 0,22 m. **No reproduce lo medido**:

| banda y | predicho | medido | error |
|---|---|---|---|
| 560-650 | 4,8 px | 10,7 px | −55 % |
| 700-800 | 10,1 px | 16,4 px | −38 % |
| 900-1080 | 18,9 px | 30,6 px | −38 % |

Y el sesgo ni siquiera es constante (×2,2 arriba, ×1,6 abajo). **La caja
del detector no es el balón**: la inflan el desenfoque de movimiento y el
tamaño mínimo práctico de caja. Un umbral en píxeles derivado así estaría
mal calibrado de una forma distinta en cada cámara.

Lo que sí es geometría pura, sin constantes empíricas, es qué parte de la
imagen ocupa una franja del CAMPO. La regla adoptada:

> franja = proyección de `x ≥ zona_min − margen_campo_m`, subida por
> arriba lo que ocupan `altura_aerea_m` según la escala local.

Los dos márgenes tienen sentido futbolístico, que es lo que los hace
viajar: **20 m** porque durante un hueco el balón viene hacia la cámara
(medido: tres huecos reaparecen 150 px más abajo), y **3 m** porque un
despeje sube, y un balón en el aire aparece más arriba que su proyección
de suelo. Para el benjamín da **534-805**, que cubre 47/47 y el 100 % de
los balones de menos de 12 px, con el 25 % del alto y 5 tiles.

Guarda nueva: si la franja derivada ocupa más del 80 % del alto, **da
error en vez de devolverla**. Devolver la imagen entera sería trocearlo
todo creyendo que se ahorra, y nadie se enteraría hasta ver la factura.

## Un solo interruptor

`balon.sahi.activo` ya no existe: lo sustituye `balon.esquema`
(`entero` | `sahi` | `mixto`), y un config que todavía traiga `activo`
**para el script** en vez de ignorarlo. Dos interruptores para una cosa es
`cota_plantilla.activa` otra vez.

La firma del checkpoint lleva ahora el esquema y la franja: sin eso,
reanudar un caché empezado con otro esquema mezclaría dos detectores
dentro del mismo fichero.

## Verificación del 1-oct-2026: ¿el caso "peor" de la corrección de arriba ya muerde?

Tras corregir el mecanismo de GREEDYNMM (arriba: la confianza final es la
de quien gane el score, no la de la caja pequeña por ser pequeña), Alex
pidió cruzar los scores reales de las 10 marcas conocidas contra los del
balón real en los mismos instantes, para saber si el caso invertido
—la marca puntuando más que el balón— es teórico o ya está pasando.

**Script**: `scripts/marcas_vs_balon_score.py`, reutilizando el pipeline
real (`src.balon.carga`, `seleccionar_balon_activo`) para que "el balón
real de ese frame" sea el mismo que usa producción, no un criterio
inventado para la medida.

**Resultado, sobre la parte entera (`cache_balon_p1.pkl`)**:

| | score p10 | p50 | p90 | n |
|---|---|---|---|---|
| candidatos de MARCA (crudos, antes del filtro) | 0,38 | 0,50 | 0,62 | 11.982 |
| balón REAL seleccionado por producción | 0,43 | 0,64 | 0,75 | 8.086 |

En mediana el balón real puntúa más que las marcas (0,64 contra 0,50),
pero las colas se solapan: **14,7 % de los instantes de balón real
tienen, dentro de ±1,0 s, al menos un candidato de marca con MÁS
confianza que el balón en ese momento** (1.192 de 8.086). **No es solo
teórico.**

⚠️ **Lo que esto NO dice, para no leerlo de más**: que la marca puntúe
más alto en un instante CERCANO no significa que GREEDYNMM los fusionara
de verdad — para eso además hacen falta las cajas solapando por encima
del umbral IOS (0,5), y el balón real rara vez está físicamente ENCIMA de
una marca salvo en el caso ya documentado y aceptado (saque de centro,
penalti). Esto mide la PRECONDICIÓN (confianza) sobre candidatos ya
separados por el filtro de marcas, no una fusión confirmada caja a caja.
Sirve para decir "el riesgo es real, no de laboratorio", no para
cuantificar cuántas fusiones concretas ya han pasado.

## Las dos métricas de adopción nuevas (`src/balon/metricas_adopcion.py`)

Construidas y con tests (`tests/test_metricas_adopcion.py`, 8 casos). Las
pidió Alex explícitamente para que "huecos cerrados" deje de ser el único
criterio: un sistema puede dar 0 huecos y estar enganchado 300 frames a
una marca, que es justo lo que pasó la primera vez con el mixto.

- **`duracion_maxima_anclada`**: no necesita GT, es una propiedad de la
  trayectoria de SALIDA. El tramo continuo más largo sin salir de un
  radio de 1 m, cortando también por huecos de detección largos. Sobre
  el `v3` actual: **5,3 s** — una parada de juego razonable, nada
  alarmante.
- **`fraccion_en_marcas`**: sobre el `v3` actual da **0,00 %**, como
  tiene que ser — el filtro de marcas ya las quita ANTES de que
  `seleccionar_balon_activo` elija una, así que la salida no puede
  aterrizar en una celda de marca por construcción. El valor es útil
  como GUARDA DE REGRESIÓN para cualquier cambio futuro al pipeline
  (el selector condicional del punto 5, por ejemplo): si algún día deja
  de ser 0, algo ha vuelto a dejar pasar una marca.

⚠️ **Es solo la MITAD de lo que pidió Alex**, y hay que decirlo: el
`static-lock ratio` que describió tiene dos partes — "cae en una marca"
Y "mientras el balón real está en otra zona". La segunda mitad necesita
saber dónde está el balón real, y **no hay GT de posición de balón en
el proyecto** (ni en `gt_benja/` ni en `ground_truth_tracking/`, que solo
anotan `player` y `referee`; `scripts/oraculo_balon.py` ya lo decía en
su propio docstring). `fraccion_en_marcas` mide solo si el OUTPUT cae en
una marca, sin poder confirmar si el balón real estaba realmente en otro
sitio en ese instante. Es una cota superior del problema, no la métrica
completa: un valor alto no prueba el fallo (podría ser el coste aceptado
de un balón real posado en la marca), pero un valor bajo sí lo descarta.

## BLOQUEADO por falta de GT: los puntos 2 (recall completo), 4 y 5 del plan de Alex

Comprobada la premisa antes de construir nada más (como pide
`CLAUDE.md`): **no existe en el proyecto ningún GT de posición de balón**
—ni coordenadas de píxel ni de metros, en ningún frame. Esto bloquea,
tal y como estaban planteados, tres de los cinco pasos que pidió Alex:

- **Punto 2 (recall@K de candidatos crudos contra el GT)**: no se puede
  calcular "en qué posición del ranking queda el candidato correcto" sin
  saber cuál es el candidato correcto. Lo que SÍ se pudo hacer sin GT —el
  cruce de scores marcas-vs-balón de arriba— está hecho y es la pieza que
  más importaba de este punto.
- **Punto 4 (señal de diferencia-de-fondo en frames sin candidatos)**:
  "mide si esos máximos caen cerca del balón real" es, otra vez, recall
  contra una posición que no existe en ningún fichero del proyecto.
- **Punto 5 (selector condicional)**: depende de que el punto 2 muestre
  un hueco real de recall, que no se ha podido medir.

**No se ha construido nada de esto.** La vía para destrabarlo es
etiquetar un GT de posición de balón, aunque sea pequeño — con la
herramienta que ya existe para huecos concretos
(`scripts/gt_huecos_balon.py`) o una nueva más simple que solo pida un
clic por frame en una muestra de 30-50 frames repartidos entre
"candidato bajo encontrado" y "cero candidatos". Es la decisión de Alex:
si vale la pena ese etiquetado ahora, o si se deja documentado y cerrado
aquí como los otros negativos del proyecto.
