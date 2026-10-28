# Diagnóstico 26-oct (b): error de equipo por observación con la pista encendida, y tres clips

Rama `medir-26oct-b`, sale de `main` (a6e2b4c, con la pista del árbitro encendida en F7). **SOLO
medir y renderizar**: no se enciende ningún flag nuevo ni se cambia ningún parámetro. Criterios
escritos ANTES de medir; commit solo con pytest en 0; nada va a `main`.

Relojes: frame / 29,97 = **archivo**; el reproductor de Alex = archivo **+ 1:33**.

## A. Error de equipo por observación, con la pista encendida

**Línea base**: **16,0 %** de equipo equivocado con la etiqueta de la IDENTIDAD (el voto de la
identidad, sin la etiqueta por observación), en la ventana del GT (`docs/diagnostico_22oct_e.md`).

**Medida, sobre las MISMAS filas:**
- Una pasada de `desde_cache` del benjamín, parte entera, con `main` tal cual (pista encendida),
  capturando dos etiquetas por fila real: la del voto de su identidad (`equipos[id]`, con las reglas
  de portero, árbitro y staff) y la final por observación (ventana de 1,5 s, después de la pista).
- El casado es el de `scripts/comparar_escalas.py` (1-a-1, húngaro, 2 m, filas reales): solo mira
  POSICIONES, así que las dos etiquetas se comparan sobre exactamente las mismas parejas.
- **Control**: con la etiqueta de identidad, la medida tiene que dar ≈ 16,0 %. Si no, el protocolo
  no es el mismo y la comparación no vale.
- Error **con IC 95 %** (bootstrap por FRAMES, 2.000 remuestreos: las personas de un frame no son
  independientes), separado por:
  - **cruce / no cruce**: la persona del GT tiene a otra del GT del equipo RIVAL a ≤ 2 m en ese
    frame;
  - **equipo A / B**, según el GT.
- La diferencia identidad − observación también con IC, **pareada** (mismas filas, mismo remuestreo).

**El GT no está repartido por el partido.**
- El de CVAT cubre 30 s del minuto 5.
- `gt_equipos_benja.csv` es del tramo de 60 s y va indexado por id de un detector anterior, que ya no
  vale (CLAUDE.md: un GT indexado por id caduca).
- Por eso se prepara una **hoja de revisión** muestreada en los 20 min, estratificada:
  - **cruce / no cruce**: la fila tiene a una fila real del equipo contrario (etiqueta por
    observación) a ≤ 2 m;
  - repartida en **10 tramos de 2 min**;
  - **60 + 60 filas** (6 + 6 por tramo).
- Formato de `revision_equipos.py`: identidad y etiqueta OCULTAS, y una copia `con_recuadro/` para
  el Finder.
- Alex marca el equipo real de la persona del recuadro. La clave (las dos etiquetas del sistema) va
  aparte.

**Criterio (antes de medir):**
- **Cuenta como mejora** si, sobre las mismas filas:
  - la diferencia pareada identidad − observación tiene el **IC 95 % entero por encima de 0**;
  - y el error por observación tiene el **IC entero por debajo del 16,0 %**.
- Si el IC de la diferencia toca 0: **no decidido**, y se dice con cuántas filas.
- **Cuántas filas hacen falta para decidir** (binomial, con un factor ×2 por agrupar en frames):
  - para ver una diferencia de **d** puntos con un IC de semiancho ≤ d/2, en torno a p ≈ 0,16,
    hacen falta n ≈ 2 · p(1−p) · (1,96 / (d/2))²;
  - **d = 10 puntos → ~410 filas** · **d = 5 → ~1.650** · **d = 2 → ~10.300**.
  - La ventana del GT tiene ~720 filas casadas: decide diferencias de **≳ 7,6 puntos**.
  - La hoja solo decide diferencias grandes: **≳ 19 puntos con 120 filas, ≳ 26 por estrato de 60**.
    Sirve para ver si fuera del minuto 5 se repite el ORDEN de magnitud, no para afinar.

¿Qué podría estar inventando? El GT no anota al árbitro: sus filas no se casan con nadie y quedan
fuera de las dos etiquetas. El error por observación de aquí es el de los JUGADORES. Lo que la pista
saca del equipo (el árbitro) no se ve en esta medida; lo vieron las hojas del 26-oct (59/60).

## B. Tres clips con cajas (solo renderizar)

- **Generador**: `scripts/render_clips_26oct.py`.
  - Frames SIEMPRE por el lector común (`src/utils/video_ffmpeg.py`).
  - El generador antiguo (`generar_video_detecciones.py`) lee con `cv2.VideoCapture`, que en el Mac
    no es el decodificador de producción, así que no se reutiliza su lectura; sí su selección del
    balón (`balon_activo`).
  - Codifica en h264 con el ffmpeg CLI, ≤ 1280 px de ancho, 10 fps (los frames procesados).
