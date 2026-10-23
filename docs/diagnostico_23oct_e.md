# Diagnóstico 23-oct (e): adopción preparada del árbitro, balón, recall por zona y orden

Ramas:
- **`fix-23oct-e`** (sale de `fix-23oct-d`): este informe y los bloques 2-4.
- **`adopcion-viterbi`** (sale de `fix-23oct-e`): el bloque 1.

**Nada se fusiona a `main`.** Criterios escritos y commiteados ANTES de medir; un commit por bloque,
solo con pytest en código 0. Producción solo cambia tras flag.

Relojes del benjamín: frame / 29,97 = tiempo del **archivo**; el reproductor de Alex va **+1:33**.

> **Veredicto visual de Alex (23-oct), sobre los clips del 23-oct (d):** en 1:00-1:45 y 7:00-7:45
> del archivo (2:33-3:18 y 8:33-9:18 del reproductor), los vídeos de **«hoy» no identifican bien al
> árbitro**; la **variante 2 sí**. Las hojas de revisión (`arbitro_viterbi`, `viterbi_a_otro`) y
> Villaviciosa **siguen sin revisar**.

---

## Bloque 1 — adopción preparada, sin fusionar (rama `adopcion-viterbi`)

**El formato sale de UN solo campo.** Es el `tipo` del modelo de campo que ya usa la clasificación de
equipos (`campo.config` → `configs/campo_benja.yaml` → `campo.tipo: f7`). Sin sección `campo`, el
modelo es el F11 de Villaviciosa, exactamente como hasta hoy. Los valores por defecto de cada
formato van en UNA tabla, en un solo módulo.
- `arbitro.viterbi` (variante 2, «añade») **por defecto en F7**.
- En **F11 apagado**, hasta que se mida Villaviciosa.
- Una clave `activo` explícita en el YAML manda sobre el valor del formato.
- En F7 sin `rutas.cache_chaleco`, el processor **da error**, con el mensaje de cómo generar la caché.
  No se apaga en silencio: un interruptor que se cae sin avisar es peor que no tenerlo.

**Comprobaciones (criterio de que la adopción está bien preparada):**
1. **Flag apagado (`activo: false` explícito) = `main`**: el CSV del partido entero del benjamín,
   corrido con el código de `main` (worktree) y con el de `adopcion-viterbi`, es **idéntico byte a
   byte**.
2. **F11 sin tocar**: Villaviciosa (60 s), `main` contra `adopcion-viterbi` con sus valores por
   defecto: **idéntico byte a byte**.
3. **F7 por defecto = variante 2**: el CSV del benjamín con los valores por defecto es idéntico
   byte a byte al `v2_anade.csv` del 23-oct (d).
4. **Tests de COMPORTAMIENTO** (la lección de `tests/test_interruptores_de_config.py`):
   - cambiar el `tipo` del campo de f7 a f11 cambia si corre la pista;
   - `activo: false` explícito la apaga en F7;
   - F7 sin caché de chaleco da error.
5. **Salidas en `outputs/adopcion/`**: el CSV y la pizarra HTML del partido entero, sin vídeos.

**CLAUDE.md**: una sección «Rutas cerradas», con una línea por ruta (qué se probó, fecha, por qué
falló):
- grupo tercero por color;
- `devolver_por_color`;
- `margen_equipo`;
- puerta por observación;
- tono/brillo antiguo (sensor ciego);
- v3 de máscara;
- tope de cardinalidad (2 intentos);
- asociación con color (B1/B2);
- corte en cruces sin color;
- dedupe;
- relleno de huecos;
- balón con prior de campo y corte duro.

¿Qué podría estar inventando? «Idéntico a `main`» solo prueba lo que se compara: el CSV de dos
partidos desde caché. El modo `full` (GPU) no se ejecuta aquí, y **el modo `full` no genera la
caché de chaleco**: en F7 hay que correr `scripts/cache_chaleco.py` después. Se dice en el aviso
del error y en el informe.

## Bloque 2 — el balón, solo medición (producción no se toca)

