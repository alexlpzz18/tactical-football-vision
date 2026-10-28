# Los cambios de color que quedan, y vistas agregadas de la pizarra (28-oct-2026)

Rama `vistas-agregadas`, sale de `pizarra-dibujo`. Sin código de producción: todo en `scripts/`.
Los datos solo se leen. Criterios escritos y commiteados ANTES de medir. A `main` solo va
documentación.

Relojes: archivo; reproductor = archivo + 1:33.

## 1. Los ~31 cambios de color por minuto que quedan con histéresis de 1 s (14:00-15:30)

**Medida (la de Alex)**:
- sobre la pizarra `outputs/pizarra_dibujo/histeresis_1s.html`, con el mismo simulador a 10 Hz;
- **salto de posición** en cada cambio de color: la distancia entre la posición de la ficha en la
  muestra anterior y en la siguiente al cambio (0,1 s). Mediana y p90.
- **Criterio (el de Alex)**: si el salto mediano es **< 0,5 m**, son cambios de etiqueta EN EL
  SITIO, no asociación, y la explicación «ficha pasando de una persona a otra» no vale.

⚠️ **Aviso antes de medir**:
- Una identidad cambia de persona en un CRUCE, cuando las dos personas están juntas.
- Además la posición de la ficha va suavizada (~2 s) e interpolada.
- Así que un cambio de persona también da un salto pequeño en 0,1 s: el umbral de 0,5 m no
  distingue «etiqueta en el sitio» de «asociación» por construcción.
- Se informa el criterio tal cual, y además un **control fijado ahora**, que sí separa las dos
  cosas:
  - **rival cerca**: en el instante del cambio, ¿hay otra ficha VISIBLE del equipo contrario a
    < 2 m?
  - Se compara con la tasa base: la misma pregunta en todas las muestras visibles de fichas de
    equipo del tramo.
  - Si el cambio está **enriquecido ≥ 2×** en rival cerca, apunta a cruces (asociación o recorte
    mezclado). Si está cerca de 1×, apunta a la etiqueta fallando sola.
- Y, también fijado ahora: el **salto a 1 s** (la posición 0,5 s antes y 0,5 s después del cambio),
  que verá mejor un cambio de persona que se separa después.

## 2. Vistas agregadas (prototipo, sin tocar los datos)

**Entrada**:
- el CSV de `main` (`outputs/diagnostico_26oct_b/posiciones_main.csv`), filas reales dentro del
  campo (0-62 × 0-40 m);
- equipo por fila: A = {A, portero_A}, B = {B, portero_B}, la etiqueta por observación.
- Sin identidades.

**(a) Series de tiempo por equipo, por frame**:
- **centroide** (media de x, y);
- **anchura** (extensión en y);
- **altura de la línea defensiva** = distancia a SU portería de la media de los **2 jugadores de
  campo más retrasados** (sin el portero; F7). A defiende x = 62 y B defiende x = 0
  (`configs/team_classification_benja.yaml`, `equipo_mx_alto: A`).

**(b) Posiciones medias por ventana** de 10 s, 1 min y 5 min, como imagen estática sobre el campo:
- sin identidades no hay «la posición media del jugador 7». Se usa la **forma media del equipo**:
  KMeans con k = 7 sobre todas las posiciones de ese equipo en la ventana (k = 7 = jugadores en
  F7, portero incluido);
- más el centroide de la ventana.

**Ventanas**:
- en el tramo 14:00-15:30: 10 s, 1 min (y los 90 s enteros);
- en los 20 min: 10 s, 1 min y 5 min.

**Evaluación contra el GT de 30 s** (frames 9750-10635, 5:25-5:55 del archivo, 60 frames a
0,5 s):
- las mismas cuentas sobre el GT (posición del pie, equipo del GT, porteros por su etiqueta) y
  sobre el sistema EN ESOS frames;
- error del **instante**: por frame y equipo, |centroide sistema − GT| (euclídea), |anchura| y
  |línea defensiva|; mediana y p95;
- error **a 10 s**: 3 ventanas × 2 equipos = 6 valores, la media de la ventana contra la media del
  GT; máximo y media;
- **forma media a 10 s**: los 7 centros del sistema contra los 7 del GT, casados 1-a-1 (Hungarian);
  distancia media. Se informa, sin umbral;
- **1 min y 5 min NO se pueden evaluar**: el GT dura 30 s. Se dice así.

**Criterio (el de Alex)**: a 10 s, **centroide ≤ 1 m y anchura ≤ 1,5 m**, en el MÁXIMO de las 6
ventanas-equipo, porque con 6 valores un p95 no significa nada. La línea defensiva se informa sin
umbral.

**Coste de CPU**: tiempo de pared de las series y de las formas de los 20 min, sin contar el dibujo
de las imágenes, en este Mac.

