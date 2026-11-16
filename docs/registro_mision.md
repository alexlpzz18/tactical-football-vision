# Registro de la misión: un sistema que analice bien CUALQUIER partido (F7 y F11)

Memoria entre sesiones. Cada entrada: hipótesis, criterio previo, resultado, decisión, siguiente paso.
Encargo de Alex del 13-nov-2026 (definición de terminado, método y restricciones: en el propio encargo).

## Partidos de desarrollo y de validación (declarado ANTES de ajustar nada)

| partido | papel | por qué | estado de los datos |
|---|---|---|---|
| benjamín F7 (Gredos), parte 1 | **desarrollo** | todo el sistema está ajustado sobre él | cachés completos, GT de 30 s |
| alevín A F11 (Casarrubuelos), tramo de 60 s | **desarrollo** | lleva meses de banco («Villaviciosa») | cachés, GT de 30 s |
| alevín B F11 (Dux), parte 1 | **desarrollo** | es el caso que falla y sobre el que se va a iterar | cachés completos, mini-GT de equipo a ojo (79 jugadores) |
| **cadete A F11**, parte 1 | **validación** | mismo campo y cámara, otro partido, otras equipaciones, nunca mirado | vídeo cortado; **sin detecciones (GPU)** |
| **alevín B, parte 2** | **validación** (débil: mismo partido, otra luz y campos cambiados) | no se ha procesado ni mirado | vídeo cortado; **sin detecciones (GPU)** |
| **F11 de Bazán** (1920×798) | **validación** | otro campo y otra cámara | **el vídeo no está en este Mac** |

No se ajusta nada mirando los de validación. Un cambio solo se adopta si mejora o no empeora en todos.

## Entrada 1 (13-nov): línea base y conciliación

Instrumento: `scripts/linea_base_mision.py`. Simula a 10 Hz lo que dibuja `replay_tactico` (sus dos
filtros y su interpolación), SIN histéresis. **Control del instrumento**: en el tramo 14:00-15:30 del
benjamín da 48,0 cambios de color/min y 27,3 eventos/min, las cifras ya conocidas (`pizarra_fichas.md`).
«Zona visible» = interior del campo a ≥ 2 m de las líneas (proxy; en el benjamín sobrecuenta la franja
que la cámara no ve). Salidas en `outputs/linea_base_mision/`.

| criterio (objetivo) | benjamín 5-20 min | alevín A 60 s | **alevín B, parte 1 (30 min)** |
|---|---|---|---|
| 1. cambios A↔B por min (≤ 5) | 34,1 | 131,2 | **122,0** |
| 2. saltos > 3 m en 0,2 s, por min (0) | 0,0 | 50,1 | **51,7** |
| 2. p99 de velocidad de ficha (≤ 9 m/s) | 5,3 | 13,5 | **15,0** |
| 3. apariciones/desapariciones por min (≤ 5) | 22,7 | 119,2 | **70,3** |
| 3. simultáneas A · B: p50 (tope 7 u 11) | 6 · 7 | 13 · 10 | **13 · 10** |
| 3. % del tiempo por encima del tope, A · B | 4,1 · 14,0 | 76,1 · 19,5 | **63,7 · 40,6** |
| identidades por minuto | 13,9 | 84,2 | **44,8** |
| vida mediana de una identidad | 37,9 s | 12,2 s | **15,5 s** |

Alex tiene razón: el F11 es de otro orden de magnitud que el benjamín en los tres criterios.
Criterios 4 y 5 (exactitud): en el alevín B solo hay el mini-GT de equipo (79,7 %; objetivo ≤ 2 % de
error ⇒ muy lejos). No hay verdad de posición ni de identidad en el alevín B ni en validación: hace
falta (ver «Lo que necesito de Alex»).

### De dónde sale cada cosa (conciliación en los datos)

