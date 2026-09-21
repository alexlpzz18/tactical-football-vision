# El árbitro que sigue sumándose a B, y el baile de colores

21-sep-2026. Revisión de la pizarra de la parte entera. Dos preguntas de Alex:

1. *"El árbitro sigue sumándose a B muchas veces, pese al catálogo por
   observación. ¿En qué % de frames está bien etiquetado y qué pasa cuando
   falla? Puede que lo que quede sea su identidad mezclando personas y no el
   catálogo."*
2. *"Un jugador que cambia de equipo a mitad de jugada no puede pasar en
   producto. Los casos concretos del partido entero: cuántos, qué
   identidades, qué instantes, qué tienen en común."*

Reproducir: `scripts/arbitro_medicion.py` y `scripts/baile_de_colores.py`.
Hojas de recortes en `outputs/` (no se versiona): `arbitro_verdad.png`,
`baile_parpadeos.png`, `id420.png`.

---

# 1. EL ÁRBITRO

## La verdad que no existía

El GT del benjamín **no anota al árbitro**. Se construyó una, y el control es
lo que la hace útil:

- **En la ventana del GT (60 frames)**, el árbitro es la única fila que no
  casa con ninguna persona anotada y tiene verde flúor en el torso. El flúor
  se mide sobre los **píxeles del vídeo**, no sobre el histograma del
  catálogo, así que es independiente de lo que se evalúa. Sale **una fila
  por frame en 59 de 60**, y las 59 son de la id 292. Comprobado a ojo en
  15 recortes: todas son el árbitro; los 5 controles, jugadores.
- ⚠️ **El primer intento contaba al portero de B como árbitro**: también
  viste verde flúor (42 filas). Se separa por la posición y por el GT, que
  sí lo anota.

## Cuánto está bien etiquetado

| | árbitro como `otro` (bien) | como B | como A | como staff |
|---|---|---|---|---|
| **ventana del GT** (59 frames, verdad) | **47,5 %** (28) | **50,8 %** (30) | 1,7 % (1) | — |
| **partido entero** (10.451 filas, proxy) | **58,3 %** | 37,8 % | 0,8 % | 2,8 % |

- El árbitro está visible en el **84 %** de los frames (10.034 de 11.989).
- En los frames con una sola fila de árbitro, está como `otro` el **60,1 %**.
- Por minuto varía entre el **3 % y el 98 %** (minuto 14: 98 %; minutos 1,
  7 y 12: 3-6 %).

El proxy del partido entero —masa del histograma en la región flúor— separa
**58 ventanas de árbitro de 663 de jugador con cero falsos** en la ventana del
GT, y su cadena de posiciones es la de un árbitro (mediana 0,82 m/s, p95
2,8 m/s, centro del campo). Aviso: en el 4 % de los frames hay una segunda
fila verde a más de 8 m que no sé identificar.

## ¿Es la identidad mezclada o es el catálogo? Son las dos, y se pueden separar

**Todas las filas de árbitro mal etiquetadas están en identidades
contaminadas.** Solo 8 filas (0,2 %) están en identidades puras:

| identidad que contiene la fila mal etiquetada | filas | % |
|---|---|---|
| **MEZCLADA** (20-80 % de sus ventanas son árbitro) | 2.988 | 68,6 |
| jugador con un tramo de árbitro (<20 %) | 1.357 | 31,2 |
| PURA (≥80 %) | 8 | 0,2 |

La id 292 es el caso extremo: **4.046 filas, 55 % árbitro** (2.206: 1.191 como
B, 1.011 como `otro`, 4 como A), y el resto jugadores (B 1.108, A 724).

**Esto confirma tu diagnóstico de que la identidad mezcla personas. Pero no
exculpa al catálogo**, porque el catálogo por observación existe justo para
identidades mezcladas y aquí falla en la mitad de las ventanas que SÍ son
árbitro. En la ventana del GT la id 292 es árbitro puro y aun así 29 de 58
ventanas no disparan.

## Por qué falla el catálogo: la saturación del chaleco

El arquetipo `verde_fluor` pide saturación S ≥ 170 en el bin dominante. En esta
cámara **el chaleco alterna entre S≈248 y S≈72-104**:

