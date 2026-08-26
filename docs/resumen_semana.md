# Dónde estamos frente a dónde empezamos

*Semana del 25-26 de agosto de 2026. Rama `experimento/asociacion-global`.*

## Las métricas de producto

| pata | estado | centroide (mediana) | media | p90 | anchura | ocupación |
|---|---|---|---|---|---|---|
| **benjamín** | antes | 1,30 m | 1,89 m | 4,77 m | 0,74 m | 4,6 % |
| | **ahora** | **0,97 m** | **1,43 m** | **3,39 m** | **0,40 m** | **2,8 %** |
| | | **−25 %** | **−24 %** | **−29 %** | **−46 %** | **−39 %** |
| **Villaviciosa** | antes | 3,55 m | 3,87 m | 6,42 m | 3,81 m | 9,0 % |
| | ahora | 3,55 m | 3,85 m | 6,34 m | 3,81 m | 9,0 % |

Y las observaciones con el equipo equivocado en el benjamín: **15,5 % → 3,2 %**.

⚠️ **Villaviciosa no se mueve**, y hay que decirlo tan claro como lo otro:
casi todo lo que ha pagado esta semana es específico del caso del
benjamín —entrenadores en la banda, público del campo de al lado, líneas
del área, color por recorte fiable—. Allí no hay nada de eso, o el color
no permite explotarlo. De las seis cosas adoptadas, cuatro son neutras en
Villaviciosa y ninguna la degrada.

## Lo que se adoptó, y por qué cada una

| cambio | qué arregla | benjamín | Villaviciosa |
|---|---|---|---|
| **staff lento** (fuera de la línea Y < 2,75 m/s, hasta 1,5 m *dentro*) | el entrenador de la banda, fragmentado en tres | anchura −54 % | neutro |
| **portero por ÚLTIMO HOMBRE** con dos salvaguardas | el `id 55`: un jugador de campo coronado portero | empate, pero 8/8 en el caso negativo | empate |
| **`n_init: 50`** en el KMeans del fit | el ruido de Villaviciosa: cobertura ±0,047 → ±0,003 | idéntico | quita el ruido |
| **un solo árbitro** (exclusividad, sin umbral) | el catálogo robando un naranja | idéntico | idéntico |
| **`min_obs_lejos_m: 6`** | el señor del campo de al lado, 4 detecciones | media −0,06 m | idéntico |
| **anchura implícita ≥ 0,15** (plausibilidad física) | la línea del área pequeña, 81 detecciones | mediana −25 %, anchura −38 % | mejora p90 |
| **etiqueta por observación** *(solo benjamín)* | naranjas pintados de blanco | centroide 1,30 → 0,36 m | **lo empeora: no se activa** |

## Lo que se midió y se RECHAZÓ

- **El híbrido por profundidad**: era un artefacto del eje equivocado.
- **El doble pase por colores**: destroza a los porteros.
- **El tercer grupo definido por color** (tercer intento): las
  distribuciones se pisan en Villaviciosa.
- **Los cinco criterios de comportamiento del árbitro**: el árbitro se
  mueve MENOS que la mayoría de jugadores en 50 s.
- **`margen_equipo`**: adoptado y revertido el mismo día — la ventana se
  mueve con el detector.
- **El filtro físico de altura y los máximos**: quitan cientos de
  detecciones y no cambian nada.
- **La ventana temporal en Villaviciosa**: ninguna variante viaja.

## Las cinco lecciones de método

1. **Una guarda que CUENTA no puede detectar un fallo de IDENTIDAD.** La
   guarda del tercer grupo daba el visto bueno con el árbitro dentro de
   un equipo. Y al día siguiente cazó otro bug mío.
2. **Un dueño mayoritario sobre 1 voto no es un hecho.** La identidad del
   árbitro salía etiquetada "jugador" por UNA observación de 493.
3. **Dos señales débiles que juntas son fuertes.** El staff lento, las
   salvaguardas del portero y el árbitro único tienen la misma forma:
   ninguna señal separa sola, pero cada impostor falla al menos una.
4. **Elegir el CENTRO de la meseta, no el valor que va justo.** Y si no
   hay meseta común entre patas, el parámetro no existe.
5. **Los umbrales van pegados al detector.** `margen_equipo` funcionaba a
   0,68 con un caché y destrozaba con otro del mismo partido.

## La deuda que queda

- **El config por partido** (`por_observacion` solo en el benjamín): un
  cliente nuevo necesitaría que alguien decida por él. Con un tercer
  partido hay que volver a buscar el selector automático.
- **El árbitro no se abstiene**: sin árbitro en el tramo corona a alguien
  que ya estaba fuera del cómputo. Idea barata sin construir: exigirle un
  mínimo de velocidad.
- **Villaviciosa sigue en 3,55 m** de centroide, y su suelo de ruido es
  0,83. Lo que la mueva no está en estas reglas.
- **Las mediciones en cuarentena** de `docs/suelo_de_ruido.md` se hicieron
  con `n_init: 10` y habría que repetirlas.
