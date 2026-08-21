# Tests de oráculo: dónde está el margen, medido (20-ago-2026)

Rama `experimento/asociacion-global`. `scripts/oraculos.py`.

Se sustituye una etapa por su versión perfecta —usando el GT del
benjamín— y se mira cuánto sube el resultado. Un mes decidiendo por
intuición dónde estaba el margen; esto lo mide.

## Resultado

Error contra el GT en **métricas de producto** (mediana sobre los
fotogramas del GT):

| variante | nIds | centroide | anchura | profundidad |
|---|---|---|---|---|
| SISTEMA (línea base) | 84 | **1,55 m** | 0,93 m | 1,48 m |
| + contacto: clics CRUDOS | 84 | 2,57 m | 1,02 m | 1,46 m |
| + contacto: clics CORREGIDOS | 84 | 1,61 m | 1,03 m | 0,03 m* |
| **+ oráculo de ASOCIACIÓN** | **14** | **0,42 m** | **0,33 m** | 1,02 m |
| + asociación y contacto | 14 | 0,00 m* | 0,00 m* | 0,03 m* |

\* circular: el GT se construye con esos mismos clics corregidos, así que
la profundidad y el caso conjunto salen cero por construcción. Sirven de
comprobación de que el montaje es coherente, no de medida.

## Lectura: el margen está en la ASOCIACIÓN, no en el anclaje

**Arreglar la asociación divide el error de centroide por 3,7** (1,55 →
0,42 m) y el de anchura por 2,8. Y baja de 84 identidades a 14, que es el
número real de personas.

**Arreglar el anclaje no mejora el centroide**: 1,55 → 1,61 m con los
clics corregidos, y a peor (2,57 m) con los crudos. La anchura tampoco
(0,93 → 1,03).

Eso es un dato duro contra la prioridad que traía la segunda opinión: el
anclaje por pose ataca un sesgo que **las métricas colectivas apenas
notan**, porque un desplazamiento sistemático de todos los jugadores en
la misma dirección **mueve el centroide pero no deforma el bloque**, y ni
siquiera mueve mucho el centroide si el sesgo es parecido para todos.

## Dos limitaciones del oráculo de contacto, dichas claras

1. **Solo altera 1 de cada 5 fotogramas del caché.** El GT está a 1 de
   cada 15 y el caché a 1 de cada 3, así que en el 80 % de los fotogramas
   el anclaje sigue siendo el borde de la caja. El efecto medido es una
   **cota inferior**.
2. **No existe un anclaje "perfecto" disponible.** Los clics crudos
   llevan el sesgo hacia arriba (marcaron el cuerpo, no el suelo) y los
   corregidos se derivaron de las cajas. No hay tercera fuente — y por eso
   la medición en PÍXELES contra RTMPose es la vía correcta para zanjarlo,
   como propuso Alex.

## Un bug que delató un resultado implausible

La primera pasada daba el oráculo de contacto **16,9 m peor** que el
sistema. Eso no es un hallazgo, es un fallo: el conversor a CVAT numera
los tracks 0..N−1 por orden de `jugador`, así que `obj_id` **no** es el
número de jugador. Cada detección recibía la posición de otro niño.

Sin el reflejo de desconfiar de un número imposible, la conclusión habría
sido "el anclaje por pose empeora el producto" — falsa, y habría cerrado
la línea por el motivo equivocado.

## Qué queda por medir de este punto

- **Oráculo de homografía**: no se me ocurre una aproximación honesta con
  los datos actuales. Haría falta una referencia independiente de la
  propia homografía (un objeto estático de posición conocida). Queda
  abierto y no bloquea nada.

---

# PUNTO 3: ¿cuánta contaminación mete nuestra propia puerta? (20-ago-2026)

`scripts/pureza_sin_reentrada.py`. Se desactiva la re-entrada —buffer a
cero, cada reaparición abre tracklet nuevo— y se mide la pureza contra el
GT del benjamín.

| buffer de re-entrada | tracklets | puros | % puros | **pureza obs** | frag. |
|---|---|---|---|---|---|
| **0,0 s (SIN re-entrada)** | 30 | 13 | 43 % | **84,4 %** | 2,1 |
| 0,5 s | 25 | 10 | 40 % | 80,0 % | 1,8 |
| **1,5 s (el adoptado)** | 24 | 9 | 38 % | **80,1 %** | 1,7 |
| 3,0 s | 23 | 9 | 39 % | 78,1 % | 1,6 |

(14 personas reales en el GT)

## Dos lecturas, y la segunda reordena el punto 4