**Cambios de color (122/min)**
- En la pizarra y en los datos cuadran (122,0 contra 122,4): no es un fallo de dibujo.
- 91,3/min son entre dos filas REALES seguidas; 31,1/min llevan una fila interpolada.
- ⚠️ **Los introduje yo el 12-nov** al encender el voto por ventana de 1,5 s en el F11. Con el voto por
  identidad (producción anterior) hay **0 cambios/min**, pero con los equipos mal (4 contra 15 por
  fotograma, y B por encima de 11 el 100 % del tiempo). Cambié un error largo por muchos cortos: el
  acierto del mini-GT sube (66 → 80 %) y la pizarra parpadea. Las dos cosas están mal; no revierto
  hasta medir la H1, pero NO es adoptable así.
- El aviso estaba escrito en el config del benjamín («NO VIAJA» a Villaviciosa) y lo adopté mirando
  solo el equipo equivocado. Es el principio del criterio de adopción que solo mira lo que mejora.

**Saltos (52/min) y velocidades imposibles**
- No dependen de la etiqueta (salen iguales con el CSV de producción) ni de huecos: el 0 % ocurre
  dentro de un hueco; 139 de 144 pasos/min a > 15 m/s son entre dos filas reales seguidas.
- **No son cambios de persona.** En las detecciones crudas del seguimiento, el 6,8 % de los pasos de
  una identidad supera los 15 m/s (667/min), y de esos el **97 % mueve el pie ≤ 20 px** (mediana 5,9 px;
  4,4 px en vertical; la altura de la caja cambia 4,2 px sobre 25). Es el temblor del borde inferior de
  la caja multiplicado por la proyección rasante: 0,08 m/px cerca, 0,16 en medio, **0,38 m/px lejos**
  (y más en vertical). Pasos rápidos: 2,6 % cerca, 6,2 % en medio, 15,6 % lejos.
- El suavizado de producción (media de 0,5 s, igual en todo el campo) los baja de 667 a 144/min, y no
  basta. En el benjamín hay 0 porque allí el suavizado se alarga con la resolución local
  (`escalado_resolucion`, ~2 s); en el F11 está apagado y además se calcula con una homografía, que el
  alevín B no tiene (usa el modelo de lente).

**Apariciones y fichas de más (70 eventos/min; A por encima de 11 el 64 % del tiempo)**
- 44,8 identidades nuevas por minuto contra 13,9 del benjamín; vida mediana 15,5 s.
- Sin conciliar todavía: cuánto es fragmentación (muere una y nace otra cerca), cuánto duplicados (dos
  identidades sobre una persona) y cuánto gente que no juega (árbitro, calentamiento). Es el paso 0 de H3.

**Balón**: no hay línea base útil. El detector lo ve en el 9,4 % del tramo (2-4 px en casi todo el campo).

## Plan de hipótesis (criterios ANTES de medir; máximo dos intentos por ruta)

Orden por lo que más pesa en lo que ve Alex y por coste (todo en CPU sobre cachés salvo H4 y H5).

### H1. Posición: suavizado con el ruido LOCAL de la proyección, usando pasado y futuro
- **Qué**: sustituir en el F11 la media fija de 0,5 s por un suavizador de dos sentidos (RTS, velocidad
  constante) cuyo ruido de medida en cada punto es el temblor en píxeles (σ medido del detector)
  llevado a metros con el jacobiano de la cámara (homografía o modelo de lente). Lejos suaviza mucho,
  cerca casi nada. Detrás de un interruptor; el benjamín no cambia.
- **Argumento nuevo frente a las rutas cerradas** («suavizado por tiempo», «Kalman del balón»): allí la
  ventana era igual en todo el campo y el problema era otro; aquí está medido que el 97 % de los saltos
  es temblor de ≤ 20 px amplificado, con un factor 5× entre cerca y lejos.
- **Criterio**: alevín B, parte 1: 0 saltos > 3 m en 0,2 s y p99 ≤ 9 m/s.
- **Lo que no puede romper** (¿qué podría estar inventando? un jugador que no gira): (a) en la zona
  CERCANA, donde el píxel es fiable, la fila suavizada queda a ≤ 0,5 m (p95) de su propia detección;
  (b) contra el GT del alevín A (30 s): error de posición casado 1-a-1 no peor que hoy, por franja;
  (c) retraso en cambios de dirección: en un sintético con un giro de 90° a 6 m/s, error máximo ≤ 1 m;
  (d) centroide y anchura del alevín A no peores.
