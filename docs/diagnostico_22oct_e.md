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

---

## Resultado del bloque 0 — invariantes de hoy

`scripts/diag22e_invariantes.py`. Filas reales dentro del campo; porteros en su equipo.

| | frames | media A / B / otro | A > tope | **B > tope** | otro ≥ 2 |
|---|---|---|---|---|---|
| benjamín (tope 7) | 11.989 | 5,60 / 6,85 / 0,85 | 1,1 % | **28,5 %** | 12,2 % |
| Villaviciosa (tope 11) | 500 | **11,65** / 7,62 / 1,02 | **54,6 %** | 0,0 % | 4,2 % |

**El invariante que más se rompe no es el del árbitro: es el recuento de UN equipo.**
- En el benjamín, B pasa de 7 en el 28,5 % de los frames; en Villaviciosa, A pasa de 11 en más de
  la mitad.
- Es el desequilibrio de etiqueta del 22-oct (b), ahora contado contra el reglamento.
- En Villaviciosa casa con su 23,6 % de equipo equivocado.

**Reconciliación del 12,6 % con el 4,3 % de la guarda (benjamín):**
- 12,56 % con todas las filas → **12,19 %** solo con las reales (1.462 frames).
- De esos 1.462 frames con ≥ 2 `otro` reales:
  - **520 (4,3 % del partido)** tienen ≥ 2 identidades de la guarda. Es su cifra.
  - **930** tienen una fila `otro` SUELTA de una identidad A/B: el catálogo arbitral por
    observación. La guarda mira identidades enteras y no puede verlas.
  - 12 tienen una identidad `otro` que la guarda no cuenta (< 25 obs o mediana fuera del campo).
- ⇒ Las dos cifras son correctas y miden cosas distintas. Dos tercios de la simultaneidad la crea el
  catálogo POR OBSERVACIÓN, que actúa dentro de identidades de jugador.

**¿Quiénes son los ≥ 2 `otro`?** El árbitro es la detección del proxy; el borde, ≤ 2 m de una línea.

| tipo de frame | frames |
|---|---|
| **árbitro + alguien en el interior** | **1.372 (94 %)** |
| sin árbitro (interior) | 57 |
| árbitro + árbitro (dos filas suyas) | 28 |
| árbitro + borde (staff en la línea) | 5 |

⇒ **No es árbitro + staff dentro de la línea: es árbitro + JUGADORES.** El segundo `otro` está en el
interior, y casi siempre es una observación suelta que el catálogo saca de una identidad de jugador.

**Árbitro dentro de un equipo, ventana del GT (benjamín)**, la línea base de 1(b):
- **53,5 %** de los frames (151 de 282 con fila del árbitro);
- como referencia, el 53,0 % de los frames de la ventana no tiene ningún `otro` en el campo.

**Villaviciosa, ventana del GT**, filas `otro` reales casadas con el GT: 90 con el árbitro, 7 con un
jugador y 6 con nadie. Allí `otro` es casi siempre el árbitro.

**¿Qué podría estar inventando?**
- «Árbitro» es el proxy por detección. Si no lo marca, una fila del árbitro cuenta como «interior»
  y un frame «sin árbitro» puede tenerlo. Pero «árbitro + interior» exige que el proxy SÍ marque una
  fila y que haya otra distinta: esa otra no es él, salvo duplicado de caja (los 28 «árbitro +
  árbitro» dicen que eso pasa poco).
- «Borde» a 2 m incluiría a un jugador en la banda: aun así son solo 5 frames.

---

## Resultado del bloque 1 — tope de cardinalidad: NO CUMPLE en dos intentos; la ruta se cierra

**Implementación** (tras flag; apagado = salida idéntica byte a byte a la de `main`, comprobado en
las DOS patas):
- `src/team_classification/tope_cardinalidad.py`, con un MILP (`scipy.optimize.milp`, HiGHS);
- flag `equipos.tope_cardinalidad` en los dos configs del processor, con `activo: false`;
- `clasificar_identidades` saca a una función (`color_de_identidad`) el color medio que vota, para
  que el solver use exactamente el mismo; el CSV de hoy no cambia;
