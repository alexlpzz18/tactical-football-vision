# Diagnóstico 23-oct (a): B2 en métricas de producto, y el chaleco por fila con el sensor que ve

Rama `fix-23oct-a`, sale de `fix-22oct-g`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque, solo con pytest en código 0. Producción solo cambia tras flag (apagado = idéntico a
`main`).

---

## Bloque 1 — B2 (`tracking.corte_cruces`) con el pipeline completo, en métricas de PRODUCTO

> ⚠️ **Nota**: estos criterios se escriben CONOCIENDO el resultado de ayer (B2 doblaba las
> identidades y no cumplía). Es una revisión del tope de identidades, que era un PROXY del daño:
> aquí se mide el daño directamente, en las métricas que ve el producto.

Pasadas `desde_cache` del pipeline ENTERO (cosido por pureza, porteros, staff, árbitro, voto por
observación en el benjamín), en las dos patas: hoy (flag apagado), B2 (flag encendido, parámetros
de ayer) y B2 con el color permutado (control). Solo filas reales.

| métrica | criterio |
|---|---|
| equipo equivocado con voto (GT, protocolo de `comparar_escalas.py`) | ≤ hoy + 0,3 (benjamín 1,2 %; Villaviciosa 23,6 %) |
| árbitro dentro de un equipo, ventana GT del benjamín (proxy fijado, 22-oct e) | 53,5 % → **≤ 35 %** |
| árbitro dentro de un equipo, Villaviciosa (GT) | ≤ 5,3 % |
| otro ≥ 2, partido entero (benjamín) | ≤ 12,2 % |
| B > 7, partido entero (benjamín) | ≤ 20 % |
| A > 11, Villaviciosa | ≤ hoy (54,6 %) |
| centroide y anchura (`foto_de_estado.medir`) | ≤ hoy + 0,05 m, las dos patas |
| ocupación | no peor que hoy en más de 0,5 puntos |
| regla de portero | sigue acertando: las filas casadas con el portero del GT etiquetadas `portero_X` de su lado, no menos que hoy − 2 puntos |

- **Ocupación**: en `foto_de_estado` es un ERROR (diferencia de reparto por zonas, menos es
  mejor), así que «no peor» es ≤ hoy + 0,5.
- **Se reportan además**, sin criterio:
  - metros de recorrido INTERPOLADO (suma de los pasos hacia filas `es_real=0`);
  - huecos > 2,5 s sin posición dentro de una identidad (número y segundos);
  - IDF1 y fragmentación (identidades del sistema por persona del GT).
- **Control**: B2 con el color permutado entre detecciones del mismo frame. **El color real tiene
  que ganar** en equipo equivocado y en árbitro dentro de un equipo, en las dos patas.
- **Métricas de asociación para el futuro**: se añaden a `src/evaluation/` una función de IDF1 y
  fragmentación desde un CSV de posiciones (sobre `metricas.calcular_metricas_tracking`, que ya
  calcula IDF1), con test.

¿Qué podría estar inventando? Las métricas de producto agregan por equipo y frame: un corte que
reparte mal a dos compañeros no las mueve. Por eso van IDF1 y la fragmentación al lado.

## Bloque 2 — el chaleco por fila, con el sensor que ve (ffmpeg, SIN máscara anti-césped)

Por cada fila real: el torso de su caja (la misma franja que la feature: filas 0,12-0,45 y columnas
0,15-0,85 de la caja), decodificado con el ffmpeg CLI y SIN máscara. **Puntuación** = fracción de
sus píxeles dentro de la banda del chaleco.

**Verdad por fila.**
- **Villaviciosa**: el GT anota al árbitro. Fila «árbitro» si se casa (1-a-1, 2 m, con todas las
  personas) con el árbitro del GT; «jugador» si con un jugador.
