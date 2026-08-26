# El árbitro: los cinco criterios fallan, y no compensa perseguirlo

*26-ago-2026. Reproducir: `python scripts/arbitro_criterios.py`.*

⚠️ **El GT del benjamín NO anota al árbitro** (14 tracks: 12 jugadores y 2
porteros). Solo el de Villaviciosa lo tiene (track 22). Así que la
medición contra verdad de posición solo se puede hacer en una pata.

## Los tres criterios de Alex, medidos: los tres fallan

| criterio | puesto del árbitro | él | el mejor jugador |
|---|---|---|---|
| dispersión longitudinal (max−min de x) | **14º de 23** | 20,9 m | 32,7 m |
| desviación típica de x | **18º de 23** | 4,6 m | 7,5 m |
| mediana cerca del centro | **11º de 23** | 11,3 m | 0,2 m |
| entre los dos porteros | empatado | 100 % | **20 de 22 jugadores también al 100 %** |

El árbitro **se mueve MENOS** que la mayoría de los jugadores, no más. Y
"entre los dos porteros" no discrimina nada: los porteros definen un
intervalo que ocupa casi todo el campo, así que todo el mundo está
dentro.

## Y dos señales alternativas mías, también fallan

| señal | puesto del árbitro |
|---|---|
| ¿de qué bloque es? \|d(centroide A) − d(centroide B)\| / suma | 7º de 23 |
| distancia al vecino más cercano (estar solo) | 11º de 23 |

Los jugadores salen MÁS equidistantes de los dos bloques que el árbitro, y
los que están más solos son los porteros.

## Por qué fallan: la ventana

Los tres criterios de Alex hablan de un **partido entero** —"recorre el
campo de área a área"— y la ventana medida son **50 segundos**. En 50 s el
árbitro no cruza el campo: sigue al balón, que se queda en una zona,
mientras un lateral sí hace una carrera larga. Puede que los criterios
sean ciertos en 90 minutos; con lo que hay no se puede saber, y no se
adopta lo que no se puede medir.

## Pero, sobre todo: no compensa

Coste de contar al árbitro como un jugador más, medido sobre el GT de
Villaviciosa metiéndolo en cada equipo:

| | centroide | anchura |
|---|---|---|
| árbitro colado en el equipo A (12 jugadores) | **0,41 m** | **0,00 m** |
| árbitro colado en el equipo B (10 jugadores) | **0,61 m** | **0,00 m** |
| *para comparar: error del sistema hoy* | *3,55 m* | *3,81 m* |
| *para comparar: suelo de ruido de esa pata* | *0,83 m* | *1,25 m* |

**El daño está POR DEBAJO del suelo de ruido de la pata**, y es una
séptima parte del error actual. Perseguir al árbitro no paga.

### Y explica por qué el entrenador sí pagaba

El entrenador (regla del staff lento) valía 0,68 m de media de centroide
y **0,57 m de anchura**; el árbitro vale 0,41-0,61 m y **cero** de
anchura. La diferencia no es que uno sea más "no jugador" que el otro:

> **Lo que rompe el bloque es estar en el BORDE, no ser un no-jugador.**

Un entrenador en la banda estira el rectángulo; un árbitro en medio del
juego se mezcla con la nube de jugadores y apenas mueve la media. Es la
misma lección que la descomposición del centroide: la basura costaba el
61 % del error de anchura porque estaba en los extremos.

## Estado

Línea **cerrada por ahora**, con dos salidas si alguna vez interesa:

1. **Un tramo más largo con GT.** Los criterios de dispersión necesitan
   minutos, no segundos. Habría que anotar al árbitro en un tramo de
   varios minutos — y en el benjamín, anotarlo por primera vez.
2. **El catálogo de equipaciones**, que es lo único que ha funcionado: en
   el benjamín caza al árbitro a nivel de identidad (583 observaciones,
   verde flúor → 'otro'). En Villaviciosa no lo caza, y su color está a
   0,60-0,94 de los prototipos, solapando el 50 % con los jugadores.

Lo siguiente del tercer grupo es el **staff**, que además ya tiene media
regla hecha y cuyo daño sí está medido y es grande.

---

# El enfoque correcto era DESCARTAR, no identificar

*26-ago-2026, corrección de Alex. Reproducir: `python scripts/censo_otros.py`.*

