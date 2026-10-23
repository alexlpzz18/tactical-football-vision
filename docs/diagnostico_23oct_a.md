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