- **Benjamín**: ⚠️ **su GT NO anota al árbitro** (CLAUDE.md). Verdad por ELIMINACIÓN en la ventana
  del GT, sobre la detección cruda de cada fila:
  - «árbitro»: dentro del campo, a ≥ 2 m de las líneas y a **> 3 m de toda persona del GT** (el GT
    anota a los 14 jugadores: el árbitro es el único no anotado en el campo);
  - «jugador»: casada 1-a-1 a **≤ 1 m** con un jugador del GT;
  - las de 1-3 m quedan fuera (ambiguas).
  - **Segunda verdad, independiente**: las 29 cajas que Alex marcó «arbitro» en la hoja de
    revisión (`outputs/hoja_equipos/revision.csv`). Se reporta qué fracción marca la prueba.

**La banda** (benjamín), fijada en la PRIMERA mitad de la ventana del GT (frames 9750-10185):
- sobre los píxeles del torso de las filas «árbitro» con S ≥ 100 y V ≥ 150 (candidatos a chaleco:
  deja fuera el césped, V ≈ 113-128, y la piel, de poca S);
- H ∈ [p5, p95], S ≥ p5 y V ≥ p5 de esos píxeles;
- se compara con la de partida (H 40-52, S ≥ 150, V ≥ 235).

En Villaviciosa, igual sobre su árbitro (amarillo flúor).

**El umbral τ por fila** (fracción mínima de píxeles en la banda), también en la primera mitad: el
que da el MAYOR recall de árbitro con ≤ 0,5 % de falsos positivos en filas de jugador.

**Criterios**, sobre la SEGUNDA mitad (frames 10200-10635; también se dan para la ventana entera):
- falsos positivos ≤ **0,5 %** de las filas de jugador;
- recall de filas del árbitro ≥ **80 %**;
- en las dos patas;
- y el AUC por fila.

**Controles:**
- la banda DESPLAZADA +30 en H no debe separar (AUC cerca de 0,5);
- la máscara anti-césped actual (la puntuación contada sobre los píxeles que sobreviven a ella)
  tiene que separar PEOR (AUC menor).

**Partido entero, sin GT** (benjamín), con la banda y τ fijados:
- filas marcadas por frame dentro del campo: ≤ 1 persona salvo en el **5 %** de los frames;
- cuántas filas marcadas caen en identidades que hoy son de un equipo (mayoría A/B).

**Villaviciosa necesita el vídeo, que no está en local.** Se deja la celda de Colab
(`scripts/diag23a_chaleco.py --pata villa`). Hasta que corra, «no medido», y la prueba no puede
pasar en las dos patas.

**Si pasa**: se propone, SIN implementar, cómo usar la marca por fila para sacar al árbitro de los
equipos sin la amplificación por identidad.

¿Qué podría estar inventando? La verdad por eliminación del benjamín incluye cualquier cosa no
anotada a > 3 m de los jugadores: staff que pisa el campo, una caja fantasma, un recogepelotas. Por
eso la segunda verdad (las marcas de Alex), que es independiente.

---

## Resultado del bloque 1 — B2 en métricas de producto: NO CUMPLE (mejora mucho el benjamín, empeora Villaviciosa)

`scripts/diag23a_b2_producto.py`. Pipeline entero, solo filas reales.

