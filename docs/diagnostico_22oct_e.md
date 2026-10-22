# Diagnóstico 22-oct (e): invariantes de recuento, etiqueta con tope de cardinalidad, balón recortado al campo

Rama `fix-22oct-e`, sale de `fix-22oct-d`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque; como mucho dos intentos por variante. Producción solo cambia tras flags apagados por
defecto: con ellos apagados, la salida idéntica a `main` (comprobado byte a byte).

Relojes del vídeo del benjamín: el del ARCHIVO y el del reproductor de Alex (+1:33).

---

## Bloque 0 — línea base de invariantes (solo medición; partido entero; filas REALES)

- Por frame, nº de filas reales **A** (con portero_A), **B** (con portero_B) y **otro**, DENTRO del
  campo (benjamín 62 × 40; Villaviciosa 100 × 64). % de frames con A > tope, B > tope y otro ≥ 2
  (tope 7 en el benjamín, 11 en Villaviciosa). Hoy, sobre las pasadas de producción.
- **Reconciliar el 12,6 % (bloque 1a del 22-oct d) con el 4,3 % de la guarda.** Se dice qué parte
  de la diferencia viene de cada cosa:
  - todas las filas contra solo las reales;
  - filas `otro` sueltas de identidades A/B (catálogo por observación);
  - identidades `otro` que la guarda no cuenta (< 25 obs, o con la mediana fuera del campo);
  - y el resto.
- **Desglose de los frames con otro ≥ 2** (benjamín). Cada fila `otro` es:
  - **árbitro**, si su detección es del proxy fijado el 22-oct (b);
  - **borde**, si está a ≤ 2 m de una línea (staff que pisa el campo);
  - **interior**, si no.

  Tipos de frame: árbitro + borde, árbitro + interior, árbitro + árbitro, sin árbitro. En
  Villaviciosa, en la ventana del GT, las filas `otro` casadas con el árbitro del GT, con un jugador
  o con nadie.
- **Árbitro dentro de un equipo en la ventana del GT (benjamín)**, la línea base de 1(b): % de los
  frames de la ventana con fila de una detección del árbitro (proxy fijado) en los que esa fila es
  A/B. Aparte, como referencia: % de frames de la ventana sin ningún `otro` en el campo (el «~50 %»
  del 22-oct d).

¿Qué podría estar inventando? «Borde» es geometría: un jugador pegado a la banda cuenta como borde.
Por eso se separa del árbitro por el proxy, no por la posición.

## Bloque 1 — etiqueta con tope de cardinalidad (ruta nueva; flag `equipos.tope_cardinalidad`)

**Qué se implementa** (`src/team_classification/tope_cardinalidad.py`, flag en el bloque `equipos:`
del config del processor, apagado por defecto):

- Se corre la clasificación de hoy y se FIJAN las identidades que sus reglas hacen portero_A,
  portero_B o staff. Los porteros cuentan en el tope de su equipo; el staff no cuenta.
- El resto de identidades recibe una etiqueta ∈ {A, B, otro} minimizando Σ coste, con el **coste de
  color actual, sin tocar la feature**. Para la identidad i, con n_i observaciones con color y su
  color medio m_i (el MISMO que usa `clasificar_identidades`):
  - c(A) = n_i · ‖m_i − prototipo_A‖ y c(B) = n_i · ‖m_i − prototipo_B‖;
  - c(otro) = n_i · (1 − f_i) · d_otro.
    - d_otro = ‖m_i − prototipo_otro‖ si el clasificador lo tiene (Villaviciosa);
    - si no (benjamín: medido, NO tiene prototipo `otro`), la separación ‖A − B‖, que es la escala
      de «lejos de los dos» que ya usa `dist_max`;
    - f_i = fracción de las observaciones de la identidad cuya ventana de 1,5 s dispara el catálogo
      arbitral (el mismo test que `etiquetar_por_observacion`).
- **Restricciones**, en cada frame, contando solo observaciones DENTRO del campo:
  - A ≤ tope − porteros_A presentes;
  - B ≤ tope − porteros_B presentes;
  - otro ≤ 1.

  Los conjuntos de identidades presentes a la vez son los cliques que de verdad ocurren. Se usan
  los de cada frame, no los del grafo de intervalos primera-última, porque una identidad con huecos
  no está presente en sus huecos. Los frames con el mismo (conjunto, porteros) dan una sola
  restricción.
