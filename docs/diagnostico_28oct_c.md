# Diagnóstico 28-oct (c): las dos hojas de Alex, el balón con GT y la caja fundida

Rama `medir-28oct-c`, sale de `medir-28oct-balon`. **SOLO medir**: no se cambia ningún parámetro.
Criterios escritos y commiteados ANTES de abrir las marcas de Alex. Commit solo con pytest en 0.

Relojes: archivo; reproductor = archivo + 1:33.

## 1. Equipo: la hoja de 120 filas por los 20 min (`~/Downloads/revision (1).csv`)

- Se cruza `equipo_correcto` (marca de Alex) con la etiqueta OCULTA del sistema por observación
  (`clave_equipo_por_obs_20min.csv`, columna `etiqueta_observacion`).
- **Mapeo de la marca**:
  - A y B (teclas 1-2), tal cual;
  - **portero_A → A, portero_B → B** (teclas 3-4);
  - **árbitro y staff** (teclas 5-6) cuentan como **error**, porque el sistema puso esa fila en un
    equipo (las 120 son filas A/B);
  - **jugador sin equipo, no es persona y dudoso** (teclas 7-9) se **excluyen** y se cuentan aparte;
  - una fila sin marca también se excluye y se cuenta.
- El equipo del sistema es el de la etiqueta por observación, con los porteros en su equipo.
- **Error** = marca (mapeada) ≠ equipo del sistema.
- IC 95 % de Wilson. Cada fila es de un frame distinto, separados en el tiempo, así que se tratan
  como independientes.
- **Cortes**: cruce / no cruce, cada tramo de 2 min, y equipo según la marca de Alex.
- Se informa además, sobre las mismas filas, el error que tendría el voto de la identidad.

**Criterio:**
- **≤ 6 errores de 120** → el 1,2 % se sostiene fuera del minuto 5;
- **≥ 12** → no se sostiene;
- **entre 7 y 11** → no decidido, y se dice dónde se concentran.
- Si se excluyen muchas filas, el umbral se aplica en proporción: ≤ 5 % se sostiene, ≥ 10 % no.

## 2. Balón: la hoja de GT de 200 frames (`~/Downloads/respuestas_gt_balon.csv`)

- Se pasa con `python scripts/gt_balon_rapido.py leer …` a
  `data/annotations/gt_balon_benja/gt_balon_por_frame.csv`.
- **Lectura de cada respuesta**:
  - `acepta`: balón visible y la candidata elegida lo es;
  - `clic`: balón visible en otro sitio, o sin candidata;
  - `rechaza_no_visible`: el balón no se ve (si había candidata elegida, es un **falso positivo**);
  - `no_se`: se excluye.
- **Por zona**, con IC de Wilson:
  - % de frames con balón visible = (acepta + clic) / respondidos;
  - **recall** de la elegida sobre los visibles = acepta / (acepta + clic con candidata elegida);
  - **falsos positivos** = rechaza / frames con candidata elegida.
- **Dos definiciones de zona**, porque no son la misma cosa:
  - **(i) la de la hoja**: el tercil de metros por píxel de la candidata elegida, con el que se
    estratificó;
  - **(ii) la del 14,9 %**: el tercio del campo donde está la mediana de los jugadores en ese frame,
    la que dio el 14,9 % el 26-oct (b).
- **Criterio, sobre (ii)**:
  - si en la zona cercana el balón es **visible en < 50 %** de los frames y el recall sobre los
    visibles es **parecido** al de las otras zonas (los IC se solapan), el 14,9 % es de **encuadre**;
  - si no, del **detector**.
- ⚠️ **Sesgo conocido, antes de mirar**: 180 de los 200 frames se eligieron por TENER una candidata
  elegida. La visibilidad por zona está sesgada hacia arriba, y los frames sin balón solo están
  representados por los 20 «sin candidata». Si no hay frames suficientes de la zona cercana (menos de
  15), el criterio queda **NO DECIDIDO** con esta hoja.

