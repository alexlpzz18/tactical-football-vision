# Parpadeo en cruces: máscara de torso tapado e intercambio de colas (plan, 19-nov-2026)

Tarea 2 de la cola de la noche. Rama `literatura-sota`. Solo pruebas: interruptores apagados,
salidas en `outputs/literatura/`. Criterios escritos y commiteados ANTES de medir; dos intentos por ruta.

## Respuestas a las preguntas previas (leídas en el código y en `docs/`)

- **(a) ¿«Congelar en el cruce» definía el cruce en metros o por solape en la imagen?** En **metros**:
  radio R = 1,5 y 2,0 m alrededor de la identidad (`docs/parpadeo.md`, 26-ago). ⇒ se prueba la máscara
  en la imagen.
- **(b) ¿La ventana de 1,5 s está centrada o mira solo hacia atrás?** **Centrada**: vota cada observación
  de la identidad con |t − t_actual| ≤ 0,75 s (`etiquetar_por_observacion`, `pipeline_equipos.py`).
- **(c) ¿Se guarda por fila la probabilidad continua de equipo?** **No**: el CSV guarda solo la etiqueta.
  La evidencia continua existe en el clasificador (`margen_ab`, añadido el 13-nov) pero no se exporta.

## Variante a: máscara de torso tapado en la imagen (`por_observacion.ocluidas_modo: torso`)

- Una observación NO vota color si más del **15 % de su pecho** (la banda de la que sale el color:
  12-45 % del alto, 15-85 % del ancho) está tapado por otras cajas, y también las **3 observaciones
  anteriores y las 3 siguientes de su identidad**. Decide la ventana centrada con las limpias; si toda
  la ventana está tapada, se buscan limpias de la misma identidad a ±1,5 s (`ampliar_ventana_s: 3`).
- **Argumento nuevo frente a la ruta cerrada «excluir ocluidos del voto» (21-sep, 2 variantes)**: aquella
  medía el **IoU de las cajas enteras** (> 0,10: marcaba el 13,5 % de los recortes, muchos solo pisados
  en las piernas, y no veía los torsos tapados por cajas que se solapan poco en total) y no ampliaba en
  el tiempo. Aquí se mide sobre el **pecho**, con fracción tapada (no IoU), y se amplía ±3 observaciones.
  Si el resultado es el mismo que entonces, la conclusión de septiembre («el baile es la identidad
  cambiando de persona, no color sucio») queda reforzada y la línea se cierra del todo.

## Variante b: intercambio de colas entre rivales (`intercambio_colas.activo`)

- Dos identidades cuyas cajas se solapan (IoU > 0,10): si en la ventana de 1,5 s de ANTES son de equipos
  distintos con margen ≥ 0,15 (en unidades de la separación A−B), y en la de DESPUÉS cada una tiene el
  color de la otra con el mismo margen, se intercambian sus observaciones posteriores al solape.
- **Argumento nuevo frente a «intercambiar colas por continuidad de movimiento» (20-ago, no construida)**:
  aquella decidía con la geometría y arreglaba 3 de 24 fallos; esta solo actúa entre RIVALES (el 86-94 %
  de los cambios en cruce) y decide con el color medio de ventanas limpias, no con un recorte.

## Criterios (los de Alex)

En el tramo 14:00-15:30 del benjamín (840-930 s de la parte 1), sin histéresis visual:
1. **cambios de color por minuto bajan ≥ 50 % frente a 48** (≤ 24);
2. el **error de equipo** no sube: GT de 30 s (1,245 %, casado 1-a-1 a 2 m) y **hoja de 120 marcas** de
   Alex (`equipo_por_obs_20min`, medida sobre la caja de la marca);
3. el **IDF1 dentro de cada equipo** (GT de 30 s) no baja.

Control: «actual» con los configs de `main` reproduce 48,0 cambios/min y 1,245 %. Se mide también en el
benjamín de 60 s y en el alevín A, que no pueden empeorar.

---

## Resultado (20-nov): NO CUMPLEN ninguna de las dos. Sin segundo intento

Tramo 14:00-15:30 del benjamín, sin histéresis; configs de `main`. Control: «actual» reproduce 48,0
cambios/min y 1,245 % (y 0,9 % en la hoja de 120, 1 de 109 marcas).

| | cambios de color/min (≤ 24) | equipo mal, GT 30 s | hoja de 120 | IDF1 dentro del equipo A · B |
|---|---|---|---|---|
| actual | 48,0 | 1,245 % | 0,9 % | 0,641 · 0,628 |
| a. torso tapado (> 15 % del pecho, ±3 obs.) | **49,3** | **1,94 %** | **1,8 %** | 0,639 · 0,628 |
| b. intercambio de colas entre rivales | 44,0 (−8 %) | **1,70 %** | 0,9 % | **0,531** · 0,615 |

- **a**: no baja el parpadeo y empeora el acierto en las dos verdades. Repite el resultado de septiembre
  con otra definición de oclusión (sobre el pecho y ampliada en el tiempo): queda REFORZADA la conclusión
  de entonces, el parpadeo no es color contaminado.
- **b**: baja el parpadeo un 8 % (pedía 50 %) y rompe identidades buenas (IDF1 de A −11 puntos).
- **Sin segundo intento**: las dos van en la dirección contraria al criterio (el error sube), no se
  quedan cortas. Un intento más con otro umbral no tiene argumento.
- Arreglo de mi instrumento por el camino: las cajas de la hoja de 120 están en coordenadas del RECORTE
  que vio Alex, no del fotograma; se casan como las dibujó la hoja (la detección más cercana a la
  posición de la fila). La primera pasada daba «109 sin fila» y no se leyó.