- **Blandas**: holgura ≥ 0 con penalización λ = **1,0 por frame y por persona de exceso**, fijada
  antes de medir: un frame de exceso pesa lo que una observación a distancia 1. Así toleran cajas
  fantasma breves.
- **Solver**: `scipy.optimize.milp` (HiGHS), binarias por identidad y etiqueta.
- **Con el flag encendido se apaga `etiquetar_por_observacion`**: la etiqueta es por identidad, y
  una etiqueta por observación posterior rompería los topes. Se cuenta como parte del intento 1.
- `tope` = 7 (F7) / 11 (F11) y λ, en el config.

**Criterios** (antes de medir). A, B ≤ tope y otro ≤ 1 se cumplen por CONSTRUCCIÓN y NO cuentan como
evidencia.

- **(a)** benjamín, ventana del GT: equipo equivocado (protocolo de `comparar_escalas.py`) ≤ hoy +
  0,3 puntos y cobertura ≥ hoy − 0,5;
- **(b)** benjamín, ventana del GT: árbitro dentro de un equipo (definición del bloque 0) ≤ 20 %;
- **(c)** Villaviciosa, que se puede medir (las cachés están en local y el GT anota al árbitro):
  árbitro dentro de un equipo ≤ 5,3 % y equipo equivocado ≤ 23,6 %;
- **(d)** etiquetas distintas por (identidad, minuto), en media sobre las filas reales, ≤ hoy; y
  solver < 60 s en los 20 min.

**Control**: los costes de color se PERMUTAN al azar entre identidades (semilla 0; cada identidad
conserva su n_i y su presencia). El equipo equivocado del benjamín tiene que ser **≥ el de la
versión real + 5 puntos**. Si no, el resultado no depende del color y no se lee.

**Se reporta**:
- cuántas filas reales cambian de etiqueta frente a hoy;
- una hoja de revisión `tope_cardinalidad` con 60 recortes al azar (semilla 0) de filas cuya
  etiqueta cambia, con identidad y etiqueta ocultas (formato de `revision_equipos.py`, ffmpeg CLI).

**Intento 2**, solo si el 1 falla ÚNICAMENTE por (a): la misma optimización sobre TROZOS de
identidad de 1,5 s (la ventana de `etiquetar_por_observacion`) en vez de identidades enteras, con el
mismo coste por trozo. Si falla por otra cosa, no hay intento 2.

¿Qué podría estar inventando? Un error de equipo bajo en 30 s del minuto 5 puede convivir con malas
decisiones en los minutos 10-12 (ya pasó con v3). Por eso (c) mira la otra pata y el control mira
si el color manda.

## Bloque 2 — v3 como coste, no como asignación (solo si el 1 pasa; un único intento)

c(otro) se sustituye por n_i · (1 − g_i) · d_otro, donde g_i = fracción media, sobre las
observaciones de la identidad, de los píxeles del torso (centro de la caja, filas 0,20-0,45 y
columnas 0,35-0,65) que caen en la caja del chaleco: H 40-52, S ≥ 150, V ≥ 235. Medido con el ffmpeg
CLI. Mismos criterios y control. En Villaviciosa (amarillo, sin vídeo en local), (c) «no medido»:
no se adopta.

## Bloque 3 — balón, solo cosmético (flag `balon.recortar_a_campo`)

Con el flag, toda fila de balón del CSV fuera del rectángulo del campo se lleva al punto más
cercano del rectángulo, solo en la exportación (contactos y posesión no cambian).

**Criterio**:
- 0 filas fuera del campo;
- las filas que ya estaban dentro, idénticas a `main` fila a fila;
- las de 0-3 m fuera (saques) quedan SOBRE la línea (x ∈ {0, 62} o y ∈ {0, 40}).

Flag apagado: CSV idéntico byte a byte a `main`.

Se documenta que es **cosmético**: la posición recortada no es más precisa; solo deja de pintarse
fuera.