- **Ventanas** (60-90 s), elegidas con reglas fijadas aquí:
  1. **14:00-15:30** del archivo: la ventana de control del balón.
  2. **la de más cruces entre rivales**: los 75 s con más parejas (fila A, fila B) reales a ≤ 2 m,
     sumadas por frame (ventana deslizante con paso de 5 s), sin solaparse con la 1.
  3. **el árbitro, claro y en la zona visible**: los 75 s con más frames de la pista del árbitro
     cuya caja mide ≥ 60 px de alto (cerca de la cámara), sin solaparse con las anteriores.
- **Qué se dibuja:**
  - caja por etiqueta (A, B, otro, staff) con el id de la identidad;
  - el portero, con una marca propia;
  - la pista del árbitro, con un contorno blanco grueso y «ÁRBITRO»;
  - las filas cuya etiqueta por observación DIFIERE del voto de su identidad, con un «≠»;
  - **balón**, tal como lo produce `main` (sin máscara ni recorte): un círculo con su estado
    («dentro del campo», «proyectado fuera del campo» o «sin detección») y la confianza;
  - contador por frame A / B / otro y bandera **B > 7**;
  - reloj del archivo y del reproductor.
- **Resumen del balón por zona** (zona = tercio del campo, en profundidad, donde está la mediana de
  los jugadores en ese frame):
  - % de frames con balón;
  - cuántos proyectan fuera del campo, y de esos, cuántos caen en la región de píxeles del campo de
    al lado. Esa región (cx < 940, cy < 603) es la regla del 23-oct (e), que como filtro NO cumplió:
    aquí solo DESCRIBE, no decide.
- **Salida fuera de git**: `outputs/clips_26oct/`.

---

## Resultado A — el error por observación es 1,2 % contra 16,0 % de identidad: MEJORA, en todos los cortes

`python scripts/diag26b.py capturar | error | hoja --salida outputs/diagnostico_26oct_b`.

**Control superado.**
- La captura es `main` tal cual: su CSV es idéntico byte a byte a la variante 2, y la etiqueta
  capturada coincide al 100 % con la del CSV.
- Sobre las MISMAS 723 filas casadas (814 personas del GT, 60 frames, 1-a-1 a 2 m), el casado de
  `comparar_escalas` da **116 / 723 = 16,0 %** con la etiqueta de la identidad (la línea base,
  exacta) y **9 / 723 = 1,2 %** con la de la observación.

| corte (ventana del GT) | filas | voto de la identidad (IC 95 %) | por observación (IC 95 %) | diferencia pareada (IC 95 %) |
|---|---|---|---|---|
| **total** | 723 | **16,0 %** [13,0; 19,2] | **1,2 %** [0,4; 2,3] | **14,8 pts** [11,9; 17,9] |
| en cruce (rival a ≤ 2 m) | 116 | 29,3 % [21,5; 37,7] | 4,3 % [0,0; 10,2] | 25,0 pts [16,1; 33,6] |
| sin cruce | 607 | 13,5 % [10,3; 17,0] | 0,7 % [0,2; 1,3] | 12,9 pts [9,6; 16,4] |
| equipo A (GT) | 353 | 10,2 % [7,3; 13,3] | 1,7 % [0,6; 3,1] | 8,5 pts [5,7; 11,5] |
| equipo B (GT) | 370 | 21,6 % [17,9; 25,7] | 0,8 % [0,0; 1,7] | 20,8 pts [17,2; 24,8] |

**Criterio: CUMPLE.**
- La diferencia pareada tiene el IC entero por encima de 0, en el total y en los cuatro cortes.
- El IC del error por observación está entero por debajo del 16,0 %.
- Con 723 filas, el criterio decidía diferencias de ≳ 7,6 pts; la medida es de 14,8.

**Lo que dicen los cortes:**
- **Los cruces son donde más gana**: el voto de la identidad se equivoca el 29,3 %, porque la
  identidad mezcla a dos personas al cruzarse, y por observación baja al 4,3 %.
- Aun así, los cruces siguen siendo el sitio peor: su IC llega al 10,2 %, con solo 116 filas.
- **El voto de la identidad falla el doble en B (21,6 %) que en A (10,2 %).** Por observación, los
  dos se quedan en ~1-2 %.

¿Qué podría estar inventando?
- **Es UNA ventana de 30 s del minuto 5**, el minuto bueno (CLAUDE.md: «el GT de una ventana no
  representa el partido»). Para el resto del partido no hay GT: es la hoja.
