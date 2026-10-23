# Diagnóstico 23-oct (d): velocidades de la pista, emisión cruzada, regla de portero y clip

Rama `fix-23oct-d`, sale de `fix-23oct-c`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque, solo con pytest en código 0. Producción solo cambia tras flag (apagado = idéntico a
`main`). Todo se mide sobre la **variante 2 («añade»)** del 23-oct (c), la que se quedó más cerca.
Su pista es la misma que la de la variante 1: las dos variantes solo difieren en qué hacen después.

Relojes: frame / 29,97 = tiempo del **archivo**; el reproductor de Alex va **+1:33**.

---

## Bloque 1 — los pasos de la pista a más de 9 m/s

Ayer: el 1,03 % de los pasos de la pista supera 9 m/s, y el criterio era ≤ 1 %. **El criterio de
ayer no se cambia**; aquí solo se explica de dónde sale ese 1,03 %.

**Paso** = dos frames CONSECUTIVOS de la pista, aunque haya un hueco entre ellos (la misma definición
que `metricas_pista`). Velocidad = distancia en metros / Δt.

Cada paso de más de 9 m/s se clasifica por:
- **zona**: metros por píxel en el pie (la homografía local; < 0,1 cerca, 0,1-0,2 medio, > 0,2 fondo);
- **magnitud**: 9-12, 12-20, 20-40 y > 40 m/s;
- **hueco**: Δt de un frame procesado (≤ 0,15 s) o más (la pista saltó frames o pasó por «no visible»);
- **¿cambia la detección elegida de persona?**: las dos detecciones pertenecen a identidades
  DISTINTAS del tracker (la identidad sale del CSV, con la caja cruda más cercana, como el proxy de
  siempre);
- **¿cae el chaleco?**: alguna de las dos detecciones tiene log LR ≤ 0;
- **¿caja fundida?**: alguna de las dos cajas solapa otra caja del frame con IoU > 0,1 (la definición
  de cruce del 23-oct b).

**Control: los jugadores al mismo muestreo.**
- Para cada persona del GT del benjamín (14 tracks, frames 9750-10635), en CADA frame procesado de la
  ventana: su posición del GT interpolada linealmente entre las anotaciones (cada 15 frames).
- La pista del jugador es la detección casada 1-a-1 a ≤ 1 m de esa posición (Hungarian, el protocolo
  de siempre).
- Su fracción de pasos > 9 m/s se calcula con la MISMA definición de paso.
- Se compara con la fracción de la pista del árbitro en la misma ventana y en el partido entero.

**Lectura fijada antes (de Alex):**
- Los jugadores dan **≥ 0,7×** la fracción del árbitro: el criterio no era específico (el temblor
  de las detecciones también lo dispara), y el fallo del 1,03 % **no cuenta**.
- Dan **menos de 0,7×**: son saltos reales de la pista. Se añade una **penalización de continuidad**
  tras un parámetro (por defecto 0 = la pista idéntica a hoy), y se mide con los criterios de AYER,
  sin cambiarlos.

¿Qué podría estar inventando?
- El casado a ≤ 1 m del GT RECORTA los saltos de los jugadores: una detección que salta más de ~2 m
  ya no se casa. Esto sesga el control hacia ABAJO, es decir, a favor de «saltos reales». Se dice
  cuánto pesa repitiendo el control a ≤ 2 m.
- La ventana del GT es de 30 s del minuto 5: el árbitro se compara también en esa ventana.

## Bloque 2 — emisión con mitades cruzadas

La ventana del GT se parte en dos por el frame 10192: H1 = 9750-10191 y H2 = 10192-10635. Se hacen
dos modelos de emisión, con la misma verdad del 23-oct (a) y los mismos bins:
- uno estimado solo con H1 y evaluado en H2;
- otro estimado solo con H2 y evaluado en H1.

Para cada uno, la variante 2 sobre la parte entera:
- **cobertura** y **B > 7**, en el partido entero;
- **centroide** (`foto_de_estado`), SOLO en la mitad que el modelo no vio.

La referencia es el modelo de la ventana entera (el de ayer), medido sobre la misma mitad.

**Criterio**:
- el centroide no cambia más de **0,03 m**;
- cobertura y B > 7 no cambian más de **1 punto**.

Si cambian, se dice cuánto y en qué dirección.

