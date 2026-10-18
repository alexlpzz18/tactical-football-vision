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

## Segunda vuelta (9-oct-2026)

### Las pérdidas del post-proceso: las mueve el SUAVIZADO, y la causa es la asociación

`scripts/diagnostico_filas_movidas.py` (espía en `suavizar_trayectorias`). **Los 9 casos de la etapa
e, no solo 5:**
- **No es la reproyección**: ByteTrack guarda la posición de la detección del caché, no la de su
  Kalman. La entrada al post-proceso coincide con la detección (0,00 m en los 9).
- **No es el casado**: nada mueve la fila después del suavizado (CSV = posición suavizada, 0,00 m).
- **Es el suavizado**, que la mueve 0,8-6,4 m.

**Por qué la mueve:**
1. **La ventana no es de 0,5 s sino de ~2 s.** `escalar_con_resolucion: 1.0` alarga la ventana
   base (5 muestras) según la resolución MEDIA de toda la identidad: factor 15-31 en estos casos,
   ventanas de 19-21 muestras. En el partido entero la ventana real tiene una **mediana de 1,9 s**
   (p90 2,5 s) y el **82 % de las trayectorias pasa de 1 s**. El método es la media móvil, y
   promedia muestras reales consecutivas aunque haya un hueco entre ellas (hasta 1,3 s en un caso).
2. **Dentro de esos 2 s la identidad no es una sola persona.** Mirando a qué persona del GT cubre en
   los frames del GT de la ventana, en **5 de 9 recorre 2-3 personas** (por ejemplo, el id 274
   pasa por los tracks 13, 12 y 3; el id 308 por los tracks 12, 5 y 3), y en los demás alterna
   saltos de 4-8 m entre muestras consecutivas (40-80 m/s). En el partido entero, **el 4,0 % de
   los pasos entre muestras reales consecutivas supera los 12 m/s**. ⚠️ Con un umbral fijo eso
   incluye temblor del fondo (allí 1 px vale 0,42 m): no son todos saltos de identidad.

Contrafactual (no es una propuesta): con la ventana base de 0,5 s, o con la mediana en vez de la
media, se recuperan **3 de los 9** (a ≤ 1,3 m). En los otros 6 hasta los vecinos inmediatos son otra
persona, y ningún suavizado lo arregla. **El suavizado es quien mueve la fila; la causa es una
identidad que mezcla personas**: la prioridad uno de siempre, la asociación. La ventana de 2 s
multiplica su alcance.

⚠️ Corrige lo de ayer: no son «5 movidas + 4 de casado». Las 9 las mueve el suavizado; en 4 el
movimiento es de 0,8-2 m y la fila acaba cubriendo a otra persona en el 1-a-1. Y CLAUDE.md habla de
«suavizado de 0,5 s»: en la práctica son ~2 s.

### El sesgo hacia la cámara está en la CAJA, no en tu clic (salvo el portero)

`scripts/sesgo_pies_gt.py` (criterio commiteado antes). Pie de la caja del detector contra tu clic
SIN corregir y corregido. dy > 0 = el pie de la caja queda más abajo en la imagen = más cerca de la
cámara. Emparejado 1-a-1 sin condicionar en dy: 784 de 814 clics.

| | n | dy sin corregir | dy corregido | hacia la cámara (corregido) | dy / alto |
|---|---|---|---|---|---|
| todas | 784 | +7,5 px (1,45 m) | **−0,1 px (0,0 m)** | | 0,00 |
| **filas mal puestas** | 50 | +13,5 px | **+8,5 px** | **2,2 m**, el 82 % hacia la cámara | 0,23 |
| — de ellas, el portero (track 6) | 10 | | +47 px en todas sus parejas | | 0,51 |
| — **sin el portero** | 40 | +11,3 px | **+5,3 px** | **1,8 m**, el 78 % | 0,14 |

- **El signo NO cambia en las filas mal puestas** (criterio 1): no es un artefacto de tu corrección.
  Era aritméticamente imposible: la corrección solo baja el clic, y ahí el pie ya queda por debajo
  del clic corregido. En la población entera tu corrección deja el sesgo en −0,1 px: está bien
  calibrada.
- **10 de las 50 son el portero**, cuyo clic está en el PECHO (`docs/portero_cortado.md`): esas sí
  son un artefacto del GT, uno ya conocido y distinto de la corrección.
- **Las otras 40 son de la CAJA** (criterio 2: dy/alto 0,14 frente a −0,01 en las normales). No es
  una caja más alta de lo normal (alto implícito 0,87× la mediana frente a 0,96×). Lo que tienen es
  **otra caja pegada: el 70 % toca otra caja**, frente al 34 % de las normales (78 % y 47 % a
  < 10 px). Es el mecanismo de `docs/proximidad_deteccion.md`: con otra persona encima, el pie de
  la caja baja hasta el de la persona de delante.

⇒ El 17 % del desglose (DES) **no es un artefacto del GT**, salvo la parte del portero (10 de 50).
El resto es la caja del detector en situaciones de proximidad.