**2a. Las candidatas del detector en el tramo de 60 s del benjamín** (t 300-360 s del archivo,
`cache_balon_piloto.pkl`).
- Por frame, TODAS las candidatas: caja en píxeles y confianza. ⚠️ La caché guarda solo las de
  confianza **≥ 0,35** (el umbral del detector); por debajo no hay nada que listar.
- **Etiquetado a ojo de ~40 candidatas** (20 del campo de al lado y 20 de balón real), en una hoja de
  recortes con la posición en el fotograma. Los paneles de `outputs/diagnostico_balon/` sirven de
  guía: ahí están los 7 «campo de al lado» del 22-oct.
- Las posiciones se dibujan sobre un fotograma.
- ¿Se separan por **región** de la imagen, **tamaño** de la caja o **confianza**?
- **Criterio**: una regla en PÍXELES (una sola variable o un rectángulo de la imagen; nada más
  complejo con 40 muestras) que deje fuera **≥ 90 %** del campo de al lado y dentro **≥ 95 %** del
  balón real.
- **Control** con la misma regla, sin reajustarla:
  - en «la caché v4»: no existe ninguna caché de BALÓN v4 en `data/` (solo `cache_balon_piloto` y
    `cache_balon_p1`, ambas del modelo `best_balon_v1`), así que **NO MEDIDO**, y se dice;
  - en otro tramo: la parte entera, minutos 14-16 (contiene f27048, campo de al lado), con 15+15
    candidatas etiquetadas igual; la regla tiene que mantener las dos tasas.
- Si no hay separación, se dice.

¿Qué podría estar inventando? Una regla ajustada a 40 muestras puede separarlas por casualidad. Por
eso el control lleva un tramo distinto y la regla no se reajusta.

**2b. Propuesta, SIN implementar: seguimiento del balón en el espacio de la imagen.**
- Filtro de Kalman en píxeles (posición y velocidad).
- Una puerta que CRECE con el tiempo desde la última detección aceptada.
- En cada frame se elige la candidata dentro de la puerta.
- **Criterio para cuando se implemente:**
  - «campo de al lado» de 7 a **≤ 2** de los 30 paneles;
  - **ningún panel «ok» empeora**;
  - huecos **≤ hoy + 3 puntos**.

## Bloque 3 — recall de los detectores por zona (para decidir la ampliación de datos)

**Jugadores**, contra el GT de 30 s del benjamín (60 frames) y el de Villaviciosa:
- Detecciones de la caché de producción, antes del tracker (`rutas.cache` de
  `processor_benja_parte_entera.yaml` y de `processor.yaml`).
- Zona por la distancia a la cámara, medida con los metros por píxel en el pie de la caja del GT:
  terciles de cada partido (cerca / media / lejos), con sus cortes informados.
- **Recall y precisión con IoU ≥ 0,5** (1-a-1, húngaro), como pide Alex.
  - ⚠️ El GT del benjamín es una PLANTILLA FIJA de 18 × 40 px y las cajas del detector son ~1,5×
    más altas (CLAUDE.md: «un criterio de emparejado es un parámetro»). El IoU castiga la
    plantilla, no al detector. Por eso se informa también el emparejado de **centro**: el centro de
    la caja del GT cae dentro de la detección, 1-a-1.
- La precisión solo cuenta las detecciones con el pie dentro del campo. En el benjamín el GT no anota
  al árbitro ni al staff, así que su precisión es una cota INFERIOR.
- **Errores de las filas que faltan**, cada GT sin casar en una clase:
  - **fundida**: una detección casada con OTRA persona solapa a esta con IoU ≥ 0,3;
  - **cortada**: la caja del GT toca el borde de la imagen;
  - **muy pequeña**: la caja del GT mide < 20 px de alto;
  - **mal localizada**: hay detección con IoU 0,1-0,5 sin casar;
  - **nada**: ninguna detección con IoU > 0,1.

**Balón**: ninguno de los dos GT anota el balón (solo tracks `player` y, en Villaviciosa, `referee`).
- Por eso: en los 30 paneles, ¿cuántos frames con balón visible en el vídeo tienen una candidata
  sobre él, en las zonas cercana y lejana?