- **Control**: con el ruido de medida constante tiene que reproducir (± 5 %) las cifras de hoy.

### H2. Etiqueta de equipo estable SIN perder acierto: decidir con pasado y futuro
- **Paso 0 (premisa)**: de los 122 cambios/min, ¿cuántos son rachas cortas (< 2 s) flanqueadas por la
  misma etiqueta (ruido de la evidencia) y cuántos cambios sostenidos (la identidad cambió de persona)?
  En el benjamín la mitad era lo segundo y por eso «etiqueta por trozos» no pagó. Si en el F11 ≥ 70 %
  son rachas cortas, se construye; si no, se cierra sin construir.
- **Qué**: en vez de votar cada ventana por separado, la secuencia de evidencias de una identidad se
  decodifica entera (Viterbi de 2 estados con coste de cambio): cambia de equipo solo si la evidencia
  lo sostiene. No es histéresis de dibujo: cambia el DATO.
- **Criterio**: alevín B ≤ 5 cambios A↔B/min **y** mini-GT ≥ 79,7 − 1 punto; benjamín: equipo
  equivocado ≤ 1,2 + 0,3 puntos y cambios no mayores que hoy; alevín A: equipo equivocado ≤ 17,5 %.
- **Obligatorio informar**: jugadores-segundo mal etiquetados y duración de los episodios de error,
  antes y después (no cambiar errores cortos por largos). Para eso hace falta la hoja de H2 (abajo).

### H3. Presencia: fragmentos y duplicados
- **Paso 0**: conciliar los 70 eventos/min: (i) muertes con un nacimiento a ≤ 2 s y ≤ 5 m (fragmento
  re-enlazable); (ii) parejas de identidades a < 1,5 m durante > 1 s (duplicado); (iii) identidades que
  nunca son de un equipo (árbitro, gente de fuera). Decide qué se construye.
- **Qué (si (i) domina)**: re-enlace offline DENTRO de cada equipo, con el movimiento extrapolado en los
  dos sentidos sobre posiciones ya suavizadas por H1 (la ruta (a) de `mapa_rutas_cruces.md`, nunca
  probada; el veto de equipo necesita H2). Si (ii) domina: fusión de duplicados simultáneos del mismo
  equipo.
- **Criterio**: eventos ≤ 5/min y simultáneas ≤ 11 por equipo en ≥ 99 % del tiempo, con IDF1 dentro de
  cada equipo (GT del alevín A y del benjamín) ≥ el de hoy. Lo que se cumple por construcción no cuenta.

### H4. Recall lejano (GPU)
- Franjas lejanas ampliadas en la detección (hoy la red amplía ×1,07). Criterio: recall ≥ 80 % lejos sin
  subir los falsos positivos por fotograma más de un 10 %. Solo después de H1-H3: hoy no es lo que más
  se ve.

### H5. Balón: ruta nueva por MOVIMIENTO (cámara fija)
- El detector no puede ver 2-4 px. Con cámara fija, un balón en juego es una mancha pequeña que se
  mueve rápido: diferencia entre fotogramas + tamaño + trayectoria físicamente plausible (parábolas y
  rectas), con el detector de apariencia como confirmación donde exista.
- **Paso 0 (premisa, CPU)**: en los fotogramas donde el detector SÍ ve el balón (9,4 %), ¿aparece ahí
  una mancha en la diferencia de fotogramas, y cuántas manchas candidatas más hay por fotograma? Si el
  balón conocido aparece en ≥ 80 % y hay ≤ 20 candidatas, se construye el seguimiento por trayectoria.
- **Criterio final**: necesita verdad: un tramo de 60 s con el balón marcado en TODOS sus fotogramas
  (lección cerrada del 28-oct: frames sueltos no sirven).

