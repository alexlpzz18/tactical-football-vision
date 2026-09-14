# El 81 % de balón es en realidad un 58 %: hay un balón fantasma

29-ago-2026. **Corrección de un número que ya habíamos celebrado.**

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
