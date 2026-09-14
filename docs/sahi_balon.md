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
