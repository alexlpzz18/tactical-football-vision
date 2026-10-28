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
