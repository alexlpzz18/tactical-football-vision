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
  un borde interior de tesela (2 × 4 teselas, solape 0,2, la geometría de `get_slice_bboxes` de
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