## Lo que necesito de Alex (agrupado)

1. **GPU para validación**: procesar la detección de `cadete_villa_p1` (y, si quiere, la parte 2 del
   alevín B) con el orquestador de Colab que ya funciona. Coste como la parte 1 del alevín B.
2. **El vídeo de Bazán** en `data/raw/` (o en Drive) si quiere validar en otro campo.
3. **Marcas humanas** (una sola sesión, cuando H1-H2 estén medidas): hoja de equipo de ~150 filas
   repartida por el partido con la caja de la fila, en el alevín B y en el cadete (≈ 25 min cada una), y
   60 s de balón fotograma a fotograma para H5 (≈ 40 min).

## Entrada 2 (13-nov): H1, intento 1 — RTS con ruido local medido (`suavizado.metodo: rts`)

Código: `src/tracking/suavizado_rts.py` (interruptor en `postprocesar`), banco `scripts/banco_mision.py`.
El ruido se mide de los propios datos (segunda diferencia por celda y por eje; no necesita cámara) y el
filtro pierde peso en las medidas atípicas (el temblor no es gaussiano: σ robusta 0,07-0,12 m y p99 de
velocidad cruda de 47 m/s).

| | alevín B: saltos/min · p99 | alevín A: saltos · p99 · error pos. (mediana) · centroide | benjamín: saltos · p99 · error pos. · centroide · anchura |
|---|---|---|---|
| hoy (media 0,5 s) | 52,0 · 15,1 | 27,1 · 11,6 · 0,705 m · 4,446 m | 0 · 6,0 · 0,491 · 0,469 · 0,381 |
| rts a = 4 | 11,5 · 11,3 | 9,0 · 8,7 · 0,683 · 4,475 | 2 · 8,4 · 0,437 · 0,423 · 0,317 |
| **rts a = 3** | **7,1 · 10,3** | **2,0 · 8,0 · 0,697 · 4,479** | 1 · 7,9 · 0,436 · 0,430 · 0,291 |
| rts a = 2 | 2,9 · 8,9 | 2,0 · 7,3 · 0,697 · 4,481 | 0 · 7,1 · 0,429 · 0,438 · 0,296 |

- **Criterio (0 saltos, p99 ≤ 9): NO CUMPLE estrictamente.** a = 3 quita el 86 % de los saltos del
  alevín B y el 93 % del alevín A sin mover el error de posición contra el GT; a = 2 casi llega (2,9 y
  8,9) pero falla la guarda del giro (1,24 m con σ = 1 m; a = 3 da 1,01 m).
- Guarda (a) (cerca, fila a ≤ 0,5 m p95 de su detección): 0,77 m con a = 3. **No cumple el número que
  fijé**, pero hoy es 0,88 m: el criterio estaba puesto sin conocer la línea base. La mediana es 0,08 m.
- Benjamín (no se le aplica: su suavizado está calibrado; se midió por control): mejora posición,
  centroide y anchura, y sube 1 observación de equipo equivocado. No se toca.
- **Lo que queda son cambios de persona, no temblor.** Ejemplos de los saltos restantes: la detección
  de la identidad salta 6-15 m de un fotograma al siguiente (a veces tras un hueco de 0,4-1,2 s) y se
  queda allí. El suavizado reparte ese teletransporte en varios pasos. Ningún suavizado lo arregla: hay
  que CORTAR la identidad ahí.

### H1b / H3a (criterio ANTES de medir): cortar los teletransportes de una identidad

- **Qué**: antes de clasificar equipos, partir una identidad donde su posición hace un cambio de nivel
  físicamente imposible: la mediana de las 3 observaciones de después está a más de
  `v_max · Δt + margen de ruido local` de la mediana de las 3 de antes (v_max = 10 m/s). La mediana de 3
  ignora un pico suelto; solo corta si el salto se QUEDA. Interruptor, apagado por defecto.