**Balón inventado, último intento.**
- Con el GT:
  - **inventado** = un frame con candidata elegida donde el GT dice `rechaza_no_visible` (no hay
    balón);
  - o donde dice `clic` a más de **2 m** del elegido, medidos con la escala local
    (`escala_px_por_m` en el punto marcado: 2 m × píxeles por metro).
- Tasa con IC, por zona.
- **Control**: los tramos 14:46-14:48 y 15:12-15:15 que vio Alex. Entre los 200 solo hay **un**
  frame de cada uno (f26610, 14:47,9; f27394, 15:14,0). Por eso se prepara una **mini-hoja de control**
  con ~10 frames de cada tramo, en el mismo formato.
  - **La medida no se da por buena hasta que Alex marque la mini-hoja y la medida marque al menos un
    frame inventado en cada tramo.** Hasta entonces se informa la tasa de los 200 como provisional.

## 3. La hipótesis de la caja fundida

- **El postproceso de SAHI** que usa el pipeline es el de por defecto de `sahi` 0.12.1, porque
  `processor.py` no pasa ningún parámetro: `GREEDYNMM`, métrica `IOS` y umbral 0,5. Teselas 2 × 4
  con solape 0,2, más la imagen entera.
- ⚠️ **Cambiar IOS por IoU ya se probó** (BACKLOG 19, 28-sep, `docs/ios_vs_iou_jugadores.md`), y
  está cerrado como negativo:
  - IoU separa cajas fundidas, pero el 49 % de las nuevas son FRAGMENTOS (cabeza, torso, pierna);
  - su «pie» no es el pie de nadie.
  - Aquella vez solo se midió la altura de las cajas. **No se midió el tracking** (IDF1,
    fragmentación, mezcla en cruces), que es lo que pide Alex. Por eso esto no es «un intento más»
    de lo mismo, sino un plan nuevo con otra medida.
- **Diagnóstico (3a)** en los tres instantes (14:40, 14:44 y 15:06 del archivo, ± 1 s):
  - se eligen los frames en que las dos personas del cruce comparten UNA detección del caché (dos
    filas sobre la misma caja, o una sola fila para las dos identidades);
  - se vuelve a detectar en CPU (venv con numpy 1.26 y el mismo detector, `best_v4pre.pt`), con los
    parámetros de producción y SIN fusión (NMS por IoU con umbral 0,99: no junta casi nada).
  - **Control**: con los parámetros de producción, la detección en CPU tiene que reproducir las cajas
    del caché (≥ 95 % casadas a IoU ≥ 0,9). Si no, la CPU no sirve para comparar y se dice.
  - **Hipótesis confirmada** si, sin fusión, aparecen las DOS cajas donde producción tenía una.
- **Solo si se confirma, (3b)**: UNA alternativa, **NMS por IoU con umbral 0,5**, sobre el tramo de
  60 s del benjamín (600 frames, el que contiene la ventana del GT).
  - Se re-detecta en CPU y se corre `desde_cache` con el caché nuevo.
  - Se compara con el caché de producción (si el control de 3a pasa) en:
    - personas por frame;
    - recall por zona (la medida del 23-oct e);
    - error de equipo en cruces (la del 26-oct b);
    - IDF1 y fragmentación (`asociacion_desde_csv`).
  - **Lectura fijada antes**: solo cuenta como mejora si el IDF1 sube ≥ 0,5 puntos, la fragmentación
    no empeora más de 0,2 y el error en cruces no sube.
  - **Máximo dos intentos**: el segundo, solo si el primero muestra qué ajustar, con el criterio
    escrito antes.

¿Qué podría estar inventando? Tres instantes elegidos por Alex no dicen cuántas veces pasa en el
partido. Si la hipótesis se confirma, lo que pesa es el 3b, y aun así es UN tramo de 60 s del
minuto 5.

## 4. Fusiones a `main` y la etiqueta del balón

- Fusión `--no-ff` de `medir-28oct-balon`, que contiene `medir-26oct-b`, a `main`.
- **Arreglo**: la etiqueta del balón en `render_clips_26oct.py` no puede pisar la de ÁRBITRO. Se
  coloca por encima del círculo y se desplaza si choca con otra.