¿Qué podría estar inventando? Con ~35 filas de árbitro por mitad, el suavizado de Laplace pesa más.
Un modelo «estable» podría serlo porque la pista la manda el movimiento y no la emisión. Se informa
también el log LR de cada bin de los tres modelos.

## Bloque 3 — la regla de portero (solo medición, no se implementa nada)

**(a) La fila de más en los frames con B > 7.**
- 30 frames con B > 7 de la variante 2, repartidos por el partido: 30 tramos iguales de tiempo, y un
  frame al azar (semilla 1) de cada tramo que tenga alguno.
- Panel por frame: el vídeo con todas las cajas (etiqueta e identidad) y, al lado, la pizarra de ese
  frame.
- Clasificación a ojo de la fila de más:
  - **portero con rol equivocado**, con dos subtipos: (a1) el portero verde de B etiquetado como
    jugador de B; (a2) el portero de A etiquetado B;
  - árbitro;
  - fantasma o balón;
  - duplicado;
  - jugador de A etiquetado B;
  - otro.

**(b) ¿Quién se lleva `portero_A` / `portero_B`, y cuál es el portero real?**
- Proxy del **portero real** por frame: la detección más profunda dentro de su área (área F7 del
  modelo: x 0-12 y 50-62, y 7-33):
  - para B, la de mayor x con x ≥ 50;
  - para A, la de menor x con x ≤ 12.
  - Es POSICIÓN DEL INSTANTE, no de la identidad: la regla de producción decide sobre el conjunto de
    fragmentos de una identidad, así que el proxy no es la misma medida.
- **Control del proxy, ANTES de usarlo:**
  - en la ventana del GT, los tracks GT de los porteros (la persona con la mediana de x más extrema
    de cada lado): ¿el proxy cae a ≤ 1,5 m de ellos?
  - en los 30 paneles, con el proxy marcado: ¿es el portero (camiseta verde de B / negra de A)?
  - Si el proxy acierta menos del **80 %** en alguno de los dos, la fracción de rol correcto queda
    **NO MEDIDA** y solo vale la lectura a ojo.
- **Frames con ambos porteros visibles** = el proxy encuentra candidato en las dos áreas.
- Por lado se mide:
  - la **fracción de frames con rol correcto** (la detección del proxy lleva `portero_X`);
  - la tabla de identidades que se llevan `portero_X`, con filas y tramo;
  - los fallos por tipo:
    1. la etiqueta se la lleva OTRA detección; se cuenta si es un jugador del otro equipo según el
       voto de color de ESA observación;
    2. el portero real está **cortado por el borde inferior** (la caja toca el borde) y no lleva su
       etiqueta;
    3. nadie lleva la etiqueta en ese frame (sin corona);
    4. dos `portero_X` a la vez.
- **Propuesta** del cambio mínimo con su criterio, SIN implementar.

## Bloque 4 — el clip 10:00-10:45 del archivo (11:33-12:18 del reproductor)

- Vídeo con etiquetas y pizarra, con **hoy** y con la **variante 2**, para que Alex los compare
  (`diag23b_auditoria.py render`).
- Explicación, con los datos de la pista, de por qué en el frame **f23553** (**13:05,9** archivo /
  **14:38,9** reproductor) la variante 2 deja al árbitro en B.

---

## Resultado del bloque 1 — los pasos a más de 9 m/s

`python scripts/diag23d.py velocidades --salida outputs/diagnostico_23oct_d` (`velocidades.json`; el
detalle paso a paso, en `bloque1_pasos.json`).

Comprobación previa: la pasada de hoy y la de la variante 2 dan un CSV **idéntico byte a byte** al
de ayer (`cmp`). Se mide lo mismo que se midió.

### La lectura fijada: el criterio NO era específico

| | pasos | > 9 m/s |
|---|---|---|
| pista del árbitro, partido entero | 11.641 | **1,03 %** (120) |
| pista del árbitro, solo la ventana del GT | 289 | 0,0 % (0) |
| **jugadores del GT, mismo muestreo, casados a ≤ 1 m** | 3.074 (14 personas) | **2,28 %** |
| jugadores del GT, casados a ≤ 2 m | 3.637 | 4,81 % |