- ⚠️ Con confianza ≥ 0,25 **no se puede medir**: la caché empieza en 0,35, y bajar el umbral es
  volver a detectar en GPU. Se mide con ≥ 0,35 y se dice.

**Lectura fijada antes:**
- Si el recall de jugadores en la zona visible del benjamín es **≥ 95 %**, ampliar los datos de
  jugadores **no ayuda al benjamín**; sirve solo para generalizar a F11.
- La lectura se hace con el emparejado de centro, porque el IoU está sesgado por la plantilla.
- Si los dos emparejados no coinciden en el lado del 95 %, se dice.

## Bloque 4 — orden

Lista, **sin borrar nada**, de los ficheros de `outputs/` de ramas cerradas, ordenados por tamaño,
marcando cuáles son regenerables:
- **en el Mac**, desde cachés y scripts del repo;
- **solo con GPU** (Colab);
- **no regenerables**: trabajo a mano (etiquetas, hojas marcadas) o entradas que ya no existen.

---

## Resultado del bloque 1 — adopción preparada (rama `adopcion-viterbi`, commit db17b22, SIN fusionar)

**Qué cambia en esa rama:**
- **Un solo campo decide el formato.** `ModeloCampo.formato` (`src/campo_modelo.py`) sale del `tipo`
  del modelo de campo (`campo_benja.yaml` → `f7`). Sin sección `campo`, es el F11 de Villaviciosa.
- **Los valores por defecto que dependen del formato**, en una tabla: `DEFECTOS_POR_FORMATO`, con
  `arbitro_viterbi` F7 = encendido y F11 = apagado.
- **`viterbi_activo()`** (`processor.py`): la clave `arbitro.viterbi.activo` si está escrita; si
  no, el formato.
- `team_classification_benja.yaml`: `variante: anade` y **sin `activo`** (lo decide el formato).
- Los tres configs del benjamín (`_parte_entera`, de 60 s v3 y v4) llevan `rutas.cache_chaleco`. Las
  cachés se copiaron a `data/tracking_benja/` (fuera de git); hay que subirlas a Drive.
- F7 sin caché de chaleco **da error**, con el mensaje de cómo generarla. El modo `full` no la crea.
- `tests/test_formato_arbitro.py`, 5 tests, uno de ellos EJERCE el interruptor con la caché real de
  60 s:
  - el valor por defecto cambia el CSV respecto a `activo: false`;
  - los cambios son solo a `otro`;
  - sin chaleco, da error.

**Comprobaciones:**

| | resultado |
|---|---|
| 1. benjamín entero, `activo: false` explícito, contra `main` (worktree de `main` con los mismos datos) | **idéntico byte a byte** (`cmp`) |
| 2. Villaviciosa 60 s (F11, valores por defecto) contra `main` | **idéntico byte a byte** |
| 3. benjamín entero con los valores por defecto (F7) contra `v2_anade.csv` del 23-oct (d) | **idéntico byte a byte** |
| 4. tests de comportamiento | 5 de 5; la suite entera en la rama: 763 passed |
| 5. `outputs/adopcion/` | `posiciones_benja_p1_viterbi.csv` (+ meta) y `pizarra_benja_p1_viterbi.html`, sin vídeos |

**CLAUDE.md** (en la rama de adopción): sección «Rutas cerradas», con las 12 rutas pedidas, una
línea cada una (qué se probó, cuándo, por qué falló y dónde está la medida).

¿Qué podría estar inventando? «Idéntico a `main`» es sobre el CSV desde caché de DOS partidos. No
cubre el modo `full` ni otro F7 sin caché de chaleco (para ese caso está el error). Tampoco dice
nada de si la variante 2 está bien en Villaviciosa: allí sigue apagada.

## Resultado del bloque 2 — el balón

### 2a. Las candidatas y la regla en píxeles: separa el campo de al lado, pero NO CUMPLE en el control

`python scripts/diag23e.py candidatas | segunda_tanda | hoja_control_regla | regla --salida outputs/diagnostico_23oct_e`.
Etiquetas en `docs/etiquetas_balon_23oct_e.json`: es trabajo a mano, no se puede regenerar.