| minuto | 3-5, 8-9, 14, 17-18 | 1, 7, 12 |
|---|---|---|
| S dominante mediana | 248 | 72-88 |
| catálogo dispara | 50-76 % | 4-8 % |
| árbitro realmente como `otro` | 49-98 % | 3-6 % |

Correlación por minuto entre "el catálogo dispara" y "está como `otro`":
**0,91**. Las ventanas que fallan tienen su bin dominante en H≈28, S≈56-104:
**es el chaleco**, pero por debajo del umbral. Reproduzco la decisión del
catálogo y coincide con la etiqueta real en 57 de 58 casos, así que es
justo lo que hace el sistema.

⚠️ **NO se puede arreglar bajando el umbral de S sin más.** Con la regla
actual (bin dominante) y S ≥ 70:

| | árbitro captado | jugadores capturados |
|---|---|---|
| S ≥ 170 (hoy) | 48,3 % | 0 de 663 |
| **S ≥ 70** | 93,1 % | **15 de 663** |
| S ≥ 70, partido entero | — | **6,4 % de todas las ventanas A/B** (109 identidades) |

Es exactamente la trampa de siempre: el criterio arregla lo que quieres y
rompe lo que no miras. Una regla por **masa** en la región (H 20-90, S ≥ 80)
separa 58 de 663 sin falsos, pero solo está validada en 30 s de GT y la
zona de dudas (la segunda fila verde) no está resuelta. **No se adopta.**

## LO QUE EL CRITERIO DE ADOPCIÓN NO MIRÓ: el catálogo captura al portero de A

Entre `posiciones_benja_p1.csv` y `posiciones_benja_p1_v2.csv` el catálogo
mandó **3.555 filas a `otro`**. **2.791 (78,5 %) parecen árbitro. 764 no.**

De esas 764, **501 están en el área del portero de A** (x<10, 13 identidades):

| identidad | etiqueta antes | filas | posición | instante |
|---|---|---|---|---|
| **468** | A | 240 | x 7,8 · y 22,9 | 11:04-11:29 |
| **420** | portero_A | 205 | x 6,9 · y 23,0 | 08:15-08:38 |
| 586, 612, 695… | A | 13-18 c/u | x≈7 · y 21-24 | varios |

**La id 420 es el portero de A**: camiseta negra, el "1" en la espalda,
dentro de su área (`outputs/id420.png`). El catálogo lo cuenta como árbitro
—probablemente el arquetipo `negro`—. Coste: unas 500 filas, ~6 % del tiempo
del portero de A; pero es el jugador que define la línea defensiva.

⚠️ **Mi propia métrica no lo veía.** "Equipo equivocado" solo cuenta las
observaciones etiquetadas A o B, así que un jugador mandado a `otro` o
`staff` es invisible. En la ventana del GT ningún jugador anotado está
etiquetado `otro`/`staff` (control superado), pero la ventana no incluye
ninguno de estos instantes.

El resto de los 764: 101+21+21+14 filas en y≈−1 (fuera del campo, en la banda:
espectadores o staff, `otro` es razonable).

## Lo que NO sé

- Que la verdad del partido entero es un **proxy**, calibrado en 30 s.
- La **segunda fila verde** (417 frames, a >8 m): no la he identificado.
- Que el **1,2 % de equipo equivocado** de CLAUDE.md y lo que mido hoy no
  cuadran: con el mismo procedimiento sale **1,7 %** a 2 m (1,1 % a 1 m,
  2,5 % a 3 m) sobre los tres CSV, que dan idénticos porque solo difieren en
  filas de árbitro. El número depende del protocolo de casado (aquí, 1-a-1
  entre TODAS las filas del frame); no he reproducido el protocolo original.

---

# 2. EL BAILE DE COLORES

## Cuántos son

**741 cambios A↔B** entre observaciones consecutivas de la misma identidad
(**37 por minuto**, constante en el tiempo). De ellos:

| | |
|---|---|
| en un tramo **continuo** (hueco ≤ 0,35 s) | **567** |
| tras un hueco (la identidad reaparece con otro color) | 174 |
| identidades con al menos uno | **192 de 320** |

