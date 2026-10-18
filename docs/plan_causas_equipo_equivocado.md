# Plan: ¿por qué una fila sale con el EQUIPO EQUIVOCADO? (18-oct-2026) — SOLO MEDICIÓN

Rama `clasificacion-benja`. Producción no se toca. Nada de modelos nuevos hasta tener (a).
El criterio (`scripts/causas_equipo_equivocado.py::CRITERIO`) se commitea ANTES de medir.

## De dónde venimos

- `docs/arbitro_y_baile_de_colores.md`: 741 cambios A↔B en la parte entera. El 73 % cae en una caja
  solapada o anómalamente ancha, frente al 30,6 % de la línea base. El árbitro, cerca en el 3,8 %
  frente al 4,8 % de la base, no es la causa. Pero eso describe CAMBIOS, no ERRORES: en la ventana
  del GT, 8 de 18 cambios corrigen la etiqueta.
- `docs/desglose_del_error.md`: el equipo equivocado pesa el 6 % del error de centroide (9 filas de
  814 en la ventana del GT, casado 1-a-1 a 2 m).

## Lo que se mide

Sobre la salida de producción de HOY, regenerada desde el caché de la parte entera con un espía
que guarda la CAJA exacta de cada fila real (la detección de esa identidad en ese frame, no «la más
cercana» a una posición suavizada).

**Tres poblaciones:**
1. **E (con verdad)**: en la ventana del GT (5:25-5:55 de archivo, 6:58-7:28 del reproductor),
   casado 1-a-1 a 2 m con las filas reales (el protocolo del desglose), las personas cubiertas por
   una fila del OTRO equipo (los porteros cuentan con el suyo). Aparte, las cubiertas por una fila
   `otro`/`staff`.
2. **Á (árbitro, sin GT)**: el GT no anota al árbitro. Las filas A/B que el **proxy de píxeles**
   (`scripts/arbitro_medicion.py`: masa flúor de la ventana de 1,5 s ≥ 0,27, fuera de la zona del
   portero de B y sin etiqueta `portero_B`) dice que son el árbitro, en la ventana y en el partido.
   Son filas con el equipo equivocado por definición: el árbitro no es de ningún equipo.
3. **C (cambios A↔B, partido entero)**: con la definición de `scripts/baile_de_colores.py`, la fila
   de DESPUÉS de cada cambio. Sin GT no se sabe cuál de los dos lados es el error: se mide el
   contexto del cambio, no un error.

**Las causas, EXCLUYENTES y en este orden** (la primera que se cumple):

| | causa | regla (fijada antes) |
|---|---|---|
| 1 | árbitro | el proxy de píxeles de arriba |
| 2 | staff | la fila está fuera del rectángulo del campo por más de 2 m (la tolerancia de `staff`) |
| 3 | portero | en E, la persona del GT es un portero; en todas, la fila está dentro de un área (margen 2 m) y es la más cercana a esa portería de todas las filas A/B/portero del frame |
| 4 | caja con dos personas | su caja solapa con otra del frame (IoU > 0,10) o es > 25 % más ancha de lo normal para su alto (mediana de ancho/alto por franja de alto en la línea base, como en el baile) |
| 5 | recorte limpio | ninguna de las anteriores: caja sola, de proporciones normales, y aun así el color se equivoca |

**El control que hace que los porcentajes signifiquen algo:** la misma clasificación sobre la LÍNEA
BASE. En E, las personas casadas con su equipo bien; en el partido, 5.000 filas A/B reales al azar
(semilla 0). Una causa solo se atribuye por su **exceso** sobre la base: exceso = n × (p − p_base).
Una causa con la misma tasa en errores que en aciertos no explica nada.

**Controles de que el instrumento funciona** (si fallan, no se lee nada):
- la clasificación es exhaustiva: la suma por causas = el total de cada población;
- **el proxy del árbitro en la ventana del GT tiene que marcar una fila en ≥ 55 de los 60 frames**
  (el árbitro está en el campo, y su documento lo encontró en 59 de 60);
- el número de cambios A↔B se recalcula sobre el CSV de hoy y se informa: puede no ser 741, porque
  el pipeline ha cambiado desde septiembre.

⚠️ **Límite que hay que decir antes de mirar**: en E se esperan unas 9 filas. Con n tan pequeño, el
reparto por causas es una DESCRIPCIÓN de esos casos, no una tasa. Los porcentajes con n < 30 se
dan, pero con su n delante y sin leerlos como proporciones del partido.

## (b) La hoja de revisión (para Alex)

Tres ventanas de 60 s del benjamín, **1 frame por segundo** (180 imágenes):
1. **la del GT**: 5:10-6:10 de archivo (6:43-7:43 del reproductor), que contiene los 30 s del GT;
2. **un minuto malo**: el minuto entero (de 5 a 19, sin solaparse con la del GT) con menos filas
   A/B/portero en el campo por frame en el CSV de hoy;
3. **una al azar**: un inicio uniforme entre 5:00 y 19:00 (semilla 0) que no se solape con las
   otras dos.

En cada imagen, TODAS las cajas del caché que entran al tracking, con un número de caja, la
identidad y la etiqueta DEL INSTANTE (la de esa observación, no la moda de la identidad: la guarda
de `tests/test_renderizadores_no_colapsan.py`). Las cajas sin identidad, en gris. Arriba, los dos
relojes. Se sacan con `posicionar_en_frame()` y lectura secuencial, nunca con `cap.set`.

## Resultado (18-oct-2026)

`scripts/causas_equipo_equivocado.py pasada` y `medir`, sobre la producción de hoy (parte entera).