**Primero, una corrección de datos.** Hay dos pasadas del detector sobre el tramo de 60 s:
- `cache_balon_piloto.pkl`: 519 candidatas, solo 21 frames con dos o más.
- `cache_balon_p1.pkl`, la de producción y la de los 30 paneles del 22-oct: 1.083 candidatas,
  268 frames con dos o más.

En la del piloto **no está ninguno** de los balones del campo de al lado de los paneles (f9306,
f9360, f9738, f10472 y f10474 salen vacíos). Se usa la de producción.

**Selección para etiquetar, sin mirar la posición**: candidatas de frames con DOS O MÁS candidatas
(semilla 0, y otra tanda con semilla 1). Etiquetadas a ojo: **96 en el tramo** (15 campo de al lado,
38 balón real y 43 otro).
- ⚠️ Pedía 20 + 20; del campo de al lado salen **15**, no 20.
- De esos 15, 10 son balones del otro partido y 5 son personas sobre ese campo.

**Lo que separa es la REGIÓN; el tamaño y la confianza no:**

| | campo de al lado (mín · mediana · máx) | balón real |
|---|---|---|
| cx (px) | 195 · 348 · 536 | 39 · 307 · 1.773 |
| **cy (px)** | **536 · 549 · 573** | **543 · 678 · 823** |
| ancho (px) | 4,0 · 6,7 · 11,1 | 4,9 · 15,2 · 22,8 |
| confianza | 0,37 · 0,45 · 0,64 | 0,38 · 0,66 · 0,76 |

- Tamaño y confianza se solapan enteros.
- El único balón real con cy < 573 a la izquierda era uno en el aire (f10624, a 1.149 px).

**La regla.** En el tramo, todas las reglas de la forma «cx < X y cy < Y» que cumplen forman una
meseta de X 490-1390 y Y 566-640. Se fijó su CENTRO, **cx < 940 px y cy < 603 px**, antes de mirar
el control.

| | campo de al lado fuera | balón real dentro | ¿cumple (≥ 90 % y ≥ 95 %)? |
|---|---|---|---|
| tramo de 60 s (ajuste) | 15 / 15 = 100 % | 38 / 38 = 100 % | sí, por construcción |
| **control: minutos 14-16** (88 etiquetadas, 48 de ellas en una hoja ciega y barajada) | **9 / 9 = 100 %** | **33 / 36 = 91,7 %** | **NO** |
| control en «la caché v4» | — | — | **NO MEDIDO**: no hay caché de balón v4 |

**Los 3 balones reales que saca**, todos a cy 598-601, rozando el corte de 603:
- **C09 y C25** (f26888, f26870; 14:56,9 / 16:29,9 y 14:56,3 / 16:29,3): **saques de banda con
  el balón SOBRE LA CABEZA, delante de la grada**. Son los mismos que tumbaron el corte duro del
  22-oct (c).
- **C00** (f27116; 15:04,6 / 16:37,6): el balón en la tierra, tras la línea de fondo.

**Lo que enseña la imagen** (`outputs/diagnostico_23oct_e/candidatas_en_la_imagen.jpg`):
- El campo de al lado está ENCIMA de la línea superior de la grada, y esa línea va **inclinada**
  (de cy ≈ 590 a la izquierda a ≈ 600 junto a la portería del fondo).
- Un rectángulo pone el borde horizontal y corta por donde pasan los saques de banda.
- **La separación existe, pero por el borde de la grada y no por una horizontal.** Un polígono que
  siga ese borde probablemente pasaría.
- No se prueba aquí: sería una regla NUEVA ajustada después de ver el control, y el control ya no
  serviría.
- Para un intento nuevo, el criterio ya está: el mismo de hoy, con un tercer tramo de control.

**Lo que la regla también deja fuera, sin que se pidiera**: 14 de las 43 «otro» del control. Son
personas en la loma detrás del fondo, la cara de un entrenador y balones del otro campo en la tierra
de la esquina. No es el campo de al lado, pero tampoco es el balón del partido.