- con el flag encendido no corre el voto por observación; en el intento 2 lo sustituye la etiqueta
  por trozo.

`scripts/diag22e_tope.py`, desde caché, sin vídeo: las dos patas (incluida Villaviciosa, que aquí SÍ
se puede medir) × costes reales y permutados.

| | hoy | **intento 1** (identidad) | permutado | **intento 2** (trozo 1,5 s) | permutado | criterio |
|---|---|---|---|---|---|---|
| **(a)** benjamín, equipo equivocado | 1,2 % | **23,0 %** | 34,4 % | **1,8 %** | 46,2 % | ≤ 1,5 % → **NO / NO** |
| (a) benjamín, cobertura | 90,05 % | 90,05 % | 90,05 % | 90,05 % | 85,0 % | ≥ 89,55 → sí / sí |
| **(b)** benjamín, árbitro en un equipo (ventana GT) | 53,5 % | **2,5 %** | 2,5 % | **13,1 %** | 94,7 % | ≤ 20 % → sí / sí |
| **(c)** Villaviciosa, equipo equivocado | 23,6 % | **18,5 %** | 38,3 % | **18,3 %** | 42,5 % | ≤ 23,6 → sí / sí |
| **(c)** Villaviciosa, árbitro en un equipo (GT) | 5,3 % | **1,1 %** | 100 % | **42,1 %** | 97,9 % | ≤ 5,3 → sí / **NO** |
| **(d)** etiquetas por (identidad, minuto), benjamín | 1,45 | 1,00 | 1,00 | **1,51** | 2,06 | ≤ hoy → sí / **NO** |
| (d) tiempo del solver, benjamín 20 min | — | 7,9 s | 7,9 s | 6,7 s | 7,8 s | < 60 s → sí / sí |
| control: permutado ≥ real + 5 puntos | | | 34,4 ≥ 28,0 ✓ | | 46,2 ≥ 6,8 ✓ | |
| *invariantes (por construcción, no son evidencia)*: frames con B > 7 / otro ≥ 2 | 28,5 / 12,2 % | 7,1 / 1,4 % | | 2,3 / 1,4 % | | |
| filas reales que cambian de etiqueta (benjamín) | | 43.964 (25 %) | | 12.776 (7,3 %) | | |

**El control pasa en los dos intentos**: con los costes permutados todo empeora mucho. El resultado
depende del color, así que se puede leer.

**Intento 1 (por identidad): falla solo por (a), que es lo que permitía el intento 2.**
- *De dónde sale el 23 %* (diagnóstico, no intento):
  - el mismo solver con topes que nunca muerden da **16,0 %**;
  - el sistema de HOY sin el voto por observación da también **16,0 %**: el coste reproduce
    exactamente el voto por identidad;
  - ⇒ **el voto por observación vale 16,0 → 1,2 % en la ventana del GT**, y etiquetar por
    identidad lo pierde;
  - los topes, encima, suman ~7 puntos: con identidades quimera (una persona es N identidades, y
    una identidad son a veces dos personas), «cumplir el 7» se consigue mandando la identidad
    entera al otro equipo.
- **En Villaviciosa, en cambio, mejora las dos cosas**: equipo equivocado 23,6 → 18,5 % y árbitro
  5,3 → 1,1 %. Allí no hay voto por observación que perder, y A pasaba de 11 en el 55 % de los
  frames.

**Intento 2 (por trozos de 1,5 s): falla por (a) por poco, por (c) y por (d).**
- Benjamín: 1,8 %, unos 4 fallos más de ~723.
- Villaviciosa: el árbitro dentro de un equipo **sube de 5,3 a 42,1 %**. Es el principio de
  CLAUDE.md: «el árbitro en un recorte suelto NO EXISTE; su color solo aparece al promediar ~40
  recortes». Un trozo de 1,5 s son ~12 recortes en Villaviciosa: su color medio no distingue al
  árbitro, y el tope «otro ≤ 1» lo reparte. Por identidad (intento 1) sí lo veía.