- Los jugadores dan **2,2× la fracción del árbitro**, por encima del 0,7× fijado: **el fallo del
  1,03 % no cuenta**.
- Ningún benjamín corre a más de 9 m/s. Si los jugadores casados con el GT, con su posición real
  conocida, pasan ese umbral el 2,3 % de las veces, lo que dispara el criterio es el **temblor de la
  detección**: 1 px vale hasta 0,42 m en el fondo y un paso dura 0,1 s.
- El sesgo previsto va en la dirección que refuerza la lectura: casar a 2 m (más permisivo) DUPLICA
  la fracción de los jugadores.
- **No se añade la penalización de continuidad.** El criterio de ayer no se cambia: formalmente sigue
  en ✗. Lo que cambia es lo que dice ese ✗.

### De dónde salen los 120 pasos de la pista

| | sí | no | lo que dice |
|---|---|---|---|
| cruzan un **hueco** (Δt > 0,15 s) | 54 | 66 | solo el 2,0 % de los pasos tiene hueco, pero el 22,8 % de ellos supera 9 m/s; sin hueco, el 0,58 % |
| tienen **caja fundida** (IoU > 0,1) | 74 | 46 | el 19 % de todos los pasos tiene caja fundida; con ella, el 3,3 % supera 9 m/s; sin ella, el 0,49 % |
| **cambian de identidad** del tracker | 10 | 110 | casi nunca salta a OTRA persona del tracker |
| el **chaleco cae** (log LR ≤ 0) | 2 | 118 | la pista casi nunca pisa una detección sin chaleco |

- **Por zona**: cerca 0,54 %, medio 0,82 %, fondo **1,34 %**. Crece con los metros por píxel, que es
  la firma del temblor y no la de un cambio de persona.
- **Por magnitud**: 57 en 9-12, 45 en 12-20, 17 en 20-40 y 1 > 40 m/s. Son casi todos saltos de
  1-2 m en 0,1 s: una caja fundida desplaza su pie.
- Quedan **32 pasos** (0,27 % de la pista) sin hueco y sin caja fundida.

### ¿Qué podría estar inventando este número?
- El 0,0 % del árbitro en la ventana del GT son 0 de 289 pasos. Con la tasa del partido se esperarían
  3, y ver 0 pasa un ~5 % de las veces. No es prueba de nada; por eso la comparación se hace contra
  la tasa del partido.
- El control de los jugadores no es una pista de Viterbi: casa por persona en cada frame. Puede saltar
  de detección cuando dos jugadores están a menos de 1 m, lo mismo que puede hacer la pista. Las dos
  medidas tienen el mismo tipo de ruido; por eso el control vale.
- «Caja fundida» y «fondo» no son independientes: en el fondo las cajas son pequeñas y se solapan más.
  No se ha separado una cosa de la otra.

## Resultado del bloque 2 — emisión con mitades cruzadas: PASA

`python scripts/diag23d.py cruzada --salida outputs/diagnostico_23oct_d` (`cruzada.json`).

**Los tres modelos** (log LR por bin; bins [0, 0,002, 0,005, 0,01, 0,02, 0,05, 0,1, 0,2, 1]):

| modelo | filas de árbitro / jugador | log LR |
|---|---|---|
| ventana entera (ayer) | 71 / 610 | −1,64 · 2,06 · 0,45 · 1,36 · 2,06 · 1,36 · 3,16 · 5,0 |
| solo H1 (9750-10191) | 33 / 323 | −2,30 · 2,09 · 0,99 · 2,09 · 2,09 · 2,09 · 2,09 · 5,0 |
| solo H2 (10192-10635) | 38 / 287 | −1,31 · 1,86 · 0,76 · 1,17 · 1,86 · 1,17 · 2,96 · 5,0 |

**La variante 2 con cada modelo**, comparada con el modelo de la ventana entera:

| | cobertura | B > 7 | centroide en la mitad NO vista | pista con la misma detección |
|---|---|---|---|---|
| estima H1, evalúa H2 | 97,08 % (−0,03) | 8,45 % (0,00) | 1,078 m (0,000) | 99,93 % |
| estima H2, evalúa H1 | 97,12 % (+0,01) | 8,41 % (−0,04) | 0,261 m (0,000) | 99,90 % |