¿Qué podría estar inventando?
- 3 ventanas de 10 s del minuto 5: el criterio se juzga sobre 6 números. El oráculo del 28-oct (d/e)
  decía que a 10 s el error de ETIQUETA ya cumple. Esto mide el sistema entero (etiqueta +
  presencia + posición), que es más.
- Las filas que faltan (el encuadre) mueven el centroide: el GT anota a quien Alex ve, y el sistema
  pierde a quien no detecta.
- KMeans depende de la semilla: semilla fija (0) y n_init 10.

---

# Resultados

`python scripts/vistas_agregadas.py cambios` y `… vistas` → `outputs/vistas_agregadas/`. El CSV de
datos sale con el mismo SHA-256 antes y después.

## 1. Los cambios que quedan con histéresis de 1 s: son de ETIQUETA, no de asociación

| | resultado |
|---|---|
| cambios de color | 47 en 90 s = 31,3/min (reproduce el 28-oct) |
| **salto en 0,1 s** (p50 · p90) | **0,21 · 0,38 m** |
| salto en 1 s (0,5 s antes → 0,5 s después) | 2,25 · 3,71 m |
| rival a < 2 m en el instante del cambio | 21,3 % |
| rival a < 2 m, tasa base | 13,9 % |
| **enriquecimiento** | **1,53×** (< 2×) |

- **Criterio de Alex: salto mediano 0,21 m < 0,5 m → son cambios de etiqueta en el sitio.**
- **Mi explicación «ficha pasando de una persona a otra» NO vale y se retira.**
- El control fijado antes de medir dice lo mismo: los cambios no se concentran en los cruces
  (1,5×, por debajo de 2×). La etiqueta cambia sola, sostenida > 1 s, con la ficha sin moverse de
  su sitio.
- El salto a 1 s (2,25 m) no separa nada: un jugador recorre unos 2 m en 1 s.
- ¿Qué podría estar inventando? Con 47 cambios, el enriquecimiento tiene ruido: 1,5× podría ser
  1,2-2×. Y «etiqueta en el sitio» no dice si el color NUEVO es el bueno: la ventana de 1,5 s de
  esa identidad pasa a votar el otro equipo durante > 1 s, y sin GT en este tramo no se sabe cuál
  de los dos acierta.
- **Lo que queda abierto**: por qué la etiqueta por observación cambia de forma sostenida sin
  cruce. Candidatos ya medidos que no lo explican solos: caja fundida (28-oct c/f) y puerta de
  calidad de caja (0 de 11).

## 2. Vistas agregadas

**Coste de CPU** (este Mac, 20 min): series **7,5 s**; formas a 10 s, 1 min y 5 min **7,8 s**.
Unos 15 s en total, más el dibujo de las imágenes. El proceso entero tardó 29 s.

**Contra el GT de 30 s** (5:25-5:55 del archivo, 6:58-7:28 del reproductor):

| | instante (p50 · p95) | a 10 s (máx. · media de 6) |
|---|---|---|
| centroide | 0,62 · 4,31 m | **2,57** · 1,03 m |
| anchura | 0,45 · 4,01 m | **1,56** · 0,62 m |
| línea defensiva | 0,44 · 3,68 m | 2,24 · 0,65 m |

- **Criterio (centroide ≤ 1 m y anchura ≤ 1,5 m a 10 s, en el máximo): NO CUMPLE.**
- **Por ventana**:
  - 4 de las 6 ventanas-equipo cumplen el centroide;
  - lo rompe sobre todo la **tercera ventana (5:45-5:55), equipo A**: 2,57 m de centroide y 2,24 m
    de línea defensiva. Es el «tercio 3» ya documentado (`desglose_por_episodios.md`): filas
    desplazadas, error del sistema entero, no de la etiqueta;
  - y la primera del B (1,38 m de centroide, 1,56 m de anchura), con 0,65 jugadores de menos por
    frame.
- En media, a 10 s, el centroide (1,03 m) roza el umbral y la anchura (0,62 m) lo cumple sobrado.
- El oráculo del 28-oct (d/e) decía que con SOLO el error de etiqueta, 10 s bastaba. Esto mide el
  sistema entero (presencia y posición), y no basta en un episodio malo.
- **Forma media a 10 s** (los 7 centros contra los 7 del GT, casados 1-a-1): 0,95-5,39 m de
  distancia media. Sin umbral; se ve en las imágenes que la forma es reconocible en las ventanas
  buenas.
- **1 min y 5 min no se pueden evaluar**: el GT dura 30 s.

**Las imágenes** (`outputs/vistas_agregadas/`):
- `tramo_14_00_15_30_series.png`
- `tramo_14_00_15_30_formas_10s.png` y `_formas_60s.png`
- `partido_20min_series.png`
- `partido_20min_formas_10s.png`, `_60s.png` y `_300s.png`
- y `series_20min.csv`.
- El campo de las formas NO va espejado como la pizarra (`espejar: y`): y = 0 abajo.

## Código

`scripts/vistas_agregadas.py`, en la rama `vistas-agregadas`, sin fusionar. A `main`, solo este
informe.