Los continuos, por lo que dura la etiqueta nueva: **99 parpadeos** (≤ 1,5 s y
vuelve), 71 cortos (1,5-5 s), **90 duraderos** (> 5 s), 307 cierran el tramo.

Sentido: 383 A→B y 358 B→A. Simétrico.

## Qué identidades (con nombres)

Las diez con más cambios: **310 (20) · 161 (18) · 781 (18) · 366 (15) · 288
(15) · 525 (15) · 292 (14) · 12 (14) · 429 (13) · 764 (13)**. Las 10 suman el
21 % y las 30 mayores el 45 %: **está repartido, no es un puñado de culpables**.

Los 741 con su instante, identidad y contexto están en
`outputs/baile_casos.csv`.

## Qué tienen en común, contra la línea base

| rasgo | cambios | todas las filas A/B |
|---|---|---|
| vecino a < 1,5 m | 39,1 % | 14,2 % |
| **rival a < 1 m** | 14,0 % | 5,1 % |
| **caja solapada con otra (IoU > 0,10)** | **57,6 %** | 15,7 % |
| **caja solapada fuerte (IoU > 0,30)** | **25,4 %** | 3,6 % |
| solapada O caja > 25 % más ancha de lo normal | **73,0 %** | 30,6 % |
| árbitro a < 3 m | 3,8 % | 4,8 % |

- **El árbitro NO es la causa** (3,8 % contra 4,8 %).
- **73 % ocurre en identidades MEZCLADAS**: 414 de 567 continuos, en 115 de las
  320 identidades (>20 % de su etiqueta minoritaria).
- **No hay saltos de posición**: mediana 0,19 m y **ninguno > 1,5 m**. No son
  dos cuerpos que se cruzan; es el color cambiando sobre una trayectoria
  continua.

## Qué son (8 casos mirados, `outputs/baile_parpadeos.png`)

| caso | qué se ve |
|---|---|
| **#6 (01:40), #309 (07:19), #595 (11:48), #724 (15:03), #736 (16:37), #887 (19:28)** | **la caja contiene dos jugadores solapados, uno de cada equipo**, o un jugador con un rival pegado. Según cuál domina el recorte, la etiqueta baila |
| **#7 (00:24)** | **la identidad salta de cuerpo**: un naranja, luego un blanco, luego **el árbitro**. Error de asociación, no de color |
| **#308 (05:54)** | naranja aislado, sin nadie cerca, etiquetado A-B-A. **No lo explico** |

Cuantificado sobre los 741: **el 73 % de los cambios cae en una caja
solapada o anómalamente ancha, contra el 30,6 % de la línea base**. Restando
la base, el mecanismo "dos personas en una caja" explica del orden de **el
58 %** de los cambios. **El 21 % (157) no tiene ni vecino a < 1,5 m ni caja
solapada ni ancha**: ese resto no lo explico.

## Con la verdad del GT, en 30 s

En la ventana hay 19 cambios continuos en 16 identidades. Cruzados con la
persona del GT (18 con verdad):

| | |
|---|---|
| **corrigen** (mal → bien) | 8 |
| **rompen** (bien → mal) | 10 |

**Casi la mitad de los cambios son la etiqueta ACERTANDO**: la identidad ha
pasado a otra persona y la etiqueta la sigue. Y de las 14 observaciones
equivocadas de 605 (2,3 % de las A/B), **8 están a ≤ 1,5 s de un cambio** y 6
son un tramo entero mal.

## Consecuencia para decidir (NO decidido)

- **Suavizar los cambios es peligroso**: si la mitad son aciertos, un filtro
  que los quite empeora. (Coherente con CLAUDE.md: *taparlo esconde el
  fallo*.)
- El 73 % en identidades mezcladas y el 58 % por dos-personas-en-una-caja
  apuntan a **antes de la etiqueta**: la asociación y la caja, no el umbral.
- Los 99 parpadeos y la caja solapada sí admiten una guarda: **no etiquetar
  por color una observación cuya caja se solapa con la de un rival**, y
  heredar la etiqueta del entorno. Habría que medir qué corrige (los ~10
  "rompen" de la ventana) y **qué podría inventar** (los 8 "corrigen").