**Controles: pasan.** La clasificación es exhaustiva. El proxy del árbitro lo encuentra en **56 de 60**
frames de la ventana (pedía ≥ 55). Hoy hay **739 cambios A↔B** (566 continuos; en septiembre eran
741 y 567). Ninguna fila real queda sin caja.

### (a) Las causas

| población | n | árbitro | staff | portero | caja con dos personas | recorte limpio |
|---|---|---|---|---|---|---|
| **E: equipo equivocado con GT** (ventana) | **9** | 0 | 0 | 0 | 4 | 5 |
| E: cubiertas por `otro`/`staff` | 0 | — | — | — | — | — |
| *base E: casadas con su equipo bien* | 714 | 0 | 0 | 107 (15 %) | 198 (28 %) | 409 (57 %) |
| **C: cambios A↔B** (partido) | **739** | 15 (2 %) | 0 | 12 (2 %) | **540 (73 %)** | 172 (23 %) |
| C: solo los continuos | 566 | 8 | 0 | 8 | 407 (72 %) | 143 (25 %) |
| *base del partido: 5.000 filas A/B al azar* | 5.000 | 152 (3 %) | 9 | 259 (5 %) | 1.474 (29 %) | 3.106 (62 %) |

**Exceso sobre la base** (lo único que se atribuye):
- **C, cambios A↔B: la caja con dos personas explica 322 de los 739** (240 de los 566 continuos).
  Ninguna otra causa supera su tasa de base: el árbitro (2 % frente a 3 %) y el portero (2 % frente a
  5 %) están POR DEBAJO. Confirma `docs/arbitro_y_baile_de_colores.md` con cajas exactas.
- **E, con GT: la caja con dos personas explica 1,5 de los 9** (4 de 9 frente al 28 % de los aciertos).
  Los otros 5 son recortes limpios, a la misma tasa que los aciertos (56 % frente a 57 %).
  **n = 9: es una descripción de esta ventana, no una tasa.**

**Lo que se ve en los 9 casos con GT** (`E_casos.csv`, uno a uno):
- **7 de los 9 están a y ≥ 34 m, junto a la banda de y = 40**, frente al 30 % de los aciertos
  (Fisher p = 0,005).
- Dos son el mismo instante: 5:27,3 de archivo (7:00,3 del reproductor), un A y un B en el mismo
  sitio, los dos equivocados. Es un cruce con las etiquetas intercambiadas.
- Concentrados además entre 5:41 y 5:55 de archivo (7:14-7:28 del reproductor): es el «tercio 3»
  ya conocido de la ventana.
- ⚠️ Con 9 casos en 30 s esto no dice nada del partido (`EL GT DE UNA VENTANA NO REPRESENTA EL
  PARTIDO`); dice dónde mirar en la hoja.

### El árbitro: la mayor fuente de equipo equivocado, y el GT no la ve

Etiqueta de las filas que el proxy de píxeles marca como árbitro:

| | `otro` (bien) | **B** | A | `staff` | `portero_A` |
|---|---|---|---|---|---|
| partido entero | 6.098 (59 %) | **3.955 (38 %)** | 80 | 289 | 29 |
| ventana del GT | 28 | **27** | 1 | — | — |

- **En la ventana del GT hay 28 filas de árbitro contadas en un equipo, contra 9 errores de jugador
  verificados.** El casado contra el GT no puede verlas, porque el GT no anota al árbitro: por eso el
  «1,2 % de equipo equivocado» de CLAUDE.md las deja fuera.
- **En el partido son 4.035 filas** (el 3,0 % de las 134.163 filas reales A/B), casi siempre en el B.
  Como estimación, y no como medida: si la tasa de 1,24 % de los jugadores valiera para todo el
  partido, serían ~1.660 filas, así que **el árbitro pesaría unas 2,4 veces más que todos los errores
  de jugador**. Es coherente con `docs/desglose_del_error.md` (el árbitro es la mitad de los sobrantes).

### (b) La hoja de revisión

`python scripts/hoja_revision_equipos.py --trabajo DIR --salida outputs/hoja_equipos` (no se versiona,
71 MB). 180 imágenes, 3.084 cajas (17 por imagen de media):

| ventana | archivo | reproductor |
|---|---|---|
| `gt` | 5:10-6:10 | 6:43-7:43 |
| `minuto_malo` | 8:00-9:00 (10,2 filas A/B/portero en el campo por frame, frente a 12,9 de mediana) | 9:33-10:33 |
| `azar` (semilla 0) | 16:04-17:04 | 17:37-18:37 |

Ya en la primera mirada: en la imagen 21 de `gt` (5:30 de archivo, 7:03 del reproductor), **el árbitro
(caja 8, #292) sale como B**. En la 30 de `minuto_malo` (8:29 de archivo, 10:02 del reproductor), **un
jugador blanco (caja 7, #431) sale como portero_A** en el centro del campo, y un naranja (caja 11,
#436) como `otro`.

**Formato** (`outputs/hoja_equipos/revision.csv`; una fila por CAJA MAL, no por imagen):

    ventana,imagen,caja,equipo_correcto,causa,nota
    gt,20_5-30.0.jpg,8,arbitro,arbitro,chaleco verde
    minuto_malo,29_8-29.0.jpg,7,A,portero,el 4 blanco en el centro

- `equipo_correcto`: A · B · portero_A · portero_B · arbitro · staff · no_es_persona · dudoso
- `causa`: caja_dos_personas · arbitro · portero · staff · color_limpio · otra · no_se
- `cajas.csv` dice qué es cada número de caja (frame, los dos relojes, identidad, etiqueta, caja en
  píxeles y posición en metros).

**Tiempo estimado: 75-90 min** (unos 25-30 min por ventana; ~25 s por imagen para recorrer 17 cajas,
más ~15 s por cada caja que se apunte). Se puede hacer por ventanas.
