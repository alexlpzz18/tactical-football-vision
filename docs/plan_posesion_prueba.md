# Prueba #4: posesión barata en el alevín B (plan, 27-nov-2026)

Escrito y commiteado ANTES de que Alex etiquete. Rama `alevinb-preparacion`. Sin tocar el detector ni
la producción: solo el CSV de posiciones (con SigLIP) y las candidatas en bruto del balón.

## Qué se etiqueta

3:00-6:00 del archivo `alevinb_p1.mp4`, con la página `outputs/etiquetado_posesion/index.html`: Alex
marca el instante en que empieza cada fase, con cuatro etiquetas: **verde / blanco / disputa /
parado-fuera**. La verdad de cada ventana (4 s y 6 s, sin solape) es la fase con más tiempo dentro.

## Indicadores (parámetros congelados en `scripts/posesion_prueba.py`)

| | qué es |
|---|---|
| T1 | siempre el equipo con más tiempo de posesión en las etiquetas (trivial) |
| T2 | el equipo con más jugadores en la mitad del balón (última posición conocida; trivial) |
| I1 | voto del más cercano al balón a ≤ 2,5 m; ventana sin votos ⇒ la anterior |
| I2 | HMM de 2 estados (verde/blanco), Viterbi, coste de cambio 6 nats a 12,5 muestras/s |
| I3 | HMM de 3 estados (verde/blanco/muerto), coste de muerto 24 nats; balón muerto por jugadores lentos (< 1 m/s: +2; 1-1,4: +1; > 2: −1) y balón fuera del campo (+4) |
| I4 | I3 + empuje colectivo sin balón (0,5 nats por m/s de diferencia de velocidad hacia la portería rival) |

Del repositorio público `404-Possession-Not-Found` (sin licencia: se reimplementa, no se copia) se
toman el decodificador de 3 estados con costes de cambio y dos de sus pistas de balón muerto. Se
descarta su detector de toques: pide ~0,44 s seguidos de balón observado y en 3:00-6:00 solo hay 9
rachas así. Sus 90 rasgos y su modelo entrenado, no (decisión de Alex).

**Dos cambios a las pistas de referencia, hechos ANTES de ver etiquetas** (solo mirando la salida del
propio indicador, no la verdad):
1. Fuera la pista «balón sin ver > 2 s»: allí faltaba el balón el 41 % del tiempo; aquí el 83 %, así
   que salta siempre (con ella el modelo marcaba «parado» el 53 % del tramo).
2. Filtro de candidatas QUIETAS (≥ 25 apariciones a ± 3 px en ± 10 s). Con la cámara estable a 0,22
   px, algo que repite píxel durante segundos es un objeto parado. El 49 % de las candidatas del tramo
   lo son, todas fuera del campo (la principal, un balón junto a la banda cercana en (33, −3) m, 550
   apariciones); dentro del campo, ninguna. Sin el filtro, el 39 % de los fotogramas tenía «balón
   fuera». Con los dos cambios, el modelo de 3 estados marca «parado» el 21 % del tramo.

## Criterios

**Éxito** (Alex, 26-nov): en ventanas con posesión (verdad verde o blanco), **acierto ≥ 80 %** con
algún indicador I1-I4, **y claramente por encima de T1 y T2** (al menos +10 puntos sobre el mejor de
los dos). Se informa con ventanas de 4 y 6 s; vale si cumple en las dos.

Se informa también (no decide; pedido por Alex el 27-nov):
- el reparto del TIEMPO del tramo por fase según las marcas, en particular **qué % es «disputa»**;
- el acierto en todo el juego vivo contando la disputa (los modelos de 2 y 3 estados nunca dicen
  «disputa», así que ahí fallan siempre);
- **precisión y recall de «parado/fuera»** por ventanas (I3/I4): la precisión dice si el modelo
  corta juego vivo, el recall si se le escapa balón parado hacia las métricas.

**¿Qué podría estar inventando?** Un indicador puede acertar por inercia si un equipo tiene la
posesión casi todo el tramo: por eso T1. Y puede acertar por la geometría (el que ataca tiene más
gente en esa mitad) sin ver el balón: por eso T2. Si uno de los dos se queda a menos de 10 puntos,
el indicador no aporta.

Un solo tramo de 3 minutos es poco: si cumple, es una señal para ampliarlo, no una adopción.