¿Qué podría estar inventando?
- **15 + 9 muestras del campo de al lado**: un 100 % con 9 tiene un intervalo de confianza ancho
  (cota inferior al 95 % ≈ 66 %).
- **La clasificación es mía, de un recorte.** Las dudosas fueron a «otro» y no entran en las dos
  tasas.
- **El control falla por 1 balón** (34 / 36 = 94,4 % todavía no llega). No es un fallo marginal de
  redondeo: es el mismo caso que ya rompió el corte duro.

### 2b. Propuesta (NO implementada): seguimiento del balón en el espacio de la IMAGEN

**Por qué en píxeles**: en metros, la homografía de suelo mezcla el balón del otro campo con
cualquier balón alto (22-oct d). En la imagen, el balón del partido se mueve de forma continua y
el del otro campo está en otra región, con su propio movimiento.

**Diseño:**
1. Estado: Kalman de velocidad constante en píxeles, `(u, v, du, dv)` del centro de la caja.
   - Ruido de proceso alto en velocidad: un chut cambia de golpe.
   - Ruido de medida proporcional al tamaño de la caja.
2. **Puerta que crece con el tiempo desde la última detección aceptada**: radio
   r(Δt) = r₀ + v_max_px(v) · Δt.
   - v_max_px depende de la fila de la imagen: un balón a 30 m/s recorre muchos menos píxeles en el
     fondo que cerca. Se saca de la homografía, en el pie.
   - Un tope r_max evita que la puerta abarque la imagen entera tras un hueco largo.
3. **Elección dentro de la puerta**: la candidata de menor distancia de Mahalanobis a la predicción.
   - Si no hay ninguna dentro, el frame se queda **sin balón**. No se coge «la mejor de fuera».
   - Esto es lo contrario del prior de campo: allí, sin alternativa, se quedaba con la de fuera.
4. **Re-adquisición**: tras un hueco mayor que T_max, se acepta una candidata nueva solo si se
   confirma en k frames seguidos con movimiento coherente.
   - Una sola detección no basta: así no salta al balón quieto del otro campo, ni a las marcas de la
     base del muro (que son estáticas: CLAUDE.md, las marcas del campo).
5. **La pizarra no cambia**: se sigue proyectando la base, con las fases aéreas de siempre. Lo que
   cambia es QUÉ candidata se elige.

**Criterio, fijado para cuando se implemente** (los 30 paneles de `outputs/diagnostico_balon/`):
- «campo de al lado» de **7 → ≤ 2**;
- **ningún panel «ok» empeora**;
- frames del tramo sin balón **≤ hoy + 3 puntos** (hoy, 51,6 %: el 22-oct b);
- y la segunda pregunta, «¿qué podría estar inventando?»: lo que elige tiene que MOVERSE como un
  balón. Mediana de desplazamiento por muestra ≥ la del balón real del tramo; las marcas dan 0,02 m.

## Resultado del bloque 3 — recall de los detectores por zona

`python scripts/diag23e.py recall --salida outputs/diagnostico_23oct_e` (`recall.json`).
- Detecciones de la caché de producción, antes del tracker.
- Zonas: terciles de metros por píxel en el pie de la caja del GT.
  - Benjamín: ≤ 0,157 · ≤ 0,224 · más.
  - Villaviciosa: ≤ 0,635 · ≤ 0,877 · más.

**Jugadores, benjamín (60 frames, 814 personas del GT):**

| zona | GT | recall IoU ≥ 0,5 | **recall centro** | precisión IoU | precisión centro (cota inferior) | faltan (por centro) |
|---|---|---|---|---|---|---|
| cerca | 272 | 0,4 % | **94,9 %** | 0,7 % | 88,6 % | 14: 8 mal localizadas, 6 sin detección |
| media | 271 | 21,0 % | **93,4 %** | 19,2 % | 85,6 % | 18: 9 mal localizadas, 8 sin detección, 1 fundida |
| lejos | 271 | 59,4 % | **96,3 %** | 59,0 % | 94,4 % | 10: 8 mal localizadas, 1 fundida, 1 sin detección |
| **total** | 814 | 26,9 % | **94,8 %** (IC 95 % por frames: 93,5-96,2) | 25,4 % | 89,4 % | 42 |