**Decisión: no se adopta, y la ruta se cierra (dos intentos). El bloque 2 no se ejecuta** (era solo
si el 1 pasaba).

Como dato para un plan futuro, no como tercer intento:
- **los topes ayudan donde la etiqueta ya es por identidad** (Villaviciosa, intento 1, mejora todo);
- **estorban donde manda el voto por observación** (benjamín);
- y la unidad que serviría a los dos sitios no es la identidad ni el trozo fijo: hacen falta
  identidades PURAS. Otra vez, la asociación.

**¿Qué podría estar inventando?**
- **El 2,5 % de árbitro en un equipo del intento 1 (benjamín)** es real, pero sale junto a un 23 %
  de equipo equivocado: una métrica que solo mira al árbitro no ve que se rompieron los jugadores
  (la lección de las marcas del campo).
- **El 18,5 % de Villaviciosa** está medido en 60 s y una sola ventana del GT de 100 frames.
- **Los invariantes** (B > 7 de 28,5 a 2,3 %) son por construcción: no dicen que las etiquetas
  estén bien, solo que respetan el tope.

**Filas que cambian y hojas de revisión** (60 recortes cada una, semilla 0, identidad y etiqueta
ocultas, ffmpeg CLI):
- `tope_cardinalidad` (intento 1). Cambios A→B 14.321, B→A 19.738, a/desde `otro` ~9.900.
- `tope_trozo` (intento 2). Cambios B→otro 4.896, B→A 3.123, otro→A/B 3.511, A→otro 358, A→B 888.

Se abren con `python scripts/revision_equipos.py html --ventana tope_trozo` (o `tope_cardinalidad`).
Si se marca alguna, la del intento 2 es la más informativa: es la que está a 0,6 puntos del criterio
en el benjamín, y la hoja diría si sus 12.776 cambios fuera de la ventana del GT aciertan.

## Bloque 2 — NO ejecutado

Era «solo si el 1 pasa». No pasa.

---

## Resultado del bloque 3 — balón recortado al campo (flag `balon.recortar_a_campo`): CUMPLE (cosmético)

**Implementación.**
- `ParametrosBalon.recortar_a_campo` (por defecto `False`), en el bloque `balon:` de
  `configs/campo_benja.yaml` (`false`).
- `recortar_al_campo()` lleva el punto al más cercano del rectángulo [0, 62] × [0, 40].
- Se aplica en `procesar_balon.py` al EXPORTAR, sobre las filas `balon` y `balon_aereo`: contactos,
  posesión, fases aéreas y tramos se calculan antes y no cambian.
- Test nuevo en `tests/test_corte_duro_balon.py`.

**Flag apagado**: el CSV conjunto es idéntico byte a byte a `main`.

**Flag encendido** (parte entera):

| | resultado | criterio |
|---|---|---|
| filas de balón fuera del campo | 947 → **0** | 0 → sí |
| filas que ya estaban dentro | **idénticas** a `main` (todas las columnas) | sí |
| filas a 0-3 m fuera (saques) | **947 de 947 sobre la línea** | sí |
| jugadores y resto de columnas | idénticos; solo cambian `x_m` e `y_m` | — |
| desplazamiento de las recortadas | mediana 1,29 m, máximo 2,96 m | (informativo) |

El máximo no pasa de 3 m porque en la pizarra de `main` no hay ninguna fila de balón a más de 3 m
fuera: la plausibilidad las quita antes (bloque 3 del 22-oct d).

⚠️ **Es COSMÉTICO, no precisión.** El punto recortado no es donde estaba el balón:
- en un saque, es la línea por la que salió, y es lo esperable;
- en un balón aéreo interpolado o en un relleno, es simplemente el borde más cercano a una
  posición que ya era aproximada.
- No debe usarse para medir: las distancias o velocidades calculadas sobre filas recortadas
  subestiman el recorrido real, hasta 2,96 m por fila.

Queda **apagado**: encenderlo es una decisión de presentación de Alex, no de medida.
