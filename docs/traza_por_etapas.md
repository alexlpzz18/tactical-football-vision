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

## Resultado (8-oct-2026)

814 personas-frame (60 frames × 14, menos las que el GT no anota). Pasada de producción de hoy desde
el caché de la parte entera. Reproducir: `scripts/traza_por_etapas.py pasada` y `medir`.

### 1. Los dos recalls NO se reconcilian (criterio: ≤ 1 punto)

| casado | recall del detector (cajas crudas) |
|---|---|
| píxeles (centro dentro o pies < 20 px), el del 96,7 % | **97,8 %** (sobre este caché; el 96,7 % era otro caché) |
| **metros, 1-a-1, 2 m** (el común) | **91,3 %** |
| metros, 1-a-1, 5 m | 96,4 % |

6,5 puntos de diferencia. Los casos en que discrepan: 63 casan en píxeles y no en metros (y 10 al
revés). De esos 63:
- **19: la caja es de OTRA persona del GT.** El casado en píxeles **no es 1-a-1**: una caja
  fundida cuenta como detección de las dos personas que contiene. El 96,7 % estaba inflado por eso.
- **44: caja libre, pero su pie cae a 2-5 m del clic del GT.** En 61 de los 63 el pie detectado
  está MÁS ABAJO en la imagen (más cerca de la cámara), una mediana de 16 px, que en profundidad
  son ~0,24 m/px. 13 son del portero cercano (track 6, el clic en el pecho, ya conocido) y 28 están
  a x ≥ 40 m, donde unos píxeles son metros.

⇒ Los dos números miden cosas distintas: el de píxeles responde «¿hay una caja encima?» y el de
metros, «¿hay una caja PROPIA cuyo pie cae donde está la persona?». Para el producto vale el
segundo.

⚠️ **Pista sin medir**: el desglose dejó «sin nombre» las filas mal puestas 2-5 m (DES), con el
desplazamiento en profundidad y el 85 % hacia la cámara. Aquí aparece lo mismo **ya en la caja
cruda**, antes del tracking. O el clic del GT (una plantilla fija) queda por encima del pie, o la
caja del detector se alarga por abajo. Con este GT no se distingue.

### 2. Con el MISMO casado (2 m), del detector al CSV

| | personas casadas | |
|---|---|---|
| caja cruda | 743 (91,3 %) | |
| fila del CSV (A/B/portero, `es_real=1`) | **723 (88,8 %)** | 91 ausencias, exactamente las del desglose |

El paso de 743 a 723 cuadra: −7 perdidas en el tracking (sin identidad), −24 en el post-proceso
(CSV) y +11 personas sin caja propia a 2 m que sí tienen fila a 2 m (la posición suavizada cae más
cerca). Con cualquier etiqueta sale lo mismo: 88,8 %.

**De las 91 ausencias a 2 m, 51 tienen fila a 2-5 m** (la fila existe, mal puesta), y 60 no
tienen caja PROPIA a 2 m ya en el detector. Las ausencias a 2 m son sobre todo localización en el
detector, no pérdidas del pipeline.

### 3. Las 40 personas sin fila a ≤ 5 m: dónde se pierden

| etapa | casos | qué es |
|---|---|---|
| a. caja cruda | **23** | ninguna caja propia a ≤ 5 m: el detector no la ve (o está fundida) |
| b. filtros (plausibilidad, tamaño) | **0** | |
| c. identidad | **7** | la caja existe y pasa los filtros, pero el tracking no la mete en ninguna identidad (6 de 7) |
| d. etiqueta | **1** | identidad con etiqueta `otro`/`staff` en ese instante |
| e. CSV | **9** | caja en una identidad A/B, pero la fila del CSV no la cubre |
| **total** | **40** | contabilidad cerrada; ninguna reaparece en una etapa posterior |

Las 9 de (e) son de dos clases: en **5, la fila del CSV está a 4-6 m de su propia detección**,
casi todo en x (profundidad) y a x ≥ 40 m (el post-proceso o el suavizado la mueven); en 4 la fila
está a 0,8-2,2 m pero el casado 1-a-1 se la da a otra persona más cercana. No se reparten en una
persona: 11 tracks distintos, como mucho 9 casos el track 9.

**Pérdidas reales del pipeline después del detector: 17 de 814 (2,1 %)**: tracking 7, etiqueta 1,
post-proceso 9. **En el detector, 23 (2,8 %).** Los filtros no cuestan nada aquí.