- **Argumento nuevo frente a «corte de velocidad» y «cortar en cruces» (cerradas)**: aquellas cortaban
  por velocidad instantánea con umbral fijo (ruido del fondo) o en cada cruce (fragmentaban). Esta solo
  corta cambios de nivel imposibles con el ruido medido en esa zona.
- **Criterio**: alevín B, con rts a = 3: saltos ≤ 1/min y p99 ≤ 9 m/s. Sin romper: alevín A y benjamín
  (GT) con equipo equivocado, centroide, anchura y error de posición no peores (± ruido de 1 observación
  o 2 cm); y los cortes en el benjamín (donde hoy hay 0 saltos) tienen que ser ≤ 1 por minuto: si corta
  más, está cortando otra cosa.
- **Se informa**: cortes por minuto por pata y eventos/min (un corte es una ficha que muere y otra que
  nace; lo recoge después el re-enlace de H3).

## Entrada 3 (13-nov): H5, paso 0 del balón por movimiento — NO CUMPLE la premisa

`scripts/balon_movimiento_paso0.py`, 200 fotogramas de los minutos 0-15 del alevín B donde el detector
ve un balón que no es una marca fija (407 disponibles). Diferencia de tres fotogramas (f−2, f, f+2).

| umbral de diferencia | balón conocido con mancha | manchas candidatas por fotograma fuera de personas (p50 · p90) |
|---|---|---|
| 12 | 48,7 % | 305 · 453 |
| 20 | 41,7 % | 205 · 337 |
| 30 | 33,7 % | 120 · 211 |

Criterio escrito antes: ≥ 80 % y ≤ 20 candidatas. **No cumple ninguno de los dos.**
- **Hallazgo que cambia el problema**: de los 158 balones conocidos con velocidad medible, **141 están
  QUIETOS** (≤ 1 px por fotograma) y solo 17 se mueven. El detector ve el balón casi solo cuando está
  parado (saques, faltas); el 9 % «con balón» de este partido es sobre todo balón parado. En juego, el
  balón (2-4 px y borroso) no lo ve casi nunca.
- Cuando se mueve, la mancha aparece el 71-77 % de las veces (17 casos: no es una medida).
- Hay cientos de manchas por fotograma: compresión del vídeo, público, árboles, piernas.
- **No se construye el seguimiento por movimiento con esta forma.** Un segundo intento tendría que
  restringirse al interior del campo y exigir trayectoria, pero sin verdad del balón EN JUEGO no se
  puede ni medir: el «balón conocido» está sesgado al balón parado. ⇒ **Bloqueado por etiquetado**:
  hace falta un tramo de 60 s con el balón marcado en todos los fotogramas en los que se vea.

## Entrada 4 (13-nov): H1b, intento 1 del corte de teletransportes — NO CUMPLE (corta de más)

Regla del intento 1: cambio de nivel entre la mediana de 3 observaciones antes y después mayor que
`10 m/s · Δt + 1 m + 3·σ local`. Con rts a = 3:

| | saltos/min | p99 | eventos/min | identidades/min | GT |
|---|---|---|---|---|---|
| alevín B | 7,1 → **1,1** | 10,3 → **8,1** | 68,8 → 112,5 | 43,7 → 64,8 | — |
| alevín A | 2,0 → 0,0 | 8,0 → 7,3 | 94,2 → 107,2 | 70,1 → 75,2 | sin cambio (centroide 4,48 → 4,46 m) |
| benjamín (solo corte) | 0 → 0 | 6,0 → 5,8 | 21 → 47 | 25 → 39 | centroide 0,469 → 0,407; equipo +1 obs |

- Saltos y p99 del alevín B cumplen (1,1/min; 8,1 m/s), **pero el control del benjamín falla**: 14 cortes
  en 60 s donde no había ningún salto (criterio: ≤ 1/min). Y en el alevín B corta ~21 veces por minuto
  para quitar 6 saltos por minuto. Está cortando más que teletransportes: la σ robusta (mediana) no ve
  las colas del temblor, que es justo lo que supera el margen.