| | benjamín hoy | **benjamín B2** | benjamín B2 permutado | Villaviciosa hoy | **Villaviciosa B2** | Villaviciosa B2 permutado | criterio |
|---|---|---|---|---|---|---|---|
| equipo equivocado con voto | 1,2 % | 1,4 % | 1,1 % | 23,6 % | 23,2 % | 24,1 % | ≤ hoy + 0,3 → sí / sí |
| árbitro dentro de un equipo | 53,5 % | **4,3 %** | 2,5 % | 5,3 % | **0,0 %** | 75,8 % | ≤ 35 / ≤ 5,3 → sí / sí |
| otro ≥ 2 (partido / tramo) | 12,2 % | **7,2 %** | 9,7 % | 4,2 % | 20,4 % | 3,0 % | benjamín ≤ 12,2 → sí |
| B > 7 (benjamín) / A > 11 (Villaviciosa) | 28,5 % | **17,0 %** | 23,1 % | 54,6 % | **69,8 %** | 80,6 % | ≤ 20 → sí / ≤ 54,6 → **NO** |
| centroide | 0,863 m | **0,591 m** | 0,506 m | 4,374 m | **4,747 m** | 5,030 m | ≤ hoy + 0,05 → sí / **NO** |
| anchura | 0,389 m | 0,389 m | 0,387 m | 4,805 m | **5,295 m** | 4,736 m | ≤ hoy + 0,05 → sí / **NO** |
| ocupación (error, menos es mejor) | 4,06 | 2,49 | 2,73 | 13,8 | **17,5** | 17,4 | ≤ hoy + 0,5 → sí / **NO** |
| portero bien etiquetado | 100 % | 100 % | 99,1 % | 88,4 % | 91,9 % | 85,9 % | ≥ hoy − 2 → sí / sí |
| metros interpolados | 297 | 391 | 439 | 195 | 201 | 230 | (informativo) |
| huecos > 2,5 s sin posición (nº / s) | 22 / 94 | **62 / 219** | 57 / 206 | 0 / 0 | 0 / 0 | 0 / 0 | (informativo) |
| IDF1 | 0,589 | 0,566 | 0,556 | 0,442 | **0,364** | 0,371 | (informativo) |
| identidades por persona del GT (media) | 3,07 | 4,29 | 5,14 | 5,68 | 7,91 | 8,41 | (informativo) |

*Línea base*: el criterio citaba 0,97 / 0,40 m de centroide y anchura en el benjamín. Medido hoy con
`foto_de_estado.medir` sobre el CSV de producción da 0,863 / 0,389. El criterio va relativo a hoy,
así que no cambia el veredicto.

**No cumple**: en Villaviciosa empeoran A > 11, el centroide, la anchura y la ocupación.

**Control: el color real NO gana en el benjamín** (error 1,4 contra 1,1 y árbitro 4,3 contra 2,5
del permutado). En Villaviciosa sí gana (23,2 contra 24,1; 0,0 contra 75,8).

**¿Qué podría estar inventando? Lo que mejora el benjamín no es el color: es CORTAR en los
cruces.**
- Con el color permutado, el benjamín mejora igual o más: árbitro dentro de un equipo 2,5 %,
  centroide 0,51 m.
- Es coherente con el bloque B del 22-oct (f): las quimeras árbitro + jugador se forman en los
  cruces, y partir la identidad ahí ya las deshace, se reenlace bien o mal.
- El precio está en las métricas de asociación, que es por lo que se añadieron:
  - IDF1 baja (0,589 → 0,566);
  - las identidades por persona suben (3,1 → 4,3);
  - los huecos > 2,5 s sin posición casi se triplican (94 → 219 s): los trozos sueltos de B2 dejan
    a personas sin ficha más tiempo.
- La mejora del centroide (0,86 → 0,59) puede venir en parte de ahí: sin ficha no hay error de
  posición.
- En Villaviciosa, donde ya se etiqueta por identidad y la impureza era menor, partir empeora el
  recuento (A > 11, otro ≥ 2 del 4 al 20 %).

**Decisión**: no se adopta; el flag sigue apagado.
- **Dato para un plan futuro**: el corte en cruces SIN color arregla al árbitro del benjamín (53,5
  → 2,5-4,3 %). Lo que falta es reunir los trozos sin perder las fichas: el mismo cuello de botella
  del 22-oct (g).
- **Métricas nuevas**: `src/evaluation/asociacion_desde_csv.py` (IDF1 y fragmentación por persona
  desde un CSV), con test. Desde hoy van junto a la pureza, que premia partir.
