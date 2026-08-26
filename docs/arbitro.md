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