**1. Nuestra puerta mete poca contaminación: 4,3 puntos.** De 84,4 % sin
re-entrada a 80,1 % con el buffer adoptado. A cambio baja la
fragmentación de 2,1 a 1,7 tracklets por persona. El intercambio es
razonable y el buffer se queda.

**2. Y esto es lo importante: SIN re-entrada la pureza sigue siendo solo
84,4 %, y apenas el 43 % de los tracklets son puros.** O sea que **la
mezcla ocurre mayoritariamente DENTRO del seguimiento continuo** —en los
cruces, fotograma a fotograma— y no en las reapariciones.

Es un resultado incómodo: la puerta de re-entrada, que es donde hemos
invertido las últimas semanas, ataca 4 puntos mientras 16 vienen de otro
sitio.

## Consecuencia directa para el punto 4

**Un grafo global que solo UNA tracklets no puede alcanzar el oráculo.**
El oráculo de asociación (centroide 0,42 m) supone identidad perfecta
*por observación*; los tracklets que entrarían al grafo ya vienen
contaminados en un 16 %, y unir bien piezas sucias no las limpia.

Así que el diseño del punto 4 tiene que ser **partir y unir**, no solo
unir:

1. **Partir** los tracklets contaminados (clustering de embeddings dentro
   de cada uno — que es exactamente lo que hace GTA-Link, cuyo algoritmo
   es MIT aunque su checkpoint no sirva).
2. **Unir** globalmente los trozos limpios con el grafo.

En ese orden. Sin el primer paso, el segundo tiene un techo del 84 %.

---

# 4a: PARTIR los tracklets con la apariencia (20-ago-2026)

`src/tracking/partir_tracklets.py` + `scripts/medir_particion.py`.

No con DBSCAN sobre embeddings sueltos, sino con **detección de punto de
cambio**: en una identidad, un intercambio de persona es un cambio
ORDENADO EN EL TIEMPO, no un grupo cualquiera. Se busca el instante que
maximiza la distancia entre la firma de antes y la de después.

La salvaguarda contra el cuarto negativo del proyecto: se compara la
**media de una ventana**, nunca un embedding suelto, y solo se corta en el
mejor punto de cada tracklet.

## Primera tabla — y por qué NO se puede leer tal cual

| variante | tracklets | puros | % puros | pureza obs | frag. |
|---|---|---|---|---|---|
| sin partir (base) | 24 | 9 | 38 % | 80,1 % | 1,7 |
| umbral 0,04 | 83 | 62 | 75 % | **91,3 %** | 5,9 |
| umbral 0,06 | 55 | 37 | 67 % | 89,4 % | 3,9 |
| umbral 0,08 | 35 | 18 | 51 % | 87,8 % | 2,5 |
| umbral 0,10 | 24 | 9 | 38 % | 80,1 % | 1,7 |
| umbral 0,13 | 24 | 9 | 38 % | 80,1 % | 1,7 |

Parece que gana 0,04 con +11 puntos de pureza. **Es falso**, y por la
misma trampa que ya nos pilló con la accuracy de equipos: **la pureza
premia fragmentar.** Un trozo de una sola observación es 100 % puro por
definición. A 0,04 el cortador está troceando casi al máximo permitido.

## El control que lo zanja: cortar en puntos AL AZAR

Mismo número de cortes, colocados al azar:

| umbral | por apariencia | al azar | **ventaja real** |
|---|---|---|---|
| 0,04 | 91,3 % | 88,3 % | **+3,0** |
| 0,06 | 89,4 % | 84,3 % | **+5,1** |
| **0,08** | 87,8 % | 81,8 % | **+6,0** |

**La señal de apariencia aporta ~6 puntos de pureza, no 11.** El resto era
trocear.

Y el óptimo se invierte: **gana 0,08**, el umbral que MENOS corta, porque
es el que mejor aprovecha cada corte. Cortar más añade fragmentación sin
comprar pureza real.

## Punto de operación y lo que le deja al grafo

Con **umbral 0,08**: 24 → 35 tracklets, pureza **80,1 % → 87,8 %**,
fragmentación de 1,7 a 2,5 por persona. El coste de fragmentación que
Alex pidió medir en vez de asumir: **×1,5**, no ×3,5 como sugería el
umbral agresivo.

**El grafo recibirá piezas con ~88 % de pureza, no 100 %.** Ese es su
techo real, y conviene tenerlo delante antes de construirlo: el oráculo
de asociación (centroide 0,42 m) supone identidad perfecta por
observación, y desde 88 % no se llega ahí solo uniendo.

El 12 % que la apariencia no ve son, previsiblemente, los cruces entre
compañeros del mismo equipo — el caso #43, donde dos niños con la misma
equipación tienen embeddings casi iguales. Es el techo estructural que ya
estaba anotado.
