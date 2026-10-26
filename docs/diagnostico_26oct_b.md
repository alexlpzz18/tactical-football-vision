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