**Jugadores, Villaviciosa (100 frames, 2.118 personas del GT):**

| zona | GT | alto del GT (px, mediana) | recall IoU ≥ 0,5 | **recall centro** | precisión centro | faltan (por centro) |
|---|---|---|---|---|---|---|
| cerca | 706 | 34,3 | 90,8 % | **99,2 %** | 96,7 % | 6: 4 muy pequeñas, 2 fundidas |
| media | 706 | 26,1 | 86,8 % | **95,8 %** | 86,0 % | 30: 20 mal localizadas, 4 fundidas, 4 muy pequeñas, 2 sin detección |
| lejos | 706 | 20,0 | 52,1 % | **64,6 %** | 87,9 % | **250: 167 muy pequeñas (< 20 px)**, 41 sin detección, 26 fundidas, 16 mal localizadas |
| total | 2.118 | | 76,6 % | 86,5 % (IC 84,4-88,5) | 90,1 % | 286 |

**Lectura fijada antes: el benjamín NO llega al 95 % por la letra (94,8 %), pero NO se distingue de
él.**
- El IC 95 % es [93,5; 96,2] y contiene al 95.
- Los dos emparejados no coinciden de lado: con IoU sale 26,9 %. Ese número es el sesgo de la
  plantilla fija de 18 × 40 px (en la zona cercana, con jugadores de ~100 px de alto, el IoU es
  0,4 %), no el detector.
- Lo que falta en el benjamín **no es lo que arregla más datos**: casi nada es pequeño ni fundido.
  - «Mal localizada» (25 de 42) es una detección que solapa con la persona pero cuyo centro no
    contiene el centro de la plantilla. Es sobre todo la plantilla en los jugadores grandes y
    cercanos.
  - «Sin detección» son 15.
- ⇒ **Ampliar los datos de jugadores no es la palanca del benjamín.** Su techo de recall está en
  ~95 % y lo que falta es localización y emparejado.
- **En Villaviciosa sí**: el tercio lejano pierde el 35 %, y dos tercios de eso son personas de
  menos de 20 px. Es el «por debajo de 25 px el detector se degrada» de CLAUDE.md. Ampliar datos
  con jugadores muy pequeños sirve para generalizar a F11 (o se cambia la cámara).

¿Qué podría estar inventando?
- **El emparejado de centro es generoso con las cajas grandes**: una detección que funde a dos
  personas contiene los dos centros, pero en el húngaro solo casa con UNA. Por eso las fundidas
  salen como fallo, no como acierto.
- **La precisión del benjamín es una cota inferior**: el GT no anota al árbitro ni al staff que pisa
  el campo, y esas detecciones cuentan como falsas.
- **Los 60 frames son el minuto 5.** La ventana del GT no representa el partido (CLAUDE.md), y en
  los minutos 0-5 el recuento era peor.

**Balón: ninguno de los dos GT anota el balón** (solo tracks `player` y, en Villaviciosa,
`referee`).
- Medido a ojo en los 30 paneles del 22-oct, redibujados con TODAS las candidatas (≥ 0,35; no se
  puede bajar a 0,25: la caché empieza en 0,35):
  - **Zona cercana** (4 paneles: f8992, f9012, f9144 y f9282, balón a < 15 m de la cámara): **4 de
    4** tienen una candidata sobre el balón.
  - **Zona lejana** (los otros 24): la medida **no es fiable** a la resolución de los paneles. En
    los 4 frames donde la única candidata está en el campo de al lado (f9306, f9360, f9738 y
    f10472), no encuentro el balón del partido en la imagen, pero no puedo afirmar que sea visible
    y no detectado.
- **NO MEDIDO con rigor.** Haría falta un recorte ampliado de cada panel, como la hoja de
  candidatas, o anotar el balón en CVAT.

## Resultado del bloque 4 — `outputs/` (NO se ha borrado nada)