- Va en una rama propia, con pytest en 0, y se fusiona a `main`.

---

# Resultados

## 1. Equipo: 12 de 120 → el 1,2 % NO se sostiene en el partido

`python scripts/diag28c.py equipo --marcas outputs/diagnostico_28oct_c/revision_equipo_por_obs_20min_alex.csv`
→ `outputs/diagnostico_28oct_c/equipo.json`.

- Marcas: A 56 · B 53 · portero_A 5 · portero_B 5 · árbitro 1. **0 excluidas.**
- **Errores: 12/120 = 10,0 % [5,8; 16,7]**. Por la regla, **≥ 12 → no se sostiene**.

| corte | por observación (sistema) | voto de la identidad (mismas filas) |
|---|---|---|
| total | 12/120 = 10,0 % | 35/120 = 29,2 % |
| cruce | **10/60 = 16,7 %** [9,3; 28,0] | 23/60 = 38,3 % |
| sin cruce | **2/60 = 3,3 %** [0,9; 11,4] | 12/60 = 20,0 % |
| A (marca) | 5 | 22 |
| B (marca) | 6 | 12 |
| árbitro | 1 | — |

- Por tramo de 2 min: 1, 2, 1, 2, 1, 0, 0, 1, 3, 1. **Repartido**, sin un tramo malo.
- **Dónde está: en los cruces.** 10 de los 12 errores están en filas de cruce. Fuera de los cruces,
  el 3,3 % es compatible con el 1,2 % del minuto 5 (los IC se solapan).
- ⚠️ La hoja se estratificó 50/50 cruce / no cruce, y en el partido solo el **16,6 %** de las filas
  A/B reales está en un cruce. **Reponderado al partido: 5,5 % [1,9; 10,0]**. Es el número que
  representa los 20 min; el 10,0 % es el de la hoja.
- ¿Qué podría estar inventando? El 1,2 % no era falso: el GT de 30 s cae en un minuto con pocos
  cruces. Lo que era falso es leerlo como el error del partido. Y la etiqueta por observación sigue
  ganando al voto de identidad por 3-6× en los dos estratos.

## 2. Balón con GT (200 frames de Alex)

`python scripts/gt_balon_rapido.py leer ~/Downloads/respuestas_gt_balon.csv` y
`python scripts/diag28c.py balon` → `outputs/diagnostico_28oct_c/balon.json`.

Respuestas: acepta 171 · clic 14 · rechaza 15 · no_se 0.

**(i) Zona de la hoja** (tercil de m/px de la candidata elegida):

| zona | visible | recall de la elegida | falsos positivos |
|---|---|---|---|
| cerca | 95,0 % [86,3; 98,3] | 57/57 = 100 % [93,7; 100] | 3/60 = 5,0 % [1,7; 13,7] |
| media | 96,7 % [88,6; 99,1] | 54/58 = 93,1 % [83,6; 97,3] | 2/60 = 3,3 % [0,9; 11,4] |
| lejos | 100 % [94,0; 100] | 60/60 = 100 % [94,0; 100] | 0/60 |
| sin candidata | 10/20 = 50 % visibles | — | — |

**(ii) Zona del juego** (la del 14,9 %):

| zona | n | visible | recall | FP |
|---|---|---|---|---|
| cerca | **7** | 71,4 % [35,9; 91,8] | 4/5 | 1/6 |
| media | 135 | 91,1 % [85,1; 94,8] | 114/117 = 97,4 % [92,7; 99,1] | 3/120 = 2,5 % |
| lejos | 58 | 98,3 % [90,9; 99,7] | 53/53 = 100 % [93,2; 100] | 1/54 = 1,9 % |

- **Criterio (sobre (ii)): NO DECIDIDO.** La zona cercana del juego tiene 7 frames (< 15). La hoja
  no puede decir si el 14,9 % es de encuadre o de detector.
