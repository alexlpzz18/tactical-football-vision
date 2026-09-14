# El 81 % de balón es en realidad un 58 %: hay un balón fantasma

29-ago-2026. **Corrección de un número que ya habíamos celebrado.**

> ⚠️ **Y la primera mitad se queda corta: la corrige la segunda.** Aquí se
> habla de UN fantasma y de un 58,3 %. Al barrer la imagen entera
> aparecieron **10 celdas de marcas del campo** y el número honesto bajó a
> **45,0 %** — el mismo que daba el frame entero. Salta a *"Segunda
> ronda"* si buscas la cifra buena.

## Lo que pasó

La pasada con el esquema mixto dio **14.550 frames con balón de 17.983
(80,9 %)**, contra el 53,4 % anterior. Se anunció como la mayor mejora que
ha tenido el balón.

Al medir la posesión salió algo raro: los instantes SIN dueño estaban a
**12,4 m de mediana** del jugador más cercano, y su x mediana era 46,4 m
—el fondo del campo—. Un balón a 12 m de todo el mundo es sospechoso.

## El control que lo destapó

Partiendo las detecciones por franja de campo:

| x (m) | n | salto entre muestras | conf | lado |
|---|---|---|---|---|
| 0-25 | 1.627 | 0,30 m | 0,62 | 22,1 px |
| 25-35 | 2.679 | 0,25 m | 0,68 | 15,7 px |
| 35-45 | 3.180 | 0,21 m | 0,66 | 11,3 px |
| **45-55** | **5.050** | **0,02 m** | **0,54** | **4,9 px** |
| 55-62 | 963 | 0,19 m | 0,64 | 9,7 px |

Un "balón" que **no se mueve** (0,02 m contra 0,20-0,30), mide **4,9 px**
—por debajo del muro de 7,1 px del detector anterior— y tiene la
confianza más baja.

Agrupando por posición en la imagen, el veredicto:

```
( 370,  620) px :  7799 detecciones  (96,7 % de las sospechosas)
```

**Un único punto fijo**, presente desde t=0 hasta t=1197 s, en 7.974
frames distintos. No es el balón: es un objeto estático del fondo que el
troceado de la franja ha empezado a ver.

## El número honesto

| | frames | % |
|---|---|---|
| caché | 17.983 | |
| con detección plausible | 13.633 | 75,8 % |
| de esos, **solo el fantasma** | 3.144 | 17,5 % |
| **con balón de verdad** | **10.489** | **58,3 %** |

El esquema mixto sigue siendo una mejora grande y real —**de 45,2 % a
58,3 %** tras el filtro de plausibilidad, +13 puntos— pero **no es el
81 %**.

## La buena noticia: la posesión aguanta

El fantasma está a 12 m de todos, así que **nunca llega a tener dueño** y
no contamina el reparto:

| | con fantasma | sin fantasma |
|---|---|---|
| posesión de A (radio 3 m) | 39,0 % | **38,7 %** |
| cobertura | 34,3 % | 34,8 % |

0,3 puntos. El número de posesión era robusto sin que lo supiéramos.

## Por qué no lo quitó la guarda que existe para esto

`seleccionar_balon_activo` tiene exactamente este propósito: *"los balones
parados lejos del juego se descartan aunque el detector esté segurísimo"*.
No lo quita — el 30,6 % de los balones activos son el fantasma, también
pasándole las posiciones reales de los jugadores (se comprobó: el primer
intento le pasó un diccionario vacío, y ese resultado no valía).

La condición es `desplazamiento < 0,05 m` **Y** `distancia al jugador más
cercano > 25 m`. El fantasma cumple la primera (0,02) pero está a **12,4 m**.

Y el umbral de 25 m es, medido, **prácticamente inalcanzable**:

| distancia del balón al jugador más cercano | % de instantes |
|---|---|
| > 10 m | 31,8 % |
| > 15 m | 23,0 % |
| **> 25 m** | **0,63 %** |
| máximo observado | 27,7 m |

En un campo de 62×40 con 14 jugadores, estar a 25 m de TODOS casi no
ocurre. **No es que la guarda falle: es que no puede dispararse.** Es
primo hermano de `cota_plantilla.activa` —un interruptor que nadie lee— y
de la guarda ortográfica: parece que protege, y no protege.

⚠️ Pendiente de arreglar, y **no adoptado todavía**: bajar el umbral
tocaría producción y hay que medirlo contra las dos patas. La alternativa
más limpia no es tocar el 25 m sino añadir la señal que sí separa: un
candidato **anclado al mismo píxel durante minutos** no es un balón,
mida lo que mida su distancia a los jugadores.

## La lección

El esquema mixto se adoptó con un criterio correcto —47/47 huecos del
fondo cerrados, control intacto— y aun así introdujo un falso positivo
masivo que ese criterio **no podía ver**: el comparador medía huecos
CERRADOS y balones CONSERVADOS, no balones INVENTADOS en sitios donde
antes no había nada.

La columna `distractores` existía para eso y estaba en 1,59 candidatos por
frame; se leyó como ruido inofensivo. Lo era para la posesión, y no lo era
para el titular.

**Un criterio de adopción que solo mira lo que quieres mejorar no ve lo
que rompes.**