`outputs/` ocupa 6,1 GB (15 GB libres en el disco, 97 %). Marcas:
- **R-mac**: regenerable en el Mac desde cachés y scripts del repo;
- **R-gpu**: regenerable solo con GPU (re-detectar en Colab);
- **NO**: trabajo a mano o entrada que no se puede reproducir.

| fichero o carpeta | MB | ¿regenerable? | nota |
|---|---|---|---|
| `detecciones_benja_p1.mp4` | 987,7 | R-mac | `generar_video_detecciones.py` desde la caché |
| `video_parte_entera_v3.mp4` | 987,7 | R-mac | ídem, con el CSV v3 |
| `video_parte_entera.mp4` | 987,7 | R-mac | ídem |
| `pool_balon_pegado/` | 459,7 | **NO** (en parte) | contiene `etiquetado/` y anotaciones CVAT; el paquete YOLO se puede rehacer, las etiquetas no |
| `diagnostico_22oct_b/` | 439,9 | R-mac | el 98 % es `cache_colores_v3.pkl` (420 MB): se rehace con `diag22b_feature_v3.py` (CPU, 20 min) |
| `fragmento_balon_7m03/` | 359,0 | R-mac | vídeos y pizarras de un fragmento |
| `diagnostico_23oct_d/` | 325,7 | R-mac | capturas de la pista (`captura_*.pkl`) y clips; **rama abierta** |
| `detecciones_conjunto_balon.mp4` | 246,8 | R-mac | |
| `hoja_equipos/` | 141,5 | **NO** | contiene `revision.csv` (marcado a mano) |
| `diagnostico_23oct_b/` | 115,6 | R-mac | 84 MB de paneles de auditoría |
| `diagnostico_22oct_g/` | 112,5 | R-mac | CSV de variantes |
| `recortes_sueltos/` | 81,7 | R-mac | |
| `etiquetado_balon_dirigido/` | 78,7 | **NO** (en parte) | `labels/`: etiquetas a mano |
| `diagnostico_22oct_e/`, `_22oct_f/` | 58,0 · 53,9 | R-mac | |
| `hoja_recuento/`, `hoja_recuento 2/`, `hoja_recuento.zip` | 51,5 × 2 + 51,2 | R-mac (la hoja) | las tres son la misma hoja (copia y zip); la revisión de Alex quedó en el informe |
| `diagnostico_23oct_c/` | 49,7 | **NO** para esta rama | sus cachés de chaleco son ENTRADAS de la adopción (copiadas ya a `data/tracking_benja/`) |
| 9 vídeos de 48,8 MB (`FINAL_`, `ACUMULADO_`, `EXPERIMENTAL_benja_cajas.mp4`, `detecciones_benja*.mp4`, `video_jugadores_balon_5m10.mp4`, `detecciones_muestra3min.mp4`) | 439 | R-mac | |
| `gt_huecos/` | 34,5 | R-mac | |
| `arbitro_obs/` | 33,5 | R-mac | lo usa `diag22b_filas.py` como entrada |
| `diagnostico_22oct_c/`, `_22oct_d/`, `_23oct_a/`, `_22oct/` | 31,5 · 20,1 · 19,8 · 8,5 | R-mac | `_22oct_d/posiciones_hoy.csv` es entrada del modelo de emisión: **no borrar** |
| `gt_balon_en_vuelo/`, `gt_posicion_balon/` (+ ` 2` y `.zip`), `gt_desempates/` (+ `.zip`) | ~9 cada una | **NO** | `respuestas*.csv` y `.numbers`: GT de Alex |
| el resto (< 8 MB cada uno) | ~60 | casi todo R-mac | |

- **Lo que más libera sin perder nada**:
  - los tres vídeos de la parte entera (2,9 GB, R-mac);
  - `cache_colores_v3.pkl` (420 MB, R-mac en CPU);
  - las copias duplicadas `hoja_recuento 2` y `gt_posicion_balon 2` con sus `.zip`, ~120 MB.
    Antes de borrarlas, comprobar con `diff -r` que son copias idénticas.
- **Nada de esto se ha borrado.**