- **El GT no anota al árbitro**: estas cifras son de JUGADORES. Lo que la pista saca del equipo lo
  cubren las hojas del 26-oct (59/60).
- **El IC del cruce es ancho (116 filas)**: el 4,3 % es compatible con hasta un 10 %.

**La hoja para los 20 minutos (para Alex).**
- `outputs/hoja_equipos/equipo_por_obs_20min/con_recuadro/` (Finder) o
  `outputs/hoja_equipos/revision_equipo_por_obs_20min.html`.
- 120 filas reales A/B: 10 tramos de 2 min × (6 en cruce + 6 fuera); 32 tienen la etiqueta de la
  observación distinta del voto.
- Se marca el equipo real de la persona del recuadro. La clave (las dos etiquetas del sistema, cruce
  y tramo) está en `clave_equipo_por_obs_20min.csv`.
- Con 120 filas decide diferencias de ≳ 19 pts: sirve para ver si fuera del minuto 5 se repite el
  orden de magnitud (16 → 1).

## Resultado B — los tres clips (`outputs/clips_26oct/`, fuera de git)

`python scripts/render_clips_26oct.py --captura outputs/diagnostico_26oct_b --salida outputs/clips_26oct`.

| clip | archivo | reproductor | por qué esta ventana | frames · MB |
|---|---|---|---|---|
| `clip_1_balon_14_16.mp4` | 14:00-15:30 | 15:33-17:03 | ventana de control del balón (regla fijada) | 899 · 15,4 |
| `clip_2_cruces.mp4` | 0:40-1:55 | 2:13-3:28 | la de **más cruces entre rivales**: 1.497 parejas (A, B) reales a ≤ 2 m, sumadas por frame (la máxima de todas las ventanas de 75 s) | 749 · 11,0 |
| `clip_3_arbitro.mp4` | 3:10-4:25 | 4:43-5:58 | la de más frames con el **árbitro claro y cerca**: 743 frames de la pista con su caja ≥ 60 px de alto | 750 · 11,9 |

- Los tres son h264, 1280 × 720, a 10 fps. Cada uno se RELEYÓ con `ffprobe`: los frames leídos son
  los escritos.
- ⚠️ **La ventana de más cruces cae en los minutos 0-2**, que son OTRO RÉGIMEN (CLAUDE.md: fit
  desviado, jugadores en otra franja, recuento correcto en el 15,9 % de los frames). Muestra el
  peor caso de los cruces, no el típico.
- **Qué se ve**:
  - caja por etiqueta (A lila, B naranja, otro amarillo, staff gris) con el id;
  - «POR» y una caja más gruesa en los porteros;
  - la pista del árbitro con un contorno blanco y «ÁRBITRO»;
  - un **cuadro magenta** en las filas cuya etiqueta del instante difiere del voto de su
    identidad;
  - el balón como círculo (verde dentro del campo, rojo proyectado fuera) con su confianza, y «sin
    detección» en la cabecera cuando no hay;
  - en la cabecera, el contador A / B / otro, la bandera «B > 7» y los dos relojes.
- Las detecciones que no pertenecen a ninguna identidad, en gris fino.

### El balón por zona (zona = tercio en profundidad donde está la mediana de los jugadores)

**Partido entero** (11.989 frames de jugadores; balón activo de `main`, sin máscara ni recorte):

| zona del juego | frames | con balón | proyectado fuera | … en la región del campo de al lado | … resto (aéreo, saques, otros) |
|---|---|---|---|---|---|
| cerca (x 0-20,7 m) | 1.219 | **14,9 %** | 13 | 0 | 13 |
| media (x 20,7-41,3) | 7.607 | 59,8 % | 522 | 53 | 469 |
| lejos (x 41,3-62) | 3.163 | 60,6 % | 396 | 115 | 281 |

En los clips, por ejemplo el de 14:00-15:30: lejos 80,4 % con balón y 95 proyectados fuera (38 en
la región del campo de al lado).

**Lectura**:
- **Cuando el juego está cerca de la cámara, el balón casi no está (14,9 %).** Es el encuadre: a
  x < 20 m la cámara ve una franja estrecha del campo (CLAUDE.md, «el encuadre es geometría»), y el
  balón sale a menudo del plano.
- **De lo que proyecta fuera, la mayor parte NO cae en la región del campo de al lado** (168 de
  931): el grueso es balón aéreo, saques y otros.
- ⚠️ Esa región es la regla del 23-oct (e), que como filtro NO cumplió (saca saques de banda). Aquí
  solo DESCRIBE, y puede contar mal en los dos sentidos.

¿Qué podría estar inventando? «Con balón» es que el SISTEMA tiene un balón activo, no que el balón
esté en el plano: la falta de GT de balón es la hoja del 23-oct (f), aún sin marcar.