---

# Segunda ronda: el filtro, y la revisión de las adopciones

29-ago-2026, tarde.

## No era un fantasma: eran las MARCAS DEL CAMPO

Barriendo todas las celdas de 12×12 px del caché: **10 celdas concentran
11.982 detecciones, el 56,4 % del total**, con dispersiones de 0,6 a
3,2 px. La celda mediana del caché tiene **2** detecciones.

Mirando los recortes del vídeo se ve qué son: **el punto central, el de
penalti y una mancha oscura junto al muro del fondo**. Tienen tamaño y
color de balón, y el troceado de la franja se los presenta a la red lo
bastante grandes como para que dispare.

### Dos señales que parecían buenas y NO valen (negativos)

1. **Coexistencia** — *"el balón no está en dos sitios a la vez"*, que ya
   es un principio del proyecto para identidades. Aquí está **contaminada**:
   los propios fantasmas coexisten entre sí, así que el balón bueno sale
   "fijo" por coincidir con ellos. Daba 10 de 10, incluido el balón real
   del punto central (74,2 %).
2. **Racha continua** — un objeto del fondo debería estar siempre. Se
   detecta de forma intermitente: las rachas más largas son de 14-19 s,
   indistinguibles de un balón parado en una falta.

Lo que separa es lo aburrido: **acumular cientos de detecciones en la
misma celda a lo largo del partido**.

## El resultado, y es duro

| | frames con balón | % |
|---|---|---|
| caché crudo del mixto | 14.550 | 80,9 % |
| tras plausibilidad | 13.633 | 75,8 % |
| **tras quitar las marcas** | **8.098** | **45,0 %** |
| *(el caché anterior, frame entero)* | *8.137* | *45,2 %* |

**El esquema mixto no añadió balón: añadió marcas.** Por zonas, lo que
sobrevive al filtro: cerca 100 %, medio 60 %, **fondo 23 %**. En el fondo
—que es justo lo que el mixto venía a arreglar— **el 77,2 % era marca**.

Lo que compró de verdad, medido: de las 9.273 detecciones reales, solo
**1.382 (14,9 %)** miden menos de 7,1 px, o sea que solo las ve el
troceado. Y los frames donde SOLO hay balón pequeño —los que el frame
entero perdería— son **658, el 3,7 % del partido**.

**Y los 47/47 huecos cerrados se cerraron con marcas.** Las marcas 1-5
están en campo x 38-47 e imagen y 624-656; los huecos del fondo
arrancaban en y 590-642. El mismo sitio.

Controles de que el filtro no se pasa de frenada:

- lo quitado mide **4,9 px de mediana** (p90 5,8); el balón real mide
  10-27 px según la zona;
- lo que queda se mueve a **0,30 m por muestra**, como un balón (antes
  había tramos a 0,02);
- la posesión se mueve 2 puntos (39,0 → 41,0 %) y la cobertura baja de
  34,3 % a 32,1 %.

## La guarda de los 25 m, arreglada

Distancia del balón REAL (ya sin marcas) al jugador más cercano:

| | m |
|---|---|
| mediana | 1,6 |
| p95 | 8,3 |
| p99 | 17,2 |
| **máximo** | **25,7** |

El umbral estaba en **25 m: por encima de casi todo lo observado**. Ahora
sale de la **anchura del campo** (un cuarto): 10 m en fútbol 7, 16 en un
F11 de 64 m de ancho. Eso sí viaja a otro partido.

Efecto medido: sobre el caché crudo el umbral nuevo descarta 3.468 frames
—o sea que **ya puede dispararse**—, y sobre el caché ya limpio de marcas
solo toca 32, o sea que **no se come balón bueno**.

Con test propio que no comprueba el valor sino que **la guarda llega a
actuar** con datos plausibles. Era lo que faltaba.

## Revisión de las adopciones recientes del balón, con el ojo nuevo

*¿Qué podría estar inventando esto?*

| adopción | qué inventa | estado |
|---|---|---|
| **esquema mixto** | marcas del campo como balón | **DESTAPADO: 56 % del caché.** Su ganancia real es del 3,7 % de frames, no del 28. Decisión de Alex pendiente |
| **relleno de huecos parados** | posiciones donde no se midió | Acotado: 377 frames, marcados `es_real=False`, y no entra en contactos (se calculan antes) ni en la posesión (que lee el caché). Riesgo bajo |
| **franja derivada** | dónde trocear | Si se equivoca, trocea césped vacío. Tiene guarda: error si la franja pasa del 80 % del alto |
| **catálogo arbitral por observación** | árbitros donde hay jugadores | Ya medido en su día: 1 jugador sacrificado de 814. Sigue siendo el tipo de cosa que hay que re-mirar |

## Lo que hay que decidir

El esquema mixto cuesta **29 min de GPU contra ~6** y aporta **3,7 puntos
de frames con balón**. No está claro que compense, y la comparación justa
—el mismo filtro de marcas aplicado a un caché de frame entero— no se
puede hacer porque ese caché se sobrescribió. Es una decisión de Alex, y
la medición que la resolvería es una pasada de `entero` sobre el mismo
vídeo.