- **Intento 2 (criterio igual, escrito antes)**: cortar SOLO donde está el síntoma. Se suaviza con RTS y
  se corta donde la trayectoria SUAVIZADA sigue yendo a más de 12 m/s (lo que el suavizado no ha podido
  explicar como ruido). En el benjamín debería dar ≤ 1 corte/min por construcción del síntoma; si no, la
  ruta se cierra.

## Entrada 5 (13-nov): H2, paso 0 y reformulación (criterios ANTES de medir la secuencia)

**Paso 0** (cambios A↔B entre observaciones reales seguidas; «racha corta» = < 2 s entre dos rachas de
la otra etiqueta):

| | cambios/min | en rachas cortas | duración mediana de la racha | fracción minoritaria de la identidad (p50) |
|---|---|---|---|---|
| alevín B | 130 | **57 %** | 1,08 s | 0,26 |
| alevín A | 134 | 67 % | 0,60 s | 0,24 |
| benjamín | 36 | 45 % | 0,80 s | 0,25 |

- El criterio era ≥ 70 % para construir. **No llega (57 %)**: decidir la secuencia entera, SOLA, no puede
  cumplir ≤ 5 cambios/min: quedarían ~50/min de cambios sostenidos (la identidad lleva a más de una
  persona: su etiqueta minoritaria ocupa un 26 % del tiempo).
- ⚠️ Lo construí igualmente (`por_observacion.secuencia`, un Viterbi de 2 estados, 40 líneas, apagado
  por defecto) antes de cerrar este paso, porque en la reformulación de abajo hace otro papel. Lo digo
  porque el plan decía «si no, se cierra sin construir».

**H2' (reformulada)**: la etiqueta decidida por secuencia tiene dos usos:
1. quita las rachas cortas (el 57-67 % del parpadeo del F11);
2. cada cambio SOSTENIDO que queda es la señal de que la identidad pasó a otra persona ⇒ ahí se parte
   la identidad (cambios de color = 0 por construcción, que NO cuenta como evidencia) y el re-enlace
   dentro de cada equipo (H3) decide con quién continúa. Es «partir y luego unir» con una señal que
   no es un recorte suelto: la pista que dejó abierta `pizarra_fichas.md`.

**Criterio del uso 1 (se mide ya; barrido `coste_cambio` 2 · 4 · 8)**:
- alevín B: cambios A↔B/min bajan ≥ 50 % y mini-GT ≥ 78,7 %;
- benjamín: equipo equivocado ≤ 1,55 % (hoy 1,245) y cambios no mayores que hoy;
- alevín A: equipo equivocado ≤ 17,9 % (hoy 17,4) y centroide no peor (± 2 cm);
- un solo `coste_cambio` para las tres, en el centro de una meseta; si no la hay, no se adopta;
- contra el GT (benjamín y alevín A): jugadores-segundo mal etiquetados y duración de los episodios de
  error antes y después (no cambiar errores cortos por largos): los episodios de > 3 s no pueden subir.

## Entrada 6 (13-nov): H1b, intento 2 del corte — CUMPLE saltos y velocidad en el F11

Regla: cortar donde la trayectoria SUAVIZADA (RTS robusto) sigue a más de 10 m/s.

| con rts a = 3 + corte | saltos/min | p99 | eventos/min | identidades/min | exactitud |
|---|---|---|---|---|---|
| alevín B | 52 → **0,9** | 15,1 → **7,5** | 70 → 96 | 45 → 57 | mini-GT 79,7 → 77,2 % (2 de 79) |
| alevín A | 27 → **1,0** | 11,6 → **7,0** | 96 → 105 | 70 → 74 | equipo 17,4 → 17,8 %; centroide 4,45 → 4,48; error pos. 0,705 → 0,688 m |
| benjamín (solo corte, control) | 0 → 0 | 6,0 → 5,8 | 21 → 29 | 25 → 29 | equipo +1 obs; centroide 0,469 → 0,460 |