Los tres criterios (centroide ≤ 0,03 m; cobertura y B > 7 ≤ 1 punto) **se cumplen en las dos
direcciones**: los números no dependen de haber estimado la emisión en la misma ventana donde se
mide.

¿Qué podría estar inventando?
- **La estabilidad no dice que la emisión no importe**: el control permutado de ayer, con la misma
  pista y la emisión barajada, perdía al árbitro (cobertura 97 → 32 %). Los tres modelos comparten la
  forma: el bin sin chaleco es negativo (−1,3 a −2,3), todos los demás son positivos y el último
  satura en +5. La pista depende del ORDEN de las detecciones por chaleco, no del valor exacto, y ese
  orden es el mismo con 33 filas que con 71.
- Los 1,078 m y 0,261 m son el centroide de cada mitad, no un cambio: la segunda mitad es el tramo
  malo conocido del GT (el error triplica entre los tercios de la ventana). Lo que se compara es
  la diferencia, que es 0.

## Resultado del bloque 3 — la regla de portero (solo medición)

Scripts:
- `python scripts/diag23d.py porteros --salida outputs/diagnostico_23oct_d` (`porteros.json`; los
  paneles, en `paneles_30/`);
- `python scripts/diag23d.py tabla_filas_b ...` (`tabla_filas_b.json`), el apoyo a la lectura a ojo.

### ⚠️ Corrección de lo que escribí ayer (23-oct c)
Ayer puse que, con la pista, la fila de más era «casi siempre un PORTERO con el rol equivocado»: el
portero verde de B etiquetado como jugador de B. **Esa lectura estaba mal planteada.** El recuento de
B **incluye a `portero_B`** (`recuento_por_frame` mete a cada portero en su equipo). Así que un
portero verde etiquetado «B» cuenta exactamente igual que uno etiquetado `portero_B`: **no añade
ninguna fila**. Lo que sí añade una es que `portero_B` se lo lleve OTRA persona, la de A, mientras el
portero de verdad sigue contado en B. Hoy se clasifica con esa cuenta.

### (a) La fila de más en los frames con B > 7 (variante 2)
- Salen **28 paneles, no 30**: dos de los 30 tramos no tienen ningún frame con B > 7.
- Lectura a ojo, PROVISIONAL, apoyada en la tabla de cada fila B (voto de color de la observación,
  caja duplicada, fragmento, fundida).

