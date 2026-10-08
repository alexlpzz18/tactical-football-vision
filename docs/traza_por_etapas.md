# Traza por etapas: ¿dónde se pierde cada persona que falta? (8-oct-2026)

Solo medición, local, sin tocar producción. El criterio (`scripts/traza_por_etapas.py::CRITERIO`)
se commitea ANTES de ver ningún número.

## La pregunta

En la ventana del GT (5:25-5:55 de archivo, 6:58-7:28 del reproductor; 60 frames, 14 personas),
para cada persona que no tiene fila del sistema cerca, **¿en qué etapa del pipeline se pierde?**
Y dos números que hoy no casan entre sí: el detector encuentra al **96,7 %**
(`docs/backlog23_no_hay_deficit.md`) pero en el CSV **falta el 11,2 %** (91 de 814,
`docs/desglose_del_error.md`). ¿Se reconcilian?

## El casado, UNO para todo

El de `docs/desglose_del_error.md` (`src/evaluation/desglose_error.py::casar_frame`): **1-a-1
óptimo (húngaro) en METROS** entre las personas del GT (su pie proyectado con la homografía) y los
puntos de cada etapa. Es el único que se puede aplicar también a las filas del CSV, que no tienen
caja. Se usa con el mismo radio en todas las etapas:

- **radio 2 m** (el del banco y del desglose): recall del detector y «faltan» con el mismo casado.
- **radio 5 m**: define a quién se traza («sin fila a ≤ 5 m»). Las «ausencias» a 2 m que tienen
  fila a 2-5 m se cuentan aparte (son el DES del desglose: la fila existe, mal puesta).

El 96,7 % se midió con OTRO casado, en píxeles (centro de la caja del GT dentro de la caja
detectada, o pies a < 20 px). Se recalcula sobre el mismo caché para ver si se reproduce, y se
listan los casos en que los dos casados discrepan.

## Las etapas (sobre la pasada de producción de hoy, regenerada desde el caché de la parte entera)

| | etapa | qué puntos entran |
|---|---|---|
| a | caja cruda | todas las detecciones del caché, en su posición (mx, my) |
| b | filtros | las que sobreviven a confianza y plausibilidad física (`ancho_min_frac`, el «tamaño») |
| c | identidad | las que el tracking mete en alguna identidad |
| d | etiqueta | de esas, las que llevan A/B/portero en ese instante (etiqueta por observación o, si no hay, la de su identidad); `otro` y `staff` se caen aquí |
| e | CSV | las filas `es_real=1` con etiqueta A/B/portero (posición suavizada, recortada al campo) |

«Fila del sistema» = una fila que el bloque de su equipo usa (A/B/portero). Se da también el
número con cualquier etiqueta. El **staff** es una etiqueta, así que cae en (d), no en (b).

La etapa de pérdida es la PRIMERA en que la persona deja de estar casada. Como el casado se repite
en cada etapa, una persona podría «reaparecer» más adelante (otra asignación óptima, o la posición
suavizada que cae más cerca): se cuentan aparte, no se esconden.

## Criterio de «se reconcilian» (fijado antes)

1. **Contabilidad cerrada**: las personas sin fila a ≤ 5 m tienen que repartirse entre las etapas
   sin que sobre ni falte ninguna (la suma de la tabla = el total).
2. **Los dos recalls**: el recall del detector con el casado común (2 m, cajas crudas) y el 96,7 %
   en píxeles se reconcilian si difieren en **≤ 1 punto**. Si difieren más, se dice por qué con
   los casos concretos en que discrepan.
3. **De 96,7 a 88,8**: la diferencia entre el recall del detector y el «hay fila» del CSV, con el
   MISMO casado, tiene que repartirse entre las etapas b-e. Si no cuadra, se dice por qué.