- **Criterio del F11 (saltos ≤ 1/min, p99 ≤ 9): CUMPLE** en las dos patas F11.
- **Control del benjamín (≤ 1 corte/min): NO CUMPLE (4/min)**. Pero la premisa del control era falsa:
  pensé que en el benjamín no había teletransportes porque la pizarra no salta. Sí los hay: en los 20
  min, los cortes tienen un paso crudo mediano de 7,6 m y un cambio de nivel mediano de 8,2 m (solo el
  4 % es < 3 m); la mitad, en el fondo o fuera del campo. Su suavizado de ~2 s los escondía
  (ya estaba en CLAUDE.md: «promedia a través de saltos»). En el benjamín NO se enciende; queda como dato.
- **Coste, dicho claro**: cada corte es una ficha que muere y otra que nace (eventos 70 → 96/min en el
  alevín B). El salto ya no se ve, pero la ficha parpadea. Lo tiene que recoger el re-enlace (H3).

## Entrada 7 (13-nov): H3, paso 0 y criterios del re-enlace (ANTES de construir)

Muertes de fichas dentro del campo en el alevín B (rts a = 3 + corte), 47,8/min:

| qué hay alrededor cuando muere | % |
|---|---|
| nace otra ficha ≤ 2 s después y cerca (≤ 2 m + 8 m/s · hueco) | **47 %** |
| otra ficha recién nacida a < 1,5 m (relevo) | 8 % |
| otra ficha vieja a < 1,5 m (dos personas en una caja) | 13 % |
| nadie cerca (detección perdida, o hueco más largo) | 32 % |

Duplicados (dos fichas a < 1,5 m más de 3 s seguidos): 6/min. No son la causa de que A pase de 11.

**H3 (intento 1): re-enlace offline DENTRO de cada equipo, con el movimiento en los dos sentidos.**
Etapa final sobre las fichas ya suavizadas y etiquetadas: una ficha que muere se une a una que nace
después si (a) son del mismo equipo, (b) el hueco es ≤ 3 s y (c) el final de una, extrapolado hacia
delante, y el principio de la otra, extrapolado hacia atrás, se encuentran a ≤ 1,5 m + 4 m/s · hueco.
Asignación global (húngaro), no golosa. Antes, una ficha cuya etiqueta por secuencia cambia de equipo
se parte ahí (el cambio sostenido es otra persona). Interruptores, apagados por defecto.

**Criterios**:
- alevín B: eventos/min bajan ≥ 40 % respecto a rts + corte (96 → ≤ 58) y los saltos siguen ≤ 1/min
  (un re-enlace malo es un salto: es su control incorporado);
- GT (alevín A y benjamín): IDF1 dentro de cada equipo ≥ el de hoy; equipo equivocado, centroide y
  error de posición no peores (± 1 observación, ± 2 cm);
- % del tiempo por encima del tope de fichas por equipo: no sube;
- cambios de color = 0 por construcción: NO cuenta.

## Entrada 8 (13-nov): H2 uso 1, intento 1 de la etiqueta por secuencia — NO CUMPLE en el alevín B

Sobre rts a = 3 + corte en el F11; benjamín con su tracking.

| | cambios A↔B/min (coste 0 · 2 · 4 · 8) | exactitud |
|---|---|---|
| alevín A | 112 · 22 · 14 · **8** | equipo equivocado 17,8 · 17,1 · 17,2 · **16,2 %**; centroide 4,48 · 4,28 · 4,26 · 4,28 m; episodios > 3 s: 6 → 5 |
| benjamín | 45 · 38 · 32 · 29 | equipo 1,245 · 1,52 · **1,245** · 1,66 %; episodio más largo 0,5 · 1,0 · 1,0 · 2,5 s |
| alevín B | 116 · 37 · 25 · 15 | mini-GT 77,2 · **69,6 · 70,9 · 72,2 %** (criterio ≥ 78,7: NO) |

- En el alevín A mejora TODO a la vez (menos parpadeo y más acierto). En el alevín B baja el acierto
  7 puntos: los verdes etiquetados blanco pasan de 8 a 13-14 de 30. Causa: la evidencia no es simétrica
  (a favor del blanco es más grande en valor), y la secuencia se traga rachas verdes.