- Lo que SÍ dice:
  - cuando hay candidata elegida, el selector acierta el **95-100 %** en todas las zonas;
  - los falsos positivos son bajos (≤ 5 %);
  - **de los 20 frames sin candidata, 10 tienen el balón visible**: el detector falla con el balón
    a la vista la mitad de las veces que no da nada. Es una señal de DETECTOR, con n = 20.
- ¿Qué podría estar inventando? 180 de 200 frames se eligieron por tener candidata, así que la
  visibilidad está sesgada hacia arriba (declarado antes). Para decidir el 14,9 % hace falta una
  hoja estratificada por la zona del JUEGO, con frames sin candidata.

**Balón inventado (último intento): PROVISIONAL, falta el control.**
- Con el GT: 9 de 180 frames con candidata = **5,0 % [2,7; 9,2]** (detalle en `balon.json`).
- El control no está cubierto por los 200: solo hay un frame de cada tramo (f26610 = 14:47,9 /
  16:20,9; f27394 = 15:14,0 / 16:47,0). Mini-hoja de 20 frames preparada:
  `outputs/gt_balon_control/index.html`. **El número no se da por bueno hasta que Alex la marque.**

## 3. Caja fundida: la hipótesis NO se confirma. 3b no se corre

`<venv numpy 1.26>/bin/python scripts/diag28c_caja_fundida.py --salida outputs/diagnostico_28oct_c`
→ `caja_fundida_cajas.json` y recortes en `outputs/diagnostico_28oct_c/recortes_caja_fundida/`
(verde = producción, rojo = sin fusión).

- **Control: pasa.** La CPU con los parámetros de producción reproduce el **100 %** de las cajas
  del caché (107/107 a IoU ≥ 0,9 en los 6 frames).
- Por instante (relojes archivo / reproductor):

| instante | frame | producción | sin fusión (distintas) | lectura |
|---|---|---|---|---|
| 14:40,1 / 16:13,1 | f26376 | 1 | 1 | el detector ve UNA (el blanco, detrás) |
| 14:40,3 / 16:13,3 | f26382 | 1 | 1 | ídem |
| 14:43,8 / 16:16,8 | f26487 | **2** | 3 | ya hay dos cajas: el naranja sale como torso (33 px) |
| 14:43,9 / 16:16,9 | f26490 | 1 | 2 | **el único caso**: GREEDYNMM se come un torso de 33 px |
| 15:05,9 / 16:38,9 | f27150 | 1 | 1 | el detector ve UNA |
| 15:06,1 / 16:39,1 | f27156 | **2** | 2 | ya hay dos cajas, y aun así se funden en el tracking |

- **Veredicto: no confirmada.** En 3 de 6 frames el detector en crudo ya da una sola caja: no hay
  nada que la fusión esconda. En 2 de 6 producción YA tiene las dos cajas: la mezcla la hace la
  ASOCIACIÓN, no la detección. El único caso a favor (f26490) es un FRAGMENTO de torso, que es lo
  que cerró BACKLOG 19: su «pie» queda 37 px por encima del pie real.
- Por la regla fijada, **no se corre 3b** (NMS IoU 0,5 en el tramo de 60 s) y no se gasta el
  intento.
- ⚠️ **Un error mío cazado por el recorte**: el primer casado asignaba cada identidad a la caja de
  pie más cercano en metros, y salía «una sola caja» en los seis frames. Las cajas de torso tienen
  el pie proyectado lejos, así que las dos identidades caían en la caja grande. Recontado por
  región de imagen, las cifras son las de la tabla.
- ¿Qué podría estar inventando? Seis frames de tres instantes. Y una etapa no mirada: el NMS
  INTERNO de YOLO (IoU 0,7, dentro de cada tesela, antes de SAHI). Una persona exactamente detrás
  de otra con IoU > 0,7 se suprimiría ahí y tampoco aparecería «sin fusión». Si se quiere mirar,
  es un plan nuevo.
- **Lo que sí apunta**: en 14:44 y 15:06 el detector da las dos cajas y el tracking las mezcla.
  Coincide con CLAUDE.md: la palanca es la asociación.
