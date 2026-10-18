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