- **Intento 2 (mismo criterio)**: calibrar la evidencia por lado antes de decidir (cada lado dividido
  por su mediana y acotado a ± 2): una ventana típica vale lo mismo para los dos equipos.

## Entrada 9 (13-nov): H2 uso 1, intento 2 (evidencia calibrada) — NO CUMPLE en el alevín B. Cerrada como regla común

| | cambios A↔B/min (coste 0 · 3 · 6 · 12) | exactitud |
|---|---|---|
| alevín A | 112 · 28 · 19 · 11 | equipo 17,8 · 16,7 · 16,9 · 16,7 %; centroide 4,48 · 4,29 · 4,23 · 4,23 m; jugador-segundos mal 134 → 127 |
| benjamín | 45 · 36 · 32 · 29 | equipo 1,245 · 1,38 · 1,245 · 1,66 %; centroide 0,469 · 0,480 · 0,477 · 0,533 |
| alevín B | 116 · 65 · 49 · 35 | mini-GT 77,2 · 74,7 · 72,2 · 70,9 % (criterio ≥ 78,7: **NO**) |

- Dos intentos y el alevín B no pasa: **la etiqueta por secuencia no se adopta como regla común**. El
  interruptor queda (apagado). En el alevín A mejora parpadeo Y acierto a la vez, así que es candidata
  ahí, pero «un solo valor para todas» era el criterio.
- **Lo que enseña**: en el alevín B, al acumular evidencia a lo largo de la identidad, los verdes de la
  franja MEDIA se van al blanco (12-14 de 30, contra 8). La evidencia de color está SESGADA con la
  distancia a la cámara (con neblina, el verde oscuro lejos se aclara), y un prototipo único por
  equipo no lo recoge. Acumular una evidencia sesgada la empeora: es «el voto no era robusto, era
  sesgado» otra vez.
- ⚠️ **El instrumento se queda corto**: 79 jugadores. Una diferencia de 5 puntos son 4 recortes. Para
  seguir afinando la etiqueta en el F11 hace falta una verdad mayor ⇒ hoja de 300 recortes para Alex
  (`scripts/hoja_equipos_clic.py`, `outputs/hoja_equipos_alevinb/index.html`).

**H3, primera medida (re-enlace solo, sin partir, sobre rts + corte; offline sobre el CSV)**:
alevín B eventos 96 → 71/min (−26 %), saltos 0,9 → 1,4/min, A por encima de 11 el 66 % (antes 62 %);
alevín A eventos 105 → 80, IDF1 A 0,473 → 0,492 y B 0,396 → 0,389; benjamín 0 uniones (sin cambio).
No llega al −40 %. El recuento por encima del tope NO es de duplicados: es de etiqueta (verdes y
árbitro contados en el blanco). ⇒ **la palanca que manda ahora es el ACIERTO de equipo en el F11**.

### H6 (siguiente; criterio ANTES de medir): que el seguimiento enseñe al color
- **Idea**: una persona no cambia de equipo. En los tramos aislados (los mismos de la selección de
  feature) la identidad es una sola persona, y su equipo se decide con TODA la evidencia del tramo
  (sobre todo la de cuando está cerca, que es fiable). Esas etiquetas se propagan a sus recortes de
  media y larga distancia y con ellas se ajusta un clasificador que conoce la profundidad. Sin marcas
  humanas, y vale para cualquier campo.
- **Premisa (paso 0)**: con etiquetas a ojo, las features separaban 87-90 % por recorte
  (`plan_equipos_embeddings.md`). Se comprueba primero que las etiquetas propagadas aciertan ≥ 90 %
  contra la hoja de Alex en los recortes que cubren.
- **Criterio**: contra la hoja de Alex (300 recortes): acierto de equipo ≥ 90 % (hoy ~77-80 % en 79) y
  franja media ≥ 85 %; benjamín ≤ 1,55 %; alevín A ≤ 17,4 % y centroide no peor.
