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