No hay que encontrar al árbitro entre 23 candidatos: hay que contar y
descartar. Dentro del campo hay tres grupos, y en "otros" deberían quedar
tres personas —los dos porteros, ya identificados con 8 de 8, y el
árbitro—. Mismo principio que la exclusividad un-portero-por-área.

## El censo: el embudo funciona mucho mejor de lo que temíamos

| filtro | benjamín | Villaviciosa |
|---|---|---|
| todas las identidades | 67 | 79 |
| ni A ni B | 30 | 8 |
| + dentro del campo (geométrico) | 4 | 4 |
| + quitando los porteros | **2** | **2** |
| + quitando el staff | 2 | 2 |
| + con ≥25 observaciones | **2** | **2** |

El filtro geométrico es el que hace el trabajo pesado: en el benjamín
tira 26 de 30 (público, árboles proyectados a 176 m, entrenadores). No
quedan quince: quedan **dos**, en las dos patas.

## Quiénes son las dos, y el error de lectura que casi cometo

| pata | id | obs | **casadas con el GT** | mediana | qué es |
|---|---|---|---|---|---|
| benjamín | 28 | 493 | **1** | (31,0 · 24,0) | *"jugador"* → **es el ÁRBITRO** |
| benjamín | 1 | 204 | **0** | (24,3 · 22,2) | no es del GT |
| Villaviciosa | 67 | 136 | 27 | (66,3 · 33,8) | **árbitro** |
| Villaviciosa | 40 | 110 | 22 | (49,2 · 28,9) | jugador |

⚠️ La identidad 28 del benjamín salía etiquetada "jugador" y **eso se
apoyaba en UNA sola observación casada de 493**. Con 493 observaciones en
el centro exacto del campo, verde flúor (H=62, S=248), es el árbitro —
coincide con la descripción que ya estaba en el config. Lo delató añadir
la columna de observaciones casadas: **un dueño mayoritario sobre 1 voto
no es un hecho.**

## Y la vía sale gratis, con un parámetro que ya existía y estaba apagado

La segunda identidad de Villaviciosa (id 40, 110 obs, centro del campo) es
literalmente **el bug que ya estaba anotado** en `arbitro.py`: un jugador
que el catálogo roba porque su color se aparta del prototipo de su equipo.
El arreglo estaba escrito y en off: `arbitro.margen_equipo`.

| margen | benjamín: quedan | Villaviciosa: quedan |
|---|---|---|
| 0,00 | 2 | 2 |
| 0,50-0,60 | 2 | **1 (el árbitro)** |
| **0,65-0,75** | **1 (el árbitro)** | **1 (el árbitro)** |
| 0,80-0,90 | **0** (se pierde) | 1 (el árbitro) |

**Con `margen_equipo` entre 0,65 y 0,75, en las dos patas queda
exactamente el árbitro.** Villaviciosa tiene meseta ancha (0,50-0,90); el
benjamín, una ventana estrecha de tres puntos con acantilado en 0,80. El
centro común es **0,70**.

Coste en producto:

| pata | margen | mediana | media | p90 | anchura | ocupación |
|---|---|---|---|---|---|---|
| benjamín | 0,00 | 1,30 m | 1,64 m | 3,25 m | 0,64 m | 4,0 % |
| benjamín | **0,70** | 1,30 m | 1,64 m | 3,25 m | 0,64 m | 4,0 % |
| Villaviciosa | 0,00 | 3,55 m | 3,87 m | 6,42 m | 3,81 m | 9,0 % |
| Villaviciosa | **0,70** | 3,65 m | 3,95 m | 6,53 m | 3,81 m | 9,5 % |

Idéntico en el benjamín; en Villaviciosa se mueve 0,10 m, **muy por
debajo de su suelo de ruido (0,83 m)**, así que no es interpretable como
degradación — pero tampoco mejora. Por el criterio de adopción no entra
solo: es decisión de Alex.

## Estado

- El árbitro **sale por eliminación** en las dos patas, sin necesidad de
  ninguna señal de comportamiento. Los cinco criterios medidos antes
  siguen siendo negativos, pero ya no hacen falta.
- Lo que lo hace posible no es una regla nueva: es el **filtro geométrico**
  (que ya está) más **`margen_equipo: 0.70`** (que ya estaba escrito y
  apagado).
- Sigue valiendo menos que el suelo de ruido, así que no se ha invertido
  más de lo que costaba.
