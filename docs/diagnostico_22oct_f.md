# Diagnóstico 22-oct (f): dónde se mezclan las identidades, el segundo «otro», Villaviciosa, balón en la pizarra

Rama `fix-22oct-f`, sale de `fix-22oct-e`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque. Producción solo cambia tras flag (apagado = idéntico a `main`, comprobado byte a byte).

Relojes del vídeo del benjamín: el del ARCHIVO y el del reproductor de Alex (+1:33).

---

## Bloque A — ¿dónde se mezclan las identidades? (solo medición)

**Etapas**: se capturan las salidas de las funciones de PRODUCCIÓN mientras corre
`procesar_desde_cache`, interceptándolas sin cambiarlas. Así no hay un montaje paralelo que
pueda divergir.
1. salida de ByteTrack (`asociar_con_bytetrack`);
2. tras la puerta de re-entrada (`aplicar_puerta_reentrada`; parte, no une). Se añade porque está
   entre las dos que pide el bloque;
3. tras el cosido por pureza (`coser_por_pureza`);
4. tras el post-proceso (`postprocesar`: suavizado + interpolación), filas reales e interpoladas.

*Control del montaje*: la etapa 4 tiene que reproducir las posiciones del CSV de producción.

**Pureza** (GT de 30 s del benjamín; Villaviciosa, el suyo de 60 s):
- en cada frame del GT, las observaciones de la etapa se casan 1-a-1 a ≤ 2 m con las personas del
  GT (húngaro, sin árbitro en el benjamín);
- pureza de una identidad = fracción de sus observaciones casadas que son de su persona
  mayoritaria;
- pureza global = Σ mayoritarias / Σ casadas;
- se reporta la impureza (1 − pureza) por etapa y cuánta añade cada una.

**Cambios de persona**: dentro de una identidad, dos observaciones casadas CONSECUTIVAS (frames del
GT seguidos) de personas distintas. Cada cambio se localiza (un cambio puede tener varias marcas):
- **cerca**: las dos personas están a < 2 m en el frame del cambio o en el anterior;
- **borde de tesela SAHI**: el centro de la caja de la observación del cambio está a ≤ 20 px de
  un borde interior de tesela (2 × 4 teselas [⚠️ son 15, 5 × 3: ver el resultado], solape 0,2, la geometría de `get_slice_bboxes` de
  SAHI);
- **unión de cosido**: las dos observaciones son de tracklets distintos de la identidad (etapas
  3-4), o de identidades distintas de ByteTrack que el cosido unió;
- **tras hueco > 1 s**: entre las dos observaciones de la identidad pasa más de 1 s;
- **sin marca**: ninguna de las anteriores.

**Qué etapa genera la mayor parte de la impureza**: la diferencia de impureza entre etapas
consecutivas.

**Control (azar)**: la misma pureza si, en cada frame, las personas casadas se repartieran al azar
entre las identidades presentes (semilla 0, 20 repeticiones). La medida tiene que estar muy por
encima de ese suelo.

¿Qué podría estar inventando? El casado a 2 m: una fila desplazada 2-5 m (bloque 4 del 22-oct d) no
se casa y no cuenta, así que la impureza medida es la de las filas BIEN COLOCADAS.

## Bloque B — el segundo «otro» es un jugador

- **B1.**
  - En la ventana del GT: cuántos frames tienen otro ≥ 2 (filas reales) y, si los hay, qué persona
    del GT es el «otro» extra, qué arquetipo del catálogo por observación dispara y de qué identidad
    es.
  - Si la ventana no tiene casos (el 22-oct d midió 0 con todas las filas), se mide sin GT en el
    partido entero, sobre las filas `otro` que NO son del árbitro (proxy fijado): de qué identidad
    de hoy son, qué arquetipo dispara (se recalcula la ventana de 1,5 s con la caché de color) y
    cuánto se concentran (cuántas identidades suman el 50 % y el 80 %).
- **B2.** Candidato tras el flag `arbitro.catalogo_requiere_identidad` (en el YAML de equipos,
  apagado). El catálogo por observación solo puede mandar una fila a `otro` si:
  - su IDENTIDAD lo dispara en ≥ 50 % de sus observaciones (mayoría), o
  - su TROZO (el tracklet de la identidad al que pertenece la observación) lo dispara en ≥ X %.

  Si no, la observación se etiqueta A/B como cualquier otra.

  **X se fija antes de medir los criterios.** Sobre los tracklets de hoy con ≥ 10 observaciones,
  se calcula la fracción que dispara en los tracklets del árbitro (> 50 % de detecciones del proxy)
  y en los demás (< 10 %):
  - si el p10 de los del árbitro supera al p90 de los demás, X es el punto medio;
  - si se solapan, X es el valor que minimiza las filas mal repartidas (las del árbitro por debajo
    de X + las de los demás por encima).
