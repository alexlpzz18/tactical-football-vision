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