| la fila de más es… | frames | ejemplos (archivo / reproductor) |
|---|---|---|
| **una fila DUPLICADA**: dos identidades del CSV sobre la MISMA caja | **8** | f4923 (2:44,3 / 4:17,3), f13959, f18885 |
| **un jugador de A etiquetado B** | 4 | f9264 (5:09,1 / 6:42,1), f16779, f23289, f32244 |
| **`portero_B` llevado por un jugador de A** (identidad quimera) | 4 | f924, f11193 (#211), f34611 y f34935 (#766) |
| **fragmentos de una caja fundida** (un racimo de jugadores) | 4 | f22656, f25176, f27243, f28581 |
| **el árbitro** | 3 | f20682 (#288), f29799, f30018 (#764) |
| fantasma (caja diminuta) | 1 | f1806 (#55) |
| no se distingue | 4 | f3351, f12579, f24954, f33183 |

- La fila de más **no tiene un dueño**. El grupo mayor (8 de 28) es una fila DUPLICADA. Son
  29 filas B en los 28 frames con otra fila en la misma caja: es asociación, no color ni regla.
- El rol de portero explica 4 de 28 (14 %).
- El árbitro sigue siendo la fila de más en 3 de 28 (11 %). Ayer la auditoría de la v2 daba 1 de 20.

### (b) ¿Quién se lleva `portero_A` / `portero_B`?

**Control del proxy** (la detección más profunda de su área), contra los porteros del GT, en la ventana:

| lado | track GT | proxy a ≤ 1,5 m | |
|---|---|---|---|
| B (portería del fondo) | 7 (x mediana 56,8) | **90,0 %** de 60 | ✓ vale |
| A (portería de la cámara) | 6 (x mediana 8,1) | **49,2 %** de 59 | ✗ < 80 % |

- **Lado A: la fracción automática queda NO MEDIDA.** El portero de A está cortado por el borde
  inferior en 47 de 57 muestras (`docs/portero_cortado.md`): su pie no se ve y su posición en metros
  no es la del pie, así que «el más profundo» no es él.
- A ojo, en los 28 paneles:
  - **desde f4662 (2:35,6 / 4:08,6) `portero_A` está sobre el portero negro en todos los paneles
    donde se ve** (10 de 10);
  - **en los tres primeros (f924, f1806, f3351) el portero de A es `otro` #26**. Es una de las
    identidades del tercer grupo que avisa el log («26 (1095 obs)»): el `azul_electrico` ya
    documentado (`docs/peso_arbitro_y_portero.md`).

**Lado B** (proxy válido), en los 8.746 frames con candidato en las dos áreas:

| | frames | % |
|---|---|---|
| **rol correcto** (la detección del proxy lleva `portero_B`) | 5.268 | **60,2 %** |
| 3 · sin corona: nadie lleva `portero_B` | 2.692 | 30,8 % |
| 1b · lo lleva otra detección con voto de color B | 557 | 6,4 % |
| 1 · lo lleva un jugador del OTRO equipo (voto de color A) | 117 | 1,3 % |
| 4 · dos `portero_B` a la vez | 112 | 1,3 % |
| 2 · cortado por el borde | 0 | — |

- En 3.460 de los 3.478 fallos, **el portero real está etiquetado `B`**: se cuenta en su equipo y en
  su sitio. Para el centroide y para B > 7 **no cuesta nada**. Cuesta en el informe, si este dice
  «el portero».
- Los fallos que SÍ cuestan filas son el 1 y el 4 (229 frames, el 2,6 %): son los que salen en los
  paneles.

**Las identidades que se llevan `portero_B`**, verificadas a ojo sobre los paneles:

| id | filas | tramo (archivo) | ¿es el portero? |
|---|---|---|---|
| 11 | 409 | 0:00-0:42 | ✗ en f924 es un jugador blanco de A |
| 211 | 1.525 | 3:45-6:20 | ✓ en f9264 y f10782; ✗ en f11193 (6:13,5): la identidad pasa a un jugador de A |
| 350 | 1.953 | 6:33-9:51 | ✓ (f12579, f13959, f16779) |
| 665 | 1.502 | 13:13-15:43 | ✓ (f24954, f25176, f27243) |
| 766 | 2.536 | 15:45-20:00 | ✓ hasta f32244; ✗ en f34611 y f34935 (19:15-19:26): otra quimera con un jugador de A |
| 883 | 490 | 19:07-20:00 | ✓; a la vez que la 766 |

- Hay dos huecos sin `portero_B`: **0:42-3:45** y **9:51-13:13** (archivo). En ellos el portero verde
  es `B` (#6, #14, #525).
- El patrón del fallo que cuesta: **la regla corona una identidad entera, y la identidad, al
  alargarse, se lleva a otra persona**. Es la lección de «una persona es N identidades», vista al
  revés: una identidad son N personas.

### (c) Propuesta del cambio mínimo (NO implementado)
**«`portero_X` por observación, con dos señales»**:
- Una observación de una identidad coronada como `portero_X` conserva el rol, salvo que se cumplan
  las dos condiciones a la vez:
  1. NO es la detección más profunda de su área en ese frame (o está a > 3 m de ella);
  2. su voto de color por observación (ventana de 1,5 s, el de `etiquetar_por_observacion`) es del
     OTRO equipo.
- Si se cumplen las dos, vuelve a su voto de color.
- Además, la **exclusividad por frame**: un solo `portero_X` por frame, el más profundo.
- Es la forma de «dos señales débiles que juntas son fuertes»: la posición sola se equivoca en los
  córneres, y el color solo, con el portero verde.

**Criterio, para fijarlo ANTES de medir:**
- fallos de tipo 1 + 4 en B: 229 → **≤ 50 frames**;
- B > 7 **no sube**; equipo equivocado ≤ 1,5 %; centroide ≤ hoy;
- hoja de 60 observaciones que pierden `portero_B`: **≤ 10 % son el portero real**;
- control: las mismas dos condiciones con la etiqueta de equipo BARAJADA tienen que dar ≥ 3× más
  observaciones movidas.
- No toca el lado A: allí el proxy no vale. El portero de A en `otro` de los minutos 0-2 es otra
  causa, la del catálogo.

¿Qué podría estar inventando?
- **El 60,2 % depende del proxy**. El proxy acierta el 90 % en la ventana del GT, así que hasta ~10
  puntos de «fallo» pueden ser del proxy y no de la regla (córneres, un defensor por detrás del
  portero).
- **El voto de color de los tipos 1 y 1b** usa un clasificador reentrenado con el caché CRUDO, no
  con el filtrado que usa producción. Puede diferir en las observaciones dudosas; por eso el tipo 1
  se apoya en los paneles y no solo en el número.
- **La clasificación de los 28 paneles es mía y a ojo**, con cajas de 15-40 px. «Duplicado» se
  apoya en un hecho medible (dos filas casadas con la misma caja), los demás no tanto. Los 4 «no se
  distingue» se dejan así y no se reparten.

## Resultado del bloque 4 — el clip y el frame f23553

`python scripts/diag23d.py clip --salida outputs/diagnostico_23oct_d`. En
`outputs/diagnostico_23oct_d/clip_10m/` (no van al repo):
- `video_10m_hoy.mp4` y `video_10m_variante.mp4`;
- `pizarra_10m_hoy.html` y `pizarra_10m_variante.html`.

El tramo es 10:00-10:45 del archivo (11:33-12:18 del reproductor).

### ⚠️ En este clip hoy y la variante 2 casi no se distinguen
- Solo **13 filas** de 6.776 cambian de etiqueta, todas de A/B a `otro` (ids 292, 429 y 468).
- En ese minuto hoy ya manda al árbitro a `otro` casi siempre. Es el mismo efecto que en las cachés
  de 60 s del minuto 5, donde la v2 no cambiaba nada.
- En el partido entero cambian 5.238 filas. Los tramos de 45 s donde más se distinguen:
  - **1:00-1:45 archivo / 2:33-3:18 reproductor**: 429 filas;
  - **7:00-7:45 archivo / 8:33-9:18 reproductor**: 427 filas;
  - 0:45-1:30 archivo / 2:18-3:03 reproductor: 421 filas.
- No se han renderizado: el encargo era 10:00-10:45.

### Por qué la variante 2 deja al árbitro en B en f23553 (13:05,9 archivo / 14:38,9 reproductor)
Detalle frame a frame en `traza_f23553.json`.

1. La pista sigue al árbitro (identidad 288, chaleco 0,37-0,65, log LR +5) en TODOS los frames de
   13:02,9 a 13:05,8. En esos frames su fila es `otro`.
2. **En f23553 la pista se salta ese frame.** La detección del árbitro sigue ahí (chaleco 0,63,
   log LR +5, caja sin fundir: IoU 0,02), pero su pie salta de (37,37; 11,11) a (38,42; 10,98):
   **1,05 m en 0,1 s**. En el frame siguiente vuelve a 37,46.
3. El salto, solo, cabe en la puerta (0,78 m de la predicción, contra 1,3). Pero la pista arrastra
   la velocidad del predecesor: si pasa por f23553, la predicción del frame siguiente cae en
   ~39,2 m. Volver a 37,46 sale a 1,75 m, FUERA de la puerta. La alternativa, saltarse un frame,
   cuesta solo 1,0, y Viterbi la elige.
4. En la variante 2 solo las filas DE LA PISTA pasan a `otro`. La fila del árbitro en f23553 se
   queda con su voto de color por observación, que es **B**.

Es el **temblor de la detección** del bloque 1 (un salto de ~1 m que se deshace en el frame
siguiente), ahora con coste: la pista no se equivoca de persona, pero deja una fila suelta.

**Cuánto pasa**: en todo el partido hay 116 huecos de UN frame con la misma identidad del tracker a
los dos lados y su detección presente. En 56 de ellos esa fila sigue en un equipo. f23553 ni
siquiera entra en esa cuenta: en el frame siguiente la pista sigue en la detección de OTRA
identidad del tracker (la 618), a 0,1 m de la anterior.

**Arreglo posible (NO implementado, para decidirlo)**: rellenar los huecos cortos de la pista (≤ 2
frames) con la detección de la identidad que está a los dos lados. O, más general, no arrastrar la
velocidad de UN solo paso, sino estimarla sobre varios. Sería un intento nuevo con su criterio
fijado antes. Pesa poco: 56 filas, frente a las 5.238 que mueve la pista.