- **B3. Criterios** (benjamín, partido entero):
  - frames con otro ≥ 2 (filas reales): 12,2 % → **≤ 6 %**;
  - equipo equivocado en la ventana del GT: **≤ 1,5 %**;
  - árbitro dentro de un equipo en la ventana del GT: **≤ 53,5 %**.

  **Control**: la misma regla con las fracciones de disparo PERMUTADAS entre identidades (y entre
  tracklets), semilla 0. Si la regla usa de verdad la identidad, con el control el árbitro dentro
  de un equipo tiene que salir ≥ 10 puntos peor que con la regla real. Si no, el efecto no viene de
  la identidad.

## Bloque C — Villaviciosa, solo con la caché

- **C1.**
  - El 23,6 % de equipo equivocado, desglosado por persona del GT y por prototipo: errores y casadas
    por persona. ¿Pocas personas o difuso? Cuántas personas suman el 50 % y el 80 % de los errores.
  - Para cada persona, distancia de su color medio (caché) a su prototipo y al contrario.
  - ¿Qué es el prototipo A (amarillo, #ebe36e)? Composición de los recortes del fit que caen en el
    meta-grupo A, casados con el GT en su ventana: % árbitro / jugadores de A / jugadores de B /
    sin casar; y el color dominante de cada grupo.
  - El color REAL de cada equipación en PÍXELES con ffmpeg necesita el vídeo, que no está en local:
    **«no medido»**, y se deja preparado en la celda de Colab.
- **C2.**
  - El tope por identidad (intento 1 del 22-oct e) con el control de costes permutados, con 5
    semillas: ¿el 18,5 % sale siempre mejor que los permutados?
  - La etiqueta por observación en Villaviciosa: se busca si se probó (sí:
    `docs/foto_de_estado.md`) y se da la cifra de equipo equivocado con el protocolo de hoy,
    re-medida.
- **C3.** Por qué A > 11 en el 54,6 % de los frames. En la ventana del GT, cada fila A se casa
  (1-a-1, 2 m, con todas las personas del GT, árbitro incluido) y se clasifica: jugador de A,
  jugador de B (equipo equivocado), árbitro, o sin casar (duplicado / fantasma / fuera). Junto al
  recuento de personas del GT por equipo.

## Bloque D — balón: recorte al campo solo en la pizarra

- El flag `balon.recortar_a_campo` deja de tocar las posiciones del CSV: el recorte pasa al RENDER
  de la pizarra (`replay_tactico.generar_replay`), que hoy BORRA las posiciones fuera del campo. Con
  el flag, las filas de balón fuera se dibujan en el punto más cercano del rectángulo en vez de
  desaparecer; los jugadores no cambian.
- El CSV conserva las posiciones medidas (x_m, y_m sin tocar) y, con el flag, gana una columna
  `calidad_balon` en las filas de balón: `medida` / `aerea` / `rellena` / `fuera_del_campo`.
- Se ACTIVA en `configs/campo_benja.yaml`, a petición de Alex.

**Criterio**:
- flag apagado: CSV y HTML de la pizarra idénticos a `main`;
- encendido: posiciones del CSV idénticas, una columna más; en la pizarra, ninguna fila de balón
  desaparece por estar fuera y todas caen dentro del rectángulo; los jugadores, idénticos.

---

## Resultado del bloque A — ByteTrack genera ~80 % de la mezcla; se mezcla en los CRUCES

`scripts/diag22f_pureza.py`. *Control del montaje*: las posiciones de la etapa de post-proceso
reproducen el **100 %** de las filas del CSV de producción, en las dos patas.

| etapa | identidades | casadas | **impureza** | añade | pureza al AZAR (control) | cambios de persona |
|---|---|---|---|---|---|---|
| **benjamín** — ByteTrack | 1.126 | 736 | **18,07 %** | 18,07 | 16,4 % | 41 |
| + puerta de re-entrada | 1.126 | 736 | 18,07 % | 0,00 | 16,0 % | 41 |
| + cosido por pureza | 900 | 736 | 24,05 % | **+5,98** | 15,0 % | 46 |
| + post-proceso (CSV) | 900 | 733 | **22,78 %** | −1,27 | 15,3 % | 41 |
| **Villaviciosa** — ByteTrack | 147 | 1.599 | **12,57 %** | 12,57 | 15,4 % | 116 |
| + puerta | 147 | 1.599 | 12,57 % | 0,00 | 15,2 % | 116 |
| + cosido | 115 | 1.599 | 13,95 % | +1,38 | 14,6 % | 126 |
| + post-proceso (CSV) | 115 | 1.694 | **15,76 %** | +1,81 | 14,1 % | 147 |

- **La mayor parte de la impureza final la genera ByteTrack**: 18,1 de 22,8 en el benjamín (79 %)
  y 12,6 de 15,8 en Villaviciosa (80 %).
- El cosido añade el resto en el benjamín (+6,0) y poco en Villaviciosa (+1,4).
- La puerta de re-entrada no cambia nada en la ventana del GT.
- El control al azar da ~15 % de pureza: la medida (76-87 %) está muy por encima del suelo.

**Dónde cambian de persona** (% de los cambios con la marca, contra la tasa en TODOS los pares de
observaciones consecutivas de la misma identidad):

| marca | benjamín, ByteTrack | benjamín, CSV | Villaviciosa, ByteTrack | Villaviciosa, CSV |
|---|---|---|---|---|
| **otra persona a < 2 m** | **80,5 % vs 24,0** (×3,4) | 80,5 vs 25,3 | **62,1 vs 22,4** (×2,8) | 65,3 vs 24,5 |
| borde de tesela SAHI (≤ 20 px) | 22,0 vs 15,4 (×1,4) | 17,1 vs 15,4 | 94,0 vs **83,4** (×1,1) | 74,1 vs 79,2 |
| unión de cosido | — | 7,3 vs 0,6 | — | 2,0 vs 0,3 |
| tras hueco > 1 s | 2,4 vs 0,4 | 12,2 vs 0,8 | 6,9 vs 0,9 | 15,0 vs 3,1 |
| sin ninguna marca | 5 de 41 | 6 de 41 | 3 de 116 | 12 de 147 |

**Lectura:**
1. **El cambio de persona es un problema de CRUCES.** 4 de cada 5 cambios ocurren con otra persona
   a menos de 2 m, cuando eso solo pasa en 1 de cada 4 pares. Es lo de CLAUDE.md, «el 16 % se
   contamina dentro del seguimiento continuo, en los cruces», ahora localizado en la etapa:
   **ByteTrack**.
2. **Las teselas de SAHI no explican la mezcla.** En el benjamín la marca sale poco por encima de
   su tasa base (×1,4, 9 de 41 cambios). En Villaviciosa la geometría de SAHI (15 teselas sobre
   2.560 px) deja el 83 % de las cajas a ≤ 20 px de un borde: la marca no discrimina, y su 94 % no
   significa nada. ⚠️ La geometría real son **15 teselas (5 × 3)**, no 2 × 4: con solape 0,2,
   `get_slice_bboxes` añade columnas y filas.
3. **El cosido mezcla poco, pero mezcla en sus uniones**: en el benjamín, de sus 5 cambios nuevos,
   las uniones están 12× sobrerrepresentadas (7,3 % contra 0,6 %).

**¿Qué podría estar inventando?**
- **La pureza premia la fragmentación.** ByteTrack deja 1.126 identidades en el benjamín y el cosido
  900: una identidad partida en trozos es más pura por construcción. Parte del +6 del cosido es
  mezcla real (sus uniones están sobrerrepresentadas en los cambios) y parte es que al unir se mide
  sobre identidades más largas. El orden de magnitud (ByteTrack ~80 %) aguanta con cualquier
  reparto de esa parte.
- **Solo cuentan las filas casadas a ≤ 2 m**: una identidad que se va a una posición desplazada
  2-5 m no se casa y no suma impureza.
- **La «cercanía» es de las personas del GT**: un cruce que el GT no anota (el árbitro en el
  benjamín) no cuenta como «cerca».

---

## Resultado del bloque B — el segundo «otro» es un jugador DENTRO de una identidad de árbitro; el flag NO cumple

`scripts/diag22f_catalogo.py`.
- *Control*: el recuento de los disparos del catálogo hecho por el script (3.413) coincide exacto
  con el log de producción («3413 sacadas de los equipos por el catálogo arbitral»).
- *Flag apagado*: el CSV es idéntico byte a byte al de hoy.

**B1. En la ventana del GT no hay ningún frame con otro ≥ 2** (filas reales). En el partido entero,
en los 1.462 frames con otro ≥ 2, las 1.519 filas `otro` que NO son del árbitro (proxy):

| origen | filas |
|---|---|
| **una identidad entera del tercer grupo** (436, 129, 155, 26, 658, 814, 865) | **1.268 (83 %)** |
| catálogo por observación: `azul_electrico` | 142 |
| catálogo por observación: `verde_fluor` | 50 |
| `otro` sin que dispare el catálogo / otra identidad `otro` | 59 |

- **Concentrado, no difuso**: 3 identidades suman el 50 % y 5 el 80 % (436: 366 filas, 129: 335,
  155: 324, 26: 129, 468: 94).
- **Y esas identidades son QUIMERAS de árbitro**:
  - 436, 129 y 155 son árbitro en el 47 %, 52 % y 45 % de sus detecciones (proxy);
  - cuando son el «otro» extra, el árbitro de verdad está en ese mismo frame en OTRA identidad
    (292, o 129 y 155 alternándose), a una mediana de 5-10 m;
  - la 26 no es árbitro nunca (0 %): es una identidad de jugador o portero mandada entera a `otro`.
- `azul_electrico` (142) es el arquetipo que ya se sabía que caza al portero de A (camiseta negra).

⚠️ **Esto corrige la lectura del bloque 0 del 22-oct (e)**, donde «dos tercios de la simultaneidad
la crea el catálogo POR OBSERVACIÓN».
- Lo que aquel recuento contaba como «observación suelta» era, en la mayoría de esos frames, el
  ÁRBITRO sacado correctamente de una identidad de jugador.
- El `otro` sobrante era la otra fila: un jugador dentro de una identidad del tercer grupo.
- **El catálogo por observación acierta; lo que sobra es la mezcla de identidades.**

**X** (fijado antes de medir B3):
- de los tracklets con ≥ 10 observaciones, 6 son del árbitro y 371 de los demás;
- la fracción que dispara: p10 del árbitro 0,169 contra p90 de los demás 0,0. No se solapan, así
  que X = **0,084** (punto medio);
- 17 identidades A/B disparan en mayoría.

**B3** (benjamín, partido entero):

| | hoy | con la regla (X = 0,084) | control permutado | criterio |
|---|---|---|---|---|
| frames con otro ≥ 2 (filas reales) | 12,19 % | **11,60 %** | 4,53 % | ≤ 6 % → **NO** |
| equipo equivocado (ventana del GT) | 1,2 % | 1,2 % | 1,2 % | ≤ 1,5 % → sí |
| árbitro dentro de un equipo (ventana del GT) | 53,5 % | 53,5 % | **100 %** | ≤ 53,5 % → sí |
| observaciones que la regla deja en A/B | — | 117 | 2.966 | |

- **El control pasa**: con las fracciones permutadas el árbitro dentro de un equipo empeora 46,5
  puntos. La regla usa de verdad la identidad.
- Y el control enseña algo: su 4,5 % de otro ≥ 2 se consigue mandando al árbitro entero a los
  equipos (100 %). **Bajar el otro ≥ 2 no es evidencia si el árbitro se cuela.**
- **No cumple**: la regla solo toca 117 observaciones, porque el catálogo por observación no era la
  causa (B1).

**Decisión**: el flag queda **apagado** (`configs/team_classification_benja.yaml`,
`activo: false`, con X = 0,084 anotado). La causa del segundo `otro` es la del bloque A: identidades
que llevan a dos personas, aquí al árbitro y a un jugador, mezcladas en los cruces.

**¿Qué podría estar inventando?**
- «No es árbitro» es el proxy: si el proxy pierde detecciones del árbitro, parte de las 1.268 filas
  podrían ser él. Pero en esos frames el proxy SÍ marca al árbitro en otra identidad, a 5-10 m: no
  pueden ser las dos.
- La 26 (0 % árbitro, 1.095 filas) no está identificada: su mediana (16, 19) está en la mitad
  cercana, lejos del área del portero de A.

---

## Resultado del bloque C — Villaviciosa: el 23,6 % está CONCENTRADO, y el propio GT incumple «≤ 11 por equipo»

`scripts/diag22f_villa.py`, solo con la caché. *Control*: el desglose reproduce el 23,6 %
(358 de 1.519) y la pasada de hoy repetida da las mismas cifras.

**C1. Por persona y por prototipo.**
- **17 de 22 personas tienen algún error, pero 4 suman el 50 % y 8 el 80 %.**

| persona GT | equipo GT | casadas | mal | color dominante (caché) | dist. a A / a B |
|---|---|---|---|---|---|
| **21** | A | 90 | **90 (100 %)** | **amarillo** (235, 227, 110) | 0,73 / **0,38** |
| 13 | B | 69 | 41 (59 %) | azul claro (169, 200, 235) | 0,48 / 0,67 |
| 14 | B | 39 | 38 (97 %) | azul claro (183, 207, 235) | 0,46 / 0,81 |
| 15 | B | 59 | 34 (58 %) | amarillo pálido | 0,58 / 0,65 |
| 16 | B | 30 | 28 (93 %) | amarillo pálido | 0,67 / 0,70 |
| 1 | portero_B | 99 | 23 (23 %) | turquesa | 0,60 / 0,88 |
| 7 | A | 59 | 22 (37 %) | azul claro | 0,44 / 0,94 |

- **La premisa del bloque, corregida: el prototipo amarillo (#ebe36e) es el B de este clasificador,
  no el A.** El A es azul claro (#c6e5eb). Cada uno coincide con el color de su equipo del GT (A:
  (198, 229, 235), B: (235, 228, 124)).
- **¿Lo contamina el árbitro? No.** Recortes casados con el GT, por su prototipo más cercano:

  | prototipo | equipo A del GT | equipo B del GT | árbitro |
  |---|---|---|---|
  | B, amarillo | 20 % | 80 % | **0 %** |
  | A, azul claro | 72 % | **25 %** | 3 % |
  | `otro` | — | 9 % | **91 %** |

  El amarillo es el color REAL del equipo B; el prototipo `otro` es el árbitro. El que absorbe al
  equipo contrario es el **azul claro** (A), con un cuarto de recortes de B.
- **El césped**: la feature v1 lo enmascara; con la caché no se puede separar más.
- **El color real en píxeles con ffmpeg: NO MEDIDO.** El vídeo de Villaviciosa no está en local.

**⚠️ ¿Qué podría estar inventando el 23,6 %? El GT.**
- La persona 21 está etiquetada en el GT como equipo **A** (azul claro), pero su color en la caché
  es **amarillo** y el sistema la llama B en 90 de 90 casadas.
- Juega en el medio campo (x 31-51), así que no es un portero con otra equipación.
- Sola aporta **el 25 % de los errores**.
- C3 refuerza la sospecha: el GT tiene 11,6 personas de A por frame, más de las 11 del reglamento.
- Si la 21 fuera un error de anotación, el equipo equivocado bajaría a ~17,8 % (268 de 1.519);
  con las 14 y 16 también (azul claro etiquetadas B), a ~13,3 %.
- **No está verificado**: hace falta mirar sus recortes en el vídeo (en Colab, o Alex en CVAT).

**C2.**
- **Tope por identidad** (intento 1 del 22-oct e) con 5 semillas de control:
  - real **18,5 %**;
  - permutados 38,3 · 49,9 · 42,6 · 49,1 · 42,3 %, siempre ≥ 19,8 puntos peor; el árbitro en un
    equipo sale al 100 % con todas.
  - **La mejora de Villaviciosa con el tope es robusta y depende del color.** Pero el tope no se
    adopta: rompía el benjamín (22-oct e).
- **Etiqueta por observación en Villaviciosa: sí se probó** (`docs/foto_de_estado.md`). Re-medida
  hoy con el protocolo de `comparar_escalas.py`:

  | | equipo equivocado | árbitro en un equipo | cobertura |
  |---|---|---|---|
  | hoy | 23,6 % | 5,3 % | 75,0 % |
  | por observación (ventana A/B) | 22,3 % | 5,3 % | 75,0 % |
  | por observación + catálogo | 21,1 % | 5,3 % | 71,5 % |

  Coincide con lo de entonces (22,3 / 21,1). Allí gana poco, y con el catálogo pierde 3,5 puntos de
  cobertura. Es el «espejismo» que ya documenta `foto_de_estado.md`.

**C3. Por qué A > 11 en el 54,6 % de los frames.** En la ventana del GT (100 frames), filas reales
dentro del campo:

| | por frame |
|---|---|
| filas A del sistema | 11,50 |
| personas del GT del equipo A (porteros incluidos) | **11,62** |
| personas del GT del equipo B | 9,56 |
| filas A que son jugadores de A | 6,91 |
| filas A que son jugadores de B (equipo equivocado) | 2,12 |
| filas A que son el árbitro | 0,05 |
| filas A sin casar (desplazadas, duplicados, fuera) | 2,42 |

- **El sistema no cuenta más A que el GT: es el GT el que tiene más de 11 personas de A por
  frame.** En 53 de los 100 frames, A pasa de 11 en las filas del sistema.
- La aritmética del dominio dice que algo sobra en el GT, y la persona 21 (amarillo, etiquetada A)
  es la candidata obvia.
- Por el lado del sistema, las filas A de más son 2,1 jugadores de B mal etiquetados (el 23,6 %) y
  2,4 filas sin casar. Las compensan las personas de A que no se casan (faltantes).
- Es el principio de CLAUDE.md: «antes de culpar al sistema, comprobar la aritmética del dominio».

---

## Resultado del bloque D — el recorte del balón pasa a la pizarra; ACTIVADO

**Implementación.**
- `procesar_balon.py` **ya no toca las posiciones**: el recorte del bloque 3 del 22-oct (e), que
  movía `x_m`/`y_m` en el CSV, se retira.
- Con el flag, el CSV gana la columna `calidad_balon` en las filas de balón (`calidad_del_balon`):
  `medida` / `aerea` / `rellena` / `fuera_del_campo`. En los jugadores va vacía.
- La pizarra (`replay_tactico.generar_replay(..., recortar_balon_a_campo=...)`, leído por
  `generar_replay.py` del bloque `balon:` del config del campo) dibuja las filas de balón fuera del
  rectángulo en su punto más cercano (`recortar_al_campo`) ANTES del filtro que hoy las borraba.
- Tests: la pizarra dibuja el balón de fuera en la línea y deja a los jugadores igual; el flag está
  encendido en el benjamín.

**«Conserva las columnas _raw»**: como el CSV ya no se recorta, sus `x_m`/`y_m` SON las medidas
originales. No se añaden `x_m_raw`/`y_m_raw` porque duplicarían exactamente las mismas columnas. Si
se prefiere tenerlas con ese nombre, es un cambio de una línea.

**Criterio:**

| | resultado | ¿cumple? |
|---|---|---|
| flag apagado: CSV del balón | idéntico byte a byte a `main` | sí |
| flag apagado: HTML de la pizarra | idéntico byte a byte al que genera el código de `main` con la misma entrada | sí |
| flag encendido: posiciones del CSV | idénticas a `main`; solo una columna más (`calidad_balon`) | sí |
| calidad de las 11.326 filas de balón | medida 6.788 · aérea 2.450 · rellena 1.141 · fuera del campo 947 | — |
| pizarra: filas de balón dibujadas | **11.326 de 11.326** (hoy 10.379: las 947 de fuera se borraban) | sí |
| pizarra: balón dentro del rectángulo | 100 % | sí |
| pizarra: jugadores | idénticos | sí |

(Nota del montaje: una primera comparación del HTML salió distinta en la línea 71 porque la pizarra
lee los colores de equipo del meta JSON que encuentra junto al CSV, y los dos CSV tenían nombres
distintos. Con la misma entrada, el código de `main` y el nuevo dan el mismo HTML.)

**Activado** en `configs/campo_benja.yaml` (`balon.recortar_a_campo: true`), a petición de Alex. Es
**cosmético**: la ficha sobre la línea no es la posición del balón, y para medir hay que usar el CSV
y su columna `calidad_balon`. Las 947 filas `fuera_del_campo` están a 0-3 m (las de más de 3 m ya
las quita la plausibilidad).

---

## Nota de proceso

- **Un commit con la suite en rojo** (bloque B): la clave del YAML no llegó al fichero porque el
  ancla del reemplazo no casaba, un test falló, y la cadena de comandos commiteó igual porque un
  `tail` se comía el código de salida de pytest. Se arregló en el commit siguiente (b28221d).
- **El bloque C se commiteó sin pasar la suite entera**, y `scripts/diag22f_villa.py` disparaba la
  guarda de renderizadores (`test_renderizadores_no_colapsan.py`). Se clasificó en
  `NO_PINTAN_POR_OBSERVACION` en este commit.
- Desde entonces, cada commit se condiciona al código de salida de pytest, no a su salida impresa.
