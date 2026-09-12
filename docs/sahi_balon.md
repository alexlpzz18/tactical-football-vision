# SAHI en el balón: 47 de 47, y la costura no era la culpable

29-ago-2026.

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

De ahí `BANDA_LEJOS = (540, 720)`: 5-6 tiles en vez de 24.

⚠️ **La banda está calibrada para esta cámara.** En otro partido hay que
recalcularla, y lo suyo es sacarla de la homografía —proyectar la línea de
x=45 m y coger margen— en vez de dejarla fija. Está pendiente. Una banda
heredada de otro encuadre trocearía césped vacío y dejaría el fondo sin
trocear, y el informe no se quejaría.

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
elegido. Es el siguiente instrumento.

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
